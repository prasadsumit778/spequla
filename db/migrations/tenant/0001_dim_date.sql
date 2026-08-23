-- Verbatim from corpus/04_SPEQULA_CANONICAL_DATA_MODEL.md section 3.1.
-- Per-tenant schema (schema-per-tenant, corpus/04 section 6). No tenant_id or
-- bitemporal columns -- the literal DDL in the corpus omits them, since this
-- is deterministic calendar reference data, not sourced from any customer
-- file, despite section 1.2's blanket "every dimension table" rule. Following
-- the specific DDL over the general prose rule here.

CREATE TABLE __SCHEMA__.dim_date (
    date_key            date        PRIMARY KEY,
    day_of_month        smallint    NOT NULL,
    month_num           smallint    NOT NULL,
    month_name          text        NOT NULL,
    calendar_year       smallint    NOT NULL,
    calendar_quarter    smallint    NOT NULL,
    fiscal_year         smallint    NOT NULL,   -- FY2027 = Apr 2026 to Mar 2027
    fiscal_year_label   text        NOT NULL,   -- 'FY27'
    fiscal_quarter      smallint    NOT NULL,   -- Q1 = Apr, May, Jun
    fiscal_month_num    smallint    NOT NULL,   -- April = 1
    period_key          text        NOT NULL,   -- '2026-04'
    is_month_end        boolean     NOT NULL,
    is_quarter_end      boolean     NOT NULL,
    is_fiscal_year_end  boolean     NOT NULL,
    days_in_month       smallint    NOT NULL
);
COMMENT ON TABLE __SCHEMA__.dim_date IS
  'Grain: one calendar day. Owns the fiscal calendar. FY start month resolved by D-038 to April.';

REVOKE ALL ON __SCHEMA__.dim_date FROM model_reachable;
GRANT SELECT ON __SCHEMA__.dim_date TO model_reachable;
