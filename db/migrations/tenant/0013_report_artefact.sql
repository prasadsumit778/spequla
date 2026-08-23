-- report_artefact is in corpus/04's table inventory ("Generated report/pack,
-- versioned", P0 per corpus/08 section 2's Reports screen) but was not given
-- literal DDL. Constructed to satisfy corpus/08 section 7 (the eight pack
-- sections), section 9 (provenance: snapshot id, metric versions, mapping
-- version, freshness, reconciliation status, reviewer) and section 10
-- (mandatory sign-off, blocking-exception gate with logged override).
--
-- One row = one immutable generation. `sections` stores the FULLY COMPUTED
-- content of all eight P0 sections at generation time -- not a pointer back
-- to live tables -- because corpus/08 section 9's acceptance test is
-- "re-rendering a March pack in September reproduces the March pack,
-- including numbers that have since been restated." Re-rendering later must
-- read this stored snapshot, never recompute from fact_gl_entry, or a
-- restatement between generation and re-render would silently change a
-- document someone already signed and sent. Editable only while
-- status = 'draft' (src/reports/signoff.py enforces this; there is no DB
-- constraint against it, same posture as period_lock's status machine).

CREATE TABLE __SCHEMA__.report_artefact (
    report_artefact_id       bigserial   PRIMARY KEY,
    tenant_id                  uuid        NOT NULL,
    entity_id                    int         NOT NULL,
    period_key                     text        NOT NULL,
    profile                          text        NOT NULL,   -- 'manufacturing' | 'consumer'
    generated_at                      timestamptz NOT NULL DEFAULT now(),  -- the knowledge-time cut, corpus/08 section 9
    generated_by                        text        NOT NULL,
    mapping_version_id                    int         NOT NULL REFERENCES __SCHEMA__.mapping_version(mapping_version_id),
    metric_versions                         jsonb       NOT NULL DEFAULT '{}',  -- {metric_id: version_no}
    freshness_snapshot                        jsonb       NOT NULL DEFAULT '[]',  -- corpus/09 section 2.8, frozen at generation
    reconciliation_snapshot                     jsonb       NOT NULL DEFAULT '[]',  -- reconciliation_run rows, frozen
    sections                                      jsonb       NOT NULL,             -- the eight P0 sections, corpus/08 section 7
    chart_specs                                     jsonb       NOT NULL DEFAULT '[]',  -- corpus/08 section 8: spec, never a picture
    commentary                                        text,                              -- section 2, human-written (corpus/08 section 7)
    unmapped_value_inr                                  numeric(18,2),
    content_hash                                          text        NOT NULL,             -- sha256 of the canonical JSON, proves byte-identical re-render
    status                                                  text        NOT NULL DEFAULT 'draft',  -- 'draft' | 'signed'
    reviewer                                                  text,                              -- named at sign time, corpus/08 section 10
    signed_at                                                   timestamptz,
    blocking_exception_override_reason                            text,                     -- corpus/08 section 10: "override with a written reason, logged"
    blocking_exception_override_by                                  text,
    blocking_exception_override_at                                    timestamptz
);
CREATE INDEX ix_report_artefact_period ON __SCHEMA__.report_artefact (tenant_id, entity_id, period_key, generated_at DESC);

COMMENT ON TABLE __SCHEMA__.report_artefact IS
  'Grain: one pack generation. Immutable once status=signed. Re-rendering reads sections/chart_specs/commentary from THIS row, never recomputes, per corpus/08 section 9.';

REVOKE ALL ON __SCHEMA__.report_artefact FROM model_reachable;
