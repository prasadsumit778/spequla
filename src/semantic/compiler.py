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
# dio's formula (corpus/05) is `metric.inventory / metric.cogs *
# days_in_period` -- `days_in_period` was never substituted for anything
# (found 2026-08-24 while fixing the gross_revenue/net_revenue/cogs chain: a
# real gap, not a decision block -- dso and dpo already had this same
# placeholder problem and were already given the fix below; dio's own
# elif branch was simply never written). Same 365-day annualisation
# convention as dso/dpo, not a new decision -- D-031 (corpus/00) resolves
# dio's COST base and inventory buckets, not its days basis, and no corpus
# file states a different days-basis for dio than the one already used for
# its two sibling ratios.
DIO_DEFAULT_DAYS_BASIS = 365


def _trailing_twelve_months_value(conn, schema: str, tenant_id: str, entity_id: int, metric_id: str,
                                    period_key: str, config: ConfigRegistry,
                                    _cache: dict[tuple[str, str], "CompiledMetric"]) -> Decimal:
    """Sum of metric_id's period_sum value over the trailing twelve calendar
    months ending at (and including) period_key. D-028/D-030/D-031 (corpus/00)
    resolve dso/dpo/dio's days_basis to 365 -- that convention only measures
    real days when the revenue/cost side is an annual flow, not the single
    compiled month. Before this, dso/dpo/dio divided a one-month
    net_revenue/cogs figure by 365, inflating every result by roughly
    365/30 (found 2026-08-24 running the fixed generator's baseline end to
    end: DIO compiled at 843 days against a balance that is genuinely ~2.3
    months of monthly COGS). Months with no resolvable value (before the
    entity's first ingested period) contribute zero -- a rolling trailing
    window, not a requirement that 12 full months of history exist."""
    year, month = (int(x) for x in period_key.split("-"))
    total = Decimal("0")
    for i in range(12):
        m, y = month - i, year
        while m <= 0:
            m += 12
            y -= 1
        result = _compile_metric_cached(conn, schema, tenant_id, entity_id, metric_id, f"{y:04d}-{m:02d}", config, _cache)
        if result.status == "ok" and result.value is not None:
            total += result.value
    return total


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
                     period_key: str, config: ConfigRegistry,
                     _cache: dict[tuple[str, str], CompiledMetric] | None = None) -> CompiledMetric:
    """(metric_id, tenant, entity, period) -> CompiledMetric. Dimensions
    (customer/product/channel/...) are corpus/07's Ask-surface filters --
    out of this sprint's "AI: None" scope, which compiles a period's
    entity-level total directly.

    `_cache` is an optional, caller-owned memo shared across one logical
    request (e.g. one /overview/tiles call): dso/dio/dpo each recompute up to
    twelve months of net_revenue/cogs (_trailing_twelve_months_value, added
    2026-08-24 alongside that fix), and dio/dpo's trailing windows overlap
    completely -- without sharing a cache across the handful of top-level
    compile_metric calls a single page makes, that's dozens of redundant
    round trips to a remote Postgres for values already computed a few
    calls earlier. Internal to this module; every recursive call site below
    passes the same dict through instead of leaving the default and
    starting a fresh (uncached) one."""
    if _cache is None:
        _cache = {}
    return _compile_metric_cached(conn, schema, tenant_id, entity_id, metric_id, period_key, config, _cache)


def _compile_metric_cached(conn, schema: str, tenant_id: str, entity_id: int, metric_id: str,
                              period_key: str, config: ConfigRegistry,
                              _cache: dict[tuple[str, str], CompiledMetric]) -> CompiledMetric:
    cache_key = (metric_id, period_key)
    if cache_key in _cache:
        return _cache[cache_key]
    result = _compile_metric_impl(conn, schema, tenant_id, entity_id, metric_id, period_key, config, _cache)
    _cache[cache_key] = result
    return result


def _compile_metric_impl(conn, schema: str, tenant_id: str, entity_id: int, metric_id: str,
                            period_key: str, config: ConfigRegistry,
                            _cache: dict[tuple[str, str], CompiledMetric]) -> CompiledMetric:
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

    # corpus/05a's worked contracts declare each parameter as a small schema
    # -- {options, default, governed_by, note} -- not the resolved value
    # itself (config/metrics/dso.yml's revenue_base is the clearest example).
    # resolve_parameters/overrides.py expects a flat {name: value} mapping
    # throughout (an analyst-set override row in metric_definition already
    # is one), so the nested schema is flattened to its .default here, at
    # the one place it's read out of the contract -- found 2026-08-24 when
    # dso first actually ran against real data and crashed passing the whole
    # nested dict through as a value (and, for dso/dpo, later used as a dict
    # key) instead of just "net_revenue"/"cogs".
    _raw_params = contract.model_extra.get("contract", {}).get("parameters", {}) \
        if contract.model_extra else {}
    global_default_params = {
        name: (spec.get("default") if isinstance(spec, dict) else spec)
        for name, spec in _raw_params.items()
    }
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
        dep_id: _compile_metric_cached(conn, schema, tenant_id, entity_id, dep_id, period_key, config, _cache)
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

    # CLAUDE.md invariant 7 / corpus/07 section 8: a citation must resolve to
    # source rows. corpus/05's `source_facts` column carries the literal
    # sentinel 'derived' for every metric defined over other metrics, which
    # names no table and resolves to nothing on its own. Replace it with the
    # union of what the dependency closure actually read -- the same reason
    # row_count and load_run_ids are aggregated here rather than left empty.
    inherited: list[str] = []
    for v in dep_results.values():
        for f in v.source_facts:
            if f != "derived" and f not in inherited:
                inherited.append(f)
    out.source_facts = [f for f in reg.source_facts if f != "derived"] + \
                          [f for f in inherited if f not in reg.source_facts]

    formula = reg.formula
    if metric_id == "dso":
        revenue_base = out.parameters_used.get("revenue_base", DSO_DEFAULT_REVENUE_BASE)
        days_basis = out.parameters_used.get("days_basis", DSO_DEFAULT_DAYS_BASIS)
        formula = f"metric.accounts_receivable / metric.{revenue_base} * {days_basis}"
        values[revenue_base] = _trailing_twelve_months_value(
            conn, schema, tenant_id, entity_id, revenue_base, period_key, config, _cache)
    elif metric_id == "dpo":
        cost_base = out.parameters_used.get("cost_base", DPO_DEFAULT_COST_BASE)
        days_basis = out.parameters_used.get("days_basis", DPO_DEFAULT_DAYS_BASIS)
        formula = f"metric.accounts_payable / metric.{cost_base} * {days_basis}"
        values[cost_base] = _trailing_twelve_months_value(
            conn, schema, tenant_id, entity_id, cost_base, period_key, config, _cache)
    elif metric_id == "dio":
        days_basis = out.parameters_used.get("days_basis", DIO_DEFAULT_DAYS_BASIS)
        formula = f"metric.inventory / metric.cogs * {days_basis}"
        values["cogs"] = _trailing_twelve_months_value(
            conn, schema, tenant_id, entity_id, "cogs", period_key, config, _cache)

    try:
        out.value = eval_metric_formula(formula, values)
        out.status = "ok"
    except DivideByZero:
        out.status = "undefined"
        out.reason = "zero denominator"
    except FormulaError as e:
        out.reason = str(e)
    return out
