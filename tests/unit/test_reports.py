"""Tests for the pure statement-assembly arithmetic, corpus/08 sections 4.1,
4.2 and 5. No DB needed -- these operate on hand-built {canonical_class:
amount} dicts, same shape src/reports/query.py's class_movements/
class_balances would return."""
from datetime import date
from decimal import Decimal

from src.reports.balance_sheet import compute_balance_sheet
from src.reports.cashflow import compute_cash_flow_statement, compute_working_capital_change
from src.reports.pnl import compute_consumer_cm_ladder, compute_manufacturing_pnl

D = Decimal


def test_manufacturing_pnl_full_waterfall():
    movements = {
        "revenue.product_sales": D("-1000000"),
        "contra_revenue.sales_returns": D("20000"),
        "contra_revenue.trade_discount": D("10000"),
        "cogs.raw_material": D("500000"),
        "cogs.direct_labour": D("100000"),
        "opex.employee_cost": D("80000"),
        "opex.owner_remuneration": D("50000"),
        "da.depreciation": D("30000"),
        "other_income.interest_income": D("-5000"),
        "finance_cost.interest_debt": D("15000"),
        "tax.current": D("20000"),
    }
    r = compute_manufacturing_pnl(movements, date(2026, 4, 1), date(2026, 4, 30))
    assert r.lines["Gross revenue"] == D("1000000")
    assert r.subtotals["net_revenue"] == D("970000")   # 1,000,000 - 20,000 - 10,000
    assert r.subtotals["cogs_total"] == D("600000")
    assert r.subtotals["gross_profit"] == D("370000")
    assert r.subtotals["opex_total"] == D("130000")
    assert r.subtotals["ebitda"] == D("240000")
    assert r.subtotals["ebit"] == D("210000")           # 240,000 - 30,000
    assert r.subtotals["pbt"] == D("200000")             # 210,000 + 5,000 - 15,000
    assert r.subtotals["pat"] == D("180000")             # 200,000 - 20,000


def test_manufacturing_pnl_owner_remuneration_and_related_party_are_separate_lines():
    movements = {
        "opex.owner_remuneration": D("50000"),
        "opex.related_party_charges": D("30000"),
        "opex.employee_cost": D("80000"),
    }
    r = compute_manufacturing_pnl(movements, date(2026, 4, 1), date(2026, 4, 30))
    # corpus/08 section 4.2: "always separate lines, even when small."
    assert r.lines["Owner remuneration"] == D("50000")
    assert r.lines["Related party charges"] == D("30000")
    assert r.lines["Employee cost"] == D("80000")
    assert "Owner remuneration" != "Employee cost"


def test_manufacturing_pnl_reports_unmapped_value_separately():
    movements = {"revenue.product_sales": D("-100000"), "suspense.unmapped": D("5000")}
    r = compute_manufacturing_pnl(movements, date(2026, 4, 1), date(2026, 4, 30))
    assert r.unmapped_value_inr == D("5000")
    assert r.lines["Gross revenue"] == D("100000")


def test_consumer_cm_ladder_full_waterfall():
    movements = {
        "revenue.product_sales": D("-300000"),
        "liability.statutory_payable": D("-45000"),
        "contra_revenue.trade_discount": D("20000"),
        "cogs.raw_material": D("100000"),
        "contra_revenue.commission_marketplace": D("15000"),
        "cogs.fulfilment": D("30000"),
        "opex.selling_distribution": D("10000"),
        "opex.marketing_advertising": D("25000"),
        "opex.admin_general": D("12000"),
        "opex.employee_cost": D("18000"),
    }
    r = compute_consumer_cm_ladder(movements, date(2026, 4, 1), date(2026, 4, 30))
    assert r.subtotals["gross_revenue"] == D("300000")
    assert r.lines["GST"] == D("45000")
    assert r.subtotals["gmv"] == D("345000")             # GMV - GST = Gross revenue, exactly
    assert r.subtotals["gmv"] - r.lines["GST"] == r.subtotals["gross_revenue"]
    assert r.subtotals["net_revenue"] == D("280000")     # 300,000 - 20,000
    assert r.subtotals["gross_margin"] == D("165000")    # 280,000 - 115,000 (COGS incl. commission borne, D-004)
    assert r.subtotals["cm1"] == D("125000")               # 165,000 - 40,000
    assert r.subtotals["cm2"] == D("100000")               # 125,000 - 25,000
    assert r.subtotals["ebitda"] == D("70000")             # 100,000 - 30,000


def test_consumer_marketing_never_enters_cm1():
    # invariant #14: marketing only appears in the CM1 -> CM2 step.
    movements = {
        "revenue.product_sales": D("-100000"), "liability.statutory_payable": D("-15000"),
        "opex.marketing_advertising": D("50000"),
    }
    r = compute_consumer_cm_ladder(movements, date(2026, 4, 1), date(2026, 4, 30))
    assert r.subtotals["cm1"] == r.subtotals["gross_margin"]  # marketing did not touch CM1
    assert r.subtotals["cm2"] == r.subtotals["cm1"] - D("50000")


def test_marketplace_commission_borne_is_cogs_not_marketing_or_cm1():
    # D-004: commission borne is "a cost line above gross profit."
    movements = {
        "revenue.product_sales": D("-100000"), "liability.statutory_payable": D("-15000"),
        "contra_revenue.commission_marketplace": D("20000"),
    }
    r = compute_consumer_cm_ladder(movements, date(2026, 4, 1), date(2026, 4, 30))
    assert r.subtotals["gross_margin"] == r.subtotals["net_revenue"] - D("20000")
    assert r.lines["Operating cost"] == D("0")   # did not land in the CM1 rung
    assert r.lines["Marketing"] == D("0")         # did not land in the marketing rung


def test_balance_sheet_balances_with_computed_retained_earnings():
    balances = {
        "asset.cash_bank": D("1000000"),
        "asset.trade_receivable": D("500000"),
        "liability.trade_payable": D("-300000"),
        "equity.share_capital": D("-1000000"),
        "revenue.product_sales": D("-500000"),
        "cogs.raw_material": D("300000"),
    }
    r = compute_balance_sheet(balances, date(2026, 4, 30))
    assert r.total_assets == D("1500000")
    assert r.total_liabilities_and_equity == D("1500000")
    assert r.balances is True
    assert r.groups["equity"]["Retained earnings (computed)"] == D("200000")  # 500,000 - 300,000


def test_balance_sheet_accumulated_depreciation_reduces_fixed_assets_net():
    balances = {
        "asset.fixed_asset_gross": D("1000000"),
        "asset.accumulated_depreciation": D("-300000"),
        "asset.cash_bank": D("300000"),
        "equity.share_capital": D("-1000000"),
    }
    r = compute_balance_sheet(balances, date(2026, 4, 30))
    assert r.groups["non_current_assets"]["Fixed assets, net"] == D("700000")  # 1,000,000 - 300,000
    assert r.balances is True


def test_balance_sheet_does_not_balance_when_a_side_is_missing():
    balances = {"asset.cash_bank": D("500000"), "equity.share_capital": D("-400000")}
    r = compute_balance_sheet(balances, date(2026, 4, 30))
    assert r.balances is False


def test_balance_sheet_reports_unmapped_value_separately():
    balances = {"asset.cash_bank": D("500000"), "equity.share_capital": D("-500000"), "suspense.unmapped": D("8000")}
    r = compute_balance_sheet(balances, date(2026, 4, 30))
    assert r.unmapped_value_inr == D("8000")


# ----------------------------------------------------------- cash flow (Sprint 5)

def test_working_capital_change_matches_corpus_sign_rule():
    # corpus/03 section 4: increase in AR/inventory is a use of cash
    # (negative); increase in AP is a source of cash (positive).
    opening = {"asset.trade_receivable": D("100000"), "asset.inventory_rm": D("50000"),
                "liability.trade_payable": D("40000")}
    closing = {"asset.trade_receivable": D("150000"), "asset.inventory_rm": D("30000"),
                "liability.trade_payable": D("70000")}
    total, items = compute_working_capital_change(opening, closing)
    by_label = {i.label: i.movement for i in items}
    assert by_label["Receivables movement"] == D("-50000")   # AR up 50,000 -> use of cash
    assert by_label["Inventory movement"] == D("20000")        # inventory DOWN 20,000 -> source of cash
    assert by_label["Payables movement"] == D("30000")           # AP up 30,000 -> source of cash
    assert total == D("-50000") + D("20000") + D("30000")


def test_working_capital_change_excludes_debt_and_cash():
    # debt and cash movements must never leak into working capital -- they
    # are financing and "what the statement solves for," respectively.
    opening = {"asset.cash_bank": D("100000"), "liability.debt_term": D("200000")}
    closing = {"asset.cash_bank": D("400000"), "liability.debt_term": D("500000")}
    total, items = compute_working_capital_change(opening, closing)
    assert items == []
    assert total == D("0")


def test_working_capital_change_itemises_other_operating_balances():
    opening = {"asset.prepaid": D("10000"), "liability.statutory_payable": D("5000")}
    closing = {"asset.prepaid": D("15000"), "liability.statutory_payable": D("20000")}
    total, items = compute_working_capital_change(opening, closing)
    by_label = {i.label: i.movement for i in items}
    # prepaid (asset) up 5,000 -> -5,000; statutory payable (liability) up 15,000 -> +15,000
    assert by_label["Other operating movement"] == D("-5000") + D("15000")


def test_cash_flow_statement_reports_gap_honestly_not_a_fabricated_total():
    # OQ-004: operating/investing/financing are not fully computable. The
    # statement must say so, not sweep the gap into a number.
    opening = {"asset.cash_bank": D("100000")}
    closing = {"asset.cash_bank": D("250000")}
    r = compute_cash_flow_statement(opening, closing, {}, pbt=D("80000"), da=D("10000"),
                                        interest_expense=D("5000"), other_income=D("2000"), capex=D("30000"),
                                        period_start=date(2026, 4, 1), period_end=date(2026, 4, 30))
    assert r.operating.configured is False
    assert r.investing.configured is False
    assert r.financing.configured is False
    assert r.reconciles is False
    assert r.reason is not None
    assert r.opening_cash == D("100000")
    assert r.closing_cash_from_balance_sheet == D("250000")
    # what IS computable is still surfaced, not hidden behind the gap
    assert r.operating.total_delta == D("80000") + D("10000") + D("5000") - D("2000") + D("0")
