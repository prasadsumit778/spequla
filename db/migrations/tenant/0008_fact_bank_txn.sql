-- fact_bank_txn is in corpus/04's table inventory ("One bank statement
-- line", P0) but was not one of the tables given full "Core DDL" in
-- corpus/04 section 3 -- unlike fact_gl_entry/fact_invoice_line/etc, no
-- literal column list is stated. Constructed here from corpus/04 section 1.2
-- ("every fact table carries these, without exception") plus corpus/01's
-- Bank field specification (bank_account_ref, txn_date, value_date,
-- description, reference, debit, credit, running_balance) -- not a source
-- field this build invented, transcribed from the corpus/01 workbook.
--
-- Grain: one bank statement line, per corpus/04's table inventory entry.

CREATE TABLE __SCHEMA__.fact_bank_txn (
    fact_id             bigserial   PRIMARY KEY,
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,

    bank_account_ref    text        NOT NULL,
    event_date          date        NOT NULL REFERENCES __SCHEMA__.dim_date(date_key),  -- txn_date
    value_date          date,
    entry_date          date,
    period_key          text        NOT NULL,

    description          text        NOT NULL,   -- verbatim, per the same never-clean discipline as dim_account
    reference             text,
    amount_base           numeric(18,2) NOT NULL,  -- money in positive, money out negative (mirrors Dr/Cr convention: credit=in=positive here, since bank txns have no natural Dr/Cr side of their own)
    running_balance_reported numeric(18,2),          -- as printed on the statement, used to detect missing rows per corpus/09 section 2.1's completeness intent

    valid_from            timestamptz NOT NULL DEFAULT now(),
    valid_to               timestamptz NOT NULL DEFAULT 'infinity',
    is_current              boolean     NOT NULL DEFAULT true,
    load_run_id             bigint      NOT NULL,
    source_system           text        NOT NULL,
    source_record_id        text        NOT NULL,
    row_hash                 bytea       NOT NULL,
    mapping_version_id       int         NOT NULL REFERENCES __SCHEMA__.mapping_version(mapping_version_id)
);

CREATE INDEX ix_bank_period ON __SCHEMA__.fact_bank_txn (tenant_id, period_key) WHERE is_current;
CREATE UNIQUE INDEX ux_bank_row_hash_current ON __SCHEMA__.fact_bank_txn (tenant_id, bank_account_ref, row_hash) WHERE is_current;

COMMENT ON TABLE __SCHEMA__.fact_bank_txn IS
  'Grain: one bank statement line. amount_base positive for money in, negative for money out -- bank lines have no natural Dr/Cr side the way GL lines do, so this is the sign convention chosen for this table specifically, documented here since corpus/04 does not give one.';

REVOKE ALL ON __SCHEMA__.fact_bank_txn FROM model_reachable;
GRANT SELECT ON __SCHEMA__.fact_bank_txn TO model_reachable;
