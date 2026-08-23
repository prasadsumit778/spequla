"""Profile-specific operating views, sprint 6: the consumer CM ladder
(corpus/03 section 7, corpus/08 section 4.1) and the manufacturing
operating layer (corpus/03 section 6). Separate from statements.py's
P&L/balance-sheet endpoints because these read fact_channel_order_line /
fact_production_output directly, not just fact_gl_entry.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps.auth import Session, require_role
from src.api.deps.tenant import resolve_tenant
from src.quality.checks import check_mixed_uom
from src.reports.consumer_ladder import assemble_consumer_ladder, assemble_order_file_to_books_residual
from src.reports.manufacturing_operating import assemble_manufacturing_operating_metrics
from src.reports.query import NoApprovedMappingError, resolve_mapping_version_for_period
from src.semantic.compiler import period_bounds

router = APIRouter()


@router.get("/operating/consumer-ladder")
def get_consumer_ladder(
    period_start: date = Query(...), period_end: date = Query(...), entity_id: int = 1,
    session: Session = Depends(require_role), tenant_ctx=Depends(resolve_tenant),
):
    conn, tenant_id, schema = tenant_ctx
    try:
        mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, period_end)
    except NoApprovedMappingError as e:
        raise HTTPException(status_code=422, detail=str(e))

    ladder = assemble_consumer_ladder(conn, schema, tenant_id, entity_id, mapping_version_id,
                                          period_start, period_end)
    residual = assemble_order_file_to_books_residual(conn, schema, tenant_id, entity_id, mapping_version_id,
                                                          period_start, period_end)

    def d(v):
        return str(v) if v is not None else None

    return {
        "profile": "consumer", "period_start": str(period_start), "period_end": str(period_end),
        "mapping_version_id": mapping_version_id,
        "gmv_total": d(ladder.gmv_total), "gmv_by_model": {k: d(v) for k, v in ladder.gmv_by_model.items()},
        "discount": d(ladder.discount), "net_revenue": d(ladder.net_revenue),
        "net_revenue_by_model": {k: d(v) for k, v in ladder.net_revenue_by_model.items()},
        "cogs": d(ladder.cogs), "gross_margin": d(ladder.gross_margin), "gross_margin_pct": d(ladder.gross_margin_pct),
        "operating_cost_cm1": d(ladder.operating_cost_cm1), "cm1": d(ladder.cm1), "cm1_pct": d(ladder.cm1_pct),
        "marketing": d(ladder.marketing), "cm2": d(ladder.cm2), "cm2_pct": d(ladder.cm2_pct),
        "corporate_overhead": d(ladder.corporate_overhead), "ebitda": d(ladder.ebitda),
        "unmapped_value_inr": d(ladder.unmapped_value_inr),
        "order_file_to_books_residual": {
            "order_file_buyout_revenue": d(residual.order_file_buyout_revenue),
            "books_revenue": d(residual.books_revenue), "residual": d(residual.residual),
        },
    }


@router.get("/operating/manufacturing")
def get_manufacturing_operating(
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$"), entity_id: int = 1,
    session: Session = Depends(require_role), tenant_ctx=Depends(resolve_tenant),
):
    conn, tenant_id, schema = tenant_ctx
    period_start, period_end = period_bounds(period)
    try:
        mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, period_end)
    except NoApprovedMappingError as e:
        raise HTTPException(status_code=422, detail=str(e))

    mixed_uom = {int(c.object_ref) for c in check_mixed_uom(conn, schema, tenant_id, entity_id, period)}

    product_results, entity_result = assemble_manufacturing_operating_metrics(
        conn, schema, tenant_id, entity_id, mapping_version_id, period, period_start, period_end, mixed_uom,
    )

    def d(v):
        return str(v) if v is not None else None

    return {
        "profile": "manufacturing", "period": period, "mapping_version_id": mapping_version_id,
        "products": [
            {"product_key": r.product_key, "product_name": r.product_name, "status": r.status, "reason": r.reason,
              "uom": r.uom, "volume_produced": d(r.volume_produced), "qty_rejected": d(r.qty_rejected),
              "yield_pct": d(r.yield_pct), "rejection_pct": d(r.rejection_pct),
              "realisation_per_unit": None, "realisation_per_unit_unavailable_reason": r.realisation_per_unit_unavailable_reason,
              "capacity_utilisation_pct": None, "capacity_utilisation_unavailable_reason": r.capacity_utilisation_unavailable_reason}
            for r in product_results
        ],
        "entity": {
            "status": entity_result.status, "reason": entity_result.reason, "common_uom": entity_result.common_uom,
            "total_volume_produced": d(entity_result.total_volume_produced),
            "rm_cost_per_unit": d(entity_result.rm_cost_per_unit),
            "conversion_cost_per_unit": d(entity_result.conversion_cost_per_unit),
            "conversion_cost_components": entity_result.conversion_cost_components,
        },
    }
