"""Unit tests for the pure parts of src/quality/period_state.py."""
from decimal import Decimal

from src.quality.period_state import restatement_notify_required


def test_below_threshold_does_not_notify():
    # 0.2% of period revenue, threshold is 0.25% (D-040)
    assert restatement_notify_required(Decimal("2000"), Decimal("1000000")) is False


def test_above_threshold_notifies():
    assert restatement_notify_required(Decimal("3000"), Decimal("1000000")) is True


def test_exactly_at_threshold_does_not_notify():
    assert restatement_notify_required(Decimal("2500"), Decimal("1000000")) is False


def test_zero_period_revenue_errs_toward_notifying():
    assert restatement_notify_required(Decimal("1"), Decimal("0")) is True


def test_sign_does_not_matter():
    assert restatement_notify_required(Decimal("-3000"), Decimal("1000000")) is True
