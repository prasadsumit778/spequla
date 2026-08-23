-- Verbatim from corpus/04_SPEQULA_CANONICAL_DATA_MODEL.md section 3.5.
-- Consumer profile only.
--
-- Sequencing decision, same pattern as fact_gl_entry's customer_key/
-- vendor_key/cost_centre_key in the sprint 0 plan: customer_key is nullable
-- in the literal DDL (dim_customer is not built -- deferred since sprint 1,
-- see UNAVAILABLE_DIMENSIONS in src/semantic/ask_compiler.py), so it is
-- created here as a plain nullable int WITHOUT the REFERENCES constraint.
-- channel_key and product_key are NOT NULL in the literal DDL and their
-- dimensions (dim_channel, dim_product) are built in this same migration
-- set, so those two FKs are enforced immediately. business_unit_key's
-- dimension (dim_business_unit) was already built in sprint 1.

CREATE TABLE __SCHEMA__.fact_channel_order_line (
    fact_id             bigserial   PRIMARY KEY,
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,

    order_id            text        NOT NULL,
    line_no             int         NOT NULL,
    event_date          date        NOT NULL,
    period_key          text        NOT NULL,

    channel_key         int         NOT NULL REFERENCES __SCHEMA__.dim_channel(channel_key),
    channel_sub         text,
    product_key         int         NOT NULL REFERENCES __SCHEMA__.dim_product(product_key),
    customer_key        int,                    -- dim_customer not yet built; nullable, unconstrained (see above)
    location_key        int         REFERENCES __SCHEMA__.dim_location(location_key),

    quantity            numeric(18,4) NOT NULL,
    gross_amount        numeric(18,2) NOT NULL,
    discount_amount     numeric(18,2) NOT NULL DEFAULT 0,
    net_amount          numeric(18,2) NOT NULL,
    shipping_charged    numeric(18,2) NOT NULL DEFAULT 0,
    commission_amount   numeric(18,2) NOT NULL DEFAULT 0,
    shipping_cost       numeric(18,2) NOT NULL DEFAULT 0,
    payment_fee         numeric(18,2) NOT NULL DEFAULT 0,

    business_unit_key   int         REFERENCES __SCHEMA__.dim_business_unit(bu_key),
    revenue_model       text        NOT NULL DEFAULT 'buyout',  -- 'marketplace' | 'buyout'. D-061
    order_type          text,                      -- 'acquisition' | 'retention'. Enables CAC analogue
    commission_earned   numeric(18,2) NOT NULL DEFAULT 0,  -- marketplace model only
    advertising_earned  numeric(18,2) NOT NULL DEFAULT 0,  -- marketplace model only
    platform_fee_earned numeric(18,2) NOT NULL DEFAULT 0,  -- marketplace model only

    is_returned         boolean     NOT NULL DEFAULT false,
    return_date         date,
    return_reason       text,
    settlement_date     date,                      -- P1. Reconciliation is deferred

    valid_from          timestamptz NOT NULL DEFAULT now(),
    valid_to            timestamptz NOT NULL DEFAULT 'infinity',
    is_current          boolean     NOT NULL DEFAULT true,
    load_run_id         bigint      NOT NULL,
    source_system       text        NOT NULL,
    source_record_id    text        NOT NULL,
    row_hash            bytea       NOT NULL,
    mapping_version_id  int         NOT NULL
);
COMMENT ON TABLE __SCHEMA__.fact_channel_order_line IS
  'Grain: one order line. revenue_model determines how revenue derives: marketplace uses the *_earned columns, buyout uses net_amount. Never sum GMV across models and call it revenue. Returns per D-047. settlement_date populated where available but no settlement reconciliation runs in P0.';

CREATE INDEX ix_channel_order_line_period ON __SCHEMA__.fact_channel_order_line (tenant_id, entity_id, period_key) WHERE is_current;
CREATE UNIQUE INDEX ux_channel_order_line_current
  ON __SCHEMA__.fact_channel_order_line (tenant_id, entity_id, source_record_id)
  WHERE is_current;

REVOKE ALL ON __SCHEMA__.fact_channel_order_line FROM model_reachable;
GRANT SELECT ON __SCHEMA__.fact_channel_order_line TO model_reachable;
