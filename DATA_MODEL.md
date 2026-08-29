# DATA_MODEL.md

The SPEQULA data layer as built. HEAD `d720199`, documented 2026-08-27.
Every column below is transcribed from `db/migrations/`; every writer/reader is a grep-verified
call site in `src/` or `scripts/`.

---

## 1. Shape of the storage layer

Three stores, one of which is not a database:

| Store | What lives there | Isolation mechanism |
|---|---|---|
| **PostgreSQL 16, `app` schema** | Shared operational + PII data: tenancy, load runs, source files, audit, tokens, query log, access grants | Row-level security, `FORCE`d, keyed on `current_setting('app.tenant_id')` |
| **PostgreSQL 16, `tenant_<uuid>` schemas** | All analytical data: dimensions, bitemporal facts, mappings, exceptions, packs, forecasts | Physical schema separation, one per tenant |
| **S3-compatible object storage** | Immutable raw uploaded bytes | `tenant_id` as the first path segment |
| **Local filesystem (`config/`)** | Metric contracts, decisions, taxonomy — read-only at runtime | None; identical for every tenant |

`db/migrations/runner.py` applies `shared/*.sql` once against `app`, then loops
`tenant/*.sql` once per row in `app.tenant`, substituting `__SCHEMA__`.
**A tenant must be registered before migrations run** — `scripts/create_tenant.py` first, runner second.

There is no ORM. Every analytical query is a hand-written f-string over a `psycopg` cursor, with the
schema name interpolated and all values bound as parameters.

---

## 2. ER diagram

```mermaid
erDiagram
    %% ─────────── shared app schema (RLS-scoped) ───────────
    app_tenant                  ||--o{ app_load_run             : "scopes"
    app_tenant                  ||--o{ app_source_file          : "scopes"
    app_tenant                  ||--o{ app_audit_log            : "scopes"
    app_tenant                  ||--o{ app_token_map            : "scopes"
    app_tenant                  ||--o{ app_query_log            : "scopes"
    app_tenant                  ||--o{ app_employee_access_grant: "scopes"
    app_role                    ||--o{ app_audit_log            : "role_key"
    app_load_run                ||--o{ app_source_file          : "produced"

    %% ─────────── tenant schema: dimensions ───────────
    dim_date                    ||--o{ fact_gl_entry            : "event_date FK"
    dim_date                    ||--o{ fact_bank_txn            : "event_date FK"
    dim_account                 ||--o{ fact_gl_entry            : "account_key"
    dim_channel                 ||--o{ fact_channel_order_line  : "channel_key"
    dim_product                 ||--o{ fact_channel_order_line  : "product_key"
    dim_product                 ||--o{ fact_production_output   : "product_key"
    dim_location                ||--o{ fact_channel_order_line  : "location_key"
    dim_location                ||--o{ fact_production_output   : "location_key"
    dim_business_unit           ||--o{ fact_channel_order_line  : "business_unit_key (never populated)"

    %% ─────────── tenant schema: mapping spine ───────────
    mapping_version             ||--o{ map_account              : "one row per ledger"
    mapping_version             ||--o{ fact_gl_entry            : "placeholder v0 stamp"
    mapping_version             ||--o{ fact_bank_txn            : "placeholder v0 stamp"
    mapping_version             ||--o{ period_lock              : "governs"
    mapping_version             ||--o{ reconciliation_run       : "governs"
    mapping_version             ||--o{ report_artefact          : "governs"
    dim_account                 ||--o| map_account              : "source_record_id (soft join)"

    %% ─────────── tenant schema: operational + output ───────────
    period_lock                 ||--o| period_lock              : "restated_from"
    report_artefact             ||--o{ pack_edit_event          : "edits"
    forecast_scenario           ||--o{ forecast_run             : "runs"

    app_tenant {
        uuid        tenant_id PK
        text        name
        text        schema_name UK
        text        workos_organization_id UK
        boolean     is_synthetic
        timestamptz created_at
        timestamptz deleted_at "soft tombstone"
    }
    app_role {
        text role_key PK
        text description
    }
    app_load_run {
        bigserial   load_run_id PK
        uuid        tenant_id FK
        int         entity_id
        text        source_system
        text        status
        text        triggered_by
        timestamptz started_at
        timestamptz completed_at
        text        notes
    }
    app_source_file {
        bigserial   source_file_id PK
        uuid        tenant_id FK
        int         entity_id
        bigint      load_run_id FK
        text        file_name
        text        template_type
        bytea       content_hash
        bytea       schema_hash
        text        storage_path
        int         row_count
        timestamptz received_at
    }
    app_audit_log {
        bigserial   audit_id PK
        uuid        tenant_id FK
        text        actor
        text        role_key FK
        text        action
        text        object_type
        text        object_ref
        jsonb       detail
        timestamptz occurred_at
    }
    app_token_map {
        bigserial   token_map_id PK
        uuid        tenant_id FK
        text        entity_type "customer|vendor only"
        text        token
        text        real_name
        timestamptz created_at
    }
    app_query_log {
        bigserial   query_log_id PK
        uuid        tenant_id FK
        int         entity_id
        text        user_id
        text        role
        text        question
        text        intent
        jsonb       ir
        text        sql_text
        boolean     admitted
        text        rejection_gate
        text        rejection_reason
        int         row_count
        int         duration_ms
        text        model_version
        text        query_hash
        int         input_tokens "always null"
        int         output_tokens "always null"
        numeric     cost_inr "always null"
        timestamptz requested_at
    }
    app_employee_access_grant {
        bigserial   grant_id PK
        uuid        tenant_id FK
        text        employee_user_id
        text        employee_name
        text        granted_by
        text        reason
        timestamptz granted_at
        timestamptz expires_at "NOT NULL by design"
        timestamptz revoked_at
        text        revoked_by
    }
    dim_date {
        date     date_key PK
        smallint fiscal_year
        text     fiscal_year_label
        smallint fiscal_quarter
        smallint fiscal_month_num
        text     period_key
        boolean  is_month_end
        boolean  is_quarter_end
        boolean  is_fiscal_year_end
        smallint days_in_month
    }
    dim_account {
        serial      account_key PK
        uuid        tenant_id
        int         entity_id
        text        source_account_code
        text        source_account_name "verbatim, never cleaned"
        text        canonical_class
        text        statement_section
        text        statement_line
        char        normal_balance
        boolean     is_mapped
        int         mapping_version_id
        numeric     mapping_confidence
        text        mapping_source
        text        approved_by
        timestamptz valid_from
        timestamptz valid_to
        boolean     is_current
        bigint      load_run_id
        text        source_record_id
    }
    mapping_version {
        serial      mapping_version_id PK
        uuid        tenant_id
        int         entity_id
        int         version_no
        text        status "draft|approved|superseded"
        date        effective_from
        date        effective_to
        text        created_by
        text        approved_by
        timestamptz approved_at
        text        change_reason
    }
    map_account {
        bigserial   map_id PK
        int         mapping_version_id FK
        text        source_record_id
        text        source_account_name
        text        canonical_class
        text        statement_section
        text        statement_line
        text        derived_channel
        text        derived_geo
        text        derived_cost_centre
        numeric     confidence
        text        proposal_source
        text        proposal_reason
        text        approved_by
        timestamptz approved_at
        numeric     period_value_inr "sorts the review queue"
    }
    fact_gl_entry {
        bigserial   fact_id PK
        uuid        tenant_id
        int         entity_id
        text        voucher_no
        text        voucher_type
        int         line_no
        date        event_date FK
        date        entry_date
        text        period_key
        int         account_key FK
        int         cost_centre_key "always null"
        int         customer_key "always null"
        int         vendor_key "always null"
        numeric     amount_base "Dr+ Cr-"
        numeric     amount_txn "== amount_base"
        char        currency_code "always INR"
        numeric     fx_rate "always 1"
        text        fx_rate_source
        text        narration
        boolean     is_cancelled
        boolean     is_opening_balance
        timestamptz valid_from
        timestamptz valid_to
        boolean     is_current
        bigint      load_run_id
        text        source_system
        text        source_record_id
        bytea       row_hash UK
        int         mapping_version_id FK
    }
    fact_bank_txn {
        bigserial   fact_id PK
        text        bank_account_ref
        date        event_date FK
        date        value_date
        date        entry_date
        text        period_key
        text        description
        text        reference
        numeric     amount_base "in+ out-"
        numeric     running_balance_reported
        timestamptz valid_from
        timestamptz valid_to
        boolean     is_current
        bigint      load_run_id
        bytea       row_hash
        int         mapping_version_id FK
    }
    fact_channel_order_line {
        bigserial   fact_id PK
        text        order_id
        int         line_no
        date        event_date
        int         channel_key FK
        int         product_key FK
        int         location_key FK
        int         business_unit_key FK
        numeric     quantity
        numeric     gross_amount
        numeric     discount_amount
        numeric     net_amount
        numeric     shipping_charged
        numeric     commission_amount
        numeric     shipping_cost
        numeric     payment_fee
        text        revenue_model "marketplace|buyout, D-061"
        text        order_type
        numeric     commission_earned
        numeric     advertising_earned
        numeric     platform_fee_earned
        boolean     is_returned
        date        return_date
        date        settlement_date "P1, unreconciled"
        bytea       row_hash
    }
    fact_production_output {
        bigserial fact_id PK
        date      event_date
        int       location_key FK
        text      line_code
        int       product_key FK
        numeric   qty_produced
        numeric   qty_rejected
        text      uom "D-041 gate"
        numeric   input_qty
        int       input_product_key FK
        numeric   available_hours
        numeric   running_hours
        numeric   power_units
        bytea     row_hash
    }
    dim_channel {
        serial channel_key PK
        text   channel_type "D-046 seven values"
        text   channel_name
    }
    dim_product {
        serial product_key PK
        text   source_item_code
        text   source_item_name
        text   category
        text   declared_uom "D-041, null until declared"
        text   price_band
        text   occasion_type
    }
    dim_location {
        serial  location_key PK
        text    location_name
        text    location_type
        text    store_format "COCO|COFO|FOCO|FOFO"
        text    city
        text    state
        text    site_type
        numeric area_sqft
        date    opening_date "drives cohort forecast"
        date    closure_date
        text    status
    }
    dim_entity {
        serial   entity_key PK
        text     entity_name
        smallint fiscal_year_start_month "4, D-038"
    }
    dim_business_unit {
        serial bu_key PK
        text   bu_name
    }
    period_lock {
        serial      lock_id PK
        text        period_key
        text        status "open..restated"
        timestamptz snapshot_at
        int         mapping_version_id FK
        text        locked_by
        int         restated_from FK
        text        restatement_reason
    }
    exception {
        bigserial   exception_id PK
        text        exception_class
        text        severity "blocking|warning|informational"
        text        period_key
        text        object_type
        text        object_ref
        numeric     value_inr "orders the queue"
        text        description
        text        suggested_action
        text        status
        text        resolved_by
        text        resolution_note
        bigint      load_run_id
    }
    reconciliation_run {
        bigserial   reconciliation_run_id PK
        text        period_key
        text        check_type "trial_balance|books_to_bank"
        text        status
        numeric     books_amount_inr
        numeric     bank_amount_inr
        jsonb       modelled_differences
        numeric     residual_inr
        numeric     tolerance_pct "null, D-052 unset"
        text        run_by
        int         mapping_version_id FK
    }
    metric_definition {
        bigserial metric_definition_id PK
        text      metric_id
        int       version_no
        text      status
        jsonb     parameters "override values only"
        date      effective_from
        date      effective_to
        text      approved_by
    }
    report_artefact {
        bigserial   report_artefact_id PK
        text        period_key
        text        profile
        timestamptz generated_at
        int         mapping_version_id FK
        jsonb       metric_versions
        jsonb       freshness_snapshot
        jsonb       reconciliation_snapshot
        jsonb       sections "the eight P0 sections"
        jsonb       chart_specs "spec, never a picture"
        text        commentary "human-written"
        text        content_hash
        text        status "draft|signed"
        text        reviewer
        text        blocking_exception_override_reason
    }
    pack_edit_event {
        bigserial   pack_edit_event_id PK
        bigint      report_artefact_id FK
        text        edit_type "commentary only"
        text        edited_by
        text        previous_commentary
        text        new_commentary
    }
    forecast_scenario {
        bigserial   scenario_id PK
        text        name
        text        created_by
        jsonb       driver_assumptions
        timestamptz archived_at
        text        archived_by
    }
    forecast_run {
        bigserial run_id PK
        bigint    scenario_id FK
        date      baseline_period_end
        jsonb     baseline_snapshot
        jsonb     computed_result
        jsonb     gaps
        text      created_by
    }
```

**Note on cross-schema links:** every tenant-schema fact carries `load_run_id bigint NOT NULL` but
**no `REFERENCES`** — a tenant schema cannot foreign-key into `app`. The link is by convention and
enforced by nothing.

---

## 3. Shared `app` schema — 7 tables

All carry `ENABLE`/`FORCE ROW LEVEL SECURITY` with a `tenant_isolation` policy on
`current_setting('app.tenant_id', true)::uuid`, and all are `REVOKE ALL ... FROM model_reachable`.

| Table | Grain | Writers | Readers |
|---|---|---|---|
| `app.tenant` | one tenant | [tenant_lifecycle.py](src/admin/tenant_lifecycle.py) (tombstone), [create_tenant.py](scripts/create_tenant.py), [link_tenant_workos_org.py](scripts/link_tenant_workos_org.py) | [deps/tenant.py](src/api/deps/tenant.py) (every request), [routes/admin.py](src/api/routes/admin.py), `db/migrations/runner.py` |
| `app.role` | one role | migration `0001` only (4 seeded rows) | **nothing** — `audit_log.role_key` FK is never populated |
| `app.load_run` | one ingestion execution | [load_pipeline.py:58,68](src/ingest/load_pipeline.py#L58) | [routes/load_runs.py](src/api/routes/load_runs.py), [checks.py](src/quality/checks.py) (freshness), [tenant_lifecycle.py](src/admin/tenant_lifecycle.py) |
| `app.source_file` | one received file | [load_pipeline.py:85](src/ingest/load_pipeline.py#L85) | [load_pipeline.py:74](src/ingest/load_pipeline.py#L74) (schema-hash), [citation.py:64](src/semantic/citation.py#L64) (**the citation's source-row resolution**), [routes/load_runs.py](src/api/routes/load_runs.py) |
| `app.audit_log` | one audited action | [grants.py:68,91,130](src/access/grants.py#L68), [tenant_lifecycle.py:92](src/admin/tenant_lifecycle.py#L92) — **only 2 modules** | [routes/admin.py:113](src/api/routes/admin.py#L113) |
| `app.token_map` | one token↔name | [tokenise.py](src/ingest/tokenise.py) | [tokenise.py](src/ingest/tokenise.py), [tenant_lifecycle.py](src/admin/tenant_lifecycle.py) (purge) |
| `app.query_log` | one Ask query | [ask.py:75](src/semantic/ask.py#L75) | [routes/admin.py:194](src/api/routes/admin.py#L194) (model cost) |
| `app.employee_access_grant` | one time-bound grant | [grants.py](src/access/grants.py) | [grants.py](src/access/grants.py) |

**`audit_log` is the weakest link.** Its own DDL comment promises "access, exports, mapping changes,
metric changes, approvals." Only *access* and *tenant deletion* write to it. Uploads, mapping
freezes, pack signings and exports write nothing. Nothing at the DB level prevents `UPDATE`/`DELETE`
either — "immutable" is a convention, not a constraint or trigger.

---

## 4. Tenant schemas — 18 tables

### 4.1 Dimensions (Type-2 SCD: `valid_from`/`valid_to`/`is_current`/`load_run_id`/`source_record_id`)

| Table | Grain | Writers | Readers |
|---|---|---|---|
| `dim_date` | one calendar day | [seed_dim_date.py](scripts/seed_dim_date.py) | **nothing in `src/`** — see §6 |
| `dim_entity` | one legal entity | [seed_entity.py](scripts/seed_entity.py) | its own seed script only |
| `dim_business_unit` | one business line | **nothing** | **nothing** — see §6 |
| `dim_account` | one GL account, one version | [canonical.py:81](src/ingest/canonical.py#L81) (find-or-create), [review.py:251](src/mapping/review.py#L251) (freeze refresh) | mapping engine, trial balance, compiler, `reports/query.py`, `checks.py` |
| `dim_channel` | one sales channel (D-046) | [seed_dim_channel.py](scripts/seed_dim_channel.py) | [canonical.py](src/ingest/canonical.py) |
| `dim_product` | one SKU, one version | [canonical.py](src/ingest/canonical.py) | `checks.py` (mixed-UOM), `forecasting/baseline.py`, `manufacturing_operating.py` |
| `dim_location` | one plant/warehouse/store | [canonical.py](src/ingest/canonical.py) | `forecasting/baseline.py` (store cohorts) |

Retail attributes (`store_format`, `opening_date`, `site_type`, `area_sqft`, …) were added to
`dim_location` by migration `0020` and apparel attributes (`price_band`, `occasion_type`) to
`dim_product` by `0021`, for the corpus/13 forecast build.

### 4.2 Facts (all bitemporal, all `row_hash`-keyed, all close-not-update)

| Table | Grain | Writers | Readers |
|---|---|---|---|
| `fact_gl_entry` | one journal line | [canonical.py:218](src/ingest/canonical.py#L218) — **sole writer** | `reports/query.py`, `semantic/compiler.py`, `trial_balance.py`, `checks.py`, `repull.py`, `mapping/engine.py` |
| `fact_bank_txn` | one bank statement line | [canonical.py:307](src/ingest/canonical.py#L307) | [books_to_bank.py](src/quality/books_to_bank.py) — **which has no production caller** |
| `fact_channel_order_line` | one order line | [canonical.py](src/ingest/canonical.py) | `consumer_ladder.py`, `forecasting/baseline.py`, `checks.py` |
| `fact_production_output` | one product/line/period | [canonical.py](src/ingest/canonical.py) | `manufacturing_operating.py`, `checks.py` |

The only `UPDATE` any fact table ever receives is
`SET valid_to = now(), is_current = false` ([canonical.py:276](src/ingest/canonical.py#L276)) — lineage
columns only, never business content. `CLAUDE.md` invariant 3 and 4 hold.

Unique index `ux_gl_row_hash_current (tenant_id, row_hash) WHERE is_current` is what makes
re-uploading the same file a no-op at the database level, not just in application logic.

### 4.3 Mapping spine

| Table | Grain | Writers | Readers |
|---|---|---|---|
| `mapping_version` | one version header | [review.py:40](src/mapping/review.py#L40) (draft), [review.py:241](src/mapping/review.py#L241) (approve), [seed_mapping_version_placeholder.py](scripts/seed_mapping_version_placeholder.py) (v0) | [query.py:24](src/reports/query.py#L24) — the effective-dating resolver every read path goes through |
| `map_account` | one ledger, one version | [review.py:75](src/mapping/review.py#L75) — sole writer | `reports/query.py`, `compiler.py`, `citation.py`, `data_health.py` — **the authoritative classification join** |

`dim_account.canonical_class` is a denormalised convenience copy refreshed at freeze
([review.py:251](src/mapping/review.py#L251)); `map_account` is authoritative because it is versioned
and effective-dated.

### 4.4 Operational and output

| Table | Grain | Writers | Readers |
|---|---|---|---|
| `period_lock` | one period-state transition (append-only) | [period_state.py:84](src/quality/period_state.py#L84) — **no production caller reaches the transition functions** | [overview.py:73](src/api/routes/overview.py#L73), [pack.py:117](src/reports/pack.py#L117), [ask_compiler.py:221](src/semantic/ask_compiler.py#L221) |
| `exception` | one raised exception | INSERT: [checks.py:63](src/quality/checks.py#L63) — **no production caller**. UPDATE: [routes/exceptions.py:69](src/api/routes/exceptions.py#L69) (resolve) | `routes/exceptions.py`, `data_health.py`, `pack.py:324`, `signoff.py:139`, `routes/admin.py` — **5 readers, 0 reachable writers** |
| `reconciliation_run` | one check, one period, one run | [books_to_bank.py:133](src/quality/books_to_bank.py#L133) — **no production caller** | `data_health.py`, `pack.py`, `ask_compiler.py` |
| `metric_definition` | one per-tenant metric override | **nothing** | [overrides.py:46](src/semantic/overrides.py#L46) |
| `report_artefact` | one pack generation | [signoff.py:65](src/reports/signoff.py#L65) (insert), `:96` (commentary while draft), `:148` (sign) | `routes/reports.py`, `signoff.py`, `edits.py` |
| `pack_edit_event` | one commentary edit (append-only) | [edits.py:55](src/reports/edits.py#L55) | [edits.py:113](src/reports/edits.py#L113) |
| `forecast_scenario` | one saved driver set | [scenario.py:35](src/forecasting/scenario.py#L35), `:63` (archive) | [scenario.py:50](src/forecasting/scenario.py#L50) |
| `forecast_run` | one projection run | [scenario.py:111](src/forecasting/scenario.py#L111) | [scenario.py:136](src/forecasting/scenario.py#L136) |

### 4.5 `model_reachable` grants (CLAUDE.md invariant 6)

`GRANT SELECT` — `dim_date`, `dim_entity`, `dim_business_unit`, `dim_account`, `dim_channel`,
`dim_product`, `dim_location`, `fact_gl_entry`, `fact_bank_txn`, `fact_channel_order_line`,
`fact_production_output`.
`REVOKE ALL` — every `app.*` table, plus `map_account`, `mapping_version`, `period_lock`,
`exception`, `reconciliation_run`, `metric_definition`, `report_artefact`, `pack_edit_event`,
`forecast_scenario`, `forecast_run`.

**The grants are correct and unused.** [ask.py:198](src/semantic/ask.py#L198) never issues
`SET ROLE model_reachable` — its docstring explains that doing so would break every Ask query,
because `compile_metric` must read the `REVOKE`d `map_account`. So the role exists, is granted
correctly, and guards nothing at runtime.

---

## 5. Non-database stores

### Object storage (S3-compatible; MinIO locally)
Written by [landing.py:54](src/ingest/landing.py#L54) `put_object`, key
`{tenant_id}/{load_run_id}/{file_name}`. Bucket auto-created on first use
([landing.py:35](src/ingest/landing.py#L35)). `read_landed`
([landing.py:63](src/ingest/landing.py#L63)) exists but **has no caller** — landing is write-only.
A file rejected for schema drift returns at
[load_pipeline.py:113](src/ingest/load_pipeline.py#L113) **before** `land_file`, so its bytes are
never stored.

### `config/` on disk (read-only, identical per tenant)
`decisions.yml` (83 decisions, 16 open) · `metrics/*.yml` (61 contracts) · `taxonomy.yml`
(86 classes). Loaded by [loader.py:97](src/config/loader.py#L97) on every request. Generated from
`corpus/` by `scripts/gen_*.py`; **never hand-edited**.

---

## 6. Orphans and anomalies in the schema

| Finding | Detail |
|---|---|
| **`dim_business_unit` is fully dead** | Zero references in `src/` or `scripts/`. Created by migration `0003`, targeted by `fact_channel_order_line.business_unit_key`, which no loader ever populates. |
| **`dim_date` is written but never read** | Seeded by `scripts/seed_dim_date.py`; **no query in `src/` selects from it**. It exists solely to satisfy the `event_date` FK on `fact_gl_entry`/`fact_bank_txn` — inserts fail if it's unseeded. corpus/04 §3.1 says it "owns the fiscal calendar... nowhere else" and that "a fiscal year computed inline in application code is a defect." Both live implementations are inline Python: [calendar.py:20](src/ingest/calendar.py#L20) `fiscal_year` (called only by the seeder and tests) and [comparatives.py:48](src/reports/comparatives.py#L48) `fiscal_year_start` (called by `pack.py`). Two Python fiscal-calendar implementations; zero `dim_date` reads. |
| **`metric_definition` has no writer** | The override chain at [overrides.py:46](src/semantic/overrides.py#L46) queries it on every metric compile, but no code path and no API route inserts a row. Per-company and per-entity metric overrides are structurally unreachable; every metric resolves to `global_default`. |
| **`app.role` is never joined** | 4 rows seeded by migration `0001`; `audit_log.role_key` FK is never populated by either writer. |
| **`exception`: 5 readers, 0 reachable writers** | `write_exceptions` has no production caller, so the queue, the data-health panels, the pack's DQ appendix and the sign-off gate all read a permanently empty table. |
| **`reconciliation_run` and `period_lock`: same shape** | Their sole writers (`books_to_bank`, `period_state` transitions) have no production callers. |
| **`fact_gl_entry.mapping_version_id` is write-only** | Stamped with the v0 placeholder ([canonical.py:242](src/ingest/canonical.py#L242)); [query.py:9](src/reports/query.py#L9) states statement assembly deliberately ignores it and re-resolves by period. `NOT NULL`, always populated, read by nothing. |
| **Four GL columns are constants** | `currency_code='INR'`, `fx_rate=1`, `amount_txn == amount_base`, `is_opening_balance=false` on every row — corpus/01's GL template carries no currency field. |
| **Three FK columns are permanently null** | `fact_gl_entry.customer_key`, `.vendor_key`, `.cost_centre_key` — `dim_customer`/`dim_vendor`/`dim_cost_centre` were never built, so the `REFERENCES` clauses are commented out in the DDL. `token_map` therefore holds party tokens that nothing joins to. |
| **`query_log` cost columns always null** | `input_tokens`/`output_tokens`/`cost_inr` added by migration `0010` for the model-cost feature; no ModelClient reports usage, so `/admin/tenants/{id}/model-cost` sums nulls. |

---

# External interfaces

## 7. HTTP routes — 39 endpoints

`src/api/main.py` mounts 12 routers plus `GET /health` (unauthenticated).
**Every other route requires a verified WorkOS bearer token.** Tenant is derived from the signed
`org_id` claim — never from a header or path segment (except `/admin/*`, which is cross-tenant by
design and gated on `require_admin_role`).

| Method | Path | Auth gate | Source |
|---|---|---|---|
| GET | `/health` | **none** | [main.py:50](src/api/main.py#L50) |
| POST | `/upload` | `require_upload_role` | [upload.py:35](src/api/routes/upload.py#L35) |
| GET | `/load-runs` | `resolve_tenant` only | [load_runs.py:16](src/api/routes/load_runs.py#L16) |
| GET | `/files` | `resolve_tenant` only | [load_runs.py:34](src/api/routes/load_runs.py#L34) |
| POST | `/mapping/runs` | `require_upload_role` | [mapping.py:36](src/api/routes/mapping.py#L36) |
| GET | `/mapping/runs/{id}/queue` | `require_upload_role` | [mapping.py:57](src/api/routes/mapping.py#L57) |
| POST | `/mapping/runs/{id}/freeze` | `require_upload_role` | [mapping.py:64](src/api/routes/mapping.py#L64) |
| GET | `/statements/pnl` | `require_role` | [statements.py:23](src/api/routes/statements.py#L23) |
| GET | `/statements/balance-sheet` | `require_role` | [statements.py:52](src/api/routes/statements.py#L52) |
| GET | `/operating/consumer-ladder` | `require_role` | [operating.py:24](src/api/routes/operating.py#L24) |
| GET | `/operating/manufacturing` | `require_role` | [operating.py:61](src/api/routes/operating.py#L61) |
| GET | `/overview/tiles` | `require_role` | [overview.py:58](src/api/routes/overview.py#L58) |
| GET | `/data-health` | `require_role` | [data_health.py:75](src/api/routes/data_health.py#L75) |
| GET | `/exceptions` | `require_role` | [exceptions.py:22](src/api/routes/exceptions.py#L22) |
| POST | `/exceptions/{id}/resolve` | `require_role` | [exceptions.py:56](src/api/routes/exceptions.py#L56) |
| POST | `/ask` | `require_role` | [ask.py:42](src/api/routes/ask.py#L42) |
| POST | `/reports/generate` | `require_upload_role` | [reports.py:68](src/api/routes/reports.py#L68) |
| GET | `/reports` | `require_role` | [reports.py:205](src/api/routes/reports.py#L205) |
| GET | `/reports/{id}` | `require_role` | [reports.py:110](src/api/routes/reports.py#L110) |
| GET | `/reports/{id}/export` | `require_role` | [reports.py:121](src/api/routes/reports.py#L121) |
| PATCH | `/reports/{id}/commentary` | `require_upload_role` | [reports.py:158](src/api/routes/reports.py#L158) |
| GET | `/reports/{id}/blocking-exceptions` | `require_role` | [reports.py:173](src/api/routes/reports.py#L173) |
| POST | `/reports/{id}/sign` | `require_upload_role` | [reports.py:190](src/api/routes/reports.py#L190) |
| GET | `/reports/edits-per-pack` | `require_role` | [reports.py:83](src/api/routes/reports.py#L83) |
| POST | `/forecast/scenarios` | `require_upload_role` | [forecast.py:29](src/api/routes/forecast.py#L29) |
| GET | `/forecast/scenarios` | `require_upload_role` | [forecast.py:39](src/api/routes/forecast.py#L39) |
| GET | `/forecast/scenarios/{id}` | `require_upload_role` | [forecast.py:51](src/api/routes/forecast.py#L51) |
| DELETE | `/forecast/scenarios/{id}` | `require_upload_role` | [forecast.py:62](src/api/routes/forecast.py#L62) (archives, never deletes) |
| POST | `/forecast/scenarios/{id}/run` | `require_upload_role` | [forecast.py:85](src/api/routes/forecast.py#L85) |
| GET | `/forecast/runs/{id}` | `require_upload_role` | [forecast.py:128](src/api/routes/forecast.py#L128) |
| GET | `/admin/tenants` | `require_admin_role` | [admin.py:44](src/api/routes/admin.py#L44) |
| POST | `/admin/tenants/{id}/access-grants` | `require_admin_role` | [admin.py:70](src/api/routes/admin.py#L70) |
| GET | `/admin/tenants/{id}/access-grants` | `require_admin_role` | [admin.py:84](src/api/routes/admin.py#L84) |
| POST | `/admin/access-grants/{id}/revoke` | `require_admin_role` | [admin.py:100](src/api/routes/admin.py#L100) |
| GET | `/admin/tenants/{id}/audit-log` | `require_admin_role` | [admin.py:113](src/api/routes/admin.py#L113) |
| GET | `/admin/tenants/{id}/support-data-health` | `require_admin_role` + active grant | [admin.py:133](src/api/routes/admin.py#L133) |
| POST | `/admin/tenants/{id}/delete` | `require_admin_role` | [admin.py:177](src/api/routes/admin.py#L177) — **`DROP SCHEMA CASCADE`, irreversible** |
| GET | `/admin/tenants/{id}/model-cost` | `require_admin_role` | [admin.py:194](src/api/routes/admin.py#L194) |
| POST | `/admin/tenants/{id}/restore-rehearsal` | `require_admin_role` | [admin.py:221](src/api/routes/admin.py#L221) |

**Referenced but nonexistent:** `GET /query/{query_hash}/rows` — every citation's `drill_url`
([citation.py:111](src/semantic/citation.py#L111)) points at it. No handler exists; the UI discloses
this at [Citation.tsx:114](web/components/app/Citation.tsx#L114).

### Frontend routes (Next.js App Router)
`/` → redirects to `/overview` · `/overview` · `/statements` · `/operating` · `/forecast` ·
`/ask` · `/reports` · `/upload` · `/load-runs` · `/mapping` · `/data-health` · `/exceptions` ·
`/settings` · `/callback` (WorkOS AuthKit handler).
[middleware.ts](web/middleware.ts) applies `authkitMiddleware()` to everything except
`_next/static`, `_next/image`, `favicon.ico` — there is no unauthenticated screen.

## 8. Queues and scheduled jobs

**None. Zero.** No message broker, no task queue, no worker process, no cron entry, no Postgres job
table, no scheduler library in `requirements.txt`. `CLAUDE.md` §6 specifies "Cron plus a Postgres job
table for orchestration" — **neither was built.**

Consequences the diagram implies but the code cannot deliver:
- "Bad files … re-pulled **automatically**" — [repull.py](src/ingest/repull.py) *detects* backdated
  entries; nothing invokes it on a schedule.
- Forecast commentary "**each quarter**" — nothing fires quarterly.
- "Alerts **as they happen**" — no producer, no delivery.

Everything in this system happens because an HTTP request arrived.

## 9. Third-party APIs

| Service | Status | Where | Notes |
|---|---|---|---|
| **WorkOS** (AuthKit) | **Live, required** | [auth.py:59](src/api/deps/auth.py#L59) `workos.WorkOSClient`, [auth.py:67](src/api/deps/auth.py#L67) JWKS fetch; frontend `@workos-inc/authkit-nextjs` | Two outbound calls: `get_jwks_url()` and the JWKS fetch (cached via `lru_cache` + `PyJWKClient(cache_keys=True)`). Roles and org membership are configured in the WorkOS dashboard, not in code. |
| **S3-compatible object storage** | **Live, required** | [landing.py:24](src/ingest/landing.py#L24) via `boto3` | `create_bucket`, `put_object`, `get_object`. MinIO locally, any S3 API in production. |
| **PostgreSQL 16** | **Live, required** | `psycopg` 3 throughout | Local Docker or hosted (the checked-in `.env` points at a Supabase pooler). |
| **LLM provider** | **Stub — no vendor chosen** | [model_client.py:99](src/semantic/model_client.py#L99) `AnthropicModelClient` | All three methods raise `ModelNotConfigured`. No SDK in `requirements.txt`, no `ANTHROPIC_API_KEY` read anywhere. Blocked on VERIFY[V-012]. [ask.py:27](src/api/routes/ask.py#L27) hardwires the empty-fixture stub. |
| **Tracxn** | **Does not exist** | — | Zero occurrences of `tracxn`, `benchmark`, `competitor` or `peer` in `src/`, `web/`, `config/` or `db/` outside `node_modules`. No connector, no table, no env var, no config key. The diagram's "Connected to Tracxn for competitor benchmarking" has no implementation of any kind — and [refusal.py:27](src/semantic/refusal.py#L27) uses a competitor question as its canonical `genuinely_unanswerable` example. |

## 10. Environment variables

### Backend (`src/`, `db/`, `scripts/`)

| Variable | Required? | Default | Read at |
|---|---|---|---|
| `DATABASE_URL` | **effectively required** | `postgresql://spequla:spequla@localhost:5432/spequla` | [tenant.py:24](src/api/deps/tenant.py#L24), [runner.py:29](db/migrations/runner.py#L29), [conftest.py:20](tests/conftest.py#L20) |
| `WORKOS_API_KEY` | **hard required** | none — raises `RuntimeError` | [auth.py:61](src/api/deps/auth.py#L61) via `_require_env` |
| `WORKOS_CLIENT_ID` | **hard required** | none — raises `RuntimeError` | [auth.py:62](src/api/deps/auth.py#L62) via `_require_env` |
| `OBJECT_STORE_ENDPOINT` | no | `http://localhost:9000` | [landing.py:18](src/ingest/landing.py#L18) |
| `OBJECT_STORE_ACCESS_KEY` | no | `spequla` | [landing.py:19](src/ingest/landing.py#L19) |
| `OBJECT_STORE_SECRET_KEY` | no | `spequla_dev_only` | [landing.py:20](src/ingest/landing.py#L20) |
| `OBJECT_STORE_BUCKET` | no | `spequla-raw` | [landing.py:21](src/ingest/landing.py#L21) |
| `CORS_ALLOWED_ORIGINS` | no | `http://localhost:3000` | [main.py:26](src/api/main.py#L26), comma-separated |
| `PORT` | no | `8000` | `Dockerfile` CMD only |

Only the two WorkOS keys fail loudly. The other seven silently fall back to localhost dev defaults —
so a misconfigured production deploy points at a nonexistent local Postgres and MinIO rather than
refusing to start.

### Frontend (`web/`)

| Variable | Required? | Notes |
|---|---|---|
| `WORKOS_CLIENT_ID` | yes | AuthKit |
| `WORKOS_API_KEY` | yes | AuthKit |
| `WORKOS_COOKIE_PASSWORD` | yes | ≥32 chars; `openssl rand -base64 24` |
| `NEXT_PUBLIC_WORKOS_REDIRECT_URI` | yes | e.g. `http://localhost:3000/callback` |
| `NEXT_PUBLIC_API_BASE_URL` | no | defaults to `http://localhost:8000` ([api.ts:6](web/lib/api.ts#L6)) |

### Loading

**Nothing auto-loads `.env`.** There is no `python-dotenv` dependency and `docker-compose.yml` has no
`env_file:` key. The `.env` at the repo root is read only if you export it yourself. Next.js does load
`web/.env.local` natively. Templates: [.env.example](.env.example), [web/.env.local.example](web/.env.local.example).

**Not required anywhere:** any LLM API key, any Tracxn credential. Neither integration exists to
configure.
