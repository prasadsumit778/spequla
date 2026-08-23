-- query_log is in corpus/04's table inventory ("Every query executed, with
-- IR, SQL, rows, duration, model version", P0, grouped with the other
-- operational tables) but was not given literal DDL. Constructed to satisfy
-- corpus/07 section 7's own requirement: "Every query is logged to
-- query_log with the user, role, IR, SQL text, row count, duration and
-- model version" -- including rejected admission-control attempts, per
-- section 7's "Every rejection is logged with the user, the IR and the
-- reason." Shared app-schema table, RLS forced, same pattern as
-- load_run/source_file/audit_log -- this is operational data, not an
-- analytical fact.

CREATE TABLE app.query_log (
    query_log_id     bigserial   PRIMARY KEY,
    tenant_id         uuid        NOT NULL REFERENCES app.tenant(tenant_id),
    entity_id           int,
    requested_at          timestamptz NOT NULL DEFAULT now(),
    user_id                 text        NOT NULL,
    role                      text        NOT NULL,
    question                   text,                    -- the natural-language question, where one exists
    intent                       text        NOT NULL,
    ir                             jsonb       NOT NULL,
    sql_text                        text,                -- null when admission control rejected before compilation produced SQL
    admitted                          boolean     NOT NULL,
    rejection_gate                       text,           -- which of the seven gates rejected it, null if admitted
    rejection_reason                       text,
    row_count                                 int,
    duration_ms                                 int,
    model_version                                 text,   -- which model (and version) produced the IR, null for stub/deterministic-only paths
    query_hash                                     text
);
CREATE INDEX ix_query_log_tenant ON app.query_log (tenant_id, requested_at DESC);

ALTER TABLE app.query_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.query_log FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.query_log
  USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

REVOKE ALL ON app.query_log FROM model_reachable;
