"""Sprint 3 acceptance criterion (corpus/12): 'a period is marked reconciled
with a visible residual, and every metric on the overview screen carries a
citation that resolves to source rows.'

Read literally against invariant #7 ("a number without a resolving citation
is not displayed... not badged, not greyed out. Not displayed"), the second
half means: every one of the nine tiles either (a) resolved to a value and
carries a full, resolving citation, or (b) did not resolve and carries no
citation and no value at all -- never a fabricated number, never a citation
attached to nothing. This test asserts exactly that property across all
nine tiles, not just the two (cash, net_debt) that currently resolve for
the synthetic manufacturer -- see src/semantic/compiler.py's module
docstring for why the other seven are correctly gated, not a shortfall.

Needs live Postgres (see tests/conftest.py) -- skips cleanly otherwise,
consistent with every other sprint's DB-dependent acceptance test.
"""
from __future__ import annotations

from datetime import date

from src.config.loader import load_registry
from src.quality.books_to_bank import run_books_to_bank, write_reconciliation_run
from src.quality.period_state import get_current_period_lock, map_period, reconcile_period, validate_period
from src.quality.trial_balance import check_trial_balance
from src.semantic.citation import NotCitable, build_citation
from src.semantic.compiler import compile_metric
from tests.helpers import ingest_manufacturer, run_and_freeze_mapping

NINE_TILES = ["net_revenue", "gross_margin_pct", "ebitda", "cash", "net_debt",
                "working_capital", "dso", "dio", "dpo"]


def test_period_reaches_reconciled_with_a_visible_residual(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, _summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                              effective_from=date(2022, 4, 1))
    assert freeze.passed, freeze.reason
    period_key = "2025-03"

    validate_period(conn, schema, tenant_id, entity_id, period_key, version_id, blocking_exception_count=0)
    map_period(conn, schema, tenant_id, entity_id, period_key, version_id,
                 freeze_passed=freeze.passed, coverage_pct=freeze.coverage_pct)

    tb = check_trial_balance(conn, schema, tenant_id, period_key)
    assert tb.balanced

    recon = run_books_to_bank(conn, schema, tenant_id, entity_id, version_id, period_key)
    recon_id = write_reconciliation_run(conn, schema, tenant_id, entity_id, version_id,
                                            "books_to_bank", recon, "pytest-analyst")

    reconcile_period(conn, schema, tenant_id, entity_id, period_key, version_id,
                        trial_balance_balanced=tb.balanced, reconciliation_run_id=recon_id,
                        approved_by="pytest-analyst")

    current = get_current_period_lock(conn, schema, tenant_id, entity_id, period_key)
    assert current.status == "reconciled"
    # The residual is a real, visible number -- never hidden, never cleared
    # by the act of reconciling (D-052 stays unset; see
    # src/quality/period_state.py's docstring for why this is a human
    # action gated on the reconciliation having run, not on an invented
    # tolerance deciding pass/fail).
    assert recon.residual is not None
    assert isinstance(recon.books_total, type(recon.bank_total))


def test_every_overview_tile_either_resolves_with_a_full_citation_or_carries_no_citation_at_all(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, _summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                              effective_from=date(2022, 4, 1))
    assert freeze.passed

    config = load_registry()
    period_key = "2025-03"
    resolved_count = 0

    for metric_id in NINE_TILES:
        result = compile_metric(conn, schema, tenant_id, entity_id, metric_id, period_key, config)

        if result.status == "ok":
            resolved_count += 1
            citation = build_citation(conn, schema, tenant_id, entity_id, version_id, result, "reconciled")
            assert citation.value == result.value
            assert citation.row_count > 0
            assert citation.query_hash
            assert "fact_gl_entry" in citation.source_facts
        else:
            # Not resolved -- must have NO value and be provably not citable.
            assert result.value is None
            assert result.reason, f"{metric_id} is blocked with no stated reason"
            try:
                build_citation(conn, schema, tenant_id, entity_id, version_id, result, "reconciled")
                assert False, f"{metric_id}: a metric that did not resolve must never be citable"
            except NotCitable:
                pass

    # At least the two known-unblocked tiles must actually resolve, so this
    # test cannot pass by every tile trivially failing.
    assert resolved_count >= 2
