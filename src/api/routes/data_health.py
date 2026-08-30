"""Data health screen, corpus/09 section 6: four panels, one page --
freshness, completeness, reconciliation, exceptions.

"The unmapped rupee figure is the single most useful number on the screen"
-- returned as a plain rupee amount, never just a percentage, per that
section's own instruction.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.api.deps.auth import Session, require_role
from src.api.deps.tenant import resolve_tenant
from src.quality.checks import fetch_freshness
from src.reports.query import NoApprovedMappingError, resolve_mapping_version_for_period
from datetime import date

router = APIRouter()


def _completeness_panel(conn, schema: str, tenant_id: str, mapping_version_id: int | None) -> dict:
    if mapping_version_id is None:
        return {"mapped_pct": None, "unmapped_value_inr": None, "reason": "no approved mapping version"}
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT COALESCE(SUM(period_value_inr), 0), '
            f"       COALESCE(SUM(period_value_inr) FILTER (WHERE canonical_class = 'suspense.unmapped'), 0) "
            f'FROM "{schema}".map_account WHERE mapping_version_id = %s',
            (mapping_version_id,),
        )
        total, unmapped = cur.fetchone()
    mapped_pct = float((total - unmapped) / total) if total else 1.0
    return {"mapped_pct": mapped_pct, "unmapped_value_inr": str(unmapped), "total_value_inr": str(total)}


def _reconciliation_panel(conn, schema: str, tenant_id: str, entity_id: int, period_key: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT check_type, status, residual_inr, tolerance_pct, run_at '
            f'FROM "{schema}".reconciliation_run '
            f'WHERE tenant_id = %s AND entity_id = %s AND period_key = %s '
            f'ORDER BY run_at DESC',
            (tenant_id, entity_id, period_key),
        )
        rows = cur.fetchall()
    return [
        {"check_type": ct, "status": st, "residual_inr": str(res), "tolerance_pct": str(tol) if tol else None,
          "run_at": run_at.isoformat()}
        for ct, st, res, tol, run_at in rows
    ]


def _exceptions_panel(conn, schema: str, tenant_id: str) -> dict:
    """exception_current, not exception: a resolved exception's raised row
    still reads status='open' because resolution appends a version rather
    than overwriting (CLAUDE.md invariant #4, db/migrations/tenant/0024)."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT severity, count(*), COALESCE(SUM(value_inr), 0) FROM "{schema}".exception_current '
            f"WHERE tenant_id = %s AND status = 'open' GROUP BY severity",
            (tenant_id,),
        )
        by_severity = {sev: {"count": n, "value_inr": str(v)} for sev, n, v in cur.fetchall()}
        cur.execute(
            f'SELECT exception_class, severity, description, value_inr FROM "{schema}".exception_current '
            f"WHERE tenant_id = %s AND status = 'open' "
            f"ORDER BY CASE severity WHEN 'blocking' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, "
            f'value_inr DESC NULLS LAST LIMIT 10',
            (tenant_id,),
        )
        top_ten = [
            {"exception_class": c, "severity": s, "description": d, "value_inr": str(v) if v is not None else None}
            for c, s, d, v in cur.fetchall()
        ]
    return {"open_by_severity": by_severity, "top_ten_by_value": top_ten}


@router.get("/data-health")
def get_data_health(
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$"), entity_id: int = 1,
    session: Session = Depends(require_role), tenant_ctx=Depends(resolve_tenant),
):
    conn, tenant_id, schema = tenant_ctx
    period_end = date.fromisoformat(f"{period}-01")

    try:
        mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, period_end)
    except NoApprovedMappingError:
        mapping_version_id = None

    freshness = fetch_freshness(conn, tenant_id, entity_id)

    return {
        "period": period,
        "freshness": [
            {"source_system": f.source_system,
              "last_successful_load_at": f.last_successful_load_at.isoformat() if f.last_successful_load_at else None,
              "hours_since": f.hours_since}
            for f in freshness
        ],
        "completeness": _completeness_panel(conn, schema, tenant_id, mapping_version_id),
        "reconciliation": _reconciliation_panel(conn, schema, tenant_id, entity_id, period),
        "exceptions": _exceptions_panel(conn, schema, tenant_id),
    }
