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

from src.semantic.compiler import _fetch_leaf_amounts, leaf_amount_statements
from src.semantic.statements import (
    ExecutedStatement,
    distinct_statements,
    joined_sql,
    referenced_tables,
)

SCHEMA = "tenant_x"
CLASSES = ["revenue.product", "revenue.service"]


class _FakeCursor:
    """Records what it was asked to execute and returns nothing. Enough for
    _fetch_leaf_amounts: it reads rows as tuples and a set comprehension,
    both of which an empty result satisfies."""

    def __init__(self, log: list[tuple[str, tuple]]):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def fetchall(self):
        return []


class _FakeConn:
    def __init__(self):
        self.executed: list[tuple[str, tuple]] = []

    def cursor(self):
        return _FakeCursor(self.executed)


def _run(time_logic: str = "period_sum"):
    conn = _FakeConn()
    _, _, _, recorded = _fetch_leaf_amounts(
        conn, SCHEMA, "tenant-abc", 1, mapping_version_id=7, classes=CLASSES,
        time_logic=time_logic, period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
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
