"""P&L assembly: manufacturing cost-structure layout (corpus/08 section 4.2)
and consumer CM ladder (corpus/08 section 4.1).

Both read fact_gl_entry through the mapping resolved for the reporting
period (src/reports/query.py) -- never through the metric registry
(config/metrics/), which governs the Ask/query surface (sprint 3+), not
statement assembly. Corpus/08 section 4.2 says statements are "assembled
from statement_line on dim_account," i.e. directly from the mapping, and
that is a different, unblocked path from the compilation-gated metric
contracts (src/config/loader.py) -- a statement built from THIS company's
own mapped ledgers ties to its own books regardless of which per-company
conventions (D-012, D-015, etc.) the metric registry is still waiting on.

Each assembler is split into a DB-fetching wrapper (assemble_*) and a pure
function over an already-fetched {canonical_class: amount} dict (compute_*),
so the arithmetic is unit-testable without a live Postgres connection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from src.reports.query import class_movements
from src.reports.statement_lines import (
    CONSUMER_COGS_CLASSES,
    CONSUMER_CORPORATE_OVERHEAD_CLASSES,
    CONSUMER_DISCOUNT_CLASSES,
    CONSUMER_GROSS_REVENUE_CLASSES,
    CONSUMER_GST_CLASSES,
    CONSUMER_MARKETING_CLASSES,
    CONSUMER_OPERATING_COST_CM1_CLASSES,
    MANUFACTURING_CONDITIONAL_LINES,
    MANUFACTURING_PNL_LINES,
    MANUFACTURING_SECTIONS,
    REVENUE_SIGN,
)

# Explicit per-class sign for the consumer ladder's group sums -- Dr positive
# / Cr negative in fact_gl_entry (corpus/03 section 1); credit-side classes
# are flipped to the statement's presentation-positive.
_CONSUMER_CREDIT_SIDE_CLASSES = {"revenue.product_sales", "liability.statutory_payable"}


@dataclass
class PnLResult:
    profile: str
    period_start: date
    period_end: date
    lines: dict[str, Decimal] = field(default_factory=dict)   # presentation line -> amount, sign-adjusted
    subtotals: dict[str, Decimal] = field(default_factory=dict)
    unmapped_value_inr: Decimal = Decimal("0")


def _presented(raw_amount: Decimal, sign: int) -> Decimal:
    return raw_amount * sign


def compute_manufacturing_pnl(movements: dict[str, Decimal], period_start: date, period_end: date) -> PnLResult:
    """Pure: corpus/08 section 4.2, row order and grouping exact."""
    result = PnLResult(profile="manufacturing", period_start=period_start, period_end=period_end)

    for canonical_class, raw_amount in movements.items():
        if canonical_class == "suspense.unmapped":
            result.unmapped_value_inr += abs(raw_amount)
            continue
        if canonical_class not in MANUFACTURING_PNL_LINES:
            continue  # a BS class or a class this profile's layout doesn't show
        label, sign, _ordinal = MANUFACTURING_PNL_LINES[canonical_class]
        result.lines[label] = result.lines.get(label, Decimal("0")) + _presented(raw_amount, sign)

    # corpus/08 section 4.2's row sequence is the layout, not a summary of what
    # happened to have data. Every unconditional row is present, at zero where
    # this company posted nothing to it.
    for section_lines in MANUFACTURING_SECTIONS.values():
        for label in section_lines:
            if label not in result.lines and label not in MANUFACTURING_CONDITIONAL_LINES:
                result.lines[label] = Decimal("0")

    def line(label: str) -> Decimal:
        return result.lines.get(label, Decimal("0"))

    gross_revenue = line("Gross revenue")
    net_revenue = gross_revenue - line("Returns") - line("Discounts and rate differences")
    cogs_total = sum((line(l) for l in MANUFACTURING_SECTIONS["cogs"]), Decimal("0"))
    gross_profit = net_revenue - cogs_total
    opex_total = sum((line(l) for l in MANUFACTURING_SECTIONS["opex"]), Decimal("0"))
    ebitda = gross_profit - opex_total
    da_total = sum((line(l) for l in MANUFACTURING_SECTIONS["below_ebitda"]), Decimal("0"))
    ebit = ebitda - da_total
    other_income = line("Other income")
    finance_cost = line("Finance cost")
    pbt = ebit + other_income - finance_cost
    tax = line("Tax")
    pat = pbt - tax

    result.subtotals = {
        "net_revenue": net_revenue, "gross_profit": gross_profit, "ebitda": ebitda,
        "ebit": ebit, "pbt": pbt, "pat": pat,
        "cogs_total": cogs_total, "opex_total": opex_total,
    }
    return result


def assemble_manufacturing_pnl(conn, schema: str, tenant_id: str, entity_id: int,
                                  mapping_version_id: int, period_start: date, period_end: date) -> PnLResult:
    movements = class_movements(conn, schema, tenant_id, entity_id, mapping_version_id, period_start, period_end)
    return compute_manufacturing_pnl(movements, period_start, period_end)


def compute_consumer_cm_ladder(movements: dict[str, Decimal], period_start: date, period_end: date) -> PnLResult:
    """Pure: corpus/08 section 4.1. GMV and GST are not simple group-by
    targets -- see statement_lines.py's module docstring: GST here is booked
    on the pre-discount gross specifically so GMV - GST = Gross revenue holds
    exactly (a choice made in the synthetic data, documented there)."""
    result = PnLResult(profile="consumer", period_start=period_start, period_end=period_end)

    def sum_classes(classes: list[str]) -> Decimal:
        total = Decimal("0")
        for c in classes:
            sign = REVENUE_SIGN if c in _CONSUMER_CREDIT_SIDE_CLASSES else 1
            total += _presented(movements.get(c, Decimal("0")), sign)
        return total

    result.unmapped_value_inr = abs(movements.get("suspense.unmapped", Decimal("0")))

    gross_revenue = sum_classes(CONSUMER_GROSS_REVENUE_CLASSES)          # revenue.*, sign-flipped to positive
    gst = sum_classes(CONSUMER_GST_CLASSES)                                # liability.*, sign-flipped to positive
    gmv = gross_revenue + gst
    discount = sum_classes(CONSUMER_DISCOUNT_CLASSES)                      # contra_revenue.*, cost-sign (already positive)
    net_revenue = gross_revenue - discount
    cogs_total = sum_classes(CONSUMER_COGS_CLASSES)
    gross_margin = net_revenue - cogs_total
    operating_cost_cm1 = sum_classes(CONSUMER_OPERATING_COST_CM1_CLASSES)
    cm1 = gross_margin - operating_cost_cm1
    marketing = sum_classes(CONSUMER_MARKETING_CLASSES)
    cm2 = cm1 - marketing
    corporate_overhead = sum_classes(CONSUMER_CORPORATE_OVERHEAD_CLASSES)
    ebitda = cm2 - corporate_overhead

    result.lines = {
        "GMV": gmv, "GST": gst, "Gross revenue": gross_revenue, "Discount": discount,
        "Net revenue": net_revenue, "Cost of goods sold": cogs_total, "Operating cost": operating_cost_cm1,
        "Marketing": marketing, "Corporate overhead": corporate_overhead,
    }
    result.subtotals = {
        "gmv": gmv, "gross_revenue": gross_revenue, "net_revenue": net_revenue,
        "gross_margin": gross_margin, "cm1": cm1, "cm2": cm2, "ebitda": ebitda,
        "gross_margin_pct": (gross_margin / net_revenue) if net_revenue else None,
        "cm1_pct": (cm1 / net_revenue) if net_revenue else None,
        "cm2_pct": (cm2 / net_revenue) if net_revenue else None,
    }
    return result


def assemble_consumer_cm_ladder(conn, schema: str, tenant_id: str, entity_id: int,
                                   mapping_version_id: int, period_start: date, period_end: date) -> PnLResult:
    movements = class_movements(conn, schema, tenant_id, entity_id, mapping_version_id, period_start, period_end)
    return compute_consumer_cm_ladder(movements, period_start, period_end)
