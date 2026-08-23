-- Maps a WorkOS Organization to a SPEQULA tenant, replacing the stub
-- header-based tenant resolution from sprint 1 with the real auth provider,
-- per CLAUDE.md section 6 ("Bought auth (Clerk or WorkOS). Never build
-- auth.") and the auth-provider decision made in chat.
--
-- One tenant maps to exactly one WorkOS Organization. There is no natural
-- corpus section for this table (it is app/infra config, not a financial
-- concept), so it is documented here instead: an org with no linked tenant
-- can authenticate against WorkOS but has nothing to read or write, since
-- every other app-schema table and every request handler resolves the
-- tenant via this column, never via a client-supplied header.

ALTER TABLE app.tenant
    ADD COLUMN workos_organization_id text UNIQUE;

COMMENT ON COLUMN app.tenant.workos_organization_id IS
  'WorkOS Organization id (org_...). Set once per tenant via scripts/link_tenant_workos_org.py after creating the Organization in the WorkOS dashboard. Requests resolve tenant_id from this column via the verified session''s org_id claim, never from a client-supplied header.';
