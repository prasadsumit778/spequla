-- Implements corpus/04 table inventory: dim_business_unit, "one business
-- line... Optional in use, present in schema. D-063." Built now per your
-- explicit Sprint 1 database list even though nothing references it until
-- Sprint 6's consumer profile (corpus/03 section 7.5, D-063 resolved:
-- optional, default consumer segmentation is product and channel).

CREATE TABLE __SCHEMA__.dim_business_unit (
    bu_key         serial      PRIMARY KEY,
    tenant_id      uuid        NOT NULL,
    entity_id      int         NOT NULL,
    bu_name        text        NOT NULL,
    valid_from     timestamptz NOT NULL DEFAULT now(),
    valid_to       timestamptz NOT NULL DEFAULT 'infinity',
    is_current     boolean     NOT NULL DEFAULT true,
    load_run_id    bigint      NOT NULL,
    source_record_id text      NOT NULL
);
COMMENT ON TABLE __SCHEMA__.dim_business_unit IS
  'Grain: one business line. Optional per D-063 -- most consumer companies segment by product and channel instead. Unused in the manufacturing pilot.';

CREATE UNIQUE INDEX ux_dim_business_unit_current
  ON __SCHEMA__.dim_business_unit (tenant_id, entity_id, source_record_id)
  WHERE is_current;

REVOKE ALL ON __SCHEMA__.dim_business_unit FROM model_reachable;
GRANT SELECT ON __SCHEMA__.dim_business_unit TO model_reachable;
