"""Monthly management pack assembly, corpus/08 section 7 (the eight P0
sections), section 8 (chart specs) and section 9 (provenance).

Each section builder is DB-fetching (it needs live data to assemble), but
returns a plain, JSON-serialisable dict -- the whole point (see
src/reports/signoff.py and db/migrations/tenant/0013_report_artefact.sql)
is that `generate_pack` computes everything ONCE and the result is stored
verbatim. Re-rendering later reads the stored dict; it never calls these
functions again against what may since be a changed database.

Where a section's corpus-specified content is not computable from what this
system currently ingests or what the corpus defines (product/customer
revenue breakdown, receivable/payable/inventory ageing, the margin bridge,
the manufacturing price/volume/mix bridge, most of the cash flow statement
per OPEN_QUESTIONS.md OQ-004), the section says so explicitly and the reason
is also collected into section 9's `known_limitations` list -- "a management
pack that quietly omits its own known gaps is the thing this whole
architecture exists to prevent" (corpus/08 section 7).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from src.config.loader import ConfigRegistry
from src.quality.checks import fetch_freshness
from src.quality.period_state import get_current_period_lock
from src.reports.balance_sheet import assemble_balance_sheet
from src.reports.cashflow import assemble_cash_flow_statement
from src.reports.charts import kpi_tile_chart, line_chart, table_chart
from src.reports.comparatives import compute_comparatives, fiscal_year_start
from src.reports.pnl import assemble_consumer_cm_ladder, assemble_manufacturing_pnl
from src.reports.query import class_movements, resolve_mapping_version_for_period
from src.reports.statement_lines import MANUFACTURING_SECTIONS
from src.semantic.ask_compiler import UNAVAILABLE_DIMENSIONS
from src.semantic.bridges import compute_margin_bridge
from src.semantic.compiler import compile_metric, period_bounds

# corpus/08 section 3's nine tiles, reused here for section 3 (Financial
# summary): "Headline metrics with month, year and year-to-date comparatives."
HEADLINE_METRICS = [
    ("net_revenue", "Net revenue"), ("gross_margin_pct", "Gross margin %"), ("ebitda", "EBITDA"),
    ("cash", "Cash"), ("net_debt", "Net debt"), ("working_capital", "Working capital"),
    ("dso", "DSO"), ("dio", "DIO"), ("dpo", "DPO"),
]

# corpus/08 section 6: DSO/DIO/DPO/CCC "with trends."
WORKING_CAPITAL_METRICS = [("dso", "DSO"), ("dio", "DIO"), ("dpo", "DPO"), ("ccc", "CCC")]

_TRAILING_MONTHS = 12


def _jsonable(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return sorted(_jsonable(v) for v in obj)
    if is_dataclass(obj) and not isinstance(obj, type):
        return _jsonable(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def content_hash(sections: dict, chart_specs: list, commentary: str | None) -> str:
    """sha256 of the canonical (sorted-key) JSON serialisation -- what the
    reproducibility test compares. commentary is included so a signed pack's
    hash also proves its commentary was frozen at sign time."""
    canonical = json.dumps({"sections": sections, "chart_specs": chart_specs, "commentary": commentary},
                              sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _shift(period_key: str, months: int) -> str:
    year, month = (int(p) for p in period_key.split("-"))
    total = year * 12 + (month - 1) + months
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _trailing_months(period_key: str, count: int = _TRAILING_MONTHS) -> list[str]:
    return [_shift(period_key, -i) for i in range(count - 1, -1, -1)]


def _comparative_dict(c) -> dict:
    def m(compiled):
        if compiled is None:
            return None
        return {"status": compiled.status, "value": compiled.value, "reason": compiled.reason,
                  "period_key": compiled.period_key, "blocking_decisions": compiled.blocking_decisions}
    return {"current": m(c.current), "prior_month": m(c.prior_month), "prior_year": m(c.prior_year),
              "ytd": m(c.ytd), "ytd_prior_year": m(c.ytd_prior_year)}


def _delta(a, b):
    if a is None or b is None or a.status != "ok" or b.status != "ok":
        return None
    return a.value - b.value


# ------------------------------------------------------------------ Section 1

def build_cover(conn, schema: str, tenant_id: str, entity_id: int, profile: str, period_key: str,
                   mapping_version_id: int, mapping_version_no: int, unmapped_value_inr: Decimal,
                   metric_versions: dict) -> dict:
    """corpus/08 section 7 #1: period, basis, reconciliation status, data
    freshness per source, unmapped value, mapping version, metric versions.
    Snapshot id, preparer, reviewer and sign-off date are report_artefact's
    own columns (report_artefact_id, generated_by, reviewer, signed_at) --
    combined with this dict at render time, not duplicated here."""
    lock = get_current_period_lock(conn, schema, tenant_id, entity_id, period_key)
    freshness = fetch_freshness(conn, tenant_id, entity_id)
    return {
        "period_key": period_key, "entity_id": entity_id, "profile": profile,
        "basis": "accrual",
        "reconciliation_status": lock.status if lock else "open",
        "freshness": [{"source_system": f.source_system,
                          "last_successful_load_at": f.last_successful_load_at,
                          "hours_since": f.hours_since} for f in freshness],
        "unmapped_value_inr": unmapped_value_inr,
        "mapping_version_id": mapping_version_id, "mapping_version_no": mapping_version_no,
        "metric_versions": metric_versions,
    }


# ------------------------------------------------------------------ Section 2

def build_executive_summary(commentary: str | None) -> dict:
    """corpus/08 section 7 #2: 'Written by a human in P0.' This builder does
    not generate text -- src/reports/signoff.py's edit_commentary is the
    only way this field is ever populated."""
    return {"bullets_markdown": commentary, "written_by": "human" if commentary else None}


# ------------------------------------------------------------------ Section 3

def build_financial_summary(conn, schema: str, tenant_id: str, entity_id: int, period_key: str,
                                config: ConfigRegistry, _cache: dict | None = None) -> tuple[dict, list[dict]]:
    """corpus/08 section 7 #3. Returns (section_dict, chart_specs)."""
    tiles, charts, metric_versions = [], [], {}
    for metric_id, label in HEADLINE_METRICS:
        comp = compute_comparatives(conn, schema, tenant_id, entity_id, metric_id, period_key, config, _cache)
        tiles.append({"metric": metric_id, "label": label, **_comparative_dict(comp)})
        if comp.current.status == "ok" and comp.current.metric_version is not None:
            metric_versions[metric_id] = comp.current.metric_version
        if comp.current.status == "ok":
            charts.append(kpi_tile_chart(
                label, comp.current.value, _delta(comp.current, comp.prior_month),
                _delta(comp.current, comp.prior_year), comp.current.unit or "INR"))
    return {"tiles": tiles}, charts


# ------------------------------------------------------------------ Section 4

def build_revenue_analysis(pnl_result, profile: str) -> dict:
    """corpus/08 section 7 #4. Manufacturing wants revenue by customer and
    product with the D-059 price/volume/mix bridge; consumer wants GMV, net
    revenue and the CM ladder by channel and product. Neither breakdown is
    ingested yet (see UNAVAILABLE_DIMENSIONS, and consumer channel/product
    is fact_channel_order_line, Sprint 6) -- the entity-level totals ARE
    shown, honestly labelled as not broken down."""
    gaps = [UNAVAILABLE_DIMENSIONS["product"]]
    if profile == "manufacturing":
        gaps.append(UNAVAILABLE_DIMENSIONS["customer"])
        gaps.append("the D-059 price/volume/mix bridge needs per-product price and volume, which is "
                       "unavailable for the same reason as the product breakdown")
    else:
        gaps.append("channel breakdown needs fact_channel_order_line and dim_channel, Sprint 6 scope")
    return {
        "entity_level_lines": pnl_result.lines, "entity_level_subtotals": pnl_result.subtotals,
        "by_customer_and_product": None, "price_volume_mix_bridge": None,
        "unavailable_reasons": gaps,
    }


# ------------------------------------------------------------------ Section 5

_CONSUMER_COST_LINES = ["Cost of goods sold", "Operating cost", "Marketing", "Corporate overhead"]


def build_margin_analysis(pnl_result, prior_pnl_result) -> tuple[dict, list[dict]]:
    """corpus/08 section 7 #5: gross margin bridge, cost line movements,
    absorption variance where applicable. The bridge itself is not
    configured (src/semantic/bridges.compute_margin_bridge -- no allocation
    formula anywhere in the corpus); cost line movements ARE computable
    directly as this-period-vs-prior-period deltas on the P&L lines already
    assembled for the statements section. Line labels differ by profile --
    pnl.py's manufacturing and consumer assemblers produce different
    presentation lines (statement_lines.py vs the CM ladder's own labels)."""
    bridge = compute_margin_bridge()
    if pnl_result.profile == "manufacturing":
        cost_lines = MANUFACTURING_SECTIONS.get("cogs", []) + MANUFACTURING_SECTIONS.get("opex", [])
    else:
        cost_lines = _CONSUMER_COST_LINES
    movements = []
    for label in cost_lines:
        cur = pnl_result.lines.get(label)
        prior = prior_pnl_result.lines.get(label) if prior_pnl_result else None
        if cur is None and prior is None:
            continue
        movements.append({"line": label, "current": cur, "prior": prior,
                             "change": (cur - prior) if (cur is not None and prior is not None) else None})
    absorption_variance = pnl_result.lines.get("Absorption variance")
    charts = []
    if movements:
        charts.append(table_chart("Cost line movements", ["Line", "Current", "Prior", "Change"],
                                      [[m["line"], m["current"], m["prior"], m["change"]] for m in movements]))
    return {
        "gross_margin_bridge": None, "gross_margin_bridge_reason": bridge.reason,
        "cost_line_movements": movements, "absorption_variance": absorption_variance,
    }, charts


# ------------------------------------------------------------------ Section 6

def build_working_capital(conn, schema: str, tenant_id: str, entity_id: int, period_key: str,
                              config: ConfigRegistry, _cache: dict | None = None) -> tuple[dict, list[dict]]:
    """corpus/08 section 7 #6: DSO/DIO/DPO/CCC with trends, ageing, rupee
    impact per day. Ageing is not ingested (AR/AP ageing files land in an
    un-ingested stream, per src/quality/checks.py's own scope-boundary
    docstring). Rupee impact per day is derived from the same revenue_base/
    cost_base and days_basis compile_metric already resolved for DSO/DPO --
    not a new convention, just that formula's own /days_basis term read back.

    `_cache` (src/semantic/compiler.py's compile_metric) matters a lot here:
    this trend loop compiles dso/dio/dpo for several months, and each of
    those already recomputes a trailing-twelve-months window internally
    (added 2026-08-24) -- those windows overlap almost completely month to
    month, so a shared cache turns what would be dozens of duplicate
    sub-queries into one each."""
    if _cache is None:
        _cache = {}
    months = _trailing_months(period_key)
    charts, trends, day_impact = [], {}, {}
    for metric_id, label in WORKING_CAPITAL_METRICS:
        points = []
        for m in months:
            result = compile_metric(conn, schema, tenant_id, entity_id, metric_id, m, config, _cache)
            points.append((m, result.value if result.status == "ok" else None))
        trends[metric_id] = [{"period": p, "value": v} for p, v in points]
        charts.append(line_chart(f"{label} trend", label, points, unit="days"))

    dso = compile_metric(conn, schema, tenant_id, entity_id, "dso", period_key, config, _cache)
    if dso.status == "ok":
        days_basis = dso.parameters_used.get("days_basis", 365)
        revenue_base = dso.parameters_used.get("revenue_base", "net_revenue")
        base = compile_metric(conn, schema, tenant_id, entity_id, revenue_base, period_key, config, _cache)
        if base.status == "ok":
            day_impact["dso"] = base.value / Decimal(days_basis)
    dpo = compile_metric(conn, schema, tenant_id, entity_id, "dpo", period_key, config, _cache)
    if dpo.status == "ok":
        days_basis = dpo.parameters_used.get("days_basis", 365)
        cost_base = dpo.parameters_used.get("cost_base", "cogs")
        base = compile_metric(conn, schema, tenant_id, entity_id, cost_base, period_key, config, _cache)
        if base.status == "ok":
            day_impact["dpo"] = base.value / Decimal(days_basis)

    return {
        "trends": trends, "rupee_impact_per_day": day_impact,
        "receivable_ageing": None, "payable_ageing": None, "inventory_ageing": None,
        "unavailable_reasons": ["AR/AP ageing and inventory ageing are generated by the synthetic dataset "
                                    "but have no ingestion pipeline built yet (COA/TB/GL/Bank only)"],
    }, charts


# ------------------------------------------------------------------ Section 7

def build_cash_section(conn, schema: str, tenant_id: str, entity_id: int, period_key: str,
                           config: ConfigRegistry, _cache: dict | None = None) -> tuple[dict, list[dict]]:
    """corpus/08 section 7 #7: cash movement, borrowing position, facility
    utilisation. Facility utilisation (a credit limit and its drawn amount)
    has no metric, canonical class or field anywhere in the corpus -- not
    the same OQ-004 gap (that's a formula gap on a defined metric); this is
    simply undeclared, same shape as the UNAVAILABLE_DIMENSIONS entries."""
    months = _trailing_months(period_key)
    cash_points, debt_points = [], []
    for m in months:
        cash_r = compile_metric(conn, schema, tenant_id, entity_id, "cash", m, config, _cache)
        cash_points.append((m, cash_r.value if cash_r.status == "ok" else None))
        debt_r = compile_metric(conn, schema, tenant_id, entity_id, "net_debt", m, config, _cache)
        debt_points.append((m, debt_r.value if debt_r.status == "ok" else None))
    charts = [line_chart("Cash movement", "Cash", cash_points),
                line_chart("Borrowing position", "Net debt", debt_points)]
    return {
        "cash_trend": [{"period": p, "value": v} for p, v in cash_points],
        "borrowing_trend": [{"period": p, "value": v} for p, v in debt_points],
        "facility_utilisation": None,
        "unavailable_reasons": ["facility utilisation (credit limit and drawn amount) has no metric or "
                                    "canonical class anywhere in the corpus"],
    }, charts


# ------------------------------------------------------------------ Section 8

def build_statements(pnl_current, pnl_prior_month, pnl_prior_year, pnl_ytd,
                         bs_current, bs_prior_month, bs_prior_year, cash_flow_result) -> dict:
    """corpus/08 section 7 #8: full P&L, balance sheet and cash flow with
    comparatives, per corpus/08 section 4.2's column spec (selected period,
    prior period, prior year same period, YTD)."""
    return {
        "pnl": {"current": pnl_current, "prior_month": pnl_prior_month,
                  "prior_year": pnl_prior_year, "ytd": pnl_ytd},
        "balance_sheet": {"current": bs_current, "prior_month": bs_prior_month, "prior_year": bs_prior_year},
        "cash_flow": cash_flow_result,
    }


# ------------------------------------------------------------------ Section 9

def build_data_quality_appendix(conn, schema: str, tenant_id: str, unmapped_value_inr: Decimal,
                                    reconciliation_rows: list[dict], known_limitations: list[str]) -> dict:
    """corpus/08 section 7 #9: 'Open exceptions, unmapped value,
    reconciliation residuals, anything the reader should know before
    trusting a figure.' Always present, per corpus/08 section 11's own
    structural test."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT exception_class, severity, description, value_inr FROM "{schema}".exception '
            f"WHERE tenant_id = %s AND status = 'open' "
            f"ORDER BY CASE severity WHEN 'blocking' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, "
            f'value_inr DESC NULLS LAST',
            (tenant_id,),
        )
        open_exceptions = [{"exception_class": c, "severity": s, "description": d,
                                "value_inr": v} for c, s, d, v in cur.fetchall()]
    return {
        "open_exceptions": open_exceptions, "unmapped_value_inr": unmapped_value_inr,
        "reconciliation_residuals": reconciliation_rows, "known_limitations": known_limitations,
    }


# ------------------------------------------------------------------ Orchestrator

def generate_pack(conn, schema: str, tenant_id: str, entity_id: int, profile: str, period_key: str,
                      config: ConfigRegistry, generated_by: str) -> dict:
    """Assembles all eight P0 sections + chart specs. Returns a plain dict
    ready for src/reports/signoff.write_report_artefact -- does not write to
    the DB itself, so it stays unit-testable given a live conn."""
    period_start, period_end = period_bounds(period_key)
    mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, period_end)
    with conn.cursor() as cur:
        cur.execute(f'SELECT version_no FROM "{schema}".mapping_version WHERE mapping_version_id = %s',
                       (mapping_version_id,))
        mapping_version_no = cur.fetchone()[0]

    assemble_pnl = assemble_manufacturing_pnl if profile == "manufacturing" else assemble_consumer_cm_ladder
    pnl_current = assemble_pnl(conn, schema, tenant_id, entity_id, mapping_version_id, period_start, period_end)
    prior_month_key = _shift(period_key, -1)
    prior_year_key = _shift(period_key, -12)
    pm_start, pm_end = period_bounds(prior_month_key)
    py_start, py_end = period_bounds(prior_year_key)
    pnl_prior_month = assemble_pnl(conn, schema, tenant_id, entity_id, mapping_version_id, pm_start, pm_end)
    pnl_prior_year = assemble_pnl(conn, schema, tenant_id, entity_id, mapping_version_id, py_start, py_end)
    fy_start_key = fiscal_year_start(period_key)
    fy_start, _ = period_bounds(fy_start_key)
    pnl_ytd = assemble_pnl(conn, schema, tenant_id, entity_id, mapping_version_id, fy_start, period_end)

    bs_current = assemble_balance_sheet(conn, schema, tenant_id, entity_id, mapping_version_id, period_end)
    bs_prior_month = assemble_balance_sheet(conn, schema, tenant_id, entity_id, mapping_version_id, pm_end)
    bs_prior_year = assemble_balance_sheet(conn, schema, tenant_id, entity_id, mapping_version_id, py_end)

    pnl_movements = class_movements(conn, schema, tenant_id, entity_id, mapping_version_id, period_start, period_end)
    cash_flow_result = assemble_cash_flow_statement(conn, schema, tenant_id, entity_id, mapping_version_id,
                                                          pnl_current.subtotals, pnl_movements, period_start, period_end)

    # One memo shared by every metric this pack compiles (src/semantic/
    # compiler.py's compile_metric) -- the working-capital and financial-
    # summary sections below both resolve dso/dio/dpo and their trailing-
    # twelve-months windows repeatedly across overlapping months.
    _metric_cache: dict = {}
    financial_summary, kpi_charts = build_financial_summary(conn, schema, tenant_id, entity_id, period_key, config, _metric_cache)
    revenue_analysis = build_revenue_analysis(pnl_current, profile)
    margin_analysis, margin_charts = build_margin_analysis(pnl_current, pnl_prior_month)
    working_capital, wc_charts = build_working_capital(conn, schema, tenant_id, entity_id, period_key, config, _metric_cache)
    cash_section, cash_charts = build_cash_section(conn, schema, tenant_id, entity_id, period_key, config, _metric_cache)
    statements = build_statements(pnl_current, pnl_prior_month, pnl_prior_year, pnl_ytd,
                                       bs_current, bs_prior_month, bs_prior_year, cash_flow_result)

    known_limitations = (
        list(revenue_analysis["unavailable_reasons"]) + list(working_capital["unavailable_reasons"])
        + list(cash_section["unavailable_reasons"])
        + ([margin_analysis["gross_margin_bridge_reason"]] if margin_analysis["gross_margin_bridge_reason"] else [])
        + ([cash_flow_result.reason] if cash_flow_result.reason else [])
        + (["balance sheet does not balance for this period"] if not bs_current.balances else [])
    )

    with conn.cursor() as cur:
        cur.execute(
            f'SELECT check_type, status, residual_inr, tolerance_pct, run_at '
            f'FROM "{schema}".reconciliation_run WHERE tenant_id = %s AND entity_id = %s AND period_key = %s '
            f'ORDER BY run_at DESC',
            (tenant_id, entity_id, period_key),
        )
        reconciliation_rows = [{"check_type": ct, "status": st, "residual_inr": res, "tolerance_pct": tol,
                                     "run_at": run_at} for ct, st, res, tol, run_at in cur.fetchall()]

    unmapped_value_inr = pnl_current.unmapped_value_inr
    metric_versions: dict = {}
    for metric_id, _label in HEADLINE_METRICS:
        result = compile_metric(conn, schema, tenant_id, entity_id, metric_id, period_key, config, _metric_cache)
        if result.status == "ok" and result.metric_version is not None:
            metric_versions[metric_id] = result.metric_version

    cover = build_cover(conn, schema, tenant_id, entity_id, profile, period_key, mapping_version_id,
                            mapping_version_no, unmapped_value_inr, metric_versions)
    data_quality_appendix = build_data_quality_appendix(conn, schema, tenant_id, unmapped_value_inr,
                                                              reconciliation_rows, known_limitations)

    sections = _jsonable({
        "1_cover": cover,
        "2_executive_summary": build_executive_summary(None),
        "3_financial_summary": financial_summary,
        "4_revenue_analysis": revenue_analysis,
        "5_margin_analysis": margin_analysis,
        "6_working_capital": working_capital,
        "7_cash": cash_section,
        "8_statements": statements,
        "9_data_quality_appendix": data_quality_appendix,
    })
    chart_specs = _jsonable(kpi_charts + margin_charts + wc_charts + cash_charts)

    return {
        "tenant_id": tenant_id, "entity_id": entity_id, "period_key": period_key, "profile": profile,
        "mapping_version_id": mapping_version_id, "metric_versions": metric_versions,
        "freshness_snapshot": _jsonable(cover["freshness"]), "reconciliation_snapshot": _jsonable(reconciliation_rows),
        "sections": sections, "chart_specs": chart_specs, "commentary": None,
        "unmapped_value_inr": unmapped_value_inr, "generated_by": generated_by,
    }
