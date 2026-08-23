-- reconciliation_run is in corpus/04's table inventory ("Result of each
-- reconciliation check per period", P0) but was not given literal DDL.
-- Constructed to satisfy corpus/09's own acceptance criterion (section 8):
-- "Every reconciliation result records the modelled differences and the
-- residual separately" -- modelled_differences is a JSONB array rather than
-- a single number specifically so nothing gets collapsed into one figure,
-- per corpus/09 section 3.2's "three sources, one honest answer."

CREATE TABLE __SCHEMA__.reconciliation_run (
    reconciliation_run_id  bigserial   PRIMARY KEY,
    tenant_id               uuid        NOT NULL,
    entity_id                 int         NOT NULL,
    period_key                 text        NOT NULL,
    check_type                  text        NOT NULL,   -- 'trial_balance' | 'books_to_bank'
    status                        text        NOT NULL,   -- 'reconciled' | 'unreconciled' | 'blocked'
    books_amount_inr               numeric(18,2),
    bank_amount_inr                  numeric(18,2),          -- null for trial_balance
    modelled_differences               jsonb       NOT NULL DEFAULT '[]',
                                                    -- [{category, amount_inr, description}], corpus/09 section 3.2:
                                                    -- credit period, advances, TDS, marketplace/gateway lag,
                                                    -- unpresented instruments, inter-account transfers, unbooked bank charges
    residual_inr                        numeric(18,2) NOT NULL,
    tolerance_pct                        numeric(6,4),          -- D-052, deliberately unset until observed per company
    run_at                                timestamptz NOT NULL DEFAULT now(),
    run_by                                 text        NOT NULL,
    load_run_id                             bigint,
    mapping_version_id                        int         REFERENCES __SCHEMA__.mapping_version(mapping_version_id)
);
CREATE INDEX ix_reconciliation_period ON __SCHEMA__.reconciliation_run (tenant_id, entity_id, period_key, check_type, run_at DESC);

COMMENT ON TABLE __SCHEMA__.reconciliation_run IS
  'Grain: one reconciliation check, one period, one run. Trial balance tolerance is zero (D-051, settled). Books-to-bank tolerance_pct stays null until D-052 is set per company from observation -- a null tolerance means status is never silently reconciled, per CLAUDE.md section 3.2.';

REVOKE ALL ON __SCHEMA__.reconciliation_run FROM model_reachable;
