"""Integration test: the full period state machine against a live tenant.
Needs Postgres (see tests/conftest.py) -- skips cleanly otherwise.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.quality.books_to_bank import run_books_to_bank, write_reconciliation_run
from src.quality.period_state import (
    InvalidTransition,
    get_current_period_lock,
    lock_period,
    map_period,
    reconcile_period,
    restate_period,
    validate_period,
)
from src.quality.trial_balance import check_trial_balance
from tests.helpers import ingest_manufacturer, run_and_freeze_mapping


def _advance_to_mapped(conn, schema, tenant_id, entity_id, period_key, version_id, freeze):
    """OPEN -> VALIDATED -> MAPPED.

    A test about a later transition's OWN precondition has to start from that
    transition's predecessor state, or the predecessor check satisfies it
    first and the test passes without exercising what it names."""
    validate_period(conn, schema, tenant_id, entity_id, period_key, version_id, blocking_exception_count=0)
    map_period(conn, schema, tenant_id, entity_id, period_key, version_id,
                 freeze_passed=freeze.passed, coverage_pct=freeze.coverage_pct)


def _advance_to_locked(conn, schema, tenant_id, entity_id, period_key, version_id, freeze):
    """... -> RECONCILED -> LOCKED, via a real reconciliation run."""
    _advance_to_mapped(conn, schema, tenant_id, entity_id, period_key, version_id, freeze)
    tb = check_trial_balance(conn, schema, tenant_id, period_key)
    recon = run_books_to_bank(conn, schema, tenant_id, entity_id, version_id, period_key)
    recon_run_id = write_reconciliation_run(conn, schema, tenant_id, entity_id, version_id,
                                                "books_to_bank", recon, "pytest-analyst")
    reconcile_period(conn, schema, tenant_id, entity_id, period_key, version_id,
                        trial_balance_balanced=tb.balanced, reconciliation_run_id=recon_run_id,
                        approved_by="pytest-analyst")
    lock_period(conn, schema, tenant_id, entity_id, period_key, version_id, locked_by="pytest-analyst")


def test_full_state_machine_open_to_locked_to_restated(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                             effective_from=date(2022, 4, 1))
    assert freeze.passed

    period_key = "2025-03"

    validate_period(conn, schema, tenant_id, entity_id, period_key, version_id, blocking_exception_count=0)
    assert get_current_period_lock(conn, schema, tenant_id, entity_id, period_key).status == "validated"

    map_period(conn, schema, tenant_id, entity_id, period_key, version_id,
                 freeze_passed=freeze.passed, coverage_pct=freeze.coverage_pct)
    assert get_current_period_lock(conn, schema, tenant_id, entity_id, period_key).status == "mapped"

    tb = check_trial_balance(conn, schema, tenant_id, period_key)
    assert tb.balanced, tb.largest_contributors

    recon = run_books_to_bank(conn, schema, tenant_id, entity_id, version_id, period_key)
    recon_run_id = write_reconciliation_run(conn, schema, tenant_id, entity_id, version_id,
                                                "books_to_bank", recon, "pytest-analyst")

    reconcile_period(conn, schema, tenant_id, entity_id, period_key, version_id,
                        trial_balance_balanced=tb.balanced, reconciliation_run_id=recon_run_id,
                        approved_by="pytest-analyst")
    current = get_current_period_lock(conn, schema, tenant_id, entity_id, period_key)
    assert current.status == "reconciled"
    # The residual stays visible -- reconciling never clears or hides it.
    assert recon.residual is not None

    lock_period(conn, schema, tenant_id, entity_id, period_key, version_id, locked_by="pytest-analyst")
    locked = get_current_period_lock(conn, schema, tenant_id, entity_id, period_key)
    assert locked.status == "locked"
    assert locked.snapshot_at is not None
    assert locked.locked_by == "pytest-analyst"

    restate_period(conn, schema, tenant_id, entity_id, period_key, version_id,
                      restatement_reason="Backdated entry found touching a locked period")
    restated = get_current_period_lock(conn, schema, tenant_id, entity_id, period_key)
    assert restated.status == "restated"
    assert restated.restated_from == locked.lock_id


def test_reconcile_blocked_without_a_completed_reconciliation_run(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, _summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                              effective_from=date(2022, 4, 1))
    # Driven to MAPPED first, and matched on the reconciliation-run wording:
    # from OPEN the predecessor check refuses this call before reconcile_period
    # ever looks at reconciliation_run_id, so without both of these the test
    # would still pass while testing nothing it is named for.
    _advance_to_mapped(conn, schema, tenant_id, entity_id, "2025-03", version_id, freeze)

    with pytest.raises(InvalidTransition, match="no books-to-bank reconciliation_run"):
        reconcile_period(conn, schema, tenant_id, entity_id, "2025-03", version_id,
                            trial_balance_balanced=True, reconciliation_run_id=None,
                            approved_by="pytest-analyst")


def test_restate_blocked_unless_currently_locked(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, _summary, _freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                               effective_from=date(2022, 4, 1))
    with pytest.raises(InvalidTransition, match="is open, not locked"):
        restate_period(conn, schema, tenant_id, entity_id, "2025-03", version_id, restatement_reason="test")


def test_a_transition_refuses_when_its_predecessor_state_was_skipped(conn, tenant):
    """corpus/09 section 5's arrows: each state has exactly one way in, and a
    period may not jump the queue to reach it."""
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, _summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                              effective_from=date(2022, 4, 1))
    period_key = "2025-03"

    # MAPPED is reachable only from VALIDATED, never straight from OPEN --
    # even with a freeze that genuinely passed.
    with pytest.raises(InvalidTransition, match="is open, not validated"):
        map_period(conn, schema, tenant_id, entity_id, period_key, version_id,
                     freeze_passed=freeze.passed, coverage_pct=freeze.coverage_pct)

    # LOCKED is reachable only from RECONCILED, never straight from MAPPED --
    # even with a named locker, which is lock_period's own precondition.
    _advance_to_mapped(conn, schema, tenant_id, entity_id, period_key, version_id, freeze)
    with pytest.raises(InvalidTransition, match="is mapped, not reconciled"):
        lock_period(conn, schema, tenant_id, entity_id, period_key, version_id, locked_by="pytest-analyst")


def test_a_transition_refuses_on_a_period_already_in_that_state(conn, tenant):
    """corpus/09 section 5 draws no self-arrow on any state, so re-running a
    transition is refused rather than silently treated as idempotent. Whether
    a second GL load should be able to re-validate an already-validated period
    is a real question the corpus does not answer -- it fails loudly here
    instead of being answered in this module (see its docstring)."""
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, _summary, _freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                               effective_from=date(2022, 4, 1))
    period_key = "2025-03"

    validate_period(conn, schema, tenant_id, entity_id, period_key, version_id, blocking_exception_count=0)
    with pytest.raises(InvalidTransition, match="is validated, not open"):
        validate_period(conn, schema, tenant_id, entity_id, period_key, version_id, blocking_exception_count=0)


def test_nothing_re_enters_the_machine_after_a_restatement(conn, tenant):
    """corpus/09 section 5 draws no arrow OUT of RESTATED. What a restated
    period does next is unanswered by the corpus, so every transition refuses
    it and names the state -- rather than one of them being chosen here."""
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, _summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                              effective_from=date(2022, 4, 1))
    period_key = "2025-03"

    _advance_to_locked(conn, schema, tenant_id, entity_id, period_key, version_id, freeze)
    restate_period(conn, schema, tenant_id, entity_id, period_key, version_id,
                      restatement_reason="Backdated entry found touching a locked period")
    assert get_current_period_lock(conn, schema, tenant_id, entity_id, period_key).status == "restated"

    with pytest.raises(InvalidTransition, match="is restated, not open"):
        validate_period(conn, schema, tenant_id, entity_id, period_key, version_id, blocking_exception_count=0)
    with pytest.raises(InvalidTransition, match="is restated, not reconciled"):
        lock_period(conn, schema, tenant_id, entity_id, period_key, version_id, locked_by="pytest-analyst")
    with pytest.raises(InvalidTransition, match="is restated, not locked"):
        restate_period(conn, schema, tenant_id, entity_id, period_key, version_id,
                          restatement_reason="a second backdated entry")
