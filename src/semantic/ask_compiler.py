"""SQL compilation and execution for the Ask surface, corpus/07 section 2
stages 6-9 (SQL compilation, admission control, execution, result sanity).

Reuses src/semantic/compiler.py's compile_metric wherever a metric's own
value is needed -- that function already implements the transitive
dependency-gate, the override chain and the mapping-approval gate (Sprint
3), and this module does not duplicate any of that. What THIS module adds
is specific to the Ask surface: turning a validated IRRequest into
(a) representative SQL text a human or the admission gates can actually
read, and (b) an AskResult carrying whichever of ok / blocked / unavailable
/ error actually describes what happened, for each of corpus/07 section 4's
twelve intents.

A derived metric like ebitda is not "one query" in any literal sense --
compile_metric resolves it as a small tree of leaf queries composed in
Python. The SQL text this module produces for such a metric is the leaf
query for corpus/07's own worked example shape (a gl_class aggregate), not
a literal transcript of every query compile_metric ran -- an honest
architectural fact stated here rather than glossed over, since corpus/07
section 7's admission gates are written assuming one query per compiled
request.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from src.config.loader import ConfigRegistry
from src.quality.period_state import get_current_period_lock
from src.reports.balance_sheet import assemble_balance_sheet
from src.reports.pnl import assemble_consumer_cm_ladder, assemble_manufacturing_pnl
from src.reports.query import NoApprovedMappingError, resolve_mapping_version_for_period
from src.semantic.bridges import (
    BridgeResult,
    compute_cash_bridge,
    compute_ebitda_bridge,
    not_configured,
)
from src.semantic.compiler import CompiledMetric, compile_metric, period_bounds
from src.semantic.formula import find_gl_class_patterns, match_gl_classes
from src.semantic.ir import IRRequest

UNAVAILABLE_DIMENSIONS = {
    "customer": "customer-level breakdown needs dim_customer and fact_gl_entry.customer_key, deferred since "
                  "Sprint 1 (nullable, unconstrained FK -- corpus/12 sprint 0 plan's sequencing decision)",
    "product": "product-level breakdown needs dim_item/map_item, not yet built",
    "vendor": "vendor-level breakdown needs dim_vendor and fact_gl_entry.vendor_key, deferred since Sprint 1",
}


@dataclass
class AskResult:
    status: str  # 'ok' | 'blocked' | 'unavailable' | 'error'
    intent: str
    sql_text: str | None = None
    tables_referenced: list[str] = field(default_factory=list)
    value: object = None
    series: list[dict] = field(default_factory=list)
    bridge: BridgeResult | None = None
    reason: str | None = None
    blocking_decisions: list[str] = field(default_factory=list)
    compiled_metric: CompiledMetric | None = None
    row_count: int = 0


def _representative_gl_class_sql(schema: str, metric_id: str, formula: str, known_classes: list[str],
                                    time_logic: str) -> tuple[str, list[str]]:
    """The SQL text corpus/07's admission gates actually inspect, for a leaf
    gl_class metric. Mirrors src/semantic/compiler.py's _fetch_leaf_amounts
    query shape exactly, so what the gates see is what would really run."""
    patterns = find_gl_class_patterns(formula)
    classes = sorted({c for p in patterns for c in match_gl_classes(p, known_classes)}) if patterns else []
    date_filter = "fg.event_date <= %s" if time_logic == "period_end" else "fg.event_date BETWEEN %s AND %s"
    sql = (
        f'SELECT ma.canonical_class, SUM(fg.amount_base) '
        f'FROM "{schema}".fact_gl_entry fg '
        f'JOIN "{schema}".dim_account da ON da.account_key = fg.account_key '
        f'JOIN "{schema}".map_account ma ON ma.mapping_version_id = %s AND ma.source_record_id = da.source_record_id '
        f'WHERE fg.tenant_id = %s AND fg.entity_id = %s AND fg.is_current '
        f'AND ma.canonical_class = ANY(%s) AND {date_filter}'
    )
    return sql, [f'"{schema}".fact_gl_entry', f'"{schema}".dim_account', f'"{schema}".map_account']


def compile_and_execute(conn, schema: str, tenant_id: str, entity_id: int, ir: IRRequest,
                           config: ConfigRegistry, tenant_profile: str = "manufacturing") -> AskResult:
    handler = _INTENT_HANDLERS.get(ir.intent)
    if handler is None:
        return AskResult(status="error", intent=ir.intent, reason=f"no handler for intent {ir.intent!r}")
    return handler(conn, schema, tenant_id, entity_id, ir, config, tenant_profile)


def _period_key_from_ir(ir: IRRequest) -> str:
    if ir.period is None:
        raise ValueError("period is required for this intent")
    if ir.period.type == "month":
        return ir.period.value
    raise ValueError(f"period type {ir.period.type!r} not yet resolvable to a single month")


def _metric_value(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing") -> AskResult:
    period_key = _period_key_from_ir(ir)
    contract = config.metrics[ir.metric]
    known_classes = [c.class_ for c in config.taxonomy]
    sql_text, tables = _representative_gl_class_sql(schema, ir.metric, contract.registry.formula,
                                                        known_classes, contract.registry.time_logic)

    result = compile_metric(conn, schema, tenant_id, entity_id, ir.metric, period_key, config)
    if result.status != "ok":
        return AskResult(status="blocked" if result.status == "blocked" else "unavailable", intent=ir.intent,
                            sql_text=sql_text, tables_referenced=tables, reason=result.reason,
                            blocking_decisions=result.blocking_decisions, compiled_metric=result)
    return AskResult(status="ok", intent=ir.intent, sql_text=sql_text, tables_referenced=tables,
                        value=result.value, compiled_metric=result, row_count=result.row_count)


def _metric_trend(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing") -> AskResult:
    if ir.period is None or ir.period.resolved_range is None:
        return AskResult(status="error", intent=ir.intent, reason="metric_trend requires period.resolved_range")
    start = date.fromisoformat(ir.period.resolved_range[0])
    end = date.fromisoformat(ir.period.resolved_range[1])
    period_keys = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        period_keys.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1

    series = []
    last_result = None
    for pk in period_keys:
        r = compile_metric(conn, schema, tenant_id, entity_id, ir.metric, pk, config)
        last_result = r
        series.append({"period": pk, "status": r.status, "value": str(r.value) if r.value is not None else None,
                          "reason": r.reason})

    any_ok = any(s["status"] == "ok" for s in series)
    return AskResult(status="ok" if any_ok else (last_result.status if last_result else "error"),
                        intent=ir.intent, series=series,
                        reason=None if any_ok else (last_result.reason if last_result else None),
                        blocking_decisions=last_result.blocking_decisions if last_result and not any_ok else [])


def _metric_comparison(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing") -> AskResult:
    period_key = _period_key_from_ir(ir)
    current = compile_metric(conn, schema, tenant_id, entity_id, ir.metric, period_key, config)
    if current.status != "ok":
        return AskResult(status="blocked" if current.status == "blocked" else "unavailable", intent=ir.intent,
                            reason=current.reason, blocking_decisions=current.blocking_decisions,
                            compiled_metric=current)

    if ir.compare_to is None:
        return AskResult(status="error", intent=ir.intent, reason="metric_comparison requires compare_to")
    y, m = (int(p) for p in period_key.split("-"))
    if ir.compare_to.type in ("prior_period", "mom"):
        cy, cm = (y, m - 1) if m > 1 else (y - 1, 12)
    elif ir.compare_to.type == "yoy":
        cy, cm = y - 1, m
    else:
        return AskResult(status="error", intent=ir.intent, reason=f"unsupported compare_to {ir.compare_to.type!r}")
    compare_key = f"{cy:04d}-{cm:02d}"
    compare = compile_metric(conn, schema, tenant_id, entity_id, ir.metric, compare_key, config)

    return AskResult(
        status="ok", intent=ir.intent,
        value={"current": {"period": period_key, "value": str(current.value)},
                "compare": {"period": compare_key, "value": str(compare.value) if compare.status == "ok" else None,
                             "status": compare.status, "reason": compare.reason}},
        compiled_metric=current,
    )


def _metric_breakdown_or_ranking(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing") -> AskResult:
    for dim in ir.breakdown:
        if dim in UNAVAILABLE_DIMENSIONS:
            return AskResult(status="unavailable", intent=ir.intent,
                                reason=f"breakdown by {dim!r} is not available yet: {UNAVAILABLE_DIMENSIONS[dim]}")
    # No breakdown dimension this build can actually resolve yet (date/entity
    # are the only currently-populated dimensions, and grouping by them is
    # not a meaningful "breakdown" in the golden-question sense) -- report
    # the aggregate value honestly rather than fabricate a grouped result.
    return _metric_value(conn, schema, tenant_id, entity_id, ir, config, tenant_profile)


def _statement_view(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing") -> AskResult:
    if ir.period is None:
        return AskResult(status="error", intent=ir.intent, reason="statement_view requires a period")
    period_start, period_end = period_bounds(_period_key_from_ir(ir)) if ir.period.type == "month" else (None, None)
    if period_start is None:
        return AskResult(status="unavailable", intent=ir.intent,
                            reason="only single-month statement_view is implemented in this sprint")
    try:
        mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, period_end)
    except NoApprovedMappingError as e:
        return AskResult(status="unavailable", intent=ir.intent, reason=str(e))

    if tenant_profile == "consumer":
        pnl = assemble_consumer_cm_ladder(conn, schema, tenant_id, entity_id, mapping_version_id,
                                              period_start, period_end)
    else:
        pnl = assemble_manufacturing_pnl(conn, schema, tenant_id, entity_id, mapping_version_id,
                                            period_start, period_end)
    bs = assemble_balance_sheet(conn, schema, tenant_id, entity_id, mapping_version_id, period_end)

    return AskResult(
        status="ok", intent=ir.intent,
        value={"pnl": {k: str(v) for k, v in pnl.lines.items()},
                "pnl_subtotals": {k: (str(v) if v is not None else None) for k, v in pnl.subtotals.items()},
                "balance_sheet_balances": bs.balances,
                "unmapped_value_inr": str(pnl.unmapped_value_inr)},
        tables_referenced=[f'"{schema}".fact_gl_entry', f'"{schema}".map_account'],
    )


def _data_health(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing") -> AskResult:
    if ir.period is not None:
        period_key = _period_key_from_ir(ir)
        lock = get_current_period_lock(conn, schema, tenant_id, entity_id, period_key)
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT check_type, status, residual_inr FROM "{schema}".reconciliation_run '
                f'WHERE tenant_id=%s AND entity_id=%s AND period_key=%s ORDER BY run_at DESC',
                (tenant_id, entity_id, period_key),
            )
            checks = [{"check_type": r[0], "status": r[1], "residual_inr": str(r[2])} for r in cur.fetchall()]
        return AskResult(status="ok", intent=ir.intent,
                            value={"period": period_key, "status": lock.status if lock else "open", "checks": checks},
                            tables_referenced=[f'"{schema}".period_lock', f'"{schema}".reconciliation_run'])

    try:
        mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, date.today())
    except NoApprovedMappingError as e:
        return AskResult(status="unavailable", intent=ir.intent, reason=str(e))
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT COALESCE(SUM(period_value_inr), 0), '
            f"       COALESCE(SUM(period_value_inr) FILTER (WHERE canonical_class='suspense.unmapped'), 0) "
            f'FROM "{schema}".map_account WHERE mapping_version_id = %s',
            (mapping_version_id,),
        )
        total, unmapped = cur.fetchone()
    pct = float(unmapped / total) if total else 0.0
    return AskResult(status="ok", intent=ir.intent,
                        value={"unmapped_pct": pct, "unmapped_value_inr": str(unmapped)},
                        tables_referenced=[f'"{schema}".map_account'])


def _definition_lookup(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing") -> AskResult:
    """corpus/07 section 4: 'Registry lookup, returns the resolved contract.
    No SQL runs.' Genuinely no database touch at all."""
    if ir.metric not in config.metrics:
        return AskResult(status="unavailable", intent=ir.intent, reason=f"unknown metric {ir.metric!r}")
    contract = config.metrics[ir.metric]
    body = contract.model_extra.get("contract") if contract.model_extra else None
    return AskResult(status="ok", intent=ir.intent,
                        value={"registry": contract.registry.model_dump(), "contract": body})


def _variance_explain(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing") -> AskResult:
    if ir.metric not in ("ebitda", "closing_cash"):
        return AskResult(status="unavailable", intent=ir.intent,
                            reason=f"variance_explain for {ir.metric!r} has no bridge implemented yet "
                                    f"(see src/semantic/bridges.py: only the revenue, ebitda and cash bridges exist)")

    period_key = _period_key_from_ir(ir)
    y, m = (int(p) for p in period_key.split("-"))
    py, pm = (y, m - 1) if m > 1 else (y - 1, 12)
    prior_key = f"{py:04d}-{pm:02d}"

    current = compile_metric(conn, schema, tenant_id, entity_id, ir.metric, period_key, config)
    prior = compile_metric(conn, schema, tenant_id, entity_id, ir.metric, prior_key, config)
    if current.status != "ok" or prior.status != "ok":
        blocked = current if current.status != "ok" else prior
        return AskResult(status="blocked" if blocked.status == "blocked" else "unavailable", intent=ir.intent,
                            reason=blocked.reason, blocking_decisions=blocked.blocking_decisions)

    if ir.metric == "ebitda":
        gp_current = compile_metric(conn, schema, tenant_id, entity_id, "gross_profit", period_key, config)
        gp_prior = compile_metric(conn, schema, tenant_id, entity_id, "gross_profit", prior_key, config)
        opex_current = compile_metric(conn, schema, tenant_id, entity_id, "opex", period_key, config)
        opex_prior = compile_metric(conn, schema, tenant_id, entity_id, "opex", prior_key, config)
        if any(r.status != "ok" for r in (gp_current, gp_prior, opex_current, opex_prior)):
            return AskResult(status="unavailable", intent=ir.intent,
                                reason="gross_profit/opex breakdown unavailable for the bridge")
        bridge = compute_ebitda_bridge(gp_current.value - gp_prior.value,
                                          {"opex_total": opex_current.value - opex_prior.value},
                                          current.value - prior.value)
        return AskResult(status="ok", intent=ir.intent, bridge=bridge,
                            value={"current": str(current.value), "prior": str(prior.value)})

    return AskResult(status="unavailable", intent=ir.intent, reason="cash bridge not wired to compile_metric yet")


def _ageing(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing") -> AskResult:
    return AskResult(status="unavailable", intent=ir.intent,
                        reason="ageing needs AR/AP open-item detail (fact_ar_open/fact_ap_open or the AR/AP "
                                "ageing template), which has no ingestion pipeline built yet -- only COA, TB, "
                                "GL and Bank are ingested in this build")


def _concentration(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing") -> AskResult:
    return AskResult(status="unavailable", intent=ir.intent,
                        reason="concentration needs a customer/vendor breakdown, which needs dim_customer/"
                                "dim_vendor -- deferred since Sprint 1 (see UNAVAILABLE_DIMENSIONS)")


_INTENT_HANDLERS = {
    "metric_value": _metric_value,
    "metric_trend": _metric_trend,
    "metric_comparison": _metric_comparison,
    "metric_breakdown": _metric_breakdown_or_ranking,
    "metric_ranking": _metric_breakdown_or_ranking,
    "variance_explain": _variance_explain,
    "statement_view": _statement_view,
    "concentration": _concentration,
    "ageing": _ageing,
    "definition_lookup": _definition_lookup,
    "data_health": _data_health,
}
