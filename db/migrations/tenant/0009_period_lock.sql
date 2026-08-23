-- Verbatim from corpus/04_SPEQULA_CANONICAL_DATA_MODEL.md section 3.8.

CREATE TABLE __SCHEMA__.period_lock (
    lock_id             serial      PRIMARY KEY,
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,
    period_key          text        NOT NULL,
    status              text        NOT NULL,   -- 'open' | 'reconciled' | 'locked' | 'restated'
    snapshot_at         timestamptz,            -- the knowledge-time cut this period is pinned to
    mapping_version_id  int         NOT NULL REFERENCES __SCHEMA__.mapping_version(mapping_version_id),
    locked_by           text,
    locked_at           timestamptz,
    restated_from       int         REFERENCES __SCHEMA__.period_lock(lock_id),
    restatement_reason  text,
    UNIQUE (tenant_id, entity_id, period_key, snapshot_at)
);
COMMENT ON TABLE __SCHEMA__.period_lock IS
  'Once locked, snapshot_at is the knowledge-time timestamp every report for that period queries against. A later change does not alter the row; it creates a new one with status=restated and restated_from pointing back, per corpus/09 section 5.';

REVOKE ALL ON __SCHEMA__.period_lock FROM model_reachable;
