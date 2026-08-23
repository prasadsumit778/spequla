-- Shared app schema. Implements corpus/04 section 6 (tenancy) and corpus/12
-- sprint 0 item 2 ("Postgres provisioned with the schema-per-tenant pattern
-- and one test tenant").
--
-- This table is what db/migrations/runner.py loops over to apply tenant/
-- migrations to each tenant's own schema. It is not a fact or dimension
-- table and carries no financial data.

CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE app.tenant (
    tenant_id     uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    name          text        NOT NULL,
    schema_name   text        NOT NULL UNIQUE,   -- 'tenant_<uuid>' per corpus/04 section 6
    is_synthetic  boolean     NOT NULL DEFAULT false,
    created_at    timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE app.tenant IS
  'Grain: one tenant. Registry the migration loop and provisioning scripts read. is_synthetic marks the two synthetic reference companies so they can never be mistaken for a real tenant.';

-- The four roles from corpus/02 section 2. Reference data only: auth itself
-- is bought (Clerk or WorkOS, per CLAUDE.md section 6) and never built here.
CREATE TABLE app.role (
    role_key      text        PRIMARY KEY,
    description   text        NOT NULL
);
INSERT INTO app.role (role_key, description) VALUES
    ('promoter',            'Owner, MD or CEO. Reads the pack, asks questions. No mapping screens, no exception queue.'),
    ('client_finance_lead', 'CFO, controller or CA. Answers accounting policy questions, reviews mappings, signs off statements.'),
    ('spequla_analyst',     'Runs onboarding, proposes and approves mappings, reconciles, assembles and reviews the pack.'),
    ('admin',               'Engineering. Tenancy, connectors, deploys. No default access to client data.');

-- The model-reachable database role, per corpus/04 section 6 and CLAUDE.md
-- invariant 6: "no grant on token_map, audit_log, or any app table." Grants
-- on canonical (tenant-schema) tables are added per-tenant in
-- db/migrations/tenant/, never here.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'model_reachable') THEN
        CREATE ROLE model_reachable NOLOGIN;
    END IF;
END $$;

REVOKE ALL ON SCHEMA app FROM model_reachable;
REVOKE ALL ON ALL TABLES IN SCHEMA app FROM model_reachable;
