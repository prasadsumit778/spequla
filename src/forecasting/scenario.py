"""Scenario persistence, corpus/13 section 4. A scenario is a named, saved
driver-assumption set; a run snapshots the baseline and the computed result
together at the moment it executed. Both are append-only -- CLAUDE.md
invariant 4, the same discipline as mapping_version and report_artefact.
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal

from src.forecasting.baseline import Baseline, read_baseline
from src.forecasting.drivers import ForecastDrivers
from src.forecasting.engine import ForecastResult, project


def _jsonable(obj):
    """Same shape as src/reports/pack.py's private _jsonable -- Decimal and
    date/datetime aren't natively JSON-serialisable, and psycopg's jsonb
    adapter needs plain dicts/lists, not dataclasses."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if is_dataclass(obj) and not isinstance(obj, type):
        return _jsonable(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in obj]
    return obj


def create_scenario(conn, schema: str, tenant_id: str, entity_id: int, name: str,
                        created_by: str, drivers: ForecastDrivers) -> int:
    """drivers is validated Pydantic input by the time it reaches here
    (src/forecasting/drivers.py's field validators already ran) -- this
    function only persists it, verbatim, as the corpus/13 section 4 record
    of what was assumed."""
    with conn.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{schema}".forecast_scenario (tenant_id, entity_id, name, created_by, driver_assumptions) '
            f'VALUES (%s,%s,%s,%s,%s) RETURNING scenario_id',
            (tenant_id, entity_id, name, created_by, json.dumps(drivers.model_dump(mode="json"))),
        )
        return cur.fetchone()[0]


def list_scenarios(conn, schema: str, tenant_id: str, entity_id: int) -> list[dict]:
    """Live scenarios only. An archived one (see archive_scenario) is gone
    from every list, but never gone from the database."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT scenario_id, name, created_by, created_at FROM "{schema}".forecast_scenario '
            f'WHERE tenant_id=%s AND entity_id=%s AND archived_at IS NULL ORDER BY created_at DESC',
            (tenant_id, entity_id),
        )
        return [{"scenario_id": r[0], "name": r[1], "created_by": r[2], "created_at": r[3]}
                  for r in cur.fetchall()]


def archive_scenario(conn, schema: str, tenant_id: str, entity_id: int, scenario_id: int,
                         archived_by: str) -> None:
    """The "delete a scenario" action, corpus/13 section 4.

    It archives; it does not remove. CLAUDE.md invariant 4 -- nothing in this
    system is deleted -- and forecast_run.scenario_id points here: a run
    stores the projection these exact assumptions produced, so removing the
    row would strand that run with no record of what it assumed. Setting
    archived_at drops the scenario out of list_scenarios and get_scenario,
    which is what a user means by "delete it", while every run it already
    produced stays readable with its provenance intact.

    Raises ValueError if the scenario is not this tenant/entity's, or was
    already archived -- an archive is not idempotent-by-silence, because
    "nothing happened" and "it worked" must not look the same to the caller.
    """
    with conn.cursor() as cur:
        cur.execute(
            f'UPDATE "{schema}".forecast_scenario SET archived_at=now(), archived_by=%s '
            f'WHERE tenant_id=%s AND entity_id=%s AND scenario_id=%s AND archived_at IS NULL',
            (archived_by, tenant_id, entity_id, scenario_id),
        )
        if cur.rowcount != 1:
            raise ValueError(f"no live forecast_scenario {scenario_id} for this tenant/entity")


def get_scenario(conn, schema: str, tenant_id: str, entity_id: int, scenario_id: int,
                     include_archived: bool = False) -> tuple[str, ForecastDrivers]:
    """Returns (name, drivers). Raises if the scenario doesn't belong to
    this tenant/entity -- never trust a bare id across a tenant boundary --
    or if it has been archived, which is why run_scenario cannot project an
    assumption set the user has removed. include_archived is for reading the
    assumptions behind an already-stored forecast_run, where the whole point
    is that the record survives the archive."""
    archived_clause = "" if include_archived else " AND archived_at IS NULL"
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT name, driver_assumptions FROM "{schema}".forecast_scenario '
            f'WHERE tenant_id=%s AND entity_id=%s AND scenario_id=%s{archived_clause}',
            (tenant_id, entity_id, scenario_id),
        )
        row = cur.fetchone()
    if not row:
        raise ValueError(f"no forecast_scenario {scenario_id} for this tenant/entity")
    name, driver_json = row
    return name, ForecastDrivers.model_validate(driver_json)


def run_scenario(conn, schema: str, tenant_id: str, entity_id: int, scenario_id: int,
                     mapping_version_id: int, as_of: date, created_by: str,
                     trailing_months: int = 12) -> tuple[int, ForecastResult]:
    """Reads the current baseline (src/forecasting/baseline.py), projects it
    forward under the named scenario's saved drivers (src/forecasting/
    engine.py), and stores both the baseline snapshot and the result as one
    immutable forecast_run row. Returns (run_id, result) so the caller
    doesn't have to re-fetch what it just computed."""
    _name, drivers = get_scenario(conn, schema, tenant_id, entity_id, scenario_id)
    baseline: Baseline = read_baseline(conn, schema, tenant_id, entity_id, mapping_version_id, as_of, trailing_months)
    result = project(baseline, drivers)

    with conn.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{schema}".forecast_run '
            f'(scenario_id, tenant_id, entity_id, baseline_period_end, baseline_snapshot, computed_result, '
            f' gaps, created_by) '
            f'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING run_id',
            (scenario_id, tenant_id, entity_id, as_of, json.dumps(_jsonable(baseline)),
             json.dumps(_jsonable(result)), json.dumps(result.gaps), created_by),
        )
        run_id = cur.fetchone()[0]
    return run_id, result


def get_run(conn, schema: str, tenant_id: str, entity_id: int, run_id: int) -> dict:
    """Returns the stored snapshot verbatim -- never recomputed, same
    contract as report_artefact: a run's numbers stay exactly what they were
    the day it ran, even if the canonical model has since been restated."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT run_id, scenario_id, baseline_period_end, baseline_snapshot, computed_result, gaps, '
            f'       created_at, created_by '
            f'FROM "{schema}".forecast_run WHERE tenant_id=%s AND entity_id=%s AND run_id=%s',
            (tenant_id, entity_id, run_id),
        )
        row = cur.fetchone()
    if not row:
        raise ValueError(f"no forecast_run {run_id} for this tenant/entity")
    return {
        "run_id": row[0], "scenario_id": row[1], "baseline_period_end": row[2],
        "baseline_snapshot": row[3], "computed_result": row[4], "gaps": row[5],
        "created_at": row[6], "created_by": row[7],
    }
