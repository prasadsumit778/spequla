"""Period state endpoints for the two transitions a human performs,
corpus/09 section 5.

The other three are consequences of something else happening and have no
endpoint of their own: OPEN -> VALIDATED runs at the end of a GL load
(src/ingest/load_pipeline.load_gl_file), VALIDATED -> MAPPED runs inside
POST /mapping/runs/{id}/freeze once the freeze gate passes, and
LOCKED -> RESTATED is triggered by a backdated entry the re-pull finds
(src/ingest/repull.py), not by anyone asking for it.

These two are different. corpus/09 section 5 labels them "trial balance
ties, books to bank within tolerance" and "finance signs off" -- and D-052,
the books-to-bank tolerance, is deliberately unset, so the first cannot be
decided automatically and the second was never meant to be. Both are a named
human's action, recorded with that name, exactly as D-039 requires for the
lock.

**Neither endpoint accepts an assertion about the period's condition.** The
reconcile endpoint runs the trial balance check itself and finds the
period's own latest books_to_bank reconciliation_run; the lock endpoint
carries the mapping version forward off the period's current lock row. A
request body that could claim the trial balance ties would mean D-051's zero
tolerance was enforced against a claim rather than against the ledger. The
only thing either caller supplies is who they are, and that comes from the
verified session, not the body.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path

from src.api.deps.auth import Session, require_upload_role
from src.api.deps.tenant import resolve_tenant
from src.quality.period_state import (
    InvalidTransition,
    get_current_period_lock,
    lock_period_from_current_state,
    reconcile_period_from_current_checks,
)

router = APIRouter()

# period_key's grain is one calendar month, 'YYYY-MM' -- the same literal
# format fact_gl_entry.period_key carries (src/ingest/canonical.py) and the
# statement, pack and reconciliation paths all key on.
PERIOD_KEY = Path(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


@router.post("/periods/{period_key}/reconcile")
def reconcile(period_key: str = PERIOD_KEY, entity_id: int = 1,
                 session: Session = Depends(require_upload_role), tenant_ctx=Depends(resolve_tenant)):
    """MAPPED -> RECONCILED, corpus/09 section 5: "trial balance ties, books
    to bank within tolerance." The residual is reported back and is never
    cleared by the act of reconciling -- reconciling records that a named
    human looked at a visible residual, it does not assert the residual away
    (see src/quality/period_state.py's docstring on why D-052 leaves this a
    human action)."""
    conn, tenant_id, schema = tenant_ctx
    try:
        outcome = reconcile_period_from_current_checks(conn, schema, tenant_id, entity_id, period_key,
                                                             approved_by=session.user_id)
    except InvalidTransition as e:
        conn.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    conn.commit()
    return {
        "period_key": period_key,
        "status": "reconciled",
        "lock_id": outcome.lock_id,
        "approved_by": session.user_id,
        # The two figures the transition was actually decided on, reported
        # back rather than recomputed for display.
        "trial_balance_total": str(outcome.trial_balance_total),
        "reconciliation_run_id": outcome.reconciliation_run_id,
    }


@router.post("/periods/{period_key}/lock")
def lock(period_key: str = PERIOD_KEY, entity_id: int = 1,
            session: Session = Depends(require_upload_role), tenant_ctx=Depends(resolve_tenant)):
    """RECONCILED -> LOCKED, corpus/09 section 5: "finance signs off."
    D-039: "The SPEQULA analyst locks when the pack is signed, targeting the
    15th of the following month." snapshot_at is pinned by lock_period at
    this moment and is what every report for this period renders against
    from now on (corpus/04 section 3.8)."""
    conn, tenant_id, schema = tenant_ctx
    try:
        lock_id = lock_period_from_current_state(conn, schema, tenant_id, entity_id, period_key,
                                                       locked_by=session.user_id)
    except InvalidTransition as e:
        conn.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    conn.commit()

    current = get_current_period_lock(conn, schema, tenant_id, entity_id, period_key)
    return {
        "period_key": period_key,
        "status": current.status,
        "lock_id": lock_id,
        "locked_by": current.locked_by,
        "snapshot_at": current.snapshot_at.isoformat(),
    }
