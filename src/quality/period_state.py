"""The period state machine, corpus/09 section 5.

    OPEN -> VALIDATED -> MAPPED -> RECONCILED -> LOCKED -> RESTATED

corpus/04's literal period_lock DDL only enumerates four status values
('open' | 'reconciled' | 'locked' | 'restated') where corpus/09 section 5
names six. The column is untyped text with no CHECK constraint, so this
module uses the fuller six-value vocabulary corpus/09 is authoritative on --
adding 'validated' and 'mapped' extends the same free-text column rather
than conflicting with the literal DDL.

Per CLAUDE.md invariant #4 ("nothing is ever overwritten"), every transition
INSERTS a new period_lock row rather than updating the current one; "current
status for a period" is always the most recently inserted row.

**The MAPPED -> RECONCILED transition is a human action here, not an
automatic tolerance gate.** corpus/09 section 5 states the transition as
"trial balance ties, books to bank within tolerance" -- but D-052 (the
books-to-bank tolerance) is deliberately unset (corpus/00: "a threshold that
can only honestly be set from observation... none blocks the build"), so
"within tolerance" cannot be evaluated as true or false. Per CLAUDE.md
section 3.2's own worked example ("Where the corpus deliberately leaves one
blank, such as D-052, that blank is a decision. Leave it blank and make the
code fail loudly rather than proceed"), this module never invents a
tolerance to decide the transition automatically. Instead: reconcile_period()
requires the trial balance to tie (zero tolerance, D-051, that part IS
settled) and a books-to-bank reconciliation_run to exist for the period (the
residual computed and itemised, src/quality/books_to_bank.py) -- and then
requires a named human `approved_by` to mark the period reconciled, exactly
the way lock_period() already requires a named human sign-off per D-039. The
residual is never cleared or hidden once marked reconciled; every citation
resolving through this period keeps reporting it, per invariant #7's spirit
that a caveat is never dropped once attached.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

STATES = ("open", "validated", "mapped", "reconciled", "locked", "restated")

# D-040's resolved text (corpus/00 section 2b): "Every change to a locked
# period is flagged. Notification above 0.25 percent of period revenue,
# aligned with D-024." Every restatement is flagged regardless of size;
# this threshold only decides notify_required.
RESTATEMENT_NOTIFY_THRESHOLD_PCT = Decimal("0.0025")


@dataclass
class PeriodLockRow:
    lock_id: int
    status: str
    snapshot_at: datetime | None
    mapping_version_id: int
    locked_by: str | None = None
    locked_at: datetime | None = None
    restated_from: int | None = None
    restatement_reason: str | None = None


def get_current_period_lock(conn, schema: str, tenant_id: str, entity_id: int, period_key: str) -> PeriodLockRow | None:
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT lock_id, status, snapshot_at, mapping_version_id, locked_by, locked_at, '
            f'       restated_from, restatement_reason '
            f'FROM "{schema}".period_lock '
            f'WHERE tenant_id = %s AND entity_id = %s AND period_key = %s '
            f'ORDER BY lock_id DESC LIMIT 1',
            (tenant_id, entity_id, period_key),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return PeriodLockRow(*row)


class InvalidTransition(Exception):
    """Raised when a transition's precondition fails -- the caller sees
    exactly which corpus/09 section 5 condition was not met, never a
    generic failure."""


def _insert(conn, schema: str, tenant_id: str, entity_id: int, period_key: str, status: str,
             mapping_version_id: int, snapshot_at: datetime | None = None, locked_by: str | None = None,
             locked_at: datetime | None = None, restated_from: int | None = None,
             restatement_reason: str | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{schema}".period_lock '
            f'(tenant_id, entity_id, period_key, status, snapshot_at, mapping_version_id, locked_by, locked_at, '
            f' restated_from, restatement_reason) '
            f'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING lock_id',
            (tenant_id, entity_id, period_key, status, snapshot_at, mapping_version_id, locked_by, locked_at,
             restated_from, restatement_reason),
        )
        return cur.fetchone()[0]


def validate_period(conn, schema: str, tenant_id: str, entity_id: int, period_key: str,
                       mapping_version_id: int, blocking_exception_count: int) -> int:
    """OPEN -> VALIDATED: 'all blocking checks pass' (corpus/09 section 5).
    blocking_exception_count comes from src/quality/checks.py's catalogue
    run for this period -- passed in rather than queried here so this
    function stays a simple precondition check, independently testable."""
    if blocking_exception_count > 0:
        raise InvalidTransition(f"{blocking_exception_count} open blocking exception(s) for {period_key} -- "
                                  f"corpus/09 section 5 requires all blocking checks to pass before VALIDATED")
    return _insert(conn, schema, tenant_id, entity_id, period_key, "validated", mapping_version_id)


def map_period(conn, schema: str, tenant_id: str, entity_id: int, period_key: str,
                 mapping_version_id: int, freeze_passed: bool, coverage_pct: Decimal) -> int:
    """VALIDATED -> MAPPED: 'mapping version approved, coverage above
    threshold' -- src/mapping/review.py's freeze_mapping_version() already
    enforces the 98% coverage gate (corpus/06a Coverage tab) before a
    version can even become 'approved'; freeze_passed/coverage_pct are its
    own FreezeResult, threaded through rather than re-queried."""
    if not freeze_passed:
        raise InvalidTransition(f"mapping version {mapping_version_id} has not passed the freeze gate -- "
                                  f"corpus/06 section 6 rule 1: no statement and no metric before version 1 is approved")
    return _insert(conn, schema, tenant_id, entity_id, period_key, "mapped", mapping_version_id)


def reconcile_period(conn, schema: str, tenant_id: str, entity_id: int, period_key: str,
                        mapping_version_id: int, trial_balance_balanced: bool,
                        reconciliation_run_id: int | None, approved_by: str) -> int:
    """MAPPED -> RECONCILED. See this module's docstring for why this is a
    human action gated on the reconciliation having been RUN, not on a
    tolerance that does not exist (D-052)."""
    if not trial_balance_balanced:
        raise InvalidTransition(f"trial balance does not tie for {period_key} -- D-051, zero tolerance, blocking")
    if reconciliation_run_id is None:
        raise InvalidTransition(f"no books-to-bank reconciliation_run exists for {period_key} -- "
                                  f"run src/quality/books_to_bank.run_books_to_bank first")
    if not approved_by:
        raise InvalidTransition("reconcile_period requires a named approver, per corpus/06 section 4.3's "
                                  "'every action is logged with a timestamp and a name'")
    return _insert(conn, schema, tenant_id, entity_id, period_key, "reconciled", mapping_version_id)


def lock_period(conn, schema: str, tenant_id: str, entity_id: int, period_key: str,
                   mapping_version_id: int, locked_by: str) -> int:
    """RECONCILED -> LOCKED: 'finance signs off' (corpus/09 section 5),
    D-039: 'The SPEQULA analyst locks when the pack is signed, targeting
    the 15th of the following month.' snapshot_at is pinned here -- 'every
    report for that period queries against' this timestamp forever
    (corpus/04 section 3.8)."""
    if not locked_by:
        raise InvalidTransition("lock_period requires a named locker, per D-039")
    now = datetime.now(timezone.utc)
    return _insert(conn, schema, tenant_id, entity_id, period_key, "locked", mapping_version_id,
                     snapshot_at=now, locked_by=locked_by, locked_at=now)


def restatement_notify_required(change_amount_inr: Decimal, period_revenue_inr: Decimal) -> bool:
    """Pure: D-040's resolved threshold. Every change to a locked period is
    flagged regardless (that part is unconditional); this only decides
    whether it clears the notify bar. A zero or unknown period_revenue_inr
    cannot honestly evaluate a percentage -- errs toward notifying rather
    than silently skipping."""
    if period_revenue_inr == 0:
        return True
    return abs(change_amount_inr) / abs(period_revenue_inr) > RESTATEMENT_NOTIFY_THRESHOLD_PCT


def restate_period(conn, schema: str, tenant_id: str, entity_id: int, period_key: str,
                      mapping_version_id: int, restatement_reason: str) -> int:
    """LOCKED -> RESTATED: 'a change arrives touching a locked period.'
    corpus/09 section 5: 'A period never moves backwards silently... that is
    a restatement event with a reason, an owner and a visible delta, not a
    status flag quietly flipping.' Triggered by src/ingest/repull.py's
    backdated-entry detection finding entry_date > event_date touching a
    locked period -- the caller supplies restatement_reason naming what
    was found. Every restatement is flagged (D-040); notify_required is a
    separate signal for whoever consumes the flag, not gating whether the
    restatement itself is recorded."""
    current = get_current_period_lock(conn, schema, tenant_id, entity_id, period_key)
    if current is None or current.status != "locked":
        raise InvalidTransition(f"{period_key} is not currently locked -- restatement only applies to a "
                                  f"period that was locked (current status: {current.status if current else 'none'})")
    return _insert(conn, schema, tenant_id, entity_id, period_key, "restated", mapping_version_id,
                     restated_from=current.lock_id, restatement_reason=restatement_reason)
