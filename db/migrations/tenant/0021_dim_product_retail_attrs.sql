-- Retail product attributes for dim_product, corpus/04 section 1.3 (added
-- 2026-08-24, forecast engine build). Same rationale as
-- 0020_dim_location_retail_attrs.sql: 0015_dim_product.sql's original DDL
-- (category, declared_uom) is enough for a manufacturer's raw-material/
-- finished-good item, not enough to cut apparel merchandise by price
-- positioning or occasion, which the product-mix side of the forecast
-- engine (corpus/13) needs. Forward-only ADD COLUMN.

ALTER TABLE __SCHEMA__.dim_product
    ADD COLUMN price_band     text,   -- bucketed MRP range, e.g. 'a.<1000' .. 'f.3001-4000+'; company's own banding, undeclared where the source doesn't say
    ADD COLUMN occasion_type  text;   -- 'casual' | 'evening' | 'occasion_fusion', apparel-specific; NULL for non-apparel product rows

COMMENT ON COLUMN __SCHEMA__.dim_product.price_band IS
  'Retail price positioning, apparel profile. Not a canonical enum -- bands are a company''s own merchandising convention, carried as declared text.';
