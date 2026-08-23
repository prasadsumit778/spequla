"""Unit tests for the pure parts of src/quality/checks.py."""
from decimal import Decimal

from src.quality.checks import cash_flow_ties_to_balance_sheet


def test_ties_when_equal():
    ok, reason = cash_flow_ties_to_balance_sheet(Decimal("100"), Decimal("100"))
    assert ok is True
    assert reason is None


def test_does_not_tie_when_different():
    ok, reason = cash_flow_ties_to_balance_sheet(Decimal("100"), Decimal("95"))
    assert ok is False
    assert "100" in reason and "95" in reason


def test_missing_figure_does_not_display():
    ok, reason = cash_flow_ties_to_balance_sheet(None, Decimal("100"))
    assert ok is False
    assert reason is not None
