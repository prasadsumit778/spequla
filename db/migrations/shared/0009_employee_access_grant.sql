-- Sprint 7, corpus/02 section 7: "Employee-level access to client data is
-- time-bound, named and logged." Not in corpus/04's table inventory (that
-- file predates sprint 7) -- constructed the same way query_log,
-- reconciliation_run and report_artefact were: no literal DDL to
-- transcribe, so built from the corpus's own words. expires_at is NOT
-- NULL deliberately -- "time-bound" is not optional metadata here, it is
-- the whole point of the table; there is no such thing as a standing grant.

CREATE TABLE app.employee_access_grant (
    grant_id            bigserial   PRIMARY KEY,
    tenant_id            uuid        NOT NULL REFERENCES app.tenant(tenant_id),
    employee_user_id      text        NOT NULL,   -- the WorkOS session user_id, same identity used everywhere else as an approver
    employee_name           text        NOT NULL,   -- 'named': a human-readable name, not just an id
    granted_by                text        NOT NULL,
    reason                       text        NOT NULL,
    granted_at                    timestamptz NOT NULL DEFAULT now(),
    expires_at                      timestamptz NOT NULL,
    revoked_at                        timestamptz,
    revoked_by                          text
);
CREATE INDEX ix_employee_access_grant_active ON app.employee_access_grant (tenant_id, employee_user_id, expires_at)
  WHERE revoked_at IS NULL;

COMMENT ON TABLE app.employee_access_grant IS
  'Grain: one grant of one employee''s access to one tenant''s client data, always time-bound. src/access/grants.py is the only writer. Every actual access under a grant is separately logged to app.audit_log, not inferred from the grant''s existence.';

ALTER TABLE app.employee_access_grant ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.employee_access_grant FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.employee_access_grant
  USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

REVOKE ALL ON app.employee_access_grant FROM model_reachable;
