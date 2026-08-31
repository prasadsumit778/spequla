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
the way lock_period() already requires a named human sign-off per D-039. That
run is produced by POST /periods/{key}/reconciliation-run, its own endpoint
and not part of this transition (OPEN_QUESTIONS.md OQ-014) -- corpus/09
section 3.2 wants the residual stated, itemised and seen before anyone
decides, so computing it precedes the request that records the decision
rather than accompanying it. The residual is never cleared or hidden once
marked reconciled; every citation resolving through this period keeps
reporting it, per invariant #7's spirit that a caveat is never dropped once
attached.

**Every transition checks the state it is transitioning out of.** corpus/09
section 5 draws five arrows and states one rule about them -- "A period never
moves backwards silently" -- so a transition is admitted only from the state
the diagram draws it out of, and `_PREDECESSOR` below is that diagram as
data. This is deliberately strict about what corpus/09 does NOT draw: there
is no self-arrow on any state, and no arrow leaves RESTATED at all. Three
cases therefore raise InvalidTransition rather than being resolved here --
re-running a transition on a period already in that state, re-entering the
machine after a restatement, and a period that becomes structurally unsound
again after new data arrives (corpus/09 section 5's own sentence about that
case, "if a locked period becomes unreconciled because new data arrived,"
covers LOCKED and only LOCKED; it says nothing about a VALIDATED or MAPPED
period going bad). Each fails loudly with the current status named, per
CLAUDE.md section 3.1. A caller that hits one has found a real question about
the state machine, and that is an escalation, not a branch to add here. The
first of those three was escalated as OQ-009 and resolved for the load path
only: `src/ingest/load_pipeline.load_gl_file` skips and reports the
transition when a period already has a lock row rather than re-validating it.
That is a decision about what a caller does with the refusal. The refusal
itself is unchanged, and there is still no self-arrow here.

The five single-period transitions take their preconditions as arguments so
each stays a precondition check that is testable without a database. The
three functions at the bottom of this module are the callers that batch and
orchestrate them -- advancing every period a frozen mapping version governs,
and computing (rather than accepting) the trial balance and reconciliation
run a period is reconciled on.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from src.quality.books_to_bank import latest_reconciliation_run_id
from src.quality.trial_balance import check_trial_balance
from src.semantic.statements import ExecutedStatement

STATES = ("open", "validated", "mapped", "reconciled", "locked", "restated")

# corpus/09 section 5's arrows, drawn literally: the state a period must
# already be in for each transition to be admitted.
#
# OPEN is the ABSENCE of a period_lock row, not a stored value -- nothing
# inserts 'open', and nothing can: period_lock.mapping_version_id is NOT NULL
# REFERENCES mapping_version (db/migrations/tenant/0009_period_lock.sql), so
# no row can exist for a period before a mapping version does. Every reader
# already resolves a missing row that way (src/reports/pack.py,
# src/api/routes/overview.py and src/semantic/ask_compiler.py all read
# `lock.status if lock else "open"`), so None here is that same convention,
# not a separate sentinel.
_PREDECESSOR: dict[str, str | None] = {
    "validated": None,          # OPEN       -> VALIDATED
    "mapped": "validated",      # VALIDATED  -> MAPPED
    "reconciled": "mapped",     # MAPPED     -> RECONCILED
    "locked": "reconciled",     # RECONCILED -> LOCKED
    "restated": "locked",       # LOCKED     -> RESTATED
}

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


@dataclass
class PeriodTransitionOutcome:
    """What happened to ONE period when a caller advanced several at once --
    a GL load taking every period it touched to VALIDATED, a mapping freeze
    taking every period it governs to MAPPED.

    Those callers cannot raise on the first refusal: a load of thirty-six
    months where month eight is refused still wrote thirty-six months of
    facts, and the other thirty-five periods still transitioned. So the
    refusal becomes a reported outcome per period instead of an exception,
    and every caller surfaces the list rather than counting successes.
    `status` is the period's status AFTER the attempt: the state it reached
    when transitioned is True, the state that was already there when it is
    not."""
    period_key: str
    transitioned: bool
    status: str
    detail: str


@dataclass
class ReconciledPeriod:
    """What reconcile_period_from_current_checks actually decided on, handed
    back so the caller reports the figures the transition was made against
    rather than re-deriving them afterwards. The residual is not in here on
    purpose: it belongs to the reconciliation_run row, which is never
    superseded or cleared by the period being reconciled."""
    lock_id: int
    trial_balance_total: Decimal
    reconciliation_run_id: int


def get_current_period_lock(conn, schema: str, tenant_id: str, entity_id: int, period_key: str,
                               statement_log: list[ExecutedStatement] | None = None) -> PeriodLockRow | None:
    """`statement_log`, when passed, collects this read into the caller's
    record of what reached Postgres (src/semantic/statements.py). The Ask
    surface's data_health intent passes one, because this row is part of the
    answer that intent returns rather than a gate in front of it. Default
    None leaves the period gate and the transition paths unchanged."""
    sql = (f'SELECT lock_id, status, snapshot_at, mapping_version_id, locked_by, locked_at, '
              f'       restated_from, restatement_reason '
              f'FROM "{schema}".period_lock '
              f'WHERE tenant_id = %s AND entity_id = %s AND period_key = %s '
              f'ORDER BY lock_id DESC LIMIT 1')
    if statement_log is not None:
        statement_log.append(ExecutedStatement(sql, (f'"{schema}".period_lock',), gated=True))
    with conn.cursor() as cur:
        cur.execute(sql, (tenant_id, entity_id, period_key))
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


def _require_predecessor(conn, schema: str, tenant_id: str, entity_id: int, period_key: str,
                            target: str) -> PeriodLockRow | None:
    """Enforces corpus/09 section 5's arrow into `target`. Returns the current
    row (None when the predecessor is OPEN) so a caller that needs the row it
    is superseding -- restate_period, for restated_from -- does not read it
    twice. See this module's docstring for what is deliberately NOT admitted."""
    expected = _PREDECESSOR[target]
    current = get_current_period_lock(conn, schema, tenant_id, entity_id, period_key)
    actual = current.status if current is not None else None
    if actual != expected:
        raise InvalidTransition(
            f"{period_key} is {actual or 'open'}, not {expected or 'open'} -- corpus/09 section 5 "
            f"admits {expected or 'open'} -> {target} and no other path into {target}"
        )
    return current


def validate_period(conn, schema: str, tenant_id: str, entity_id: int, period_key: str,
                       mapping_version_id: int, blocking_exception_count: int) -> int:
    """OPEN -> VALIDATED: 'all blocking checks pass' (corpus/09 section 5).
    blocking_exception_count comes from src/quality/checks.py's catalogue
    run for this period -- passed in rather than queried here so this
    function stays a simple precondition check, independently testable."""
    _require_predecessor(conn, schema, tenant_id, entity_id, period_key, "validated")
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
    _require_predecessor(conn, schema, tenant_id, entity_id, period_key, "mapped")
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
    _require_predecessor(conn, schema, tenant_id, entity_id, period_key, "reconciled")
    if not trial_balance_balanced:
        raise InvalidTransition(f"trial balance does not tie for {period_key} -- D-051, zero tolerance, blocking")
    if reconciliation_run_id is None:
        raise InvalidTransition(f"no books-to-bank reconciliation_run exists for {period_key} -- "
                                  f"POST /periods/{period_key}/reconciliation-run first, and read the "
                                  f"residual it returns before reconciling")
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
    _require_predecessor(conn, schema, tenant_id, entity_id, period_key, "locked")
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
    current = _require_predecessor(conn, schema, tenant_id, entity_id, period_key, "restated")
    return _insert(conn, schema, tenant_id, entity_id, period_key, "restated", mapping_version_id,
                     restated_from=current.lock_id, restatement_reason=restatement_reason)


def _periods_with_facts_in_range(conn, schema: str, tenant_id: str, entity_id: int,
                                     date_from: date, date_to: date) -> list[str]:
    """Distinct period_key of current GL facts with event_date in
    [date_from, date_to) -- half-open, matching corpus/06 section 6 rule 3's
    effective dating ("a version effective from 1 April 2026 applies to April
    onwards; March renders with the prior version forever")."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT DISTINCT period_key FROM "{schema}".fact_gl_entry '
            f'WHERE tenant_id = %s AND entity_id = %s AND is_current '
            f'AND event_date >= %s AND event_date < %s ORDER BY period_key',
            (tenant_id, entity_id, date_from, date_to),
        )
        return [r[0] for r in cur.fetchall()]


def map_periods_for_mapping_version(conn, schema: str, tenant_id: str, entity_id: int,
                                        mapping_version_id: int, freeze_passed: bool,
                                        coverage_pct: Decimal) -> list[PeriodTransitionOutcome]:
    """VALIDATED -> MAPPED for every period this frozen mapping version
    governs. Called from POST /mapping/runs/{id}/freeze once
    freeze_mapping_version has passed -- corpus/09 section 5's condition on
    this arrow is "mapping version approved, coverage above threshold," which
    is precisely the event that just happened.

    Which periods the version governs is read from the data, not supplied:
    the periods with current GL facts inside the version's own
    [effective_from, effective_to) window, per corpus/06 section 6 rule 3. A
    caller cannot name a period the version does not cover.

    **A period that is not currently VALIDATED is skipped and reported, never
    dragged forward.** A period still at OPEN did not pass its blocking
    checks, or has never had a load complete for it; approving a mapping
    version says nothing whatsoever about whether that period is
    structurally sound, and corpus/09 section 5's arrow into MAPPED starts
    at VALIDATED and nowhere else. The same applies at the other end: a
    period already RECONCILED or LOCKED is left where it is rather than
    walked backwards, which section 5 forbids outright.
    """
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT effective_from, effective_to FROM "{schema}".mapping_version '
            f'WHERE mapping_version_id = %s AND tenant_id = %s AND entity_id = %s',
            (mapping_version_id, tenant_id, entity_id),
        )
        row = cur.fetchone()
    if row is None:
        raise InvalidTransition(f"no mapping_version {mapping_version_id} for entity {entity_id}")
    effective_from, effective_to = row

    outcomes: list[PeriodTransitionOutcome] = []
    for period_key in _periods_with_facts_in_range(conn, schema, tenant_id, entity_id,
                                                       effective_from, effective_to):
        current = get_current_period_lock(conn, schema, tenant_id, entity_id, period_key)
        status = current.status if current is not None else "open"
        if status != "validated":
            outcomes.append(PeriodTransitionOutcome(
                period_key, False, status,
                f"left at {status}: corpus/09 section 5 admits validated -> mapped and no other path "
                f"into mapped, so freezing a mapping version does not move this period",
            ))
            continue
        map_period(conn, schema, tenant_id, entity_id, period_key, mapping_version_id,
                     freeze_passed=freeze_passed, coverage_pct=coverage_pct)
        outcomes.append(PeriodTransitionOutcome(
            period_key, True, "mapped",
            f"validated -> mapped on mapping version {mapping_version_id}",
        ))
    return outcomes


def reconcile_period_from_current_checks(conn, schema: str, tenant_id: str, entity_id: int,
                                             period_key: str, approved_by: str) -> ReconciledPeriod:
    """MAPPED -> RECONCILED with both of reconcile_period's data preconditions
    computed here rather than asserted by whoever is asking.

    reconcile_period takes `trial_balance_balanced` and
    `reconciliation_run_id` as arguments, which is right for the function --
    it keeps it a precondition check that is unit-testable without a
    database, per this module's docstring. It is wrong for an API: a caller
    that can pass trial_balance_balanced=True can reconcile a period whose
    trial balance does not tie, and D-051's zero tolerance would then be
    enforced against a claim instead of against the ledger. So this runs
    check_trial_balance itself and finds the period's own latest
    books_to_bank reconciliation_run. Nothing about the period's condition
    arrives from outside.

    The mapping version is carried forward from the period's current lock
    row for the same reason -- the period continues under the version it was
    mapped on, not one named in a request body.
    """
    current = _require_predecessor(conn, schema, tenant_id, entity_id, period_key, "reconciled")
    tb = check_trial_balance(conn, schema, tenant_id, period_key)
    run_id = latest_reconciliation_run_id(conn, schema, tenant_id, entity_id, period_key, "books_to_bank")
    # reconcile_period re-checks the predecessor. That is deliberate: it stays
    # correct on its own, called from here or from anywhere else.
    lock_id = reconcile_period(conn, schema, tenant_id, entity_id, period_key, current.mapping_version_id,
                                   trial_balance_balanced=tb.balanced, reconciliation_run_id=run_id,
                                   approved_by=approved_by)
    return ReconciledPeriod(lock_id=lock_id, trial_balance_total=tb.total, reconciliation_run_id=run_id)


def lock_period_from_current_state(conn, schema: str, tenant_id: str, entity_id: int, period_key: str,
                                       locked_by: str) -> int:
    """RECONCILED -> LOCKED, carrying the mapping version forward off the
    period's own lock row rather than taking one from the caller -- same
    reason as reconcile_period_from_current_checks. snapshot_at, the
    timestamp every future report for this period renders against, is pinned
    by lock_period itself."""
    current = _require_predecessor(conn, schema, tenant_id, entity_id, period_key, "locked")
    return lock_period(conn, schema, tenant_id, entity_id, period_key, current.mapping_version_id,
                          locked_by=locked_by)
