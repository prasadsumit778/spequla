"""Month, year and year-to-date comparatives for a metric, corpus/08 section
7 item 3 ("Financial summary: headline metrics with month, year and
year-to-date comparatives") and section 3's tile spec ("change against the
prior month, the change against the same month last year"). D-057
(resolved, corpus/00): prior month and prior year are the mandatory
comparison set; YTD is section 4.2's own additional column
("year to date with its prior year comparative").

Built on src/semantic/compiler.compile_metric directly -- each comparative
is just the same metric compiled for a different period_key, never a
separate formula. YTD sums metrics whose registry `aggregation` is `sum`
(net_revenue, ebitda, ...) across the fiscal year (April, D-038) to date.
Every other metric -- period_end metrics (cash, working_capital, ...) and,
critically, `ratio_of_sums` metrics (dso, dpo, dio, ccc, gross_margin_pct,
all of which carry `time_logic: period_sum` despite being ratios) -- gets
no YTD figure. Naively summing a ratio_of_sums metric's monthly values
would be exactly the average-of-period-ratios CLAUDE.md invariant #11
forbids ("Quarterly gross margin is quarterly gross profit over quarterly
net revenue," never a sum or average of monthly percentages), and a true
YTD ratio-of-sums would need this metric's own numerator/denominator
re-derived over the YTD range, which compile_metric does not do -- so
ytd/ytd_prior_year are None for these rather than invented.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.config.loader import ConfigRegistry
from src.semantic.compiler import CompiledMetric, compile_metric


@dataclass
class Comparatives:
    current: CompiledMetric
    prior_month: CompiledMetric
    prior_year: CompiledMetric
    ytd: CompiledMetric | None = None
    ytd_prior_year: CompiledMetric | None = None


def _shift_period(period_key: str, months: int) -> str:
    year, month = (int(p) for p in period_key.split("-"))
    total = year * 12 + (month - 1) + months
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def fiscal_year_start(period_key: str) -> str:
    """D-038: FY runs April to March. '2026-08' -> '2026-04'; '2026-02' ->
    '2025-04' (still inside the FY that started the prior April)."""
    year, month = (int(p) for p in period_key.split("-"))
    fy_start_year = year if month >= 4 else year - 1
    return f"{fy_start_year:04d}-04"


def _months_in_range(start_key: str, end_key: str) -> list[str]:
    start_y, start_m = (int(p) for p in start_key.split("-"))
    end_y, end_m = (int(p) for p in end_key.split("-"))
    start_idx, end_idx = start_y * 12 + start_m, end_y * 12 + end_m
    return [f"{(i - 1) // 12:04d}-{(i - 1) % 12 + 1:02d}" for i in range(start_idx, end_idx + 1)]


def _sum_ytd(conn, schema: str, tenant_id: str, entity_id: int, metric_id: str, period_key: str,
               config: ConfigRegistry) -> CompiledMetric:
    fy_start = fiscal_year_start(period_key)
    months = _months_in_range(fy_start, period_key)
    parts = [compile_metric(conn, schema, tenant_id, entity_id, metric_id, m, config) for m in months]
    out = CompiledMetric(metric_id=metric_id, period_key=f"{fy_start}..{period_key}")
    unusable = [p for p in parts if p.status != "ok"]
    if unusable:
        first = unusable[0]
        out.reason = f"{first.period_key} did not resolve: {first.reason}"
        out.status = first.status
        out.blocking_decisions = first.blocking_decisions
        return out
    out.status = "ok"
    out.value = sum((p.value for p in parts), Decimal("0")) if parts else None
    out.unit = parts[0].unit if parts else None
    out.metric_version = parts[0].metric_version if parts else None
    out.row_count = sum(p.row_count for p in parts)
    for p in parts:
        out.load_run_ids |= p.load_run_ids
    return out


def compute_comparatives(conn, schema: str, tenant_id: str, entity_id: int, metric_id: str, period_key: str,
                            config: ConfigRegistry) -> Comparatives:
    current = compile_metric(conn, schema, tenant_id, entity_id, metric_id, period_key, config)
    prior_month = compile_metric(conn, schema, tenant_id, entity_id, metric_id, _shift_period(period_key, -1), config)
    prior_year = compile_metric(conn, schema, tenant_id, entity_id, metric_id, _shift_period(period_key, -12), config)

    ytd = ytd_prior_year = None
    aggregation = config.metrics[metric_id].registry.aggregation if metric_id in config.metrics else None
    if aggregation == "sum":
        ytd = _sum_ytd(conn, schema, tenant_id, entity_id, metric_id, period_key, config)
        ytd_prior_year = _sum_ytd(conn, schema, tenant_id, entity_id, metric_id, _shift_period(period_key, -12), config)

    return Comparatives(current=current, prior_month=prior_month, prior_year=prior_year,
                           ytd=ytd, ytd_prior_year=ytd_prior_year)
