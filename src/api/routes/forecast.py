"""Forecasting screen, corpus/13. Scenario save/list/run, same
require_upload_role gating and session.user_id-as-actor posture as
mapping.py and reports.py -- a saved scenario and a run are both real
written state, not a read.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.deps.auth import Session, require_upload_role
from src.api.deps.tenant import resolve_tenant
from src.forecasting.drivers import ForecastDrivers
from src.forecasting.scenario import (archive_scenario, create_scenario, get_run, get_scenario,
                                          list_scenarios, run_scenario)
from src.reports.query import NoApprovedMappingError, resolve_mapping_version_for_period

router = APIRouter()


class CreateScenarioRequest(BaseModel):
    name: str
    entity_id: int = 1
    drivers: ForecastDrivers


@router.post("/forecast/scenarios")
def create_forecast_scenario(body: CreateScenarioRequest, session: Session = Depends(require_upload_role),
                                  tenant_ctx=Depends(resolve_tenant)):
    conn, tenant_id, schema = tenant_ctx
    scenario_id = create_scenario(conn, schema, tenant_id, body.entity_id, body.name,
                                      session.user_id, body.drivers)
    conn.commit()
    return {"scenario_id": scenario_id, "name": body.name}


@router.get("/forecast/scenarios")
def get_forecast_scenarios(entity_id: int = 1, session: Session = Depends(require_upload_role),
                                tenant_ctx=Depends(resolve_tenant)):
    conn, tenant_id, schema = tenant_ctx
    scenarios = list_scenarios(conn, schema, tenant_id, entity_id)
    return [
        {"scenario_id": s["scenario_id"], "name": s["name"], "created_by": s["created_by"],
          "created_at": s["created_at"].isoformat() if s["created_at"] else None}
        for s in scenarios
    ]


@router.get("/forecast/scenarios/{scenario_id}")
def get_forecast_scenario(scenario_id: int, entity_id: int = 1,
                              session: Session = Depends(require_upload_role), tenant_ctx=Depends(resolve_tenant)):
    conn, tenant_id, schema = tenant_ctx
    try:
        name, drivers = get_scenario(conn, schema, tenant_id, entity_id, scenario_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"scenario_id": scenario_id, "name": name, "drivers": drivers.model_dump(mode="json")}


@router.delete("/forecast/scenarios/{scenario_id}")
def delete_forecast_scenario(scenario_id: int, entity_id: int = 1,
                                 session: Session = Depends(require_upload_role),
                                 tenant_ctx=Depends(resolve_tenant)):
    """Removes a saved scenario from the Forecasting screen. Archival, not a
    row DELETE -- CLAUDE.md invariant 4, and every forecast_run this scenario
    produced keeps pointing at the assumptions that produced it. See
    src/forecasting/scenario.py's archive_scenario."""
    conn, tenant_id, schema = tenant_ctx
    try:
        archive_scenario(conn, schema, tenant_id, entity_id, scenario_id, session.user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    conn.commit()
    return {"scenario_id": scenario_id, "archived": True}


class RunScenarioRequest(BaseModel):
    entity_id: int = 1
    as_of: date | None = None  # defaults to today -- the baseline's "now"
    trailing_months: int = 12


@router.post("/forecast/scenarios/{scenario_id}/run")
def run_forecast_scenario(scenario_id: int, body: RunScenarioRequest,
                              session: Session = Depends(require_upload_role), tenant_ctx=Depends(resolve_tenant)):
    conn, tenant_id, schema = tenant_ctx
    as_of = body.as_of or date.today()
    try:
        mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, body.entity_id, as_of)
    except NoApprovedMappingError as e:
        raise HTTPException(status_code=422, detail=str(e))
    try:
        run_id, result = run_scenario(conn, schema, tenant_id, body.entity_id, scenario_id, mapping_version_id,
                                          as_of, session.user_id, body.trailing_months)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    conn.commit()
    return {
        "run_id": run_id, "scenario_id": scenario_id, "baseline_as_of": as_of.isoformat(),
        "configured": result.configured, "gaps": result.gaps,
        "years": [
            {
                "year_index": y.year_index,
                "existing_store_revenue": str(y.existing_store_revenue),
                "new_store_revenue": str(y.new_store_revenue),
                "store_revenue_by_format": {k: str(v) for k, v in y.store_revenue_by_format.items()},
                "online_revenue_by_channel": {k: str(v) for k, v in y.online_revenue_by_channel.items()},
                "total_revenue": str(y.total_revenue),
                "category_mix": {k: str(v) for k, v in y.category_mix.items()},
                "gross_margin_pct": str(y.gross_margin_pct) if y.gross_margin_pct is not None else None,
                "cogs": str(y.cogs) if y.cogs is not None else None,
                "gross_profit": str(y.gross_profit) if y.gross_profit is not None else None,
                "store_rent": str(y.store_rent) if y.store_rent is not None else None,
                "store_personnel": str(y.store_personnel) if y.store_personnel is not None else None,
                "franchise_commission": str(y.franchise_commission) if y.franchise_commission is not None else None,
                "online_commission": str(y.online_commission),
                "online_ad_spend": str(y.online_ad_spend),
                "company_overhead": str(y.company_overhead) if y.company_overhead is not None else None,
                "ebitda": str(y.ebitda) if y.ebitda is not None else None,
            }
            for y in result.years
        ],
    }


@router.get("/forecast/runs/{run_id}")
def get_forecast_run(run_id: int, entity_id: int = 1, session: Session = Depends(require_upload_role),
                         tenant_ctx=Depends(resolve_tenant)):
    conn, tenant_id, schema = tenant_ctx
    try:
        run = get_run(conn, schema, tenant_id, entity_id, run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "run_id": run["run_id"], "scenario_id": run["scenario_id"],
        "baseline_period_end": run["baseline_period_end"].isoformat() if run["baseline_period_end"] else None,
        "computed_result": run["computed_result"], "gaps": run["gaps"],
        "created_at": run["created_at"].isoformat() if run["created_at"] else None,
        "created_by": run["created_by"],
    }
