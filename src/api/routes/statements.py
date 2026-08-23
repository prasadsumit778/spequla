"""P&L and balance sheet endpoints, corpus/08 sections 4 and 5.

`profile` is a request parameter rather than persisted tenant config --
company profile (manufacturing vs consumer) setup is corpus/02's onboarding
flow, which sprint 2 does not build; the caller (the frontend, which already
knows which company it's looking at) supplies it.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps.auth import Session, require_role
from src.api.deps.tenant import resolve_tenant
from src.reports.balance_sheet import assemble_balance_sheet
from src.reports.pnl import assemble_consumer_cm_ladder, assemble_manufacturing_pnl
from src.reports.query import NoApprovedMappingError, resolve_mapping_version_for_period

router = APIRouter()


@router.get("/statements/pnl")
def get_pnl(
    period_start: date = Query(...), period_end: date = Query(...),
    profile: str = Query(..., pattern="^(manufacturing|consumer)$"),
    entity_id: int = 1,
    session: Session = Depends(require_role), tenant_ctx=Depends(resolve_tenant),
):
    conn, tenant_id, schema = tenant_ctx
    try:
        mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, period_end)
    except NoApprovedMappingError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if profile == "manufacturing":
        result = assemble_manufacturing_pnl(conn, schema, tenant_id, entity_id, mapping_version_id,
                                               period_start, period_end)
    else:
        result = assemble_consumer_cm_ladder(conn, schema, tenant_id, entity_id, mapping_version_id,
                                                period_start, period_end)

    return {
        "profile": result.profile, "period_start": str(result.period_start), "period_end": str(result.period_end),
        "mapping_version_id": mapping_version_id,
        "lines": {k: str(v) for k, v in result.lines.items()},
        "subtotals": {k: (str(v) if v is not None else None) for k, v in result.subtotals.items()},
        "unmapped_value_inr": str(result.unmapped_value_inr),
    }


@router.get("/statements/balance-sheet")
def get_balance_sheet(
    as_of: date = Query(...), entity_id: int = 1,
    session: Session = Depends(require_role), tenant_ctx=Depends(resolve_tenant),
):
    conn, tenant_id, schema = tenant_ctx
    try:
        mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, as_of)
    except NoApprovedMappingError as e:
        raise HTTPException(status_code=422, detail=str(e))

    result = assemble_balance_sheet(conn, schema, tenant_id, entity_id, mapping_version_id, as_of)

    # corpus/08 section 5's hard gate: a non-balancing balance sheet is not displayed at all.
    if not result.balances:
        raise HTTPException(status_code=422, detail=(
            f"balance sheet does not balance as of {as_of}: total assets "
            f"{result.total_assets} != total liabilities and equity {result.total_liabilities_and_equity}. "
            f"Not displayed, per corpus/08 section 5."
        ))

    return {
        "as_of_date": str(result.as_of_date), "mapping_version_id": mapping_version_id,
        "groups": {g: {label: str(amt) for label, amt in lines.items()} for g, lines in result.groups.items()},
        "group_totals": {g: str(v) for g, v in result.group_totals.items()},
        "total_assets": str(result.total_assets),
        "total_liabilities_and_equity": str(result.total_liabilities_and_equity),
        "balances": result.balances,
        "unmapped_value_inr": str(result.unmapped_value_inr),
    }
