"""Unit tests for src/semantic/citation.py's resolving-citation guards,
corpus/07 section 8 / CLAUDE.md invariant 7 -- pure, no DB.

corpus/07 section 8: "Every number carries a citation object, and a number
without a resolving citation is not displayed... Every number is clickable
through to the rows that produced it." These tests cover the two ways a
citation can be built over nothing while looking exactly like one built over
40,000 rows: no source rows at all, and rows with no source file behind them.

No live Postgres needed, deliberately -- both guards short-circuit before
build_citation issues a query, and that is a property worth holding onto: a
citation over nothing is rejected without a round trip. The happy path and
the rows-exist-but-the-file-does-not path do need a database and live in
tests/integration/test_compiler_gate.py.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.semantic.citation import NotCitable, build_citation
from src.semantic.compiler import CompiledMetric


def _resolved(**overrides) -> CompiledMetric:
    """A metric that compiled successfully. Every field the guards read is
    set to a citable value; each test then breaks exactly one of them, so a
    failure names the guard that fired rather than the fixture."""
    fields = {
        "metric_id": "cash",
        "status": "ok",
        "value": Decimal("4210000.00"),
        "metric_version": 1,
        "unit": "inr",
        "source_facts": ["fact_gl_entry"],
        "row_count": 12406,
        "period_key": "2025-03",
        "load_run_ids": {7},
        "mapping_version_no": 1,
    }
    fields.update(overrides)
    return CompiledMetric(**fields)


def test_zero_row_count_is_not_citable():
    """A metric that resolved to a value no rows produced. The value is a
    real Decimal and the status is 'ok' -- nothing else distinguishes it
    from a good number, which is exactly why the guard has to exist."""
    compiled = _resolved(value=Decimal("0.00"), row_count=0, load_run_ids=set())

    with pytest.raises(NotCitable) as excinfo:
        build_citation(None, "tenant_x", "t-1", 1, 1, compiled, "reconciled")

    # The reason must name the metric and the period, so an operator reading
    # a blocked tile knows which number was withheld and for when.
    assert "cash" in str(excinfo.value)
    assert "2025-03" in str(excinfo.value)


def test_zero_row_count_is_rejected_before_any_query():
    """conn=None is the assertion: the guard fires without touching the
    database. A citation over nothing costs no round trip."""
    compiled = _resolved(row_count=0, load_run_ids=set())
    with pytest.raises(NotCitable):
        build_citation(None, "tenant_x", "t-1", 1, 1, compiled, "reconciled")


def test_empty_source_files_is_not_citable():
    """Rows exist, but no upload resolves behind them -- so source_files is
    empty and the number traces to nothing a client ever sent. Reached here
    via an empty load_run_ids, which fetch_source_files answers with [] and
    no query; the same guard covers the case where load_run_ids is populated
    but app.source_file holds no matching row (integration-tested)."""
    compiled = _resolved(row_count=12406, load_run_ids=set())

    with pytest.raises(NotCitable) as excinfo:
        build_citation(None, "tenant_x", "t-1", 1, 1, compiled, "reconciled")

    assert "cash" in str(excinfo.value)
    assert "source file" in str(excinfo.value)
    # Distinct from the zero-rows guard: this one reports rows that DO exist.
    assert "12406" in str(excinfo.value)


def test_zero_rows_and_empty_files_report_the_row_count_guard_first():
    """Both broken at once -- the cheaper, more fundamental guard wins, so
    the reason says "no source rows" rather than the downstream consequence
    of having none."""
    compiled = _resolved(row_count=0, load_run_ids=set())
    with pytest.raises(NotCitable) as excinfo:
        build_citation(None, "tenant_x", "t-1", 1, 1, compiled, "reconciled")
    assert "no source rows produced it" in str(excinfo.value)


def test_unresolved_metric_is_still_not_citable():
    """Regression: the pre-existing guard, unchanged. A blocked metric never
    reaches the new guards -- it is rejected on status alone, before
    row_count is consulted, even with a row count that would otherwise pass."""
    compiled = _resolved(status="blocked", value=None, row_count=12406,
                            blocking_decisions=["D-041"])
    with pytest.raises(NotCitable) as excinfo:
        build_citation(None, "tenant_x", "t-1", 1, 1, compiled, "reconciled")
    assert "did not resolve to a value" in str(excinfo.value)
