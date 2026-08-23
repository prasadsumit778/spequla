"""Unit tests for src/quality/books_to_bank.py's pure arithmetic --
corpus/09 section 3.2."""
from decimal import Decimal

import pytest

from src.quality.books_to_bank import ModelledDifference, compute_reconciliation


def test_residual_is_the_full_gap_when_no_modelled_differences_configured():
    # The honest state before a company's accounting-policy interview has
    # happened: nothing explains the gap yet, so all of it is residual.
    result = compute_reconciliation("2026-04", books_total=Decimal("1000000"), bank_total=Decimal("850000"))
    assert result.modelled_total == Decimal("0")
    assert result.residual == Decimal("150000")


def test_modelled_differences_reduce_the_residual_but_stay_itemised_separately():
    differences = [
        ModelledDifference("credit_period", Decimal("100000"), "Invoiced in April, collected in May"),
        ModelledDifference("tds_deducted", Decimal("20000"), "2% TDS on services"),
    ]
    result = compute_reconciliation("2026-04", books_total=Decimal("1000000"), bank_total=Decimal("850000"),
                                       modelled_differences=differences)
    assert result.modelled_total == Decimal("120000")
    assert result.residual == Decimal("30000")  # 1,000,000 - 850,000 - 120,000
    # Itemised, not collapsed: both categories are still individually visible.
    assert {d.category for d in result.modelled_differences} == {"credit_period", "tds_deducted"}


def test_unknown_category_rejected():
    with pytest.raises(ValueError):
        ModelledDifference("some_other_reason", Decimal("100"), "not one of the seven named categories")


def test_residual_can_be_negative_bank_ahead_of_books():
    result = compute_reconciliation("2026-04", books_total=Decimal("500000"), bank_total=Decimal("600000"))
    assert result.residual == Decimal("-100000")
