-- dim_product is in corpus/04 table inventory ("one SKU or item, one
-- version... includes raw materials and finished goods") but was not given
-- literal DDL. Constructed per standard dimension columns (corpus/04
-- section 1.2/1.3). Not tokenised -- corpus/04 section 1.4 names only
-- dim_customer, dim_vendor and employee references for tokenisation;
-- product/item names are not party names.

CREATE TABLE __SCHEMA__.dim_product (
    product_key       serial      PRIMARY KEY,
    tenant_id         uuid        NOT NULL,
    entity_id         int         NOT NULL,
    source_item_code  text,
    source_item_name  text        NOT NULL,
    category          text,
    declared_uom      text,       -- D-041: the single declared unit for this product family; NULL until declared
    valid_from        timestamptz NOT NULL DEFAULT now(),
    valid_to          timestamptz NOT NULL DEFAULT 'infinity',
    is_current        boolean     NOT NULL DEFAULT true,
    load_run_id       bigint      NOT NULL,
    source_record_id  text        NOT NULL
);
COMMENT ON TABLE __SCHEMA__.dim_product IS
  'Grain: one SKU or item, one version. Shared by fact_channel_order_line (consumer) and fact_production_output (manufacturing).';

CREATE UNIQUE INDEX ux_dim_product_current
  ON __SCHEMA__.dim_product (tenant_id, entity_id, source_record_id)
  WHERE is_current;

REVOKE ALL ON __SCHEMA__.dim_product FROM model_reachable;
GRANT SELECT ON __SCHEMA__.dim_product TO model_reachable;
