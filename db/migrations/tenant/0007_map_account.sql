-- Verbatim from corpus/04_SPEQULA_CANONICAL_DATA_MODEL.md section 3.7.
-- mapping_version already exists (db/migrations/tenant/0005_mapping_version.sql,
-- seeded with a version-0 system placeholder in sprint 0). This adds the
-- table that actually holds a mapping's content: one row per source account
-- per version.

CREATE TABLE __SCHEMA__.map_account (
    map_id              bigserial   PRIMARY KEY,
    mapping_version_id  int         NOT NULL REFERENCES __SCHEMA__.mapping_version(mapping_version_id),
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
COMMENT ON TABLE __SCHEMA__.map_account IS
  'Grain: one source account, one mapping version. period_value_inr exists so the review queue sorts by money rather than by count.';

CREATE INDEX ix_map_account_queue ON __SCHEMA__.map_account (mapping_version_id, period_value_inr DESC);

REVOKE ALL ON __SCHEMA__.map_account FROM model_reachable;
