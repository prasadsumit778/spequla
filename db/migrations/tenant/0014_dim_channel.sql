-- dim_channel is in corpus/04 table inventory ("one sales channel...
-- consumer pilots. Single default row for manufacturing") but was not given
-- literal DDL. Constructed per standard dimension columns (corpus/04
-- section 1.2/1.3). channel_type is the fixed, D-046-resolved (corpus/00)
-- seven-value taxonomy: "own website; marketplace (per marketplace); quick
-- commerce (per platform); owned retail (per store); franchise retail;
-- distributor; exports." The specific platform/store name (which
-- marketplace, which store) is fact_channel_order_line.channel_sub, free
-- text -- dim_channel itself holds only the seven canonical types, seeded
-- once per tenant by scripts/seed_dim_channel.py.

CREATE TABLE __SCHEMA__.dim_channel (
    channel_key       serial      PRIMARY KEY,
    tenant_id         uuid        NOT NULL,
    entity_id         int         NOT NULL,
    channel_type      text        NOT NULL,   -- D-046's seven canonical values
    channel_name      text        NOT NULL,   -- display label
    valid_from        timestamptz NOT NULL DEFAULT now(),
    valid_to          timestamptz NOT NULL DEFAULT 'infinity',
    is_current        boolean     NOT NULL DEFAULT true,
    load_run_id       bigint      NOT NULL,
    source_record_id  text        NOT NULL
);
COMMENT ON TABLE __SCHEMA__.dim_channel IS
  'Grain: one sales channel (D-046''s seven canonical types). Single default row seeded for manufacturing; the full seven seeded for consumer.';

CREATE UNIQUE INDEX ux_dim_channel_current
  ON __SCHEMA__.dim_channel (tenant_id, entity_id, source_record_id)
  WHERE is_current;

REVOKE ALL ON __SCHEMA__.dim_channel FROM model_reachable;
GRANT SELECT ON __SCHEMA__.dim_channel TO model_reachable;
