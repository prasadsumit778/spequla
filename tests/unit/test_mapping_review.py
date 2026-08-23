"""Tests for the pure parts of the review/freeze logic, corpus/06 section 4.3/6
and corpus/06a's Coverage tab freeze gate."""
from decimal import Decimal

from src.mapping.review import COVERAGE_THRESHOLD, compute_coverage


def test_coverage_full():
    assert compute_coverage(Decimal("1000"), Decimal("1000")) == Decimal("1")


def test_coverage_zero_total_is_trivially_full():
    assert compute_coverage(Decimal("0"), Decimal("0")) == Decimal("1")


def test_coverage_below_threshold():
    coverage = compute_coverage(Decimal("1000000"), Decimal("970000"))
    assert coverage < COVERAGE_THRESHOLD


def test_coverage_at_threshold_passes():
    coverage = compute_coverage(Decimal("1000000"), Decimal("980000"))
    assert coverage >= COVERAGE_THRESHOLD
