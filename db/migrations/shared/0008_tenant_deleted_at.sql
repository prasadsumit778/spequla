-- Sprint 7, corpus/12: "Retention and deletion paths." app.tenant is never
-- physically deleted (CLAUDE.md invariant 4, and every tenant-scoped row
-- in this schema -- load_run, source_file, token_map, query_log, audit_log
-- -- has a REFERENCES app.tenant(tenant_id) with no ON DELETE clause, so a
-- hard delete of the registry row would fail with a foreign-key violation
-- the moment any audit_log entry exists for that tenant). deleted_at is a
-- soft tombstone: src/admin/tenant_lifecycle.delete_tenant() sets it after
-- dropping the tenant's own analytical schema (all financial data,
-- including every PII-bearing token resolution) and purging the
-- PII-bearing operational rows (token_map, source_file, load_run,
-- query_log). audit_log is deliberately NOT purged -- it is SPEQULA's own
-- record of who did what and when, including the deletion event itself,
-- and is what "retention" actually means here: the fact that a tenant
-- existed and was deleted is retained permanently; the tenant's own
-- business and personal data is not.

ALTER TABLE app.tenant ADD COLUMN deleted_at timestamptz;

COMMENT ON COLUMN app.tenant.deleted_at IS
  'Set once, by src/admin/tenant_lifecycle.delete_tenant(). A non-null value means the tenant''s schema has been dropped and its PII-bearing app rows purged -- the row itself survives only so audit_log (which references it) stays valid.';
