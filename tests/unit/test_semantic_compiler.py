"""Unit tests for the transitive dependency-gate closure and period_bounds --
pure logic, exercised against the real config/ registry (no DB: the gate
check only needs decisions.yml and metric contracts, both on disk)."""
from datetime import date

from src.config.loader import load_registry
from src.semantic.compiler import period_bounds, transitive_blocking_decisions


def test_period_bounds():
    assert period_bounds("2026-04") == (date(2026, 4, 1), date(2026, 4, 30))
    assert period_bounds("2024-02") == (date(2024, 2, 1), date(2024, 2, 29))  # leap year


class TestTransitiveGate:
    """corpus/12 sprint 3's own test line: 'a metric with an unresolved
    decision does not serve a default.' These assert the gate reaches every
    metric in a dependency's dependency, not just a metric's own
    governed_by list -- the gap corpus/05's static `compiles` column can't
    express (see this module's docstring).

    D-001, D-002, D-006, D-012, D-015, D-016, D-017 and D-018 were resolved
    2026-08-24 (corpus/00) -- the manufacturing-only D-041/D-042 (unit of
    measure, capacity basis) are the only decisions left blocking anything,
    so the transitive examples below now route through those instead."""

    def setup_method(self):
        self.config = load_registry()

    def test_net_revenue_ebitda_and_working_capital_now_resolve(self):
        # Before 2026-08-24 these were the headline blocked examples (D-006,
        # D-012/D-015/D-016/D-017/D-018 via cogs/inventory). None of them
        # depend on the still-open D-041/D-042/D-050/D-052, so all now
        # resolve cleanly -- this is the direct evidence the resolution
        # actually took effect in the gate, not just in decisions.yml.
        for metric_id in ("net_revenue", "gross_profit", "ebitda", "working_capital",
                              "dso", "dio", "dpo", "ccc"):
            assert transitive_blocking_decisions(metric_id, self.config) == [], metric_id

    def test_cash_and_net_debt_are_not_blocked(self):
        # The two headline tiles that have always compiled: leaf gl_class
        # metrics with no unresolved decision anywhere in their (empty, or
        # cash-only) dependency chain.
        assert transitive_blocking_decisions("cash", self.config) == []
        assert transitive_blocking_decisions("net_debt", self.config) == []

    def test_realisation_per_unit_blocked_directly_and_via_volume_sold(self):
        # realisation_per_unit's own governed_by includes D-041; it also
        # depends on volume_sold, itself blocked by D-041 -- both routes
        # land on the same decision, so it must appear once, not duplicated.
        blocking = transitive_blocking_decisions("realisation_per_unit", self.config)
        assert blocking == ["D-041"]

    def test_capacity_utilisation_transitively_blocked_two_levels_deep(self):
        # capacity_utilisation_pct -> volume_produced -> D-041, plus its own
        # direct D-042 -- two distinct decisions from two different routes.
        blocking = transitive_blocking_decisions("capacity_utilisation_pct", self.config)
        assert set(blocking) == {"D-041", "D-042"}

    def test_no_duplicate_decisions_in_a_wide_dependency_fan(self):
        # capacity_utilisation_pct's own governed_by (D-042) and its
        # dependency's (D-041, via volume_produced) must each appear once.
        blocking = transitive_blocking_decisions("capacity_utilisation_pct", self.config)
        assert len(blocking) == len(set(blocking))
