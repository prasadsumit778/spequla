"""Resolution of a queued exception, corpus/09 section 4.

corpus/09 section 4 names four resolution paths -- "Fix at source and
reload. Map or reclassify. Accept with a written reason... Defer, with an
owner and a date" -- and one rule that governs all of them: "Nothing is
dismissed without a reason."

Per CLAUDE.md invariant #4 ("nothing is ever overwritten"), resolving does
not modify the raised exception. It INSERTs a new version of it carrying the
new status, exactly the way src/quality/period_state.py inserts a new
period_lock row for every transition rather than moving a status column
along. "Its current status" (corpus/09 section 4) is derived from the
versions, never stored as the mutation of a single row.

Two rows are versions of the same exception when they share
COALESCE(root_exception_id, exception_id) -- see
db/migrations/tenant/0024_exception_append_only.sql for why the lineage has
to be an explicit column here where period_lock got it free from a natural
key. That expression is the exception's stable identity, and it is what the
API, the pack and sign-off quote as exception_id; the physical row id of a
particular version is only of interest inside this module.

This module deliberately defines no transition preconditions. corpus/09
section 4 lists resolution paths and requires a reason; it does not state
which statuses may follow which, and CLAUDE.md section 3.1 forbids inventing
the rule that is missing. Re-resolving an already-resolved exception
therefore appends another version rather than being refused -- and because
nothing is overwritten, the earlier resolution and its reason remain
readable in full.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

# corpus/09 section 4's resolution paths, as statuses. 'resolved' is "fix at
# source and reload" / "map or reclassify" once done; 'accepted' is "accept
# with a written reason"; 'deferred' is "defer, with an owner and a date".
RESOLUTIONS = ("resolved", "accepted", "deferred")

# Columns copied verbatim onto every new version. raised_at is in this list
# on purpose: a resolution row must keep reporting when the exception was
# RAISED, not when it was resolved, or the queue's age and the pack's data
# quality appendix both start lying.
_CARRIED = ("tenant_id", "entity_id", "raised_at", "exception_class", "severity", "period_key",
            "object_type", "object_ref", "value_inr", "description", "suggested_action", "load_run_id")


@dataclass
class ExceptionRow:
    exception_key: int          # stable identity: the first version's exception_id
    version_exception_id: int   # the physical row this status came from
    exception_class: str
    severity: str
    status: str
    description: str
    period_key: str | None = None
    object_type: str | None = None
    object_ref: str | None = None
    value_inr: Decimal | None = None
    suggested_action: str | None = None
    raised_at: datetime | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None


_SELECT = ('exception_key, version_exception_id, exception_class, severity, status, description, '
           'period_key, object_type, object_ref, value_inr, suggested_action, raised_at, '
           'resolved_by, resolved_at, resolution_note')


class ExceptionNotFound(Exception):
    """No exception with that id in this tenant's queue."""


class ResolutionRefused(Exception):
    """corpus/09 section 4: "Nothing is dismissed without a reason." """


def get_current_exception(conn, schema: str, tenant_id: str, exception_id: int) -> ExceptionRow | None:
    """The latest version of the exception `exception_id` belongs to.
    Accepts either the stable identity or any one version's row id -- both
    resolve to the same group, so a client holding a stale id still reaches
    the current row rather than a 404.

    Shaped after src/quality/period_state.get_current_period_lock: one
    ordered read, no flag maintained anywhere."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT {_SELECT} FROM "{schema}".exception_current '
            f'WHERE tenant_id = %s AND exception_key = ('
            f'    SELECT COALESCE(root_exception_id, exception_id) FROM "{schema}".exception '
            f'    WHERE exception_id = %s AND tenant_id = %s)',
            (tenant_id, exception_id, tenant_id),
        )
        row = cur.fetchone()
    return ExceptionRow(*row) if row is not None else None


def list_exceptions(conn, schema: str, tenant_id: str, status: str) -> list[ExceptionRow]:
    """corpus/09 section 4's ordering: "By severity, then by value_inr
    descending. Always by money, never by count." Reads exception_current,
    so a resolved exception leaves the open queue even though its raised
    row is still on disk."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT {_SELECT} FROM "{schema}".exception_current '
            f'WHERE tenant_id = %s AND status = %s '
            f"ORDER BY CASE severity WHEN 'blocking' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, "
            f'value_inr DESC NULLS LAST',
            (tenant_id, status),
        )
        return [ExceptionRow(*r) for r in cur.fetchall()]


def open_blocking_exceptions(conn, schema: str, tenant_id: str, entity_id: int, period_key: str) -> list[dict]:
    """Every open BLOCKING exception for one period.

    One query with two callers, deliberately: corpus/08 section 10's sign-off
    gate ("a pack cannot be signed while a blocking exception is open for the
    period", src/reports/signoff.sign_pack) and corpus/09 section 5's
    OPEN -> VALIDATED condition ("all blocking checks pass",
    src/quality/period_state.validate_period, called from
    src/ingest/load_pipeline.load_gl_file). Two definitions of "a blocking
    exception is open" that could drift apart is exactly the shape of defect
    this system exists to prevent, so there is only one.

    Reads exception_current, not exception. Resolving an exception appends a
    new version rather than updating the raised row (CLAUDE.md invariant #4,
    db/migrations/tenant/0024), so the raised row keeps status='open'
    forever -- querying the base table here would leave a resolved blocking
    exception blocking sign-off, and now a period's validation, permanently.
    exception_id in the returned dicts is the stable identity, the same one
    the queue quotes.
    """
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT exception_key, exception_class, description, value_inr FROM "{schema}".exception_current '
            f"WHERE tenant_id = %s AND entity_id = %s AND period_key = %s AND status = 'open' "
            f"AND severity = 'blocking'",
            (tenant_id, entity_id, period_key),
        )
        return [{"exception_id": i, "exception_class": c, "description": d, "value_inr": v}
                  for i, c, d, v in cur.fetchall()]


def resolve_exception(conn, schema: str, tenant_id: str, exception_id: int, resolution: str,
                      resolution_note: str, resolved_by: str) -> ExceptionRow:
    """Appends a new version carrying the resolution. The raised row is not
    touched -- CLAUDE.md invariant #4.

    The INSERT ... SELECT reads the carried columns off exception_current
    rather than restating them from Python, so a new version cannot silently
    differ from the exception it claims to be a version of: the rupee
    exposure, the description and the raised_at that a reader sees after
    resolution are byte-for-byte the ones raised."""
    if resolution not in RESOLUTIONS:
        raise ResolutionRefused(f"resolution must be one of {', '.join(RESOLUTIONS)} "
                                f"-- corpus/09 section 4's resolution paths")
    if not resolution_note or not resolution_note.strip():
        raise ResolutionRefused('a resolution_note is required -- corpus/09 section 4: "Nothing is '
                                'dismissed without a reason."')
    if not resolved_by:
        raise ResolutionRefused("resolve_exception requires a named resolver, per corpus/06 section 4.3's "
                                "'every action is logged with a timestamp and a name'")

    current = get_current_exception(conn, schema, tenant_id, exception_id)
    if current is None:
        raise ExceptionNotFound(f"no exception {exception_id} in this tenant's queue")

    carried = ", ".join(_CARRIED)
    with conn.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{schema}".exception '
            f'({carried}, root_exception_id, status, resolved_by, resolved_at, resolution_note) '
            f'SELECT {carried}, exception_key, %s, %s, now(), %s '
            f'FROM "{schema}".exception_current WHERE tenant_id = %s AND exception_key = %s '
            f'RETURNING exception_id',
            (resolution, resolved_by, resolution_note.strip(), tenant_id, current.exception_key),
        )
        if cur.fetchone() is None:
            raise ExceptionNotFound(f"no exception {exception_id} in this tenant's queue")

    return get_current_exception(conn, schema, tenant_id, current.exception_key)
