-- Implements corpus/04 section 1.4 and corpus/02 section 8: token_map,
-- "token to real name. App schema only." CLAUDE.md invariant 6: the
-- model-reachable role has no grant on this table -- enforced below, and
-- exercised by tests/integration/test_token_map_role_denied.py.
--
-- Per D-058 (resolved): employees are excluded from model-reachable views
-- entirely, not tokenised -- so this table only ever holds customer and
-- vendor tokens.

CREATE TABLE app.token_map (
    token_map_id  bigserial   PRIMARY KEY,
    tenant_id     uuid        NOT NULL REFERENCES app.tenant(tenant_id),
    entity_type   text        NOT NULL,   -- 'customer' | 'vendor'. Never 'employee', per D-058.
    token         text        NOT NULL,   -- stable per tenant, e.g. 'VENDOR_0417', 'CUST_0912'
    real_name     text        NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_token_map_entity_type CHECK (entity_type IN ('customer', 'vendor')),
    UNIQUE (tenant_id, token)
);
COMMENT ON TABLE app.token_map IS
  'Grain: one token to real-name mapping. The model-reachable role has no grant here -- masking is a schema property, not a step anyone can forget, per corpus/02 section 8.';

ALTER TABLE app.token_map ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.token_map FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON app.token_map
  USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

REVOKE ALL ON app.token_map FROM model_reachable;
