"""Resolving a queued exception is an append, not an update.

CLAUDE.md invariant 4: "A changed fact closes the prior row and inserts a
new one... There are no destructive updates in this system." The exception
queue's resolve path used to violate this with an in-place UPDATE, which was
harmless only while write_exceptions had no production caller and the table
was therefore always empty.

corpus/09 section 4 says an exception carries "its current status" and that
"nothing is dismissed without a reason." Both of those are load-bearing
here: the reason has to survive, and so does everything the exception said
when it was raised -- the rupee exposure that put it where it was in the
queue, the description, and when it was raised. An audit log recording that
a row used to be different is not the same thing as the row still being
there.
"""
from __future__ import annotations

from decimal import Decimal as D

from src.quality.checks import ExceptionCandidate, write_exceptions
from src.quality.exception_queue import (
    ExceptionNotFound,
    ResolutionRefused,
    get_current_exception,
    list_exceptions,
    resolve_exception,
)

ENTITY_ID = 1
PERIOD_KEY = "2025-03"


def _raise_one(conn, schema, tenant_id, *, severity="warning", value=D("125000.00"),
                description="test-injected exception"):
    [exception_id] = write_exceptions(conn, schema, tenant_id, ENTITY_ID, [
        ExceptionCandidate("reconciliation", severity, description, period_key=PERIOD_KEY,
                              object_type="period", object_ref=PERIOD_KEY, value_inr=value,
                              suggested_action="Investigate the residual."),
    ])
    return exception_id


def test_resolving_leaves_the_raised_row_intact_and_readable(conn, tenant):
    tenant_id, schema = tenant
    exception_id = _raise_one(conn, schema, tenant_id)

    with conn.cursor() as cur:
        cur.execute(
            f'SELECT status, value_inr, description, raised_at, resolution_note, root_exception_id '
            f'FROM "{schema}".exception WHERE exception_id = %s', (exception_id,))
        raised = cur.fetchone()
    assert raised[0] == "open"
    assert raised[5] is None, "the first version is its own root"

    resolve_exception(conn, schema, tenant_id, exception_id, "accepted",
                         "known synthetic residual, accepted for this period", "pytest-analyst")

    # The raised row is byte-for-byte what it was. Not archived, not flagged,
    # not rewritten -- untouched.
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT status, value_inr, description, raised_at, resolution_note, root_exception_id '
            f'FROM "{schema}".exception WHERE exception_id = %s', (exception_id,))
        after = cur.fetchone()
    assert after == raised, "resolving must not modify the row the exception was raised on"

    # And the resolution is a second, separate row pointing back at it.
    with conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM "{schema}".exception WHERE tenant_id = %s', (tenant_id,))
        assert cur.fetchone()[0] == 2
        cur.execute(
            f'SELECT status, resolved_by, resolution_note, value_inr, description, raised_at '
            f'FROM "{schema}".exception WHERE root_exception_id = %s', (exception_id,))
        version2 = cur.fetchone()
    assert version2[0] == "accepted"
    assert version2[1] == "pytest-analyst"
    assert version2[2] == "known synthetic residual, accepted for this period"
    # Carried forward verbatim: what it was worth, what it said, and when it
    # was RAISED -- not when it was resolved.
    assert (version2[3], version2[4], version2[5]) == (raised[1], raised[2], raised[3])


def test_current_status_is_derived_and_the_queue_reflects_it(conn, tenant):
    tenant_id, schema = tenant
    kept = _raise_one(conn, schema, tenant_id, value=D("400000.00"), description="stays open")
    resolved = _raise_one(conn, schema, tenant_id, value=D("900000.00"), description="gets accepted")

    open_keys = [r.exception_key for r in list_exceptions(conn, schema, tenant_id, "open")]
    assert open_keys == [resolved, kept], "corpus/09 section 4: by severity, then by money descending"

    resolve_exception(conn, schema, tenant_id, resolved, "accepted", "accepted in test", "pytest-analyst")

    assert [r.exception_key for r in list_exceptions(conn, schema, tenant_id, "open")] == [kept], \
        "a resolved exception must leave the open queue even though its raised row is still on disk"
    accepted = list_exceptions(conn, schema, tenant_id, "accepted")
    assert [r.exception_key for r in accepted] == [resolved]
    assert accepted[0].value_inr == D("900000.00")

    # Identity is stable across the resolution: the id the queue quoted
    # before is the id it quotes after.
    current = get_current_exception(conn, schema, tenant_id, resolved)
    assert current.exception_key == resolved
    assert current.version_exception_id != resolved, "the current status came from a later row"
    assert current.status == "accepted"


def test_a_resolved_blocking_exception_stops_blocking_signoff(conn, tenant):
    """The reader that would have broken loudest if it kept querying the base
    table: signoff.open_blocking_exceptions. The raised row's status stays
    'open' forever, so reading it directly would block sign-off for the
    period permanently, with no way back short of an UPDATE."""
    from src.reports.signoff import open_blocking_exceptions

    tenant_id, schema = tenant
    exception_id = _raise_one(conn, schema, tenant_id, severity="blocking", value=D("50000.00"))

    blocking = open_blocking_exceptions(conn, schema, tenant_id, ENTITY_ID, PERIOD_KEY)
    assert [b["exception_id"] for b in blocking] == [exception_id]

    resolve_exception(conn, schema, tenant_id, exception_id, "resolved",
                         "fixed at source and reloaded", "pytest-analyst")

    assert open_blocking_exceptions(conn, schema, tenant_id, ENTITY_ID, PERIOD_KEY) == []


def test_every_resolution_is_kept_when_an_exception_is_resolved_twice(conn, tenant):
    tenant_id, schema = tenant
    exception_id = _raise_one(conn, schema, tenant_id)

    resolve_exception(conn, schema, tenant_id, exception_id, "deferred",
                         "deferred to April, owner: pytest-analyst", "pytest-analyst")
    resolve_exception(conn, schema, tenant_id, exception_id, "resolved",
                         "supplier restated the invoice, residual cleared", "pytest-founder")

    assert get_current_exception(conn, schema, tenant_id, exception_id).status == "resolved"

    with conn.cursor() as cur:
        cur.execute(
            f'SELECT status, resolution_note FROM "{schema}".exception '
            f'WHERE tenant_id = %s ORDER BY exception_id', (tenant_id,))
        history = cur.fetchall()
    assert [h[0] for h in history] == ["open", "deferred", "resolved"]
    # The superseded reason is not lost. "Nothing is dismissed without a
    # reason" would be hollow if the reason could be replaced.
    assert history[1][1] == "deferred to April, owner: pytest-analyst"


def test_resolution_without_a_reason_is_refused_and_writes_nothing(conn, tenant):
    tenant_id, schema = tenant
    exception_id = _raise_one(conn, schema, tenant_id)

    for note in ("", "   "):
        try:
            resolve_exception(conn, schema, tenant_id, exception_id, "accepted", note, "pytest-analyst")
            assert False, "corpus/09 section 4: nothing is dismissed without a reason"
        except ResolutionRefused:
            pass

    try:
        resolve_exception(conn, schema, tenant_id, exception_id, "dismissed", "a reason", "pytest-analyst")
        assert False, "only corpus/09 section 4's resolution paths are accepted"
    except ResolutionRefused:
        pass

    try:
        resolve_exception(conn, schema, tenant_id, 10 ** 9, "accepted", "a reason", "pytest-analyst")
        assert False, "an unknown exception_id must not be silently accepted"
    except ExceptionNotFound:
        pass

    with conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM "{schema}".exception WHERE tenant_id = %s', (tenant_id,))
        assert cur.fetchone()[0] == 1, "a refused resolution writes no version"
    assert get_current_exception(conn, schema, tenant_id, exception_id).status == "open"
