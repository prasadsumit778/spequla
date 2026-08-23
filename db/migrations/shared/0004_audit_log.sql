-- Implements corpus/04 table inventory: audit_log, "access, exports, mapping
-- changes, metric changes, approvals." CLAUDE.md invariant 6: the
-- model-reachable role has no grant on this table.

CREATE TABLE app.audit_log (
    audit_id      bigserial   PRIMARY KEY,
    tenant_id     uuid        NOT NULL REFERENCES app.tenant(tenant_id),
    actor         text        NOT NULL,   -- named person or 'system'
    role_key      text        REFERENCES app.role(role_key),
    action        text        NOT NULL,   -- e.g. 'file_upload', 'mapping_approve', 'export'
    object_type   text,
    object_ref    text,
    detail        jsonb,
    occurred_at   timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE app.audit_log IS
  'Grain: one audited action. Corpus/00 section 3 requires the audit trail to record that the SPEQULA analyst is not independent finance review for pilot one -- that fact is logged here, not inferred.';

ALTER TABLE app.audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.audit_log FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.audit_log
  USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

REVOKE ALL ON app.audit_log FROM model_reachable;
