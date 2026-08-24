# SPEQULA CANONICAL DATA MODEL

**File 04 of 12. Status: draft 1.**
Implements: architecture document sections 7 (canonical model) and 26 (multi-tenancy), narrowed to single-entity pilots.
Target: PostgreSQL 16 or later. One database, one schema per tenant for analytical data, shared app schema with row-level security.

This file is the authority on structure. File 05 is the authority on meaning. No metric formula appears in this file and no table name appears in file 03.

---

## 1. Design rules

### 1.1 Bitemporality, and why it is here on day one

Every fact answers two different time questions, and conflating them is the failure most FP&A tools never recover from.

- **Event time** is when the thing happened according to the books. `event_date` on every fact.
- **Knowledge time** is when SPEQULA learned about it. `valid_from` and `valid_to` on every fact row.

The scenario this exists for: you send the June pack on 8 July showing revenue of 42.1 Cr. On 14 July the accountant backdates journal entries into June. A naive pipeline now shows 43.4 Cr for June and the pack you sent looks wrong, with no way to tell whether it was an error or a restatement.

With bitemporality both answers remain queryable. "As reported on 8 July" is a query with `valid_from <= '2026-07-08' < valid_to`. "As it stands now" is `is_current = true`. The delta between them is a restatement with a cause, not a mystery.

**Cost of building it now:** three columns, one snapshot table and a discipline in the loader. **Cost of retrofitting it:** every query, every cached aggregate and every saved report changes at once. Do not defer this.

### 1.2 Standard columns

Every fact table carries these, without exception:

| Column | Type | Purpose |
|---|---|---|
| `fact_id` | `bigserial` | Surrogate primary key |
| `tenant_id` | `uuid` | Redundant inside a tenant schema, retained so a cross-tenant query is a visible error rather than a silent one |
| `entity_id` | `int` | Legal entity. Always populated even in single-entity pilots, so multi-entity arrives without a migration |
| `event_date` | `date` | When it happened per the books |
| `entry_date` | `date` | When it was recorded in the source system, where the source provides it. This is how backdated entries are detected |
| `valid_from` | `timestamptz` | Knowledge time start |
| `valid_to` | `timestamptz` | Knowledge time end. `'infinity'` for current rows |
| `is_current` | `boolean` | Denormalised for index efficiency. Derived, never hand-set |
| `load_run_id` | `bigint` | Which ingestion run produced this row |
| `source_system` | `text` | `tally`, `sap_b1`, `zoho`, `excel_upload`, `bank_file` |
| `source_record_id` | `text` | The natural key in the source system |
| `row_hash` | `bytea` | Content hash of the business columns. Drives deduplication and change detection |
| `mapping_version_id` | `int` | Which approved mapping version produced the canonical classification on this row |

Dimension tables carry `tenant_id`, `valid_from`, `valid_to`, `is_current`, `load_run_id` and `source_record_id`. Slowly changing dimensions are type 2 through the same knowledge-time columns, so a customer that moved from one segment to another keeps both histories.

### 1.3 Keys

Surrogate integer keys on every dimension. Natural keys retained as attributes and uniquely indexed within tenant and entity. Facts reference dimensions by surrogate key only. This matters because source systems reuse and renumber their own codes more often than anyone expects.

### 1.4 Tokenisation

`dim_customer`, `dim_vendor` and any employee reference store a **token** in the name field, never a real name. The mapping from token to real name lives in `token_map`, which sits in the app schema and on which the model-reachable role has no grant. See file 02 section 8.

### 1.5 Grain discipline

Every fact table declares exactly one grain and never deviates. A table whose grain is ambiguous produces double counting that no downstream check catches. The grain is written into the table comment in the DDL, not just into this document.

---

## 2. Table inventory

### Dimensions

| Table | Grain | P0 | Notes |
|---|---|---|---|
| `dim_date` | One calendar day | Yes | Owns the Indian fiscal calendar. Not generated on the fly |
| `dim_entity` | One legal entity or business unit | Yes | Single row in pilot one. Present so multi-entity needs no migration |
| `dim_account` | One GL account, one version | Yes | Carries both the source name and the canonical class |
| `dim_customer` | One customer, one version | Yes | Tokenised |
| `dim_vendor` | One vendor, one version | Yes | Tokenised |
| `dim_product` | One SKU or item, one version | Yes | Includes raw materials and finished goods. Apparel profile adds price_band/occasion_type, section 3.10 |
| `dim_channel` | One sales channel | Yes | Consumer pilots. Single default row for manufacturing |
| `dim_cost_centre` | One cost centre | Yes | Also carries department and plant |
| `dim_location` | One plant, warehouse or store | Yes | Apparel profile adds store_format/city/state/site_type/area_sqft/opening_date/closure_date/status, section 3.10 |
| `dim_business_unit` | One business line | Yes | Optional in use, present in schema. D-063. A company running several revenue models needs it; most consumer companies segment by product and channel instead |

### Facts

| Table | Grain | P0 | Profile |
|---|---|---|---|
| `fact_gl_entry` | One journal line | Yes | Both. The spine of the whole model |
| `fact_invoice_line` | One sales invoice line | Yes | Both |
| `fact_purchase_line` | One purchase bill line | Yes | Both |
| `fact_payment` | One receipt or payment | Yes | Both |
| `fact_bank_txn` | One bank statement line | Yes | Both |
| `fact_ar_open` | One open receivable item at one month end | Yes | Both |
| `fact_ap_open` | One open payable item at one month end | Yes | Both |
| `fact_inventory_position` | One item, one location, one month end | Yes | Both |
| `fact_production_output` | One item, one line, one production period | Yes | Manufacturing |
| `fact_channel_order_line` | One order line | Yes | Consumer |
| `fact_headcount_month` | One department, one month | P1 | Both |

### Mapping, registry and operations

| Table | Purpose | P0 |
|---|---|---|
| `map_account` | Source account to canonical class, versioned and approved | Yes |
| `map_item` | Source item to canonical product category | Yes |
| `map_channel` | Source channel string to canonical channel | Yes |
| `mapping_version` | Version header: status, approver, effective date | Yes |
| `metric_definition` | The metric contract, versioned | Yes |
| `period_lock` | Which periods are closed, by whom, on what snapshot | Yes |
| `reconciliation_run` | Result of each reconciliation check per period | Yes |
| `exception` | The exception queue | Yes |
| `load_run` | One ingestion execution | Yes |
| `source_file` | One received file, with its hash and its landing path | Yes |
| `query_log` | Every query executed, with IR, SQL, rows, duration, model version | Yes |
| `token_map` | Token to real name. App schema only | Yes |
| `audit_log` | Access, exports, mapping changes, metric changes, approvals | Yes |

Thirty-five tables. Eleven facts, ten dimensions, fourteen operational. Nothing here is present for elegance.

---

## 3. Core DDL

### 3.1 dim_date

```sql
CREATE TABLE dim_date (
    date_key            date        PRIMARY KEY,
    day_of_month        smallint    NOT NULL,
    month_num           smallint    NOT NULL,
    month_name          text        NOT NULL,
    calendar_year       smallint    NOT NULL,
    calendar_quarter    smallint    NOT NULL,
    fiscal_year         smallint    NOT NULL,   -- FY2027 = Apr 2026 to Mar 2027
    fiscal_year_label   text        NOT NULL,   -- 'FY27'
    fiscal_quarter      smallint    NOT NULL,   -- Q1 = Apr, May, Jun
    fiscal_month_num    smallint    NOT NULL,   -- April = 1
    period_key          text        NOT NULL,   -- '2026-04'
    is_month_end        boolean     NOT NULL,
    is_quarter_end      boolean     NOT NULL,
    is_fiscal_year_end  boolean     NOT NULL,
    days_in_month       smallint    NOT NULL
);
COMMENT ON TABLE dim_date IS
  'Grain: one calendar day. Owns the fiscal calendar. FY start month per DECISION-REQUIRED[D-038], default April.';
```

The fiscal calendar lives here and nowhere else. Every "last quarter" resolution, every year-on-year comparison and every period lock reads from this table. A fiscal year computed inline in application code is a defect.

### 3.2 dim_account

```sql
CREATE TABLE dim_account (
    account_key         serial      PRIMARY KEY,
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,
    source_account_code text,
    source_account_name text        NOT NULL,   -- verbatim from the books, never cleaned
    source_parent_group text,
    canonical_class     text,                   -- e.g. 'revenue.product_sales'
    statement_section   text,                   -- 'pnl' | 'bs' | 'memo'
    statement_line      text,                   -- 'net_revenue' | 'cogs.material' | 'ar'
    normal_balance      char(2),                -- 'Dr' | 'Cr'
    is_mapped           boolean     NOT NULL DEFAULT false,
    mapping_version_id  int,
    mapping_confidence  numeric(4,3),
    mapping_source      text,                   -- 'exact_rule' | 'ai_proposed' | 'human'
    approved_by         text,
    approved_at         timestamptz,
    valid_from          timestamptz NOT NULL DEFAULT now(),
    valid_to            timestamptz NOT NULL DEFAULT 'infinity',
    is_current          boolean     NOT NULL DEFAULT true,
    load_run_id         bigint      NOT NULL,
    source_record_id    text        NOT NULL
);

CREATE UNIQUE INDEX ux_dim_account_current
  ON dim_account (tenant_id, entity_id, source_record_id)
  WHERE is_current;
COMMENT ON TABLE dim_account IS
  'Grain: one GL account, one version. source_account_name is stored verbatim. Cleaning it destroys the only evidence of what the accountant meant.';
```

`source_account_name` is never normalised, trimmed of its parenthetical suffixes, or title-cased. "Sales - Retail (Delhi)" carries channel and geography information that the mapping layer extracts and that nothing else in the system can recover once it is lost.

### 3.3 fact_gl_entry

```sql
CREATE TABLE fact_gl_entry (
    fact_id             bigserial   PRIMARY KEY,
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,

    voucher_no          text        NOT NULL,
    voucher_type        text        NOT NULL,
    line_no             int         NOT NULL,

    event_date          date        NOT NULL REFERENCES dim_date(date_key),
    entry_date          date,
    period_key          text        NOT NULL,

    account_key         int         NOT NULL REFERENCES dim_account(account_key),
    cost_centre_key     int         REFERENCES dim_cost_centre(cost_centre_key),
    customer_key        int         REFERENCES dim_customer(customer_key),
    vendor_key          int         REFERENCES dim_vendor(vendor_key),

    amount_base         numeric(18,2) NOT NULL,   -- INR. Dr positive, Cr negative
    amount_txn          numeric(18,2),
    currency_code       char(3)     NOT NULL DEFAULT 'INR',
    fx_rate             numeric(14,6),
    fx_rate_source      text,

    narration           text,
    is_cancelled        boolean     NOT NULL DEFAULT false,
    is_opening_balance  boolean     NOT NULL DEFAULT false,

    valid_from          timestamptz NOT NULL DEFAULT now(),
    valid_to            timestamptz NOT NULL DEFAULT 'infinity',
    is_current          boolean     NOT NULL DEFAULT true,
    load_run_id         bigint      NOT NULL,
    source_system       text        NOT NULL,
    source_record_id    text        NOT NULL,
    row_hash            bytea       NOT NULL,
    mapping_version_id  int         NOT NULL
);

CREATE INDEX ix_gl_period      ON fact_gl_entry (tenant_id, period_key) WHERE is_current;
CREATE INDEX ix_gl_account     ON fact_gl_entry (account_key, event_date) WHERE is_current;
CREATE INDEX ix_gl_knowledge   ON fact_gl_entry (tenant_id, valid_from, valid_to);
CREATE INDEX ix_gl_backdated   ON fact_gl_entry (tenant_id, entry_date, event_date)
  WHERE entry_date IS NOT NULL AND entry_date > event_date;

COMMENT ON TABLE fact_gl_entry IS
  'Grain: one journal line. Dr positive, Cr negative in amount_base. Sum of amount_base over any complete period equals zero.';
```

**The invariant.** The sum of `amount_base` across all current rows for a complete period is exactly zero. This is the trial balance check, it is enforced as a constraint check in the pipeline rather than as a report, and a period that fails it does not proceed to statement assembly. Tolerance is zero.

The `ix_gl_backdated` partial index exists to make "what changed since we last reported" a fast query rather than a full scan, because it will be run on every load.

### 3.4 fact_invoice_line

```sql
CREATE TABLE fact_invoice_line (
    fact_id             bigserial   PRIMARY KEY,
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,

    invoice_no          text        NOT NULL,
    line_no             int         NOT NULL,
    event_date          date        NOT NULL REFERENCES dim_date(date_key),
    dispatch_date       date,
    entry_date          date,
    period_key          text        NOT NULL,

    customer_key        int         NOT NULL REFERENCES dim_customer(customer_key),
    product_key         int         REFERENCES dim_product(product_key),
    channel_key         int         REFERENCES dim_channel(channel_key),
    location_key        int         REFERENCES dim_location(location_key),

    quantity            numeric(18,4),
    uom                 text,
    rate                numeric(18,4),
    gross_amount        numeric(18,2) NOT NULL,
    discount_amount     numeric(18,2) NOT NULL DEFAULT 0,
    taxable_value       numeric(18,2) NOT NULL,
    tax_amount          numeric(18,2) NOT NULL DEFAULT 0,
    line_total          numeric(18,2) NOT NULL,

    is_credit_note      boolean     NOT NULL DEFAULT false,
    credit_note_reason  text,                     -- 'return' | 'discount' | 'rate_difference' | 'other'

    amount_txn          numeric(18,2),
    currency_code       char(3)     NOT NULL DEFAULT 'INR',
    fx_rate             numeric(14,6),

    valid_from          timestamptz NOT NULL DEFAULT now(),
    valid_to            timestamptz NOT NULL DEFAULT 'infinity',
    is_current          boolean     NOT NULL DEFAULT true,
    load_run_id         bigint      NOT NULL,
    source_system       text        NOT NULL,
    source_record_id    text        NOT NULL,
    row_hash            bytea       NOT NULL,
    mapping_version_id  int         NOT NULL
);
COMMENT ON TABLE fact_invoice_line IS
  'Grain: one sales invoice line, including credit note lines. credit_note_reason drives whether a credit note is a return or a discount, which changes net revenue.';
```

`credit_note_reason` is not cosmetic. Returns and discounts are separate concepts in file 03 and a credit note that cannot be classified goes to the exception queue rather than being assumed to be either.

### 3.5 fact_channel_order_line

Consumer profile only.

```sql
CREATE TABLE fact_channel_order_line (
    fact_id             bigserial   PRIMARY KEY,
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,

    order_id            text        NOT NULL,
    line_no             int         NOT NULL,
    event_date          date        NOT NULL REFERENCES dim_date(date_key),
    period_key          text        NOT NULL,

    channel_key         int         NOT NULL REFERENCES dim_channel(channel_key),
    channel_sub         text,
    product_key         int         NOT NULL REFERENCES dim_product(product_key),
    customer_key        int         REFERENCES dim_customer(customer_key),
    location_key        int         REFERENCES dim_location(location_key),

    quantity            numeric(18,4) NOT NULL,
    gross_amount        numeric(18,2) NOT NULL,
    discount_amount     numeric(18,2) NOT NULL DEFAULT 0,
    net_amount          numeric(18,2) NOT NULL,
    shipping_charged    numeric(18,2) NOT NULL DEFAULT 0,
    commission_amount   numeric(18,2) NOT NULL DEFAULT 0,
    shipping_cost       numeric(18,2) NOT NULL DEFAULT 0,
    payment_fee         numeric(18,2) NOT NULL DEFAULT 0,

    business_unit_key   int         REFERENCES dim_business_unit(bu_key),
    revenue_model       text        NOT NULL DEFAULT 'buyout',  -- 'marketplace' | 'buyout'. D-061
    order_type          text,                      -- 'acquisition' | 'retention'. Enables CAC analogue
    commission_earned   numeric(18,2) NOT NULL DEFAULT 0,  -- marketplace model only
    advertising_earned  numeric(18,2) NOT NULL DEFAULT 0,  -- marketplace model only
    platform_fee_earned numeric(18,2) NOT NULL DEFAULT 0,  -- marketplace model only

    is_returned         boolean     NOT NULL DEFAULT false,
    return_date         date,
    return_reason       text,
    settlement_date     date,                      -- P1. Reconciliation is deferred

    valid_from          timestamptz NOT NULL DEFAULT now(),
    valid_to            timestamptz NOT NULL DEFAULT 'infinity',
    is_current          boolean     NOT NULL DEFAULT true,
    load_run_id         bigint      NOT NULL,
    source_system       text        NOT NULL,
    source_record_id    text        NOT NULL,
    row_hash            bytea       NOT NULL,
    mapping_version_id  int         NOT NULL
);
COMMENT ON TABLE fact_channel_order_line IS
  'Grain: one order line. revenue_model determines how revenue derives: marketplace uses the *_earned columns, buyout uses net_amount. Never sum GMV across models and call it revenue. Returns per D-047. settlement_date populated where available but no settlement reconciliation runs in P0.';
```

**Note on the relationship to `fact_invoice_line`.** For a consumer brand these two tables describe overlapping reality: the order file and the books. They are deliberately not merged. The books are the accounting truth, the order file is the operational truth, and the gap between them is reported as a residual rather than resolved by picking a winner. Resolving it is settlement reconciliation, which is P1.

### 3.6 fact_production_output

Manufacturing profile only.

```sql
CREATE TABLE fact_production_output (
    fact_id             bigserial   PRIMARY KEY,
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,

    event_date          date        NOT NULL REFERENCES dim_date(date_key),
    period_key          text        NOT NULL,
    location_key        int         NOT NULL REFERENCES dim_location(location_key),
    line_code           text,
    product_key         int         NOT NULL REFERENCES dim_product(product_key),

    qty_produced        numeric(18,4) NOT NULL,
    qty_rejected        numeric(18,4) NOT NULL DEFAULT 0,
    uom                 text        NOT NULL,
    input_qty           numeric(18,4),
    input_uom           text,
    input_product_key   int         REFERENCES dim_product(product_key),

    available_hours     numeric(10,2),
    running_hours       numeric(10,2),
    power_units         numeric(14,2),

    valid_from          timestamptz NOT NULL DEFAULT now(),
    valid_to            timestamptz NOT NULL DEFAULT 'infinity',
    is_current          boolean     NOT NULL DEFAULT true,
    load_run_id         bigint      NOT NULL,
    source_system       text        NOT NULL,
    source_record_id    text        NOT NULL,
    row_hash            bytea       NOT NULL,
    mapping_version_id  int         NOT NULL
);
COMMENT ON TABLE fact_production_output IS
  'Grain: one product, one line, one production period. uom must be consistent per product per DECISION-REQUIRED[D-041]; mixed units block per-unit metrics rather than averaging them.';
```

A check constraint enforces one `uom` per `product_key` within a tenant. A second unit arriving for the same product raises an exception rather than being converted, because SPEQULA has no authority to convert tonnes to pieces.

### 3.7 map_account and mapping_version

```sql
CREATE TABLE mapping_version (
    mapping_version_id  serial      PRIMARY KEY,
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,
    version_no          int         NOT NULL,
    status              text        NOT NULL,   -- 'draft' | 'approved' | 'superseded'
    effective_from      date        NOT NULL,
    effective_to        date        NOT NULL DEFAULT '9999-12-31',
    created_by          text        NOT NULL,
    approved_by         text,
    approved_at         timestamptz,
    change_reason       text,
    UNIQUE (tenant_id, entity_id, version_no)
);

CREATE TABLE map_account (
    map_id              bigserial   PRIMARY KEY,
    mapping_version_id  int         NOT NULL REFERENCES mapping_version(mapping_version_id),
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,
    source_record_id    text        NOT NULL,
    source_account_name text        NOT NULL,
    canonical_class     text        NOT NULL,
    statement_section   text        NOT NULL,
    statement_line      text        NOT NULL,
    derived_channel     text,                    -- extracted from the ledger name where present
    derived_geo         text,
    derived_cost_centre text,
    confidence          numeric(4,3),
    proposal_source     text        NOT NULL,    -- 'exact_rule' | 'ai_proposed' | 'human'
    proposal_reason     text,
    approved_by         text        NOT NULL,
    approved_at         timestamptz NOT NULL,
    period_value_inr    numeric(18,2),           -- rupee value carried, used to sort the review queue
    UNIQUE (mapping_version_id, source_record_id)
);
COMMENT ON TABLE map_account IS
  'Grain: one source account, one mapping version. period_value_inr exists so the review queue sorts by money rather than by count.';
```

**Three properties this design gives you.** Mappings are versioned, so a signed pack from March renders with the March mapping forever. Every row records who approved it and on what basis, so an AI proposal that turned out wrong is attributable. And `period_value_inr` makes the review queue sort by rupee value, which is what turns a 900-ledger chart of accounts into a forty-line afternoon.

### 3.8 period_lock

```sql
CREATE TABLE period_lock (
    lock_id             serial      PRIMARY KEY,
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,
    period_key          text        NOT NULL,
    status              text        NOT NULL,   -- 'open' | 'reconciled' | 'locked' | 'restated'
    snapshot_at         timestamptz,            -- the knowledge-time cut this period is pinned to
    mapping_version_id  int         NOT NULL REFERENCES mapping_version(mapping_version_id),
    locked_by           text,
    locked_at           timestamptz,
    restated_from       int         REFERENCES period_lock(lock_id),
    restatement_reason  text,
    UNIQUE (tenant_id, entity_id, period_key, snapshot_at)
);
```

Once a period is locked, `snapshot_at` is the knowledge-time timestamp that every report for that period queries against. A later change to a locked period does not alter that row; it creates a new one with `status = 'restated'` and a pointer back. This is what makes "42.1 as reported 8 July, 43.4 restated 14 July, delta explained" a query rather than an archaeology project.

### 3.9 exception

```sql
CREATE TABLE exception (
    exception_id        bigserial   PRIMARY KEY,
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,
    raised_at           timestamptz NOT NULL DEFAULT now(),
    exception_class     text        NOT NULL,   -- 'unmapped' | 'completeness' | 'validity'
                                                -- | 'uniqueness' | 'consistency'
                                                -- | 'reconciliation' | 'continuity' | 'anomaly'
    severity            text        NOT NULL,   -- 'blocking' | 'warning' | 'informational'
    period_key          text,
    object_type         text,                   -- 'account' | 'invoice' | 'bank_txn' | 'period'
    object_ref          text,
    value_inr           numeric(18,2),          -- rupee exposure. Drives queue ordering
    description         text        NOT NULL,
    suggested_action    text,
    status              text        NOT NULL DEFAULT 'open',
    resolved_by         text,
    resolved_at         timestamptz,
    resolution_note     text,
    load_run_id         bigint
);
CREATE INDEX ix_exception_queue ON exception (tenant_id, status, severity, value_inr DESC);
```

**Blocking severity means blocking.** A blocking exception prevents statement assembly and prevents the pack from generating. It is not a badge on a number that ships anyway. Warnings badge the number and let it through. The distinction is configuration per check, listed in file 09.

### 3.10 dim_location and dim_product, retail attributes

Added 2026-08-24 for the apparel forecasting build (corpus/13). Both dimensions previously carried only the generic columns below section 2's table inventory names — `location_name`/`location_type` and `source_item_code`/`source_item_name`/`category`/`declared_uom` respectively, enough for a plant/warehouse or a manufacturing item, not enough to run store-cohort economics or price-band/occasion product cuts for a retail chain. These are additive columns (`ALTER TABLE ... ADD COLUMN`, `db/migrations/tenant/0020` and `0021`), nullable throughout — a plant, warehouse or non-apparel product row leaves them all NULL.

```sql
-- dim_location, retail columns
store_format   text,           -- 'COCO' | 'COFO' | 'FOCO' | 'FOFO'. Retail-store rows only
city           text,
state          text,
site_type      text,           -- 'mall' | 'high_street'. Retail-store rows only
area_sqft      numeric(10,2),
opening_date   date,           -- store vintage -- the forecast engine's cohort key
closure_date   date,
status         text            -- 'active' | 'closed' | 'planned'

-- dim_product, retail columns
price_band     text,           -- bucketed MRP range, company's own banding convention (e.g. 'a.<1000' .. 'f.3001-4000+')
occasion_type  text            -- 'casual' | 'evening' | 'occasion_fusion'. Apparel profile only
```

`store_format` is the same COCO/company-owned-company-operated, COFO/company-owned-franchise-operated, FOCO/franchise-owned-company-operated, FOFO/franchise-owned-franchise-operated taxonomy standard across Indian apparel retail — not a company-specific convention. It is orthogonal to `dim_channel.channel_type`'s existing `'owned retail'`/`'franchise retail'` split (0014_dim_channel.sql): channel identifies *which sales channel* an order line belongs to, `dim_location` identifies *which physical store*, and `store_format` on the location row is what a store-cohort forecast actually keys off — ownership and operating structure change a store's unit economics (a franchisee-operated FOFO store carries no company-borne rent or personnel cost line; the company only sees a commission), which channel type alone does not capture.

---

## 4. What the model deliberately does not have

| Absent | Why | When it arrives |
|---|---|---|
| Consolidation and elimination tables | Multi-entity is out of P0 by your decision. `entity_id` is present on every fact so this is an addition, not a migration | P2 |
| Document, chunk and embedding tables, pgvector | No document layer in the MVP. This removes a whole subsystem | P1 |
| Budget tables | Most pilots will not have a usable budget | P1 |
| `fact_ad_spend_day` | Marketing spend comes in as a monthly GL figure in P0 | P1 |
| An entity resolution table | Needed for CAC and cross-channel customer identity, neither of which is in P0 | P1 |
| A general knowledge graph | High build cost, no pilot needs it, and metric lineage is already a DAG inside the registry | Never, on current evidence |

---

## 5. Load pipeline, and what it guarantees

```
source file
  -> source_file        hash recorded, bytes retained immutably
  -> load_run           one run, one id, wrapping everything below
  -> staging            typed, currency-converted, deduplicated on row_hash
  -> entity resolution  source codes to surrogate dimension keys
  -> canonical facts    written with valid_from = now(), prior versions closed
  -> quality checks     exceptions raised, blocking ones halt the run
  -> reconciliation     trial balance, books to bank
  -> period status      updated in period_lock
```

Five guarantees this pipeline makes, and each is testable:

1. **Replayable.** Re-running from raw with the same mapping version produces byte-identical canonical output.
2. **Idempotent.** The same file loaded twice produces no duplicate facts, because `row_hash` catches it. Re-uploading a file is a weekly event, not an edge case.
3. **Non-destructive.** A changed fact closes the prior row rather than updating it. Nothing is ever overwritten.
4. **Isolated.** One failing stream does not stall the others, and the last good watermark is retained.
5. **Halting.** A blocking exception stops the run. The system never silently continues past unreliable data.

**Backdated entries are the normal case, not the exception.** Every run re-pulls a trailing window, defaulting to ninety days, because a source that stamps `updated_at` correctly is rare in this segment. Anything found in that window with `entry_date > event_date` is a backdated entry, and if it touches a locked period it is a restatement.

---

## 6. Tenancy

| Concern | MVP approach |
|---|---|
| Analytical data | One Postgres schema per tenant, `tenant_<uuid>`. A broken join cannot cross a customer boundary because the schemas are separate |
| App data | Shared tables with `tenant_id` and row-level security, forced at the connection role, not in the query text |
| Object storage | Tenant id as the first path segment on every raw file |
| Secrets | Per-tenant path in a secrets manager, never in the app database, never visible in the UI after entry |
| Migrations | Loop over schemas in one deploy. Adequate to roughly fifty tenants |
| Model-reachable role | A separate read-only database role with grants on canonical schemas only, no grant on `token_map`, `audit_log` or any app table |

Schema per tenant costs one afternoon now. Retrofitting it after a leak costs the company.

---

## 7. Open dependencies

| Item | Blocks |
|---|---|
| ~~D-038 fiscal year start~~ | **Resolved: April to March.** `dim_date` generation unblocked |
| DECISION-REQUIRED[D-041] declared unit per product | `fact_production_output` constraints, every per-unit metric |
| ~~D-046 channel taxonomy~~ | **Resolved.** `dim_channel` seeded with the seven canonical channels |
| DECISION-REQUIRED[D-047] return treatment | `fact_channel_order_line` semantics |
| ~~D-058 tokenisation scope~~ | **Resolved.** Employees excluded from model-reachable views entirely; customers and vendors tokenised with group, segment and category retained |
| DECISION-REQUIRED[D-002] revenue recognition point | Whether `event_date` on `fact_invoice_line` is invoice or dispatch date |
| ~~V-001 accounting regime~~ | **Closed: AS.** No right-of-use columns needed. Lease rentals are an ordinary opex class |
| VERIFY[V-003] Tally export structure | The staging layer for the Tally path. Nothing above staging changes |

Note that only one of these touches the canonical layer's structure. That is the point of the design: source uncertainty is absorbed in staging, and the canonical model stays stable while the world underneath it does not.
