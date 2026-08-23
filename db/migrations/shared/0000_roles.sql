-- Cluster roles. Applies before any migration that references them.
--
-- corpus/04 section 6 and CLAUDE.md invariant 6: model_reachable is the
-- model-facing database role, and every later shared migration REVOKEs or
-- GRANTs against it. Because this file runs first, it cannot assume the role
-- exists -- it must create it. An earlier version of this file granted
-- without creating, which succeeded only on a cluster where
-- 0001_tenant_registry.sql had already run under a previous numbering; on an
-- empty cluster it failed with 'role "model_reachable" does not exist'.
--
-- The guard mirrors 0001_tenant_registry.sql's block, which stays in place:
-- on a database provisioned before this file existed, 0001 is what created
-- the role, and both blocks are no-ops once it is present.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'model_reachable') THEN
        CREATE ROLE model_reachable NOLOGIN;
    END IF;
END $$;

-- Membership alone is not enough: Postgres 16 tracks the SET option
-- separately, so a user who is merely a member of model_reachable still gets
-- "permission denied to set role" from SET ROLE model_reachable.
GRANT model_reachable TO CURRENT_USER WITH SET TRUE;
