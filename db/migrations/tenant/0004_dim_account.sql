-- Verbatim from corpus/04_SPEQULA_CANONICAL_DATA_MODEL.md section 3.2.

CREATE TABLE __SCHEMA__.dim_account (
    account_key         serial      PRIMARY KEY,
    tenant_id           uuid        NOT NULL,
    entity_id           int         NOT NULL,
    source_account_code text,
    source_account_name text        NOT NULL,   -- verbatim from the books, never cleaned
    source_parent_group text,
    canonical_class     text,                   -- e.g. 'revenue.product_sales'
    statement_section   text,                   -- 'pnl' | 'bs' | 'memo'
    statement_line      text,                   -- 'net_revenue' | 'cogs.material' | 'ar'
    normal_balance      char(2),                -- 'Dr' | 'Cr'
    is_mapped            boolean     NOT NULL DEFAULT false,
    mapping_version_id  int,
    mapping_confidence  numeric(4,3),
    mapping_source      text,                   -- 'exact_rule' | 'ai_proposed' | 'human'
    approved_by         text,
    approved_at         timestamptz,
    valid_from          timestamptz NOT NULL DEFAULT now(),
    valid_to            timestamptz NOT NULL DEFAULT 'infinity',
    is_current          boolean     NOT NULL DEFAULT true,
    load_run_id         bigint      NOT NULL,
    source_record_id    text        NOT NULL
);

CREATE UNIQUE INDEX ux_dim_account_current
  ON __SCHEMA__.dim_account (tenant_id, entity_id, source_record_id)
  WHERE is_current;
COMMENT ON TABLE __SCHEMA__.dim_account IS
  'Grain: one GL account, one version. source_account_name is stored verbatim. Cleaning it destroys the only evidence of what the accountant meant. is_mapped stays false throughout sprint 1 -- mapping is sprint 2 scope.';

REVOKE ALL ON __SCHEMA__.dim_account FROM model_reachable;
GRANT SELECT ON __SCHEMA__.dim_account TO model_reachable;
