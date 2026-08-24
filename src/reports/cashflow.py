"""Indirect-method cash flow statement, corpus/08 section 6 + corpus/03
section 4.

"The MVP produces the indirect method, because it derives from the P&L and
balance sheet we already have" (corpus/03 section 4) -- so, like pnl.py and
balance_sheet.py, this reads fact_gl_entry through the resolved mapping
(src/reports/query.py), never through the metric registry.

**working_capital_change is fully specified and computed here.** Corpus/03
section 4: "Negative of: change in AR, plus change in inventory, less change
in AP, less change in other operating balances," with the sign rule stated
as unconditional -- "An increase in receivables or inventory is a use of
cash and is therefore negative. An increase in payables is a source of cash
and is positive. Applied without exception." That "without exception" is
what licenses applying the same rule to every current operating balance
sheet line (asset.advance_supplier, asset.prepaid, etc. and their liability
counterparts), not just AR/inventory/AP by name -- the itemised buckets
(receivables, inventory, payables, other operating) fall out of that single
rule applied to statement_lines.py's existing BALANCE_SHEET_LINES grouping.
Debt and equity classes are excluded from working capital by construction --
they are investing/financing, per corpus/03 section 4's own three-section
split.

**operating_cash_flow, investing_cash_flow, financing_cash_flow, and
therefore closing_cash are NOT fully computable.** See OPEN_QUESTIONS.md
OQ-004: eight of their formula's leaf components (taxes_paid,
asset_disposals, investment_movements, debt_drawn, debt_repaid,
equity_raised, dividends, interest_paid) had no gl_class formula or
canonical class anywhere in the corpus.

OQ-004 resolved 2026-08-24: two of the eight ARE derivable as balance-sheet
deltas using classes the taxonomy already has -- investment_movements from
asset.investment, equity_raised from equity.share_capital -- computed here
the same way capex already was (closing minus opening) and with the same
sign convention _classify_operating_balance uses (asset increase = use of
cash, equity/liability increase = source of cash), for consistency within
this module. The remaining six stay undefined by explicit decision, not
oversight: debt_drawn/debt_repaid can't be split from a single net period-end
balance delta (a draw and a repayment in the same month collapse to one
number), and taxes_paid/dividends/interest_paid/asset_disposals have no
corresponding canonical class for their payable/gross-movement side at all
(see the module-level classes below for exactly which ones and why).

This module computes every component that IS fully specified (pbt, da,
interest_expense, other_income, working_capital_change, capex,
investment_movements, equity_raised) and returns not_configured() for the
rest, per the same disclosed-gap pattern as src/semantic/bridges.py's
compute_margin_bridge. Per corpus/08 section 5's hard gate ("closing_cash
must equal balance sheet cash exactly, or neither displays"), the statement
therefore still does not reconcile and must not be presented as complete --
reconciles=False on the result means exactly that, the same contract as
BalanceSheetResult.balances.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from src.reports.query import class_balances
from src.reports.statement_lines import BALANCE_SHEET_LINES, COST_SIGN, REVENUE_SIGN
from src.semantic.bridges import BridgeResult, not_configured

# Debt and equity classes are excluded from working capital -- they are
# investing/financing per corpus/03 section 4's three-section split, not
# operating. Same class list D-035 defines as "debt" (corpus/00).
_DEBT_AND_EQUITY_CLASSES = {
    "liability.debt_working_capital", "liability.debt_current_maturity", "liability.bill_discounting",
    "liability.debt_term", "liability.debt_related_party", "liability.lease",
    "equity.share_capital", "equity.reserves",
}
# Cash itself is not working capital -- it is what the statement solves for.
_CASH_CLASSES = {"asset.cash_bank", "asset.cash_restricted"}
# Non-current assets other than cash are investing, not operating working capital.
_NON_CURRENT_ASSET_CLASSES = {"asset.deposit", "asset.investment", "asset.fixed_asset_gross",
                                 "asset.accumulated_depreciation", "asset.capital_wip"}

_RECEIVABLE_CLASSES = {"asset.trade_receivable"}
_INVENTORY_CLASSES = {"asset.inventory_rm", "asset.inventory_wip", "asset.inventory_fg",
                        "asset.inventory_packing_stores"}
_PAYABLE_CLASSES = {"liability.trade_payable"}


@dataclass
class WorkingCapitalItem:
    label: str
    movement: Decimal  # cash-flow sign already applied: positive = source of cash


@dataclass
class CashFlowResult:
    period_start: date
    period_end: date
    operating: BridgeResult | None = None
    investing: BridgeResult | None = None
    financing: BridgeResult | None = None
    working_capital_items: list[WorkingCapitalItem] = field(default_factory=list)
    working_capital_change: Decimal = Decimal("0")
    opening_cash: Decimal | None = None
    closing_cash_from_statement: Decimal | None = None
    closing_cash_from_balance_sheet: Decimal | None = None
    reconciles: bool = False
    reason: str | None = None


def _classify_operating_balance(canonical_class: str) -> tuple[str, int] | None:
    """(bucket_label, cash_flow_sign) for a class that belongs in working
    capital, or None if it's cash, debt/equity, or non-current (not
    operating working capital). sign: +1 for an operating liability
    (increase = source of cash), -1 for an operating asset (increase = use
    of cash) -- corpus/03 section 4's rule, applied without exception."""
    if canonical_class in _CASH_CLASSES or canonical_class in _DEBT_AND_EQUITY_CLASSES:
        return None
    if canonical_class in _NON_CURRENT_ASSET_CLASSES:
        return None
    if canonical_class not in BALANCE_SHEET_LINES:
        return None
    group, label, _presentation_sign = BALANCE_SHEET_LINES[canonical_class]
    if group not in ("current_assets", "current_liabilities"):
        return None
    if canonical_class in _RECEIVABLE_CLASSES:
        return "Receivables movement", -1
    if canonical_class in _INVENTORY_CLASSES:
        return "Inventory movement", -1
    if canonical_class in _PAYABLE_CLASSES:
        return "Payables movement", +1
    return "Other operating movement", (-1 if group == "current_assets" else +1)


def compute_working_capital_change(opening_balances: dict[str, Decimal],
                                       closing_balances: dict[str, Decimal]) -> tuple[Decimal, list[WorkingCapitalItem]]:
    """Pure. Returns (working_capital_change, itemised components) per
    corpus/08 section 6's requirement that the working capital section of
    the cash flow be itemised, not a single line."""
    buckets: dict[str, Decimal] = {}
    classes = set(opening_balances) | set(closing_balances)
    for canonical_class in classes:
        classified = _classify_operating_balance(canonical_class)
        if classified is None:
            continue
        label, sign = classified
        delta = closing_balances.get(canonical_class, Decimal("0")) - opening_balances.get(canonical_class, Decimal("0"))
        buckets[label] = buckets.get(label, Decimal("0")) + (delta * sign)

    order = ["Receivables movement", "Inventory movement", "Payables movement", "Other operating movement"]
    items = [WorkingCapitalItem(label, buckets[label]) for label in order if label in buckets]
    total = sum((i.movement for i in items), Decimal("0"))
    return total, items


def compute_operating_cash_flow(pbt: Decimal, da: Decimal, interest_expense: Decimal,
                                    other_income: Decimal, working_capital_change: Decimal) -> BridgeResult:
    """The four fully-specified components of corpus/03 section 4's
    operating_cash_flow formula, minus the undefined taxes_paid term
    (OQ-004). Returned as not_configured -- this is a real cash use the
    company definitely incurs, and presenting a total that omits it without
    saying so would be exactly the 'plausible wrong number' CLAUDE.md section
    1 exists to prevent."""
    computed_before_tax = pbt + da + interest_expense - other_income + working_capital_change
    return not_configured(
        computed_before_tax,
        "operating_cash_flow's taxes_paid component has no formula or canonical class anywhere in the "
        "corpus (OQ-004) -- pbt + da + interest_expense - other_income + working_capital_change = "
        f"{computed_before_tax}, but this is before cash tax paid, not the metric itself",
    )


def compute_investing_cash_flow(capex: Decimal, investment_movements: Decimal) -> BridgeResult:
    """capex is fully specified (D-037, corpus/00). investment_movements is
    now derived (OQ-004, 2026-08-24) as the cash-flow-signed delta of
    asset.investment. asset_disposals is still undefined -- fixed_asset_gross
    only carries a NET movement (additions less disposals), and a single net
    delta cannot be split back into gross disposals the same way debt_drawn
    and debt_repaid can't be recovered from debt's net delta."""
    computed = -capex + investment_movements
    return not_configured(
        computed,
        f"investing_cash_flow's asset_disposals component has no formula or canonical class anywhere in "
        f"the corpus (OQ-004) -- capex + investment_movements alone is {computed}",
    )


def compute_financing_cash_flow(equity_raised: Decimal) -> BridgeResult:
    """equity_raised is now derived (OQ-004, 2026-08-24) as the cash-flow-
    signed delta of equity.share_capital. debt_drawn, debt_repaid, dividends
    and interest_paid stay undefined: debt_drawn/debt_repaid can't be split
    from debt's single net period-end delta (a draw and a repayment in the
    same month collapse to one number), and dividends/interest_paid have no
    payable-side canonical class (no liability.dividend_payable or
    liability.interest_payable exists in the taxonomy) to derive an accrual
    adjustment from."""
    return not_configured(
        equity_raised,
        "financing_cash_flow's debt_drawn, debt_repaid, dividends and interest_paid components have no "
        f"formula or canonical class anywhere in the corpus (OQ-004) -- equity_raised alone is {equity_raised}",
    )


def _bs_delta_cash_flow_signed(opening_balances: dict[str, Decimal], closing_balances: dict[str, Decimal],
                                   canonical_class: str, is_source_side: bool) -> Decimal:
    """(closing - opening) for canonical_class, signed the same way
    _classify_operating_balance signs working-capital deltas: an increase is
    a use of cash (negative) for an asset-side class, a source of cash
    (positive) for a liability/equity-side class. is_source_side=True for
    liability/equity classes (e.g. equity.share_capital), False for asset
    classes (e.g. asset.investment) -- same +1/-1 convention as
    _classify_operating_balance, kept consistent within this module rather
    than re-derived independently for OQ-004's two new components."""
    delta = closing_balances.get(canonical_class, Decimal("0")) - opening_balances.get(canonical_class, Decimal("0"))
    return delta if is_source_side else -delta


def compute_cash_flow_statement(opening_balances: dict[str, Decimal], closing_balances: dict[str, Decimal],
                                    pnl_movements: dict[str, Decimal], pbt: Decimal, da: Decimal,
                                    interest_expense: Decimal, other_income: Decimal, capex: Decimal,
                                    period_start: date, period_end: date) -> CashFlowResult:
    """Pure. Assembles what's computable and marks the rest not_configured
    (see module docstring, OQ-004)."""
    result = CashFlowResult(period_start=period_start, period_end=period_end)

    wc_change, wc_items = compute_working_capital_change(opening_balances, closing_balances)
    result.working_capital_change = wc_change
    result.working_capital_items = wc_items

    investment_movements = _bs_delta_cash_flow_signed(opening_balances, closing_balances,
                                                          "asset.investment", is_source_side=False)
    equity_raised = _bs_delta_cash_flow_signed(opening_balances, closing_balances,
                                                   "equity.share_capital", is_source_side=True)

    result.operating = compute_operating_cash_flow(pbt, da, interest_expense, other_income, wc_change)
    result.investing = compute_investing_cash_flow(capex, investment_movements)
    result.financing = compute_financing_cash_flow(equity_raised)

    result.opening_cash = sum((opening_balances.get(c, Decimal("0")) for c in _CASH_CLASSES), Decimal("0"))
    result.closing_cash_from_balance_sheet = sum(
        (closing_balances.get(c, Decimal("0")) for c in _CASH_CLASSES), Decimal("0"))
    result.reconciles = False
    result.reason = ("operating_cash_flow, investing_cash_flow and financing_cash_flow are not fully "
                        "configured (OQ-004) -- closing cash cannot be derived from the statement, so per "
                        "corpus/08 section 5's hard gate the cash flow statement does not display")
    return result


def assemble_cash_flow_statement(conn, schema: str, tenant_id: str, entity_id: int, mapping_version_id: int,
                                     pnl_subtotals: dict, pnl_movements: dict[str, Decimal],
                                     period_start: date, period_end: date) -> CashFlowResult:
    opening_balances = class_balances(conn, schema, tenant_id, entity_id, mapping_version_id,
                                          period_start - timedelta(days=1))
    closing_balances = class_balances(conn, schema, tenant_id, entity_id, mapping_version_id, period_end)

    def line(classes: set[str]) -> Decimal:
        return sum((pnl_movements.get(c, Decimal("0")) for c in classes), Decimal("0"))

    pbt = pnl_subtotals.get("pbt", Decimal("0"))
    da = line({"da.depreciation", "da.amortisation"}) * COST_SIGN
    interest_expense = line({"finance_cost.interest_debt", "finance_cost.bank_charges", "finance_cost.interest_other"}) * COST_SIGN
    other_income = line({"other_income.interest_income", "other_income.fx_gain", "other_income.misc_income"}) * REVENUE_SIGN

    closing_gross_fixed = (closing_balances.get("asset.fixed_asset_gross", Decimal("0"))
                              + closing_balances.get("asset.capital_wip", Decimal("0")))
    opening_gross_fixed = (opening_balances.get("asset.fixed_asset_gross", Decimal("0"))
                              + opening_balances.get("asset.capital_wip", Decimal("0")))
    capex = closing_gross_fixed - opening_gross_fixed  # D-037: additions to gross block plus CWIP movement

    return compute_cash_flow_statement(opening_balances, closing_balances, pnl_movements, pbt, da,
                                           interest_expense, other_income, capex, period_start, period_end)
