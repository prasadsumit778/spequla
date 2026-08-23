-- Implements corpus/04 table inventory: dim_entity, "one legal entity or
-- business unit... Single row in pilot one. Present so multi-entity needs no
-- migration." Standard dimension columns per corpus/04 section 1.2.

CREATE TABLE __SCHEMA__.dim_entity (
    entity_key            serial      PRIMARY KEY,
    tenant_id             uuid        NOT NULL,
    entity_name           text        NOT NULL,
    fiscal_year_start_month smallint  NOT NULL DEFAULT 4,   -- April, per D-038 (resolved)
    valid_from             timestamptz NOT NULL DEFAULT now(),
    valid_to                timestamptz NOT NULL DEFAULT 'infinity',
    is_current              boolean     NOT NULL DEFAULT true,
    load_run_id             bigint      NOT NULL,
    source_record_id        text        NOT NULL
);
COMMENT ON TABLE __SCHEMA__.dim_entity IS
  'Grain: one legal entity. Single row in pilot one (single-entity assumption, corpus/02 section 11), present so multi-entity arrives without a migration.';

CREATE UNIQUE INDEX ux_dim_entity_current
  ON __SCHEMA__.dim_entity (tenant_id, source_record_id)
  WHERE is_current;

REVOKE ALL ON __SCHEMA__.dim_entity FROM model_reachable;
GRANT SELECT ON __SCHEMA__.dim_entity TO model_reachable;
