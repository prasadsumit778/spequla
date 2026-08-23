"""Unit tests for src/semantic/formula.py -- pure, no DB needed."""
from decimal import Decimal

import pytest

from src.semantic.formula import (
    DivideByZero,
    FormulaError,
    class_is_credit_natural,
    eval_gl_class_formula,
    eval_metric_formula,
    find_gl_class_patterns,
    match_gl_classes,
    natural_positive,
)

KNOWN = [
    "asset.cash_bank", "asset.fixed_asset_gross", "asset.accumulated_depreciation",
    "liability.debt_term", "liability.debt_working_capital", "liability.debt_related_party",
    "liability.bill_discounting", "equity.share_capital", "equity.reserves",
]


def test_match_gl_classes_exact():
    assert match_gl_classes("asset.cash_bank", KNOWN) == ["asset.cash_bank"]


def test_match_gl_classes_wildcard_prefix_excludes_non_prefixed_siblings():
    matched = match_gl_classes("liability.debt_*", KNOWN)
    assert set(matched) == {"liability.debt_term", "liability.debt_working_capital", "liability.debt_related_party"}
    assert "liability.bill_discounting" not in matched  # different prefix -- corpus/00 OQ-002


def test_match_gl_classes_pipe_list():
    matched = match_gl_classes("equity.share_capital|equity.reserves", KNOWN)
    assert set(matched) == {"equity.share_capital", "equity.reserves"}


def test_match_gl_classes_unknown_pattern_raises():
    with pytest.raises(FormulaError):
        match_gl_classes("asset.nonexistent", KNOWN)


def test_find_gl_class_patterns():
    formula = "gl_class(asset.fixed_asset_gross) - gl_class(asset.accumulated_depreciation)"
    assert find_gl_class_patterns(formula) == ["asset.fixed_asset_gross", "asset.accumulated_depreciation"]


class TestNormalBalanceSign:
    def test_asset_is_debit_natural(self):
        assert class_is_credit_natural("asset.cash_bank") is False
        assert natural_positive("asset.cash_bank", Decimal("1000")) == Decimal("1000")

    def test_liability_is_credit_natural(self):
        assert class_is_credit_natural("liability.debt_term") is True
        assert natural_positive("liability.debt_term", Decimal("-500")) == Decimal("500")

    def test_accumulated_depreciation_is_the_contra_asset_exception(self):
        # Filed under asset.* but carries a natural CREDIT balance -- the one
        # exception a real chart of accounts always has, per
        # src/reports/statement_lines.py's BALANCE_SHEET_LINES comment.
        assert class_is_credit_natural("asset.accumulated_depreciation") is True
        assert natural_positive("asset.accumulated_depreciation", Decimal("-300")) == Decimal("300")


class TestEvalGlClassFormula:
    def test_fixed_assets_net_nets_gross_and_accumulated_depreciation(self):
        # Gross 1000 (Dr, raw +1000), accumulated depreciation 300 (Cr, raw
        # -300) -- the formula must produce 700, not 1300 or 100.
        amounts = {"asset.fixed_asset_gross": Decimal("1000"), "asset.accumulated_depreciation": Decimal("-300")}
        result = eval_gl_class_formula(
            "gl_class(asset.fixed_asset_gross) - gl_class(asset.accumulated_depreciation)", amounts, KNOWN,
        )
        assert result == Decimal("700")

    def test_debt_wildcard_sums_and_flips_to_positive(self):
        amounts = {"liability.debt_term": Decimal("-1500000"), "liability.debt_working_capital": Decimal("-500000")}
        assert eval_gl_class_formula("gl_class(liability.debt_*)", amounts, KNOWN) == Decimal("2000000")

    def test_missing_class_contributes_zero(self):
        assert eval_gl_class_formula("gl_class(asset.cash_bank)", {}, KNOWN) == Decimal("0")

    def test_rejects_non_gl_class_formula(self):
        with pytest.raises(FormulaError):
            eval_gl_class_formula("metric.net_revenue - metric.cogs", {}, KNOWN)


class TestEvalMetricFormula:
    def test_subtraction(self):
        assert eval_metric_formula("metric.net_revenue - metric.cogs",
                                     {"net_revenue": Decimal("100"), "cogs": Decimal("60")}) == Decimal("40")

    def test_division(self):
        result = eval_metric_formula("metric.gross_profit / metric.net_revenue",
                                        {"gross_profit": Decimal("40"), "net_revenue": Decimal("100")})
        assert result == Decimal("0.4")

    def test_division_by_zero_raises_divide_by_zero_not_a_crash(self):
        with pytest.raises(DivideByZero):
            eval_metric_formula("metric.gross_profit / metric.net_revenue",
                                   {"gross_profit": Decimal("40"), "net_revenue": Decimal("0")})

    def test_unknown_token_raises_formula_error(self):
        with pytest.raises(FormulaError):
            eval_metric_formula("metric.inventory / metric.cogs * days_in_period",
                                   {"inventory": Decimal("1"), "cogs": Decimal("1")})

    def test_days_basis_literal_multiplication(self):
        result = eval_metric_formula("metric.accounts_receivable / metric.net_revenue * 365",
                                        {"accounts_receivable": Decimal("1000"), "net_revenue": Decimal("36500")})
        assert result == Decimal("10")
