"""Financial overview, corpus/08 section 3: the nine headline metric tiles.

"A tile for an unreconciled period is badged and shows the reason. It is not
hidden and it is not blank" -- and per CLAUDE.md invariant #7, a metric that
did not resolve to a value is not displayed as a number at all, badged or
otherwise; this endpoint returns its block reason (naming the actual
decision or infrastructural gap) in place of a value, and the frontend
renders that distinctly from a number. Every tile that DID resolve carries
its full citation (src/semantic/citation.py), corpus/07 section 8.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from src.api.deps.auth import Session, require_role
from src.api.deps.tenant import resolve_tenant
from src.config.loader import load_registry
from src.quality.period_state import get_current_period_lock
from src.reports.query import NoApprovedMappingError, resolve_mapping_version_for_period
from src.semantic.citation import NotCitable, build_citation
from src.semantic.compiler import compile_metric

router = APIRouter()

# corpus/08 section 3: "Nine, in three rows of three."
TILE_ROWS = [
    ("Profitability", ["net_revenue", "gross_margin_pct", "ebitda"]),
    ("Position", ["cash", "net_debt", "working_capital"]),
    ("Efficiency", ["dso", "dio", "dpo"]),
]


def _tile(conn, schema: str, tenant_id: str, entity_id: int, metric_id: str, period_key: str,
            mapping_version_id: int | None, reconciliation_status: str, config) -> dict:
    label = config.metrics[metric_id].registry.label
    result = compile_metric(conn, schema, tenant_id, entity_id, metric_id, period_key, config)

    if result.status != "ok":
        return {
            "metric": metric_id, "label": label, "status": result.status,
            "value": None, "reason": result.reason, "blocking_decisions": result.blocking_decisions,
        }

    try:
        citation = build_citation(conn, schema, tenant_id, entity_id, mapping_version_id, result,
                                     reconciliation_status)
    except NotCitable as e:
        return {"metric": metric_id, "label": label, "status": "undefined", "value": None, "reason": str(e)}

    c = citation.as_dict()
    c["value"] = str(c["value"])
    c["unmapped_value_inr"] = str(c["unmapped_value_inr"]) if c["unmapped_value_inr"] is not None else None
    return {"metric": metric_id, "label": label, "status": "ok", "value": c["value"], "citation": c}


@router.get("/overview/tiles")
def get_overview_tiles(
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    entity_id: int = 1,
    session: Session = Depends(require_role), tenant_ctx=Depends(resolve_tenant),
):
    conn, tenant_id, schema = tenant_ctx
    config = load_registry()
    period_end = date.fromisoformat(f"{period}-01")

    try:
        mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, period_end)
    except NoApprovedMappingError as e:
        mapping_version_id = None

    lock = get_current_period_lock(conn, schema, tenant_id, entity_id, period)
    reconciliation_status = lock.status if lock else "open"

    rows = []
    for row_label, metric_ids in TILE_ROWS:
        rows.append({
            "row": row_label,
            "tiles": [_tile(conn, schema, tenant_id, entity_id, m, period, mapping_version_id,
                              reconciliation_status, config) for m in metric_ids],
        })

    return {
        "period": period, "entity_id": entity_id,
        "reconciliation_status": reconciliation_status,
        "mapping_version_id": mapping_version_id,
        "rows": rows,
    }
