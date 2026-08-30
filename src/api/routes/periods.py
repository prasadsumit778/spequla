"""Period endpoints for the two transitions a human performs, corpus/09
section 5, and the reconciliation run that feeds the first of them.

The other three transitions are consequences of something else happening and
have no endpoint of their own: OPEN -> VALIDATED runs at the end of a GL load
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

**The books-to-bank run is its own endpoint, not part of either
transition.** POST /periods/{key}/reconciliation-run computes and records
the residual; POST /periods/{key}/reconcile consumes it. Keeping them apart
is what makes the reconcile transition mean anything: corpus/09 section 3.2
requires the residual to be stated, itemised against the seven modelled
difference categories, and *seen* before anyone decides, so computing it has
to precede the request that records the decision rather than accompany it.
It is equally deliberately not run at load time -- at first onboarding no
approved mapping version exists, the period's lock row still points at the
version-0 placeholder (src/ingest/canonical.get_placeholder_mapping_version,
which carries no map_account rows), and a run against it would record a
books total of zero and a residual that is merely the negative of the bank
total: a stored number that looks like a reconciliation and is an artefact
of running too early. Hence the MAPPED precondition below. This is
OPEN_QUESTIONS.md OQ-014, resolved 2026-08-31 to option (d).

**No endpoint here accepts an assertion about the period's condition.** The
reconciliation-run endpoint computes both totals from the ledger and the
bank facts; the reconcile endpoint runs the trial balance check itself and
finds the period's own latest books_to_bank reconciliation_run; the lock
endpoint carries the mapping version forward off the period's current lock
row. A request body that could claim the trial balance ties would mean
D-051's zero tolerance was enforced against a claim rather than against the
ledger. The only thing any caller supplies is who they are, and that comes
from the verified session, not the body.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path

from src.api.deps.auth import Session, require_upload_role
from src.api.deps.tenant import resolve_tenant
from src.quality.books_to_bank import run_books_to_bank, write_reconciliation_run
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


@router.post("/periods/{period_key}/reconciliation-run")
def reconciliation_run(period_key: str = PERIOD_KEY, entity_id: int = 1,
                          session: Session = Depends(require_upload_role), tenant_ctx=Depends(resolve_tenant)):
    """Runs the books-to-bank reconciliation for a period and records the
    result, corpus/09 section 3.2. This is what MAPPED -> RECONCILED
    consumes; it does not itself move the period.

    **Requires the period to be MAPPED**, for the reason in this module's
    docstring: MAPPED is the first state whose lock row points at an
    approved mapping version rather than the ingestion-time placeholder, and
    a run resolved through the placeholder records a books total of zero.
    The version is read off that lock row, the same way
    reconcile_period_from_current_checks reads it -- the period is
    reconciled under the version it was mapped on, never one named in a
    request body.

    **No modelled differences are supplied.** corpus/09 section 9 puts the
    per-company list of them behind the accounting policy conversation, "one
    company at a time"; nothing has been configured, so the entire books-vs-
    bank gap surfaces as residual. That is the honest state (see
    src/quality/books_to_bank.py's docstring), and a request body carrying
    them would let a caller assert part of the residual away.

    **No tolerance is supplied.** D-052 is deliberately unset, so the run is
    recorded with status 'unreconciled' and nothing here classifies the
    residual as within or above anything. A human reads the residual and
    decides, which is the next endpoint.
    """
    conn, tenant_id, schema = tenant_ctx
    current = get_current_period_lock(conn, schema, tenant_id, entity_id, period_key)
    status = current.status if current is not None else "open"
    if status != "mapped":
        conn.rollback()
        raise HTTPException(
            status_code=422,
            detail=(
                f"{period_key} is {status}, not mapped -- the books-to-bank run resolves class movements "
                f"through the mapping version on the period's own lock row, and only from mapped onwards "
                f"is that an approved version rather than the ingestion-time placeholder (a run against "
                f"the placeholder records a books total of zero and a residual that is merely the "
                f"negative of the bank total)."
            ),
        )

    result = run_books_to_bank(conn, schema, tenant_id, entity_id, current.mapping_version_id, period_key)
    run_id = write_reconciliation_run(conn, schema, tenant_id, entity_id, current.mapping_version_id,
                                          check_type="books_to_bank", result=result, run_by=session.user_id)
    conn.commit()
    return {
        "period_key": period_key,
        "reconciliation_run_id": run_id,
        "check_type": "books_to_bank",
        # 'unreconciled' while D-052 is unset -- see write_reconciliation_run.
        "status": "unreconciled",
        "run_by": session.user_id,
        "mapping_version_id": current.mapping_version_id,
        "books_total_inr": str(result.books_total),
        "bank_total_inr": str(result.bank_total),
        "modelled_differences": [
            {"category": d.category, "amount_inr": str(d.amount_inr), "note": d.note}
            for d in result.modelled_differences
        ],
        "modelled_total_inr": str(result.modelled_total),
        "residual_inr": str(result.residual),
    }


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
