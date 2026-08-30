-- Append-only resolution for the exception queue. CLAUDE.md invariant 4:
-- "A changed fact closes the prior row and inserts a new one... There are no
-- destructive updates in this system." Added 2026-08-30, replacing the
-- in-place UPDATE that src/api/routes/exceptions.py's resolve endpoint used.
--
-- corpus/09 section 4 says every exception carries "its current status" --
-- current, meaning derived, the way corpus/09 section 5's period state
-- machine derives a period's current status from its latest period_lock row.
-- This migration gives exception the one thing period_lock already had and
-- exception did not: a way to tell that two rows are two versions of the
-- same thing.
--
-- period_lock derives that from a NATURAL key -- (tenant_id, entity_id,
-- period_key) -- so a second INSERT is self-evidently the same period again.
-- An exception has no natural key; its identity is the bigserial itself. So
-- lineage has to be explicit, and root_exception_id is the exact analogue of
-- period_lock.restated_from: a self-FK, NULL on the first version, pointing
-- at the row this one supersedes the group of.
--
--   version 1 (raised):   exception_id=7, root_exception_id=NULL,  status='open'
--   version 2 (resolved): exception_id=9, root_exception_id=7,     status='accepted'
--
-- The identity of that exception is 7, forever. Version 1 is never touched:
-- its status still reads 'open', its raised_at still reads when it was
-- raised, and the queue's history is legible by reading the versions in
-- order rather than by reading an audit log that says a row used to be
-- different.
--
-- No is_current flag, deliberately. Materialising one would mean UPDATEing
-- the prior row to clear it -- reintroducing the destructive write this
-- migration exists to remove. Current is derived, exactly as
-- src/quality/period_state.get_current_period_lock derives it.

ALTER TABLE __SCHEMA__.exception
    ADD COLUMN root_exception_id bigint REFERENCES __SCHEMA__.exception(exception_id);

COMMENT ON COLUMN __SCHEMA__.exception.root_exception_id IS
  'NULL means this row is the exception as first raised. Non-null points at the exception_id of the first version, making this row a later version of that same exception. Never updated: a row''s root is fixed when it is inserted.';

-- The one place "which version is current" is defined. Every reader of the
-- queue goes through this view; nothing outside src/quality/exception_queue.py
-- selects status directly off the base table, because the base table holds
-- superseded rows whose status is deliberately stale.
CREATE VIEW __SCHEMA__.exception_current AS
SELECT DISTINCT ON (COALESCE(e.root_exception_id, e.exception_id))
       COALESCE(e.root_exception_id, e.exception_id) AS exception_key,
       e.exception_id AS version_exception_id,
       e.tenant_id, e.entity_id, e.raised_at, e.exception_class, e.severity, e.period_key,
       e.object_type, e.object_ref, e.value_inr, e.description, e.suggested_action,
       e.status, e.resolved_by, e.resolved_at, e.resolution_note, e.load_run_id
FROM __SCHEMA__.exception e
ORDER BY COALESCE(e.root_exception_id, e.exception_id), e.exception_id DESC;

COMMENT ON VIEW __SCHEMA__.exception_current IS
  'One row per exception: its latest version. exception_key is the stable identity (the first version''s exception_id) and is what the API and the pack quote; version_exception_id is the physical row this status came from. Superseded rows stay readable in the base table.';

-- ix_exception_queue (tenant_id, status, severity, value_inr DESC) still
-- serves the queue ordering, but the view's DISTINCT ON now sorts on the
-- lineage expression first, which no existing index covers.
CREATE INDEX ix_exception_versions ON __SCHEMA__.exception
    ((COALESCE(root_exception_id, exception_id)), exception_id DESC);

REVOKE ALL ON __SCHEMA__.exception_current FROM model_reachable;
