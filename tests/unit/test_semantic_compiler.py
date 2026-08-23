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
    express (see this module's docstring)."""

    def setup_method(self):
        self.config = load_registry()

    def test_net_revenue_blocked_directly_and_via_gross_revenue(self):
        # net_revenue's own governed_by includes D-006; it also depends on
        # gross_revenue, which is blocked by D-001/D-002 -- both surface.
        blocking = transitive_blocking_decisions("net_revenue", self.config)
        assert set(blocking) == {"D-006", "D-001", "D-002"}

    def test_gross_profit_transitively_blocked_via_net_revenue_and_cogs(self):
        # gross_profit's OWN governed_by is empty and corpus/05 marks it
        # compiles=yes -- it only becomes unblockable once its dependencies
        # (net_revenue, cogs) are walked.
        blocking = transitive_blocking_decisions("gross_profit", self.config)
        assert "D-006" in blocking          # via net_revenue
        for d in ("D-012", "D-015", "D-016", "D-017", "D-018"):
            assert d in blocking             # via cogs

    def test_ebitda_transitively_blocked_two_levels_deep(self):
        # ebitda -> gross_profit -> {net_revenue, cogs}. ebitda's own
        # governed_by (D-021/D-022/D-025/D-026) is fully resolved.
        blocking = transitive_blocking_decisions("ebitda", self.config)
        assert "D-006" in blocking
        assert "D-012" in blocking
        for own in ("D-021", "D-022", "D-025", "D-026"):
            assert own not in blocking  # resolved -- must not appear as a blocker

    def test_cash_and_net_debt_are_not_blocked(self):
        # The two headline tiles that genuinely compile for the synthetic
        # manufacturer today: leaf gl_class metrics with no unresolved
        # decision anywhere in their (empty, or cash-only) dependency chain.
        assert transitive_blocking_decisions("cash", self.config) == []
        assert transitive_blocking_decisions("net_debt", self.config) == []

    def test_working_capital_blocked_via_inventory(self):
        blocking = transitive_blocking_decisions("working_capital", self.config)
        assert blocking == ["D-018"]

    def test_dso_dio_dpo_all_transitively_blocked(self):
        assert set(transitive_blocking_decisions("dso", self.config)) == {"D-006", "D-001", "D-002"}
        dio_blocking = transitive_blocking_decisions("dio", self.config)
        assert set(dio_blocking) == {"D-018", "D-012", "D-015", "D-016", "D-017"}
        assert set(transitive_blocking_decisions("dpo", self.config)) == \
            {"D-012", "D-015", "D-016", "D-017", "D-018"}

    def test_no_duplicate_decisions_in_a_wide_dependency_fan(self):
        # ccc depends on dso, dio, dpo -- all three route back through cogs.
        # D-012 etc. must appear once, not three times.
        blocking = transitive_blocking_decisions("ccc", self.config)
        assert len(blocking) == len(set(blocking))
