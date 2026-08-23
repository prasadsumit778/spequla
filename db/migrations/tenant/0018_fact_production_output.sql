-- Verbatim from corpus/04_SPEQULA_CANONICAL_DATA_MODEL.md section 3.6.
-- Manufacturing profile only.
--
-- "A check constraint enforces one uom per product_key within a tenant. A
-- second unit arriving for the same product raises an exception rather
-- than being converted, because SPEQULA has no authority to convert tonnes
-- to pieces." Postgres cannot express "every row for this product_key
-- shares one uom" as a single-row CHECK constraint (it is a cross-row
-- invariant), so this is enforced at the application layer instead:
-- src/ingest/canonical.py's write_production_output_rows stamps
-- dim_product.declared_uom from the first row seen for a product and never
-- changes it; src/quality/checks.py's check_mixed_uom (D-041) raises a
-- BLOCKING exception, not a silent conversion, the moment a later row's uom
-- disagrees -- exactly "raises an exception rather than being converted."

CREATE TABLE __SCHEMA__.fact_production_output (
    fact_id             bigserial   PRIMARY KEY,
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,

    event_date          date        NOT NULL,
    period_key          text        NOT NULL,
    location_key        int         NOT NULL REFERENCES __SCHEMA__.dim_location(location_key),
    line_code           text,
    product_key         int         NOT NULL REFERENCES __SCHEMA__.dim_product(product_key),

    qty_produced        numeric(18,4) NOT NULL,
    qty_rejected        numeric(18,4) NOT NULL DEFAULT 0,
    uom                 text        NOT NULL,
    input_qty           numeric(18,4),
    input_uom           text,
    input_product_key   int         REFERENCES __SCHEMA__.dim_product(product_key),

    available_hours     numeric(10,2),
    running_hours       numeric(10,2),
    power_units         numeric(14,2),

    valid_from          timestamptz NOT NULL DEFAULT now(),
    valid_to            timestamptz NOT NULL DEFAULT 'infinity',
    is_current          boolean     NOT NULL DEFAULT true,
    load_run_id         bigint      NOT NULL,
    source_system       text        NOT NULL,
    source_record_id    text        NOT NULL,
    row_hash            bytea       NOT NULL,
    mapping_version_id  int         NOT NULL
);
COMMENT ON TABLE __SCHEMA__.fact_production_output IS
  'Grain: one product, one line, one production period. uom must be consistent per product per DECISION-REQUIRED[D-041]; mixed units block per-unit metrics rather than averaging them.';

CREATE INDEX ix_production_output_period ON __SCHEMA__.fact_production_output (tenant_id, entity_id, period_key) WHERE is_current;
CREATE UNIQUE INDEX ux_production_output_current
  ON __SCHEMA__.fact_production_output (tenant_id, entity_id, source_record_id)
  WHERE is_current;

REVOKE ALL ON __SCHEMA__.fact_production_output FROM model_reachable;
GRANT SELECT ON __SCHEMA__.fact_production_output TO model_reachable;
