-- Retail store attributes for dim_location, corpus/04 section 1.3 (added
-- 2026-08-24, forecast engine build). dim_location's original DDL
-- (0016_dim_location.sql) only carried location_name/location_type -- enough
-- for a plant or warehouse, not enough to run store-cohort economics for a
-- retail chain. Forward-only ADD COLUMN, per CLAUDE.md invariant 4 --
-- 0016's table is never edited in place. All columns nullable: a
-- plant/warehouse row never populates them, and D-051-style zero-invention
-- discipline means a store row leaves any attribute the source doesn't
-- state as NULL rather than defaulted.

ALTER TABLE __SCHEMA__.dim_location
    ADD COLUMN store_format  text,        -- 'COCO' | 'COFO' | 'FOCO' | 'FOFO', retail-store rows only
    ADD COLUMN city          text,
    ADD COLUMN state         text,
    ADD COLUMN site_type     text,        -- 'mall' | 'high_street', retail-store rows only
    ADD COLUMN area_sqft     numeric(10,2),
    ADD COLUMN opening_date  date,        -- store vintage; cohort economics key off this
    ADD COLUMN closure_date  date,
    ADD COLUMN status        text;        -- 'active' | 'closed' | 'planned'

COMMENT ON COLUMN __SCHEMA__.dim_location.store_format IS
  'Company-owned vs franchise ownership, and who operates it -- corpus/04 section 1.3.';
COMMENT ON COLUMN __SCHEMA__.dim_location.opening_date IS
  'Store vintage. A store''s cohort (year opened) drives its expected sales curve in the forecast engine (corpus/13).';
