"""The deterministic compiler.

Implements corpus/05a's contract-to-value path. Invoked directly by
(metric_id, tenant, entity, period) rather than through the semantic IR --
that's corpus/07/sprint 4's Ask surface, explicitly out of this sprint's
"AI: None" scope.

Two things this compiler does that config/metrics/'s own `compiles` flag
does not, because that flag only checks a metric's OWN governed_by list:

  1. Transitive dependency-gate closure. gross_profit is marked compiles=yes
     in corpus/05 (it has no unresolved decision of its own), but it depends
     on net_revenue (blocked by D-006) and cogs (blocked by D-012/015/016/
     017/018) -- so gross_profit cannot actually produce a number until
     those resolve. Walking `dependencies` recursively is the only way to
     know this; corpus/05's own compiles/unresolved_decisions columns do
     not express it.
  2. The override resolution chain (src/semantic/overrides.py) and the
     mapping-approval gate (corpus/06 section 6 rule 1) on top of the
     decision gate.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from src.config.loader import ConfigRegistry
from src.reports.query import NoApprovedMappingError, resolve_mapping_version_for_period
from src.semantic.formula import (
    DivideByZero,
    FormulaError,
    eval_gl_class_formula,
    eval_metric_formula,
    find_gl_class_patterns,
    match_gl_classes,
)
from src.semantic.overrides import resolve_parameters


def period_bounds(period_key: str) -> tuple[date, date]:
    """'2026-04' -> (2026-04-01, 2026-04-30)."""
    year, month = (int(p) for p in period_key.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


@dataclass
class CompiledMetric:
    metric_id: str
    status: str = "blocked"          # 'ok' | 'blocked' | 'undefined'
    value: Decimal | None = None
    reason: str | None = None
    blocking_decisions: list[str] = field(default_factory=list)
    metric_version: int | None = None
    definition_source: str | None = None      # 'global_default' | 'company_override' | 'entity_override'
    parameters_used: dict = field(default_factory=dict)
    unit: str | None = None
    source_facts: list[str] = field(default_factory=list)
    row_count: int = 0
    period_key: str = ""
    time_logic: str | None = None
    load_run_ids: set[int] = field(default_factory=set)  # which uploads back this value -- citation.py's source_files
    mapping_version_no: int | None = None  # the mapping_version.version_no that classified the facts, for citation.py


# D-028's resolved text (corpus/00 section 2b): "Period-end AR, net revenue,
# 365 days." D-030's: "On COGS, not purchases." Neither dso nor dpo has a
# `metric_definition` row to read a company override from until one is
# written, so these are the fallback when resolve_parameters finds nothing --
# not an invented default, the resolved decision's own stated resolution.
DSO_DEFAULT_REVENUE_BASE = "net_revenue"
DSO_DEFAULT_DAYS_BASIS = 365
DPO_DEFAULT_COST_BASE = "cogs"
DPO_DEFAULT_DAYS_BASIS = 365


def transitive_blocking_decisions(metric_id: str, config: ConfigRegistry,
                                     _visited: set[str] | None = None) -> list[str]:
    """Every open decision governing metric_id or any metric in its
    dependency closure, deduplicated, in first-encountered order. Empty
    means the metric is not decision-gated -- it may still fail to produce a
    value for an infrastructural reason (no approved mapping, a zero
    denominator), which is a separate, distinct blocked/undefined reason."""
    if _visited is None:
        _visited = set()
    if metric_id in _visited:
        return []
    _visited.add(metric_id)
    if metric_id not in config.metrics:
        raise KeyError(f"unknown metric_id: {metric_id!r}")

    contract = config.metrics[metric_id]
    open_ids = {d.id for d in config.decisions.values() if d.status == "open"}
    blocking = [d for d in contract.registry.governed_by if d in open_ids]
    for dep in contract.registry.dependencies:
        blocking.extend(transitive_blocking_decisions(dep, config, _visited))

    seen: set[str] = set()
    out: list[str] = []
    for d in blocking:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _fetch_leaf_amounts(conn, schema: str, tenant_id: str, entity_id: int, mapping_version_id: int,
                           classes: list[str], time_logic: str,
                           period_start: date, period_end: date) -> tuple[dict[str, Decimal], int, set[int]]:
    """Amount per canonical class, the row count, and the set of load_run_ids
    backing it, scoped to exactly the classes this metric's formula
    references -- narrower than src/reports/query.py's
    class_balances/class_movements (which fetch every class at once for
    statement assembly), because a citation's row_count and source_files
    must describe only the rows that produced THIS metric's value."""
    if not classes:
        return {}, 0, set()
    placeholders = ",".join(["%s"] * len(classes))
    if time_logic == "period_end":
        date_filter = "fg.event_date <= %s"
        date_params: tuple = (period_end,)
    else:  # period_sum: flow within the period
        date_filter = "fg.event_date BETWEEN %s AND %s"
        date_params = (period_start, period_end)

    with conn.cursor() as cur:
        cur.execute(
            f'SELECT ma.canonical_class, SUM(fg.amount_base), COUNT(*) '
            f'FROM "{schema}".fact_gl_entry fg '
            f'JOIN "{schema}".dim_account da ON da.account_key = fg.account_key '
            f'JOIN "{schema}".map_account ma ON ma.mapping_version_id = %s AND ma.source_record_id = da.source_record_id '
            f'WHERE fg.tenant_id = %s AND fg.entity_id = %s AND fg.is_current '
            f'AND ma.canonical_class IN ({placeholders}) AND {date_filter} '
            f'GROUP BY ma.canonical_class',
            (mapping_version_id, tenant_id, entity_id, *classes, *date_params),
        )
        rows = cur.fetchall()
        amounts = {r[0]: r[1] for r in rows}
        row_count = sum(r[2] for r in rows)

        cur.execute(
            f'SELECT DISTINCT fg.load_run_id '
            f'FROM "{schema}".fact_gl_entry fg '
            f'JOIN "{schema}".dim_account da ON da.account_key = fg.account_key '
            f'JOIN "{schema}".map_account ma ON ma.mapping_version_id = %s AND ma.source_record_id = da.source_record_id '
            f'WHERE fg.tenant_id = %s AND fg.entity_id = %s AND fg.is_current '
            f'AND ma.canonical_class IN ({placeholders}) AND {date_filter}',
            (mapping_version_id, tenant_id, entity_id, *classes, *date_params),
        )
        load_run_ids = {r[0] for r in cur.fetchall()}
    return amounts, row_count, load_run_ids


def compile_metric(conn, schema: str, tenant_id: str, entity_id: int, metric_id: str,
                     period_key: str, config: ConfigRegistry) -> CompiledMetric:
    """(metric_id, tenant, entity, period) -> CompiledMetric. Dimensions
    (customer/product/channel/...) are corpus/07's Ask-surface filters --
    out of this sprint's "AI: None" scope, which compiles a period's
    entity-level total directly."""
    if metric_id not in config.metrics:
        raise KeyError(f"unknown metric_id: {metric_id!r}")
    contract = config.metrics[metric_id]
    reg = contract.registry
    period_start, period_end = period_bounds(period_key)

    out = CompiledMetric(metric_id=metric_id, metric_version=reg.version, unit=reg.unit,
                           source_facts=reg.source_facts, period_key=period_key, time_logic=reg.time_logic)

    blocking = transitive_blocking_decisions(metric_id, config)
    if blocking:
        out.reason = f"blocked by {', '.join(blocking)}"
        out.blocking_decisions = blocking
        return out

    global_default_params = contract.model_extra.get("contract", {}).get("parameters", {}) \
        if contract.model_extra else {}
    resolved = resolve_parameters(conn, schema, tenant_id, metric_id, entity_id, period_end,
                                     global_default=global_default_params)
    out.definition_source = resolved.source
    out.parameters_used = resolved.parameters
    if resolved.definition_version is not None:
        out.metric_version = resolved.definition_version

    try:
        mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, period_end)
    except NoApprovedMappingError as e:
        out.reason = str(e)
        return out
    with conn.cursor() as cur:
        cur.execute(f'SELECT version_no FROM "{schema}".mapping_version WHERE mapping_version_id = %s',
                     (mapping_version_id,))
        out.mapping_version_no = cur.fetchone()[0]

    if not reg.dependencies:
        gl_patterns = find_gl_class_patterns(reg.formula)
        if not gl_patterns:
            out.reason = (f"formula {reg.formula!r} has no dependencies and is not a gl_class(...) "
                            f"expression -- not yet implemented by this compiler")
            return out
        known_classes = [c.class_ for c in config.taxonomy]
        try:
            all_classes = sorted({c for pattern in gl_patterns for c in match_gl_classes(pattern, known_classes)})
        except FormulaError as e:
            out.reason = str(e)
            return out
        amounts, row_count, load_run_ids = _fetch_leaf_amounts(conn, schema, tenant_id, entity_id,
                                                                    mapping_version_id, all_classes, reg.time_logic,
                                                                    period_start, period_end)
        try:
            value = eval_gl_class_formula(reg.formula, amounts, known_classes)
        except FormulaError as e:
            out.reason = str(e)
            return out
        out.status = "ok"
        out.value = value
        out.row_count = row_count
        out.load_run_ids = load_run_ids
        return out

    dep_results: dict[str, CompiledMetric] = {
        dep_id: compile_metric(conn, schema, tenant_id, entity_id, dep_id, period_key, config)
        for dep_id in reg.dependencies
    }
    unusable = {k: v for k, v in dep_results.items() if v.status != "ok"}
    if unusable:
        first = next(iter(unusable.values()))
        out.reason = f"dependency {first.metric_id!r} did not resolve: {first.reason}"
        out.blocking_decisions = first.blocking_decisions
        out.status = "blocked" if first.status == "blocked" else "undefined"
        return out

    values = {k: v.value for k, v in dep_results.items()}
    out.row_count = sum(v.row_count for v in dep_results.values())
    for v in dep_results.values():
        out.load_run_ids |= v.load_run_ids

    formula = reg.formula
    if metric_id == "dso":
        revenue_base = out.parameters_used.get("revenue_base", DSO_DEFAULT_REVENUE_BASE)
        days_basis = out.parameters_used.get("days_basis", DSO_DEFAULT_DAYS_BASIS)
        formula = f"metric.accounts_receivable / metric.{revenue_base} * {days_basis}"
        values.setdefault(revenue_base, values.get("net_revenue"))
    elif metric_id == "dpo":
        cost_base = out.parameters_used.get("cost_base", DPO_DEFAULT_COST_BASE)
        days_basis = out.parameters_used.get("days_basis", DPO_DEFAULT_DAYS_BASIS)
        formula = f"metric.accounts_payable / metric.{cost_base} * {days_basis}"
        values.setdefault(cost_base, values.get("cogs"))

    try:
        out.value = eval_metric_formula(formula, values)
        out.status = "ok"
    except DivideByZero:
        out.status = "undefined"
        out.reason = "zero denominator"
    except FormulaError as e:
        out.reason = str(e)
    return out
