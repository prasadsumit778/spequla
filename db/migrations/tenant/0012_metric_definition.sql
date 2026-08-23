-- metric_definition is in corpus/04's table inventory ("The metric
-- contract, versioned", P0) but was not given literal DDL. Constructed to
-- hold the per-company/per-entity OVERRIDE layer of corpus/05a's resolution
-- chain (entity_override -> company_override -> industry_pack [not in P0]
-- -> global_default): the global_default layer itself is config/metrics/
-- (generated from corpus/05 + 05a, corpus-authored, never edited per
-- company); this table holds what a specific tenant declared instead, e.g.
-- DSO's ar_basis or which declared_deductions are switched on, versioned and
-- effective-dated the same way mapping_version is (corpus/06 section 6),
-- since a metric definition change is "a versioned event with an owner, an
-- effective date and a human approval" per corpus/05a's _change_control block.

CREATE TABLE __SCHEMA__.metric_definition (
    metric_definition_id  bigserial   PRIMARY KEY,
    tenant_id               uuid        NOT NULL,
    entity_id                 int,          -- null = company-level override, set = entity-level (rare in P0 single-entity pilots)
    metric_id                   text        NOT NULL,
    version_no                    int         NOT NULL,
    status                          text        NOT NULL,   -- 'draft' | 'approved' | 'superseded'
    parameters                       jsonb       NOT NULL,   -- overridden parameter values only, e.g. {"ar_basis": "average_of_opening_and_closing"}
    effective_from                     date        NOT NULL,
    effective_to                        date        NOT NULL DEFAULT '9999-12-31',
    created_by                            text        NOT NULL,
    approved_by                            text,
    approved_at                              timestamptz,
    change_reason                              text,
    UNIQUE (tenant_id, metric_id, entity_id, version_no)
);
CREATE INDEX ix_metric_definition_lookup ON __SCHEMA__.metric_definition (tenant_id, metric_id, entity_id, status, effective_from);

COMMENT ON TABLE __SCHEMA__.metric_definition IS
  'Per-tenant override layer for metric parameters. Empty for a company that has declared no overrides -- the compiler falls through to config/metrics/ (the global default) for every parameter with no row here, per corpus/05a _resolution_order.';

REVOKE ALL ON __SCHEMA__.metric_definition FROM model_reachable;
