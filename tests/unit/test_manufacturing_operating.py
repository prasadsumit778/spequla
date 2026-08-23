"""Pure-arithmetic tests for the sprint 6 manufacturing operating layer,
corpus/03 section 6. No DB needed."""
from decimal import Decimal

from src.reports.manufacturing_operating import (
    compute_entity_operating_metrics,
    compute_product_operating_metrics,
)

D = Decimal


def test_yield_and_rejection_pct():
    r = compute_product_operating_metrics(1, "Widget", "MT", D("95"), D("5"), D("105"), is_uom_mismatched=False)
    assert r.status == "ok"
    assert r.rejection_pct == D("5") / D("100")
    assert r.yield_pct == D("95") / D("105")


def test_mixed_uom_blocks_every_per_unit_figure():
    r = compute_product_operating_metrics(1, "Widget", "KG", D("95"), D("5"), D("105"), is_uom_mismatched=True)
    assert r.status == "blocked"
    assert r.yield_pct is None
    assert r.rejection_pct is None
    assert "D-041" in r.reason


def test_entity_metrics_refuse_across_mixed_units():
    # two products, two different units -- must not silently sum them.
    ok_products = [("MT", D("100")), ("KG", D("50"))]
    r = compute_entity_operating_metrics("2026-04", ok_products, D("500000"), D("200000"))
    assert r.status == "blocked"
    assert "different units" in r.reason
    assert r.rm_cost_per_unit is None


def test_entity_metrics_compute_when_units_agree():
    ok_products = [("MT", D("100")), ("MT", D("50"))]
    r = compute_entity_operating_metrics("2026-04", ok_products, D("450000"), D("150000"))
    assert r.status == "ok"
    assert r.total_volume_produced == D("150")
    assert r.rm_cost_per_unit == D("450000") / D("150")
    assert r.conversion_cost_per_unit == D("150000") / D("150")


def test_entity_metrics_blocked_when_no_unblocked_production():
    r = compute_entity_operating_metrics("2026-04", [], D("0"), D("0"))
    assert r.status == "blocked"
    assert r.rm_cost_per_unit is None
