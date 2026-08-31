"""A record of the statements the Ask path actually sent to Postgres.

corpus/07 section 7 puts seven gates "between a compiled query and the
database". A gate can only stand there if it inspects the statement that
reaches Postgres. Until 2026-08-31 it did not: src/semantic/ask_compiler.py
kept a hand-maintained string, `_representative_gl_class_sql`, whose
docstring claimed it "mirrors compiler.py's _fetch_leaf_amounts query shape
exactly" -- a claim nothing tested and nothing could have caught going
stale. src/semantic/compiler.py built and ran its own SQL independently.
The gates read the copy; Postgres read the original.

Every module on the Ask execution path now appends what it runs here, and
the gates read this record. `ExecutedStatement.sql` is the literal string
passed to `cursor.execute`, so a divergence between what runs and what is
gated is no longer expressible.

**What `gated` means.** True marks the compiled query itself -- corpus/07
section 2's stage 6 output, executed at stage 8. That is what admission
control covers.

False marks the lookups that resolve WHICH mapping version and WHICH
parameter set the query is compiled against:
src/reports/query.py's resolve_mapping_version_for_period and
src/semantic/overrides.py's resolve_parameters. Those are stage 6 *inputs*,
not the compiled query, and one of them reads `metric_definition` -- a table
named in admission.py's FORBIDDEN_TABLES and absent from
CANONICAL_TABLE_ALLOWLIST, so gating them would reject every Ask metric
query at gate 3 before a number was ever computed. They are recorded rather
than hidden: the boundary is visible in the returned object instead of being
invisible in the code, and this docstring is where it is drawn. Whether
`metric_definition` belongs in FORBIDDEN_TABLES at all is a live question
(corpus/07 section 7 gate 5's own text names "token_map, audit_log and all
app tables"; metric_definition is a tenant-schema table, not an app table) --
a deliberate decision to record and disclose, not to resolve here.

**What is not recorded at all**, and is therefore neither gated nor visible
here: the period gate's own reads (src/quality/period_gate.py, corpus/09
section 5), which run before compilation to decide whether a period may be
read at all, and statement assembly's reads on the statement_view intent
(src/reports/pnl.py, balance_sheet.py, query.py's class_movements/
class_balances). The second of those is a real remaining hole -- the
statement_view intent reaches Postgres with no gate in front of it, exactly
as every intent did before this change -- and threading the record through
report assembly is a wider change than this one, since those functions are
shared with the monthly pack and the overview tiles.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class AdmittedStatement:
    """What admission control hands back for one statement: the SQL to
    execute, and the row cap it applied.

    `sql` is gate 7's output, not its input -- corpus/07 section 7 gate 7 is
    "Row cap. Applied", so the caller executes THIS text, not the text it
    submitted. Until 2026-08-31 nothing in the repo read it: gate 7 computed
    D-067's LIMIT 10000 and run_admission_gates returned it into a field
    with no consumer anywhere.

    `row_cap` is the cap actually applied, or None when the statement
    already carried its own LIMIT and gate 7 left it alone. The executor
    needs the number, not just the text: a cap that truncates a result which
    is then aggregated produces a number that is short and says nothing
    about it, so the executor compares the rows it got against this."""
    sql: str
    row_cap: int | None = None


# Stage 7 standing between stage 6 and stage 8 (corpus/07 section 2), as a
# type. A compiler holding one of these calls it immediately before each
# `cursor.execute` and runs whatever comes back; a compiler holding None is
# off the Ask surface -- the monthly pack and the overview tiles, which are
# deterministic paths with no model anywhere near them -- and executes what
# it built. Raises AdmissionRejected (src/semantic/admission.py) to stop a
# statement reaching Postgres at all.
AdmissionHook = Callable[[str, tuple[str, ...]], AdmittedStatement]


@dataclass(frozen=True)
class ExecutedStatement:
    """One statement, as executed. `sql` is the literal text handed to
    `cursor.execute` -- never a reconstruction of it. `tables` is what that
    statement reads, for gates 3 and 5. Frozen because a record of what has
    already run is not something a later caller may edit."""
    sql: str
    tables: tuple[str, ...] = ()
    gated: bool = True


def distinct_statements(statements: Iterable[ExecutedStatement]) -> list[ExecutedStatement]:
    """Deduplicated by SQL text, in first-seen order.

    A derived metric is a tree of leaf queries, not one query: `ebitda`
    resolves through gross_profit and net_revenue to five leaves, and
    dso/dpo/dio recompile their base metric over twelve trailing months
    (compiler.py's _trailing_twelve_months_value). That is dozens of
    executions of a handful of distinct statement texts -- the parameters
    differ, the SQL does not. Gate results are a pure function of the SQL
    text, the tables and the tenant, so collapsing repeats loses no
    rejection the gates would otherwise make, and keeps the query_log entry
    and the "view SQL" panel readable."""
    seen: set[str] = set()
    out: list[ExecutedStatement] = []
    for statement in statements:
        if statement.sql not in seen:
            seen.add(statement.sql)
            out.append(statement)
    return out


def joined_sql(statements: Iterable[ExecutedStatement]) -> str | None:
    """The distinct statements as one display/log string, or None if nothing
    ran. Feeds AskResult.sql_text -- app.query_log's sql_text column and
    corpus/08 section 2's "view SQL" panel -- which is one string by
    contract. Never gated as a unit: the gates run per statement, on the
    text each `cursor.execute` receives."""
    distinct = distinct_statements(statements)
    if not distinct:
        return None
    return ";\n\n".join(s.sql for s in distinct)


def referenced_tables(statements: Iterable[ExecutedStatement]) -> list[str]:
    """Union of every statement's tables, first-seen order. Informational
    only: gates 3 and 5 read each statement's own `tables`, never this
    aggregate, so a statement cannot borrow another's allowlist standing."""
    seen: set[str] = set()
    out: list[str] = []
    for statement in statements:
        for table in statement.tables:
            if table not in seen:
                seen.add(table)
                out.append(table)
    return out
