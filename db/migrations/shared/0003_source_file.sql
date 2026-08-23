-- Implements corpus/04 table inventory: source_file, "one received file, with
-- its hash and its landing path." Backs corpus/12 sprint 1 backend: "content
-- hashing and immutable raw landing" and the schema-hash blocking check in
-- corpus/09 section 2.6.

CREATE TABLE app.source_file (
    source_file_id  bigserial   PRIMARY KEY,
    tenant_id       uuid        NOT NULL REFERENCES app.tenant(tenant_id),
    entity_id       int         NOT NULL,
    load_run_id     bigint      NOT NULL REFERENCES app.load_run(load_run_id),
    file_name       text        NOT NULL,
    template_type   text        NOT NULL,   -- tab name from corpus/01, e.g. 'GL', 'TB', 'COA'
    content_hash    bytea       NOT NULL,   -- drives the idempotency check, corpus/09 section 2.3
    schema_hash     bytea       NOT NULL,   -- hash of the column header row; a change here blocks, corpus/09 section 2.6
    storage_path    text        NOT NULL,   -- tenant-id-prefixed object storage path, corpus/04 section 6
    row_count       int,
    received_at     timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE app.source_file IS
  'Grain: one received file. Raw bytes retained immutably at storage_path. content_hash catches a re-upload; schema_hash catches a column change, corpus/09 section 2.6.';

CREATE INDEX ix_source_file_content_hash ON app.source_file (tenant_id, content_hash);

ALTER TABLE app.source_file ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.source_file FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.source_file
  USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

REVOKE ALL ON app.source_file FROM model_reachable;
