-- dim_location is in corpus/04 table inventory ("one plant, warehouse or
-- store") but was not given literal DDL. Constructed per standard
-- dimension columns (corpus/04 section 1.2/1.3).

CREATE TABLE __SCHEMA__.dim_location (
    location_key      serial      PRIMARY KEY,
    tenant_id         uuid        NOT NULL,
    entity_id         int         NOT NULL,
    location_name     text        NOT NULL,
    location_type     text,       -- 'plant' | 'warehouse' | 'store', undeclared where the source doesn't say
    valid_from        timestamptz NOT NULL DEFAULT now(),
    valid_to          timestamptz NOT NULL DEFAULT 'infinity',
    is_current        boolean     NOT NULL DEFAULT true,
    load_run_id       bigint      NOT NULL,
    source_record_id  text        NOT NULL
);
COMMENT ON TABLE __SCHEMA__.dim_location IS
  'Grain: one plant, warehouse or store.';

CREATE UNIQUE INDEX ux_dim_location_current
  ON __SCHEMA__.dim_location (tenant_id, entity_id, source_record_id)
  WHERE is_current;

REVOKE ALL ON __SCHEMA__.dim_location FROM model_reachable;
GRANT SELECT ON __SCHEMA__.dim_location TO model_reachable;
