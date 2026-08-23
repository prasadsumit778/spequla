"""Integration test: the full period state machine against a live tenant.
Needs Postgres (see tests/conftest.py) -- skips cleanly otherwise.
"""
from __future__ import annotations

from datetime import date

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
    try:
        reconcile_period(conn, schema, tenant_id, entity_id, "2025-03", version_id,
                            trial_balance_balanced=True, reconciliation_run_id=None, approved_by="pytest-analyst")
        assert False, "must not reconcile without a reconciliation_run"
    except InvalidTransition:
        pass


def test_restate_blocked_unless_currently_locked(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, _summary, _freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                               effective_from=date(2022, 4, 1))
    try:
        restate_period(conn, schema, tenant_id, entity_id, "2025-03", version_id, restatement_reason="test")
        assert False, "must not restate a period that was never locked"
    except InvalidTransition:
        pass
