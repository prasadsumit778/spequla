-- Verbatim from corpus/04_SPEQULA_CANONICAL_DATA_MODEL.md section 3.9.

CREATE TABLE __SCHEMA__.exception (
    exception_id        bigserial   PRIMARY KEY,
    tenant_id            uuid        NOT NULL,
    entity_id             int         NOT NULL,
    raised_at              timestamptz NOT NULL DEFAULT now(),
    exception_class        text        NOT NULL,   -- 'unmapped' | 'completeness' | 'validity'
                                                    -- | 'uniqueness' | 'consistency'
                                                    -- | 'reconciliation' | 'continuity' | 'anomaly'
    severity                text        NOT NULL,   -- 'blocking' | 'warning' | 'informational'
    period_key              text,
    object_type              text,                   -- 'account' | 'invoice' | 'bank_txn' | 'period'
    object_ref                text,
    value_inr                 numeric(18,2),          -- rupee exposure. Drives queue ordering
    description                text        NOT NULL,
    suggested_action            text,
    status                       text        NOT NULL DEFAULT 'open',
    resolved_by                  text,
    resolved_at                   timestamptz,
    resolution_note                text,
    load_run_id                    bigint
);
CREATE INDEX ix_exception_queue ON __SCHEMA__.exception (tenant_id, status, severity, value_inr DESC);

COMMENT ON TABLE __SCHEMA__.exception IS
  'Blocking severity prevents statement assembly and pack generation, not just a badge. Ordered by severity then value_inr descending -- always by money, never by count, per corpus/09 section 4.';

REVOKE ALL ON __SCHEMA__.exception FROM model_reachable;
