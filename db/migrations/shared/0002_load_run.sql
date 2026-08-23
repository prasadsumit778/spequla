-- Implements corpus/04 table inventory: load_run, "one ingestion execution."
-- Shared app schema, RLS forced at the connection role per corpus/04 section 6.

CREATE TABLE app.load_run (
    load_run_id   bigserial   PRIMARY KEY,
    tenant_id     uuid        NOT NULL REFERENCES app.tenant(tenant_id),
    entity_id     int         NOT NULL,
    source_system text        NOT NULL,   -- 'tally' | 'sap_b1' | 'zoho' | 'excel_upload' | 'bank_file', per corpus/04 section 1.2
    status        text        NOT NULL DEFAULT 'running',   -- 'running' | 'succeeded' | 'failed'
    triggered_by  text        NOT NULL,
    started_at    timestamptz NOT NULL DEFAULT now(),
    completed_at  timestamptz,
    notes         text
);
COMMENT ON TABLE app.load_run IS
  'Grain: one ingestion execution. Every canonical fact row carries this id as load_run_id, per corpus/04 section 1.2, so a load is always attributable.';

ALTER TABLE app.load_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.load_run FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.load_run
  USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

REVOKE ALL ON app.load_run FROM model_reachable;
