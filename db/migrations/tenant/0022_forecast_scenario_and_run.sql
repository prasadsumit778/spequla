-- forecast_scenario / forecast_run, corpus/13 section 4. Added 2026-08-24
-- for the apparel forecasting build -- this pair used to be listed in
-- corpus/04 section 4's "what the model deliberately does not have" table
-- ("Forecast, forecast_version, scenario, assumption tables ... P1"),
-- removed there now that they exist (corpus/04 section 3.10 cross-references
-- this file).
--
-- Same append-only discipline as mapping_version/report_artefact
-- (CLAUDE.md invariant 4): a scenario's driver_assumptions is never edited
-- in place -- a changed assumption set is a NEW scenario row, so a
-- forecast_run always points at the exact assumptions that produced it,
-- forever reproducible. forecast_run.computed_result stores the FULLY
-- COMPUTED projection at run time, not a pointer back to live tables, same
-- reasoning as report_artefact.sections: re-rendering a past run must not
-- silently change because the canonical model has since been restated.

CREATE TABLE __SCHEMA__.forecast_scenario (
    scenario_id          bigserial   PRIMARY KEY,
    tenant_id             uuid        NOT NULL,
    entity_id              int         NOT NULL,
    name                     text        NOT NULL,
    created_by                text        NOT NULL,
    created_at                  timestamptz NOT NULL DEFAULT now(),
    driver_assumptions             jsonb       NOT NULL   -- src/forecasting/drivers.py's ForecastDrivers, verbatim
);
CREATE INDEX ix_forecast_scenario_tenant ON __SCHEMA__.forecast_scenario (tenant_id, entity_id, created_at DESC);
COMMENT ON TABLE __SCHEMA__.forecast_scenario IS
  'Grain: one named, saved driver-assumption set. Immutable once created -- an edited scenario is a new row, never an UPDATE.';

CREATE TABLE __SCHEMA__.forecast_run (
    run_id                 bigserial   PRIMARY KEY,
    scenario_id              bigint      NOT NULL REFERENCES __SCHEMA__.forecast_scenario(scenario_id),
    tenant_id                 uuid        NOT NULL,
    entity_id                   int         NOT NULL,
    baseline_period_end           date        NOT NULL,  -- the as_of date src/forecasting/baseline.py read
    baseline_snapshot                jsonb       NOT NULL,  -- src/forecasting/baseline.py's Baseline, frozen at run time
    computed_result                     jsonb       NOT NULL,  -- src/forecasting/engine.py's ForecastResult, frozen
    gaps                                  jsonb       NOT NULL DEFAULT '[]',  -- disclosed components not computable, per the run
    created_at                              timestamptz NOT NULL DEFAULT now(),
    created_by                                text        NOT NULL
);
CREATE INDEX ix_forecast_run_scenario ON __SCHEMA__.forecast_run (scenario_id, created_at DESC);
COMMENT ON TABLE __SCHEMA__.forecast_run IS
  'Grain: one projection run. Immutable -- re-viewing a past run reads this row, never recomputes against a canonical model that may since have been restated.';

REVOKE ALL ON __SCHEMA__.forecast_scenario FROM model_reachable;
REVOKE ALL ON __SCHEMA__.forecast_run FROM model_reachable;
