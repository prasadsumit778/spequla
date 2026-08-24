"""Balance sheet assembly, corpus/08 section 5.

"Standard grouped presentation: current assets, non-current assets, current
liabilities, non-current liabilities, equity." Profile-agnostic -- the same
assembler serves both companies, since corpus/08 section 5 does not vary the
BS layout by profile the way it does the P&L.

The hard gate: "The balance sheet must balance, and a non-balancing balance
sheet is not displayed at all." balances=False on the result means exactly
that -- the caller must not render it.

Split into a DB-fetching wrapper (assemble_balance_sheet) and a pure function
over an already-fetched {canonical_class: amount} dict (compute_balance_sheet),
so the arithmetic and the balancing check are unit-testable without a live
Postgres connection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from src.reports.query import class_balances
from src.reports.statement_lines import BALANCE_SHEET_LINES


@dataclass
class BalanceSheetResult:
    as_of_date: date
    groups: dict[str, dict[str, Decimal]] = field(default_factory=dict)  # group -> {label: amount}
    group_totals: dict[str, Decimal] = field(default_factory=dict)
    total_assets: Decimal = Decimal("0")
    total_liabilities_and_equity: Decimal = Decimal("0")
    balances: bool = False
    unmapped_value_inr: Decimal = Decimal("0")


def compute_balance_sheet(balances: dict[str, Decimal], as_of_date: date) -> BalanceSheetResult:
    """No closing entry is ever physically posted to the GL (sprint 2 does
    not implement period-end close), but the accounting identity still
    requires one to exist for the balance sheet to balance at all: real
    double-entry systems sweep cumulative P&L into retained earnings at each
    year end. Since the whole ledger trial-balances to exactly zero
    cumulatively (every period does, by construction -- corpus/09 section
    3.1, D-051), the P&L classes' cumulative raw balance and the BS classes'
    cumulative raw balance are mirror images of each other by construction.
    This computes that closing entry on the fly rather than requiring it to
    have been posted -- the same number a real close would produce."""
    result = BalanceSheetResult(as_of_date=as_of_date)
    pnl_raw_total = Decimal("0")

    for canonical_class, raw_amount in balances.items():
        if canonical_class == "suspense.unmapped":
            # Tracked for D-053's badge/block thresholds regardless of where
            # it lands on the sheet -- OQ-007 puts it on the sheet now (see
            # BALANCE_SHEET_LINES), it no longer `continue`s past the line
            # below, but this visibility figure stays independent of that.
            result.unmapped_value_inr += abs(raw_amount)
        if canonical_class not in BALANCE_SHEET_LINES:
            pnl_raw_total += raw_amount  # accumulate for the computed retained-earnings close
            continue
        group, label, sign = BALANCE_SHEET_LINES[canonical_class]
        bucket = result.groups.setdefault(group, {})
        bucket[label] = bucket.get(label, Decimal("0")) + raw_amount * sign

    retained_earnings = -pnl_raw_total  # Dr-heavy P&L (a loss) reduces equity; Cr-heavy (a profit) increases it
    equity_bucket = result.groups.setdefault("equity", {})
    equity_bucket["Retained earnings (computed)"] = equity_bucket.get("Retained earnings (computed)", Decimal("0")) + retained_earnings

    for group, lines in result.groups.items():
        result.group_totals[group] = sum(lines.values(), Decimal("0"))

    result.total_assets = (result.group_totals.get("current_assets", Decimal("0"))
                             + result.group_totals.get("non_current_assets", Decimal("0")))
    result.total_liabilities_and_equity = (
        result.group_totals.get("current_liabilities", Decimal("0"))
        + result.group_totals.get("non_current_liabilities", Decimal("0"))
        + result.group_totals.get("equity", Decimal("0"))
        + result.group_totals.get("unclassified", Decimal("0"))  # OQ-007: suspense.unmapped
    )
    # Zero tolerance, same discipline as the trial balance check (D-051) --
    # corpus/08 section 5 states this as a hard gate, not a rounding-tolerant one.
    result.balances = (result.total_assets == result.total_liabilities_and_equity)
    return result


def assemble_balance_sheet(conn, schema: str, tenant_id: str, entity_id: int,
                              mapping_version_id: int, as_of_date: date) -> BalanceSheetResult:
    balances = class_balances(conn, schema, tenant_id, entity_id, mapping_version_id, as_of_date)
    return compute_balance_sheet(balances, as_of_date)
