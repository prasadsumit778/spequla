-- forecast_scenario archival, corpus/13 section 4. Added 2026-08-25 so the
-- Forecasting screen can offer a "Delete" action on a saved scenario.
--
-- It is an archive, not a DELETE. Two reasons, both structural:
--   1. CLAUDE.md invariant 4 -- nothing in this system is ever overwritten or
--      deleted. 0022's own comment states the same discipline for this pair.
--   2. forecast_run.scenario_id is a FK to this table, and a run stores the
--      fully computed projection produced by exactly these assumptions. A row
--      DELETE would either fail on the FK or orphan a run's provenance, so a
--      past run could no longer say what it assumed. That is a plausible
--      wrong number waiting to happen.
--
-- An archived scenario stops being listed and stops being runnable. Every
-- run it already produced remains readable, forever, with its assumptions
-- still attached.

ALTER TABLE __SCHEMA__.forecast_scenario
    ADD COLUMN archived_at timestamptz,
    ADD COLUMN archived_by text;

COMMENT ON COLUMN __SCHEMA__.forecast_scenario.archived_at IS
  'Set when a user removes the scenario from the Forecasting screen. Non-null means: not listed, not runnable, still readable by any forecast_run that referenced it.';
COMMENT ON COLUMN __SCHEMA__.forecast_scenario.archived_by IS
  'session.user_id of whoever archived it. Never cleared -- un-archiving is not a supported operation.';

-- The list query is (tenant, entity, not archived) ordered by created_at; the
-- 0022 index no longer covers it on its own.
CREATE INDEX ix_forecast_scenario_live ON __SCHEMA__.forecast_scenario (tenant_id, entity_id, created_at DESC)
    WHERE archived_at IS NULL;
