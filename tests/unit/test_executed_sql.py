"""The recorded SQL is the executed SQL, not a description of it.

corpus/07 section 7 puts seven gates "between a compiled query and the
database". Until 2026-08-31 they were not: src/semantic/ask_compiler.py
built `_representative_gl_class_sql`, a hand-maintained string whose
docstring claimed it "mirrors compiler.py's _fetch_leaf_amounts query shape
exactly", and handed THAT to the gates, while compile_metric built and ran
its own SQL independently. Nothing in the repo compared the two. They had
already drifted: the reconstruction used `ma.canonical_class = ANY(%s)`,
selected two columns and had no GROUP BY; the executed statement used
`IN (%s, %s, ...)`, selected three columns, grouped by canonical_class, and
was one of a PAIR -- the second (DISTINCT load_run_id) had no counterpart in
the reconstruction at all.

These tests fail if that separation is ever reintroduced. They use a fake
connection that records the exact string handed to `cursor.execute`, so the
assertion is against psycopg's own argument, not against a second
description of it. No database: the point is the text, not the rows.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.semantic.compiler import RowCapTruncated, _fetch_leaf_amounts, leaf_amount_statements
from src.semantic.statements import (
    AdmittedStatement,
    ExecutedStatement,
    distinct_statements,
    joined_sql,
    referenced_tables,
)

SCHEMA = "tenant_x"
CLASSES = ["revenue.product", "revenue.service"]


class _FakeCursor:
    """Records what it was asked to execute and returns `rows`. Enough for
    _fetch_leaf_amounts: it reads rows as tuples and a set comprehension."""

    def __init__(self, log: list[tuple[str, tuple]], rows: list[tuple]):
        self.log = log
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def fetchall(self):
        return self.rows


class _FakeConn:
    def __init__(self, rows: list[tuple] | None = None):
        self.executed: list[tuple[str, tuple]] = []
        self.rows = rows or []

    def cursor(self):
        return _FakeCursor(self.executed, self.rows)


def _run(time_logic: str = "period_sum", conn=None, admission=None):
    conn = conn or _FakeConn()
    _, _, _, recorded = _fetch_leaf_amounts(
        conn, SCHEMA, "tenant-abc", 1, mapping_version_id=7, classes=CLASSES,
        time_logic=time_logic, period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
        admission=admission,
    )
    return conn, recorded


def test_every_executed_statement_is_recorded_verbatim():
    conn, recorded = _run()
    assert [s.sql for s in recorded] == [sql for sql, _ in conn.executed]


def test_both_statements_of_a_leaf_are_recorded_not_just_the_first():
    # The reconstruction this replaced described one statement. A leaf runs
    # two, and the second reads the same three tables -- so gating only the
    # first left a real query on fact_gl_entry unexamined.
    conn, recorded = _run()
    assert len(conn.executed) == 2
    assert len(recorded) == 2
    assert "GROUP BY ma.canonical_class" in recorded[0].sql
    assert "SELECT DISTINCT fg.load_run_id" in recorded[1].sql


def test_recorded_statements_are_marked_gated():
    _, recorded = _run()
    assert all(s.gated for s in recorded), "the compiled query is what admission control covers"


def test_recorded_tables_are_the_tables_the_statement_joins():
    _, recorded = _run()
    for statement in recorded:
        for table in (f'"{SCHEMA}".fact_gl_entry', f'"{SCHEMA}".dim_account', f'"{SCHEMA}".map_account'):
            assert table in statement.tables
            assert table in statement.sql


def test_placeholder_count_matches_the_bound_class_list():
    # The one part of the text that varies with the request. A builder that
    # got this wrong would have been invisible while the gates read a
    # separate string; now it is the string that runs.
    conn, _ = _run()
    for sql, params in conn.executed:
        assert sql.count("%s") == len(params)


def test_period_end_and_period_sum_produce_different_date_filters():
    _, period_sum = _run("period_sum")
    _, period_end = _run("period_end")
    assert "BETWEEN %s AND %s" in period_sum[0].sql
    assert "fg.event_date <= %s" in period_end[0].sql
    assert period_sum[0].sql != period_end[0].sql


def test_builder_and_executor_cannot_diverge():
    # There is one builder and one caller of it. Asserting they agree is
    # asserting the property the deleted docstring only claimed.
    conn, _ = _run()
    amounts_sql, load_runs_sql, _ = leaf_amount_statements(SCHEMA, len(CLASSES), "period_sum")
    assert [sql for sql, _ in conn.executed] == [amounts_sql, load_runs_sql]


def test_no_statements_recorded_when_no_classes_match():
    # A formula matching no canonical class issues no query, so it must
    # report none. Reporting SQL for a query that never ran is the failure
    # this whole change exists to remove.
    conn = _FakeConn()
    amounts, row_count, load_runs, recorded = _fetch_leaf_amounts(
        conn, SCHEMA, "tenant-abc", 1, 7, [], "period_sum", date(2026, 4, 1), date(2026, 4, 30))
    assert (amounts, row_count, load_runs, recorded) == ({}, 0, set(), [])
    assert conn.executed == []


class TestStatementRecord:
    """src/semantic/statements.py's own helpers."""

    def test_distinct_collapses_repeats_in_first_seen_order(self):
        a = ExecutedStatement("SELECT 1", ("t1",))
        b = ExecutedStatement("SELECT 2", ("t2",))
        assert distinct_statements([a, b, a, b, a]) == [a, b]

    def test_joined_sql_is_none_when_nothing_ran(self):
        assert joined_sql([]) is None

    def test_joined_sql_renders_every_distinct_statement(self):
        a = ExecutedStatement("SELECT 1", ("t1",))
        b = ExecutedStatement("SELECT 2", ("t2",))
        rendered = joined_sql([a, b, a])
        assert "SELECT 1" in rendered and "SELECT 2" in rendered
        assert rendered.count("SELECT") == 2

    def test_referenced_tables_unions_without_duplicating(self):
        a = ExecutedStatement("SELECT 1", ("t1", "t2"))
        b = ExecutedStatement("SELECT 2", ("t2", "t3"))
        assert referenced_tables([a, b]) == ["t1", "t2", "t3"]

    def test_a_statement_record_cannot_be_edited_after_the_fact(self):
        statement = ExecutedStatement("SELECT 1", ("t1",))
        try:
            statement.sql = "SELECT 2"
            assert False, "a record of what already ran must not be rewritable"
        except Exception:
            pass


class TestAdmissionRunsBeforeExecution:
    """The hook is called before `cursor.execute`, and what it returns is
    what runs. No database: the question is ordering and text, not rows.
    tests/integration/test_ask_admission_ordering.py asks the same questions
    of the live path."""

    def test_both_statements_of_a_leaf_are_admitted_before_either_executes(self):
        # A leaf is atomic. A tree is not -- a rejection at the fifth leaf
        # leaves the first four run -- but a rejection must never land
        # between the two halves of one leaf's read.
        order: list[str] = []

        def admission(sql, tables):
            order.append(f"admit:{'amounts' if 'GROUP BY' in sql else 'load_runs'}")
            return AdmittedStatement(sql, None)

        conn = _FakeConn()
        original_execute = _FakeCursor.execute

        def spy_execute(self, sql, params=None):
            order.append(f"execute:{'amounts' if 'GROUP BY' in sql else 'load_runs'}")
            return original_execute(self, sql, params)

        _FakeCursor.execute = spy_execute
        try:
            _run(conn=conn, admission=admission)
        finally:
            _FakeCursor.execute = original_execute

        assert order == ["admit:amounts", "admit:load_runs", "execute:amounts", "execute:load_runs"]

    def test_the_text_the_hook_returns_is_the_text_that_executes(self):
        def admission(sql, tables):
            return AdmittedStatement(f"{sql} LIMIT 10000", 10_000)

        conn, recorded = _run(admission=admission)
        assert all(sql.endswith("LIMIT 10000") for sql, _ in conn.executed)
        # And the record follows the cap, so query_log and the "view SQL"
        # panel show what ran rather than what was submitted.
        assert all(s.sql.endswith("LIMIT 10000") for s in recorded)

    def test_a_rejecting_hook_stops_the_statement_reaching_the_cursor(self):
        class Rejected(Exception):
            pass

        def admission(sql, tables):
            raise Rejected()

        conn = _FakeConn()
        with pytest.raises(Rejected):
            _run(conn=conn, admission=admission)
        assert conn.executed == [], "a rejected statement was executed anyway"

    def test_no_hook_means_no_cap_and_no_rewrite(self):
        # The monthly pack and overview tiles path: deterministic, no model,
        # no gates, unchanged text.
        conn, recorded = _run()
        assert not any("LIMIT" in sql.upper() for sql, _ in conn.executed)
        assert all(s.gated for s in recorded)


class TestRowCapTripwire:
    """D-067's LIMIT 10000 applied to a GROUP BY aggregate whose rows are
    then summed is a silent-wrong-number path. Exactly-cap must fail loudly.

    The cap is set to 2 here rather than 10,000 so the condition is
    reachable in a unit test. The number is not the point; the comparison
    is. Against real query shapes this cannot fire -- both statements
    collapse to at most the taxonomy's classes and the entity's load runs --
    which is why it is a tripwire rather than a handler."""

    def test_exactly_the_cap_raises_rather_than_returning_a_short_value(self):
        def admission(sql, tables):
            return AdmittedStatement(f"{sql} LIMIT 2", 2)

        conn = _FakeConn(rows=[("revenue.product", 100, 5), ("revenue.service", 50, 3)])
        with pytest.raises(RowCapTruncated) as raised:
            _run(conn=conn, admission=admission)
        assert raised.value.row_cap == 2
        assert raised.value.row_count == 2

    def test_the_message_names_D_067_and_the_statement(self):
        def admission(sql, tables):
            return AdmittedStatement(f"{sql} LIMIT 2", 2)

        conn = _FakeConn(rows=[("a", 1, 1), ("b", 2, 1)])
        with pytest.raises(RowCapTruncated) as raised:
            _run(conn=conn, admission=admission)
        message = str(raised.value)
        assert "D-067" in message
        assert "fact_gl_entry" in message, "the statement that tripped it must be named"
        assert "summed" in message

    def test_under_the_cap_returns_normally(self):
        def admission(sql, tables):
            return AdmittedStatement(f"{sql} LIMIT 5", 5)

        conn = _FakeConn(rows=[("revenue.product", 100, 5)])
        conn_, recorded = _run(conn=conn, admission=admission)
        assert len(recorded) == 2

    def test_an_uncapped_statement_is_never_checked(self):
        # row_cap None means gate 7 applied nothing -- there is no
        # truncation to suspect, however many rows come back.
        def admission(sql, tables):
            return AdmittedStatement(sql, None)

        conn = _FakeConn(rows=[("a", 1, 1)] * 50)
        _run(conn=conn, admission=admission)  # must not raise
