-- Verbatim from corpus/04_SPEQULA_CANONICAL_DATA_MODEL.md section 3.3, with
-- one deliberate deviation: customer_key, vendor_key and cost_centre_key are
-- created as plain nullable int columns WITHOUT their REFERENCES constraint,
-- because dim_customer, dim_vendor and dim_cost_centre are not in Sprint 1
-- scope. The constraint is added later via a forward-only ALTER TABLE, in
-- whichever sprint builds those dimensions. account_key keeps its FK since
-- dim_account is in scope now.

CREATE TABLE __SCHEMA__.fact_gl_entry (
    fact_id             bigserial   PRIMARY KEY,
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,

    voucher_no          text        NOT NULL,
    voucher_type        text        NOT NULL,
    line_no             int         NOT NULL,

    event_date          date        NOT NULL REFERENCES __SCHEMA__.dim_date(date_key),
    entry_date          date,
    period_key          text        NOT NULL,

    account_key         int         NOT NULL REFERENCES __SCHEMA__.dim_account(account_key),
    cost_centre_key     int,        -- REFERENCES dim_cost_centre(cost_centre_key), deferred to the sprint that builds it
    customer_key        int,        -- REFERENCES dim_customer(customer_key), deferred
    vendor_key           int,        -- REFERENCES dim_vendor(vendor_key), deferred

    amount_base         numeric(18,2) NOT NULL,   -- INR. Dr positive, Cr negative
    amount_txn          numeric(18,2),
    currency_code       char(3)     NOT NULL DEFAULT 'INR',
    fx_rate             numeric(14,6),
    fx_rate_source      text,

    narration           text,
    is_cancelled        boolean     NOT NULL DEFAULT false,
    is_opening_balance  boolean     NOT NULL DEFAULT false,

    valid_from          timestamptz NOT NULL DEFAULT now(),
    valid_to             timestamptz NOT NULL DEFAULT 'infinity',
    is_current           boolean     NOT NULL DEFAULT true,
    load_run_id          bigint      NOT NULL,
    source_system        text        NOT NULL,
    source_record_id     text        NOT NULL,
    row_hash              bytea       NOT NULL,
    mapping_version_id   int         NOT NULL REFERENCES __SCHEMA__.mapping_version(mapping_version_id)
);

CREATE INDEX ix_gl_period      ON __SCHEMA__.fact_gl_entry (tenant_id, period_key) WHERE is_current;
CREATE INDEX ix_gl_account     ON __SCHEMA__.fact_gl_entry (account_key, event_date) WHERE is_current;
CREATE INDEX ix_gl_knowledge   ON __SCHEMA__.fact_gl_entry (tenant_id, valid_from, valid_to);
CREATE INDEX ix_gl_backdated   ON __SCHEMA__.fact_gl_entry (tenant_id, entry_date, event_date)
  WHERE entry_date IS NOT NULL AND entry_date > event_date;
CREATE UNIQUE INDEX ux_gl_row_hash_current ON __SCHEMA__.fact_gl_entry (tenant_id, row_hash) WHERE is_current;

COMMENT ON TABLE __SCHEMA__.fact_gl_entry IS
  'Grain: one journal line. Dr positive, Cr negative in amount_base. Sum of amount_base over any complete period equals zero. The trial balance check, tolerance zero per D-051.';

REVOKE ALL ON __SCHEMA__.fact_gl_entry FROM model_reachable;
GRANT SELECT ON __SCHEMA__.fact_gl_entry TO model_reachable;
