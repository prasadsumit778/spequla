"""Seven admission-control gates, corpus/07 section 7.

"Seven deterministic gates between a compiled query and the database. Every
rejection is logged with the user, the IR and the reason." These run against
the SQL TEXT the compiler produces (src/semantic/ask_compiler.py), not
against the IR -- the whole point is to catch anything the compiler itself
might get wrong, on the actual string about to reach Postgres, not on the
compiler's own intent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

import sqlparse
from sqlparse.sql import Comparison, Parenthesis, Statement, Where
from sqlparse.tokens import Comment, DML, Keyword, Name, Number, Punctuation, String

from src.semantic.statements import AdmittedStatement

CANONICAL_TABLE_ALLOWLIST = {
    "fact_gl_entry", "fact_bank_txn", "dim_account", "dim_date", "dim_entity",
    "map_account", "mapping_version", "period_lock", "reconciliation_run",
}

# corpus/07 section 7 gate 2: "No DDL, no DML, no functions that touch the
# filesystem." Read-only means exactly SELECT (and WITH ... SELECT, a CTE).
#
# This list is the SECOND half of gate 2 and no longer its whole substance.
# The first half is now structural -- sqlparse's statement type must be
# SELECT -- which is an allowlist and catches the things a denylist keeps
# missing: MERGE, CALL, DO, SET ROLE and EXPLAIN all passed the list below
# before 2026-08-31, and all are rejected by the type check now. What a
# denylist is still needed for is the "functions that touch the filesystem"
# half, which lives inside an otherwise-legitimate SELECT and has no
# structural signature. Extended at the same time with the keywords the
# original list missed; verified to false-positive on none of the five
# statement shapes this compiler emits.
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|MERGE|CALL|DO|"
    r"EXECUTE|PREPARE|VACUUM|ANALYZE|REINDEX|CLUSTER|LOCK|SET|RESET|LISTEN|NOTIFY|"
    r"pg_read_file|pg_read_binary_file|pg_ls_dir|pg_ls_logdir|pg_stat_file|pg_sleep|"
    r"lo_import|lo_export|dblink|dblink_connect)\b",
    re.IGNORECASE,
)

# Keywords after which a table name is expected. Used to find what a
# statement actually reads (_tables_in_sql) rather than trusting what its
# caller says it reads.
_TABLE_INTRODUCERS = {"FROM", "JOIN", "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL JOIN",
                         "LEFT OUTER JOIN", "RIGHT OUTER JOIN", "FULL OUTER JOIN", "CROSS JOIN",
                         "STRAIGHT_JOIN", "INTO", "UPDATE", "TABLE"}


class UnresolvableTableReference(Exception):
    """A table introducer whose target this walk could not resolve to a
    name. Never swallowed: see _tables_in_sql on why the only safe response
    is a rejection."""


def _parse_all(sql_text: str, gate: str) -> list[Statement]:
    """Every statement in the submission.

    Gates 2 to 5 check all of them rather than only the first. Rejecting a
    multi-statement submission is gate 1's job, but a gate called on its own
    must still reject on its own grounds: gate 2 given
    `SELECT 1; DROP TABLE x` has to fail as read_only, not lean on gate 1
    having run. Each gate is a check, not a step in a sequence that only
    works in order."""
    parsed = sqlparse.parse(sql_text.strip())
    if not parsed:
        raise AdmissionRejected(gate, "empty SQL text")
    return list(parsed)


def _parse_one(sql_text: str) -> Statement:
    """The single parsed statement -- gate 1's own rule, that a submission
    is one statement, and nothing else's."""
    parsed = _parse_all(sql_text, "parse")
    if len(parsed) > 1:
        raise AdmissionRejected(
            "parse", f"{len(parsed)} statements in one submission -- admission control admits one statement "
                        f"at a time, and a second statement after a semicolon is exactly what that exists to stop")
    return parsed[0]


def _code_tokens(statement: Statement):
    """Tokens excluding string literals and comments -- the part of a
    statement that Postgres executes as code.

    Paren counting and keyword scanning both run over this rather than over
    the raw text. `WHERE narration = ':-('` read as unbalanced parentheses
    before 2026-08-31, and a keyword inside a comment or a quoted string
    counted as a keyword."""
    return [t for t in statement.flatten()
              if t.ttype not in String and t.ttype not in Comment]


def _code_text(statement: Statement) -> str:
    return "".join(t.value for t in _code_tokens(statement))


def _tables_in_sql(sql_text: str) -> list[str]:
    """Every table the SQL itself names, read out of the statement.

    Gates 3 and 5 took `sql_text` and never referenced it, checking instead
    the `tables_referenced` list their own caller handed them -- the
    compiler's self-description, not the query. A query touching
    app.token_map passed both if the caller simply did not list it. This is
    what they read now.

    **Deny by default.** sqlparse is a tokenizer, not a parser with a real
    grammar, so this walk is a token walk and there are certainly SQL forms
    it cannot resolve. Every one of those raises rather than returning a
    short list: an unresolved table introducer becomes a rejected query,
    which is loud and wrong in the safe direction, never a silently
    unchecked table. Subqueries need no special handling -- flatten() walks
    into them, so a table named only inside one is found the same way."""
    tokens = [t for statement in sqlparse.parse(sql_text.strip())
                 for t in statement.flatten()
                 if not t.is_whitespace and t.ttype not in Comment]
    found: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if not (token.ttype in (Keyword, DML) and token.normalized.upper() in _TABLE_INTRODUCERS):
            continue
        # A derived table -- FROM ( SELECT ... ) -- names nothing here; the
        # tables inside it are reached by this same walk.
        if i < len(tokens) and tokens[i].ttype is Punctuation and tokens[i].value == "(":
            continue
        parts: list[str] = []
        while i < len(tokens) and tokens[i].ttype in (Name, String.Symbol):
            parts.append(tokens[i].value)
            i += 1
            if i < len(tokens) and tokens[i].ttype is Punctuation and tokens[i].value == ".":
                parts.append(".")
                i += 1
            else:
                break  # anything after a complete name is an alias, not the table
        if not parts:
            raise UnresolvableTableReference(
                f"could not resolve what follows {token.value!r} to a table name")
        found.append("".join(parts))
    return found


def _bare(table: str) -> str:
    return table.split(".")[-1].strip('"')

# corpus/07 section 7 gate 5: "No column outside the model-reachable views.
# token_map, audit_log and all app tables are not granted." These never
# appear in a compiled Ask query -- this list exists so the gate has
# something concrete to check against, not because the compiler is expected
# to ever reference them.
FORBIDDEN_TABLES = {"token_map", "audit_log", "load_run", "source_file", "exception",
                       "query_log", "tenant", "metric_definition"}


class AdmissionRejected(Exception):
    """Raised by a gate, and -- since 2026-08-31 -- allowed to propagate out
    of the compiler so the statement that provoked it is never executed.
    `sql_text` is the statement rejected, carried so corpus/07 section 7's
    "every rejection is logged with the user, the IR and the reason" can log
    which of a tree's statements it was."""

    def __init__(self, gate: str, reason: str, sql_text: str | None = None):
        self.gate = gate
        self.reason = reason
        self.sql_text = sql_text
        super().__init__(f"gate {gate!r} rejected: {reason}")


@dataclass
class AdmissionResult:
    admitted: bool
    gate: str | None = None
    reason: str | None = None
    sql_text: str | None = None      # gate 7's output: the text to execute
    row_cap: int | None = None       # the cap gate 7 applied, None if the statement had its own LIMIT


def gate_1_parse(sql_text: str) -> None:
    """corpus/07 section 7 gate 1: "Compiles to a valid AST."

    **This checks structure, not grammar, and the difference is worth
    stating.** sqlparse does not validate SQL: `SELECT FROM WHERE ((( GROUP`
    parses cleanly and reports its type as SELECT. So what this gate
    establishes is that the submission is exactly one statement, opens as a
    read query, and has balanced parentheses in its code -- not that
    Postgres would accept it. The only thing that can decide the latter is
    Postgres, via PREPARE or EXPLAIN, which means a database round trip
    inside admission control. That is a design change and is not made here.

    Two real holes closed on 2026-08-31: `SELECT 1; DROP TABLE x` passed
    intact, because nothing looked for a second statement; and a parenthesis
    inside a string literal (`WHERE narration = ':-('`) read as unbalanced,
    because the count ran over raw text."""
    stripped = sql_text.strip()
    if not stripped:
        raise AdmissionRejected("parse", "empty SQL text")
    if not re.match(r"^\s*(SELECT|WITH)\b", stripped, re.IGNORECASE):
        raise AdmissionRejected("parse", "does not start with SELECT or WITH -- not a valid read query")
    statement = _parse_one(stripped)
    code = _code_text(statement)
    if code.count("(") != code.count(")"):
        raise AdmissionRejected("parse", "unbalanced parentheses")


def gate_2_read_only(sql_text: str) -> None:
    """corpus/07 section 7 gate 2: "No DDL, no DML, no functions that touch
    the filesystem."

    An allowlist first, a denylist second. The statement's own type must be
    SELECT -- structural, and it rejects the whole class a keyword denylist
    keeps leaking (MERGE, CALL, DO, SET ROLE, EXPLAIN all passed before
    2026-08-31). The denylist then runs over code tokens only, for the
    filesystem-function half, which hides inside a legitimate SELECT and has
    no structural signature.

    Neither is the real control. corpus/07 section 7's own note -- "the
    model-reachable role is a database object, not a code path" -- names
    that, and src/semantic/ask.py's _execute_as_model_reachable documents
    why the role is not yet used. These checks are what stands in for it."""
    for statement in _parse_all(sql_text, "read_only"):
        statement_type = statement.get_type()
        if statement_type != "SELECT":
            raise AdmissionRejected(
                "read_only", f"statement type {statement_type!r} is not SELECT -- read-only queries only")
        match = _FORBIDDEN_KEYWORDS.search(_code_text(statement))
        if match:
            raise AdmissionRejected("read_only", f"forbidden keyword {match.group(0)!r} -- read-only queries only")


def gate_3_table_allowlist(sql_text: str, tables_referenced: list[str]) -> None:
    """corpus/07 section 7 gate 3: "Only canonical tables and approved views
    visible to this role."

    Reads the SQL. Until 2026-08-31 this took `sql_text` and never
    referenced it, checking only `tables_referenced` -- a list handed in by
    the same compiler the gate exists to check, which made it a test of the
    compiler's self-description rather than of the query.

    Three checks, in order of what each catches:

      1. Every table the SQL names is in the allowlist. This is the check
         the gate was always supposed to be.
      2. Every table the SQL names was also declared by the caller. A
         statement that reads something its caller did not mention is
         rejected even when that something is allowlisted -- a compiler
         emitting an undeclared join is a defect whether or not the table is
         canonical, and this is the specific hole that let a query touching
         app.token_map through when the caller simply did not list it.
      3. The declared list is still checked on its own terms, so an
         over-declared non-canonical table is a rejection rather than a
         harmless mismatch.

    A table reference this walk cannot resolve is a rejection, not a pass."""
    try:
        named = _tables_in_sql(sql_text)
    except UnresolvableTableReference as e:
        raise AdmissionRejected("table_allowlist", f"{e} -- a table this gate cannot identify is not admitted")

    for table in named:
        if _bare(table) not in CANONICAL_TABLE_ALLOWLIST:
            raise AdmissionRejected("table_allowlist", f"{table!r} is not a canonical table or approved view")

    declared = {_bare(t) for t in tables_referenced}
    undeclared = sorted({_bare(t) for t in named} - declared)
    if undeclared:
        raise AdmissionRejected(
            "table_allowlist",
            f"the statement reads {undeclared} which the caller did not declare -- what a query touches and "
            f"what its compiler says it touches must agree")

    for table in tables_referenced:
        if _bare(table) not in CANONICAL_TABLE_ALLOWLIST:
            raise AdmissionRejected("table_allowlist", f"{table!r} is not a canonical table or approved view")


def gate_4_tenant_predicate(sql_text: str, tenant_id: str) -> None:
    """corpus/07 section 7 gate 4: "Tenant predicate. Present and correct.
    Enforced by row-level security at the connection role, not by the query
    text."

    **Present** is enforced here. The predicate must appear in the
    statement's own WHERE clause, at that clause's level -- not merely
    somewhere in the string. The substring search this replaced admitted
    `SELECT tenant_id FROM fact_gl_entry`, which has no WHERE clause at all,
    and admitted a tenant_id that scoped only a subquery.

    **Correct** is not enforced here, and cannot be. Every statement this
    compiler emits binds its tenant as a parameter, so the value is not in
    the text this gate receives; the check that ran before -- `if tenant_id
    not in sql_text and "%s" not in sql_text` -- was dead by construction,
    since "%s" is present in every parameterised query, and had never fired.
    What is checked instead is the one case that IS visible: a tenant id
    written into the text as a literal must be this tenant. That is a
    tripwire against a compiler that string-formats a tenant id rather than
    binding it, which would be an injection route as well as a scoping bug.
    It cannot fire against today's compiler, by design.

    Enforcing "correct" properly is what the corpus's own sentence
    describes: row-level security at the connection role. RISKS.md section 1
    records that as not in force -- the application connects as a Postgres
    superuser, which bypasses RLS unconditionally -- and that is
    infrastructure, not this function."""
    for statement in _parse_all(sql_text, "tenant_predicate"):
        where = next((t for t in statement.tokens if isinstance(t, Where)), None)
        if where is None:
            raise AdmissionRejected("tenant_predicate",
                                        "no WHERE clause -- no tenant predicate can be present in one")

        # Nested parentheses hold subqueries, whose predicates scope
        # themselves and not this statement's rows.
        outer = "".join(t.value for t in where.tokens
                           if not isinstance(t, Parenthesis) and t.ttype not in Comment)
        if "tenant_id" not in outer:
            raise AdmissionRejected(
                "tenant_predicate",
                "no tenant_id predicate in the statement's own WHERE clause -- a tenant_id appearing in the "
                "select list, a comment or a subquery does not scope the rows this statement returns")

        for comparison in (t for t in where.tokens if isinstance(t, Comparison)):
            if "tenant_id" not in str(comparison):
                continue
            literals = [t.value.strip("'") for t in comparison.flatten()
                          if t.ttype in String.Single or t.ttype in Number]
            if literals and tenant_id not in literals:
                raise AdmissionRejected(
                    "tenant_predicate",
                    f"the tenant predicate names a literal tenant that is not this one ({comparison}) -- a "
                    f"tenant id belongs in a bound parameter, never formatted into SQL text")


def gate_5_pii_exclusion(sql_text: str, tables_referenced: list[str]) -> None:
    """corpus/07 section 7 gate 5: "No column outside the model-reachable
    views. token_map, audit_log and all app tables are not granted."

    **The table half is enforced**, and now against the SQL rather than
    against the caller's declaration of it -- the same defect gate 3 had.
    Both the statement's own tables and the declared list are checked, so
    this stays defence in depth for gate 3 rather than a duplicate of it:
    it is what catches a forbidden table if the allowlist is ever widened by
    mistake.

    **The column half is NOT enforced, and is not silently skipped.**
    "The model-reachable views" do not exist. The only view in this repo is
    `exception_current` (db/migrations/tenant/0024), which is REVOKEd from
    model_reachable; every grant in db/migrations/tenant/ is table-level
    GRANT SELECT on a base table. So this half of the gate is written
    against a set of database objects that was never built, and there is no
    column list -- in the corpus or the repo -- to check membership against.
    Supplying one would mean choosing which columns are confidential and
    calling the choice policy, which is CLAUDE.md section 3.2's prohibition
    exactly. D-058 (corpus/00, resolved) states what those views must
    contain: employees excluded entirely, customers and vendors tokenised
    with group, segment and category retained. Building them is a schema
    deliverable, not a gate body. Raised as OPEN_QUESTIONS.md OQ-020."""
    try:
        named = _tables_in_sql(sql_text)
    except UnresolvableTableReference as e:
        raise AdmissionRejected("pii_exclusion", f"{e} -- a table this gate cannot identify is not admitted")

    for table in [*named, *tables_referenced]:
        if _bare(table) in FORBIDDEN_TABLES:
            raise AdmissionRejected("pii_exclusion", f"{table!r} is not a model-reachable table")


# D-066 (corpus/00, resolved 2026-08-24, OQ-003): gate 6's "cost estimate" is
# the AI model spend for this question (tokens x pricing -- the same cost_inr
# figure query_log already has columns for, corpus/12 sprint 7), not a row
# count. Row count is gate 7's job; the two were conflated before this
# resolution. A question is rejected outright, before it reaches the
# database, if its estimated model spend would exceed this.
COST_CAP_INR_PER_QUERY = Decimal("5")


def gate_6_cost_estimate(estimated_cost_inr: Decimal | None, cap: Decimal | None = COST_CAP_INR_PER_QUERY) -> None:
    """estimated_cost_inr is None until a real ModelClient reports token
    usage -- AnthropicModelClient is still an explicitly unconfigured
    connection point (src/semantic/model_client.py), a separate, disclosed
    gap from this one. The cap itself (D-066) is real and declared now; this
    gate has nothing to compare it against yet only because nothing upstream
    produces a cost figure yet, which is a different problem than an
    undeclared cap. None never rejects -- there's nothing to reject on."""
    if cap is not None and estimated_cost_inr is not None and estimated_cost_inr > cap:
        raise AdmissionRejected("cost_estimate",
                                    f"estimated cost ₹{estimated_cost_inr} exceeds the configured cap ₹{cap}")


# D-067 (corpus/00, resolved 2026-08-24, OQ-003): confirmed as real policy,
# not a placeholder -- corpus/07 section 7 gate 7, "Row cap. Applied."
ROW_CAP = 10_000


def gate_7_row_cap(sql_text: str) -> tuple[str, int | None]:
    """Returns the SQL to execute and the cap applied to it.

    **Gate 7 does not reject.** Gates 1-6 raise; this one rewrites and
    returns, because corpus/07 section 7 states it as "Row cap. Applied" --
    applied, not checked. A cap that aborted the statement would abort every
    statement, since nothing the compiler emits carries a LIMIT of its own.

    The second element is the cap that went on, or None when the statement
    already had a LIMIT and this gate left it alone. Returned rather than
    left implicit in the text so the executor can tell a full result from a
    truncated one -- see compiler.py's RowCapTruncated for why that
    distinction is not optional.

    "Already has a LIMIT" means at the statement's own level. A regex over
    the whole string matched a LIMIT inside a subquery too, so
    `SELECT * FROM (SELECT x FROM t LIMIT 5) s` read as capped and its outer
    result went out uncapped -- the one case where this gate silently
    applied nothing (fixed 2026-08-31)."""
    if _has_top_level_limit(sql_text):
        return sql_text, None
    return f"{sql_text.rstrip().rstrip(';')} LIMIT {ROW_CAP}", ROW_CAP


def _has_top_level_limit(sql_text: str) -> bool:
    """A LIMIT belonging to this statement, not to a subquery nested in it.
    sqlparse keeps a parenthesised subquery as a single child token, so a
    LIMIT among the statement's own top-level tokens is the statement's."""
    try:
        statement = _parse_one(sql_text)
    except AdmissionRejected:
        # Unparseable here means gate 1 already rejected it, or will. Cap it
        # anyway rather than treat "cannot tell" as "already capped".
        return False
    return any(token.ttype is Keyword and token.normalized.upper() == "LIMIT"
                  for token in statement.tokens)


def run_admission_gates(sql_text: str, tables_referenced: list[str], tenant_id: str,
                           estimated_cost_inr: Decimal | None = None,
                           cost_cap: Decimal | None = COST_CAP_INR_PER_QUERY) -> AdmissionResult:
    """Runs all seven gates in order. Returns the row-capped SQL text and
    the cap on success, or a result naming the first gate that rejected --
    corpus/07 section 7: 'Every rejection is logged with the user, the IR
    and the reason.'

    The returned `sql_text` is what the caller must execute, not a note on
    what it submitted. AdmissionGate below is the caller that does; nothing
    did before 2026-08-31."""
    try:
        gate_1_parse(sql_text)
        gate_2_read_only(sql_text)
        gate_3_table_allowlist(sql_text, tables_referenced)
        gate_4_tenant_predicate(sql_text, tenant_id)
        gate_5_pii_exclusion(sql_text, tables_referenced)
        gate_6_cost_estimate(estimated_cost_inr, cost_cap)
        capped_sql, row_cap = gate_7_row_cap(sql_text)
    except AdmissionRejected as e:
        return AdmissionResult(admitted=False, gate=e.gate, reason=e.reason, sql_text=sql_text)
    return AdmissionResult(admitted=True, sql_text=capped_sql, row_cap=row_cap)


@dataclass
class AdmissionGate:
    """corpus/07 section 2's stage 7, as the object that stands between
    stage 6 and stage 8.

    The compiler calls this immediately before each `cursor.execute` and
    executes whatever comes back. A rejection raises out of the compiler, so
    the statement that provoked it never reaches Postgres -- which is the
    ordering corpus/07's stage table has always specified and the code did
    not have: until 2026-08-31 src/semantic/ask.py ran the gates sixteen
    lines AFTER compile_and_execute had already been to the database, so a
    rejection suppressed the response rather than the query.

    **What "rejected" guarantees, precisely.** No statement reaches Postgres
    without passing all seven gates first. It does NOT mean zero statements
    ran: a derived metric is a tree, gated statement by statement as the
    tree is walked, so a rejection at the fifth leaf leaves the first four
    already executed -- each of them admitted. Guaranteeing zero would mean
    computing the whole statement set before executing any of it, which
    means a second implementation of the dependency walk that can drift from
    the real one. That is the defect this change removed, so it is not being
    reintroduced one layer up. A leaf's own two statements ARE atomic: both
    are admitted before either executes (compiler.py's _fetch_leaf_amounts).

    `admitted` accumulates what passed, so the caller can report how much
    was gated rather than asserting it."""
    tenant_id: str
    estimated_cost_inr: Decimal | None = None
    cost_cap: Decimal | None = COST_CAP_INR_PER_QUERY
    admitted: list[AdmittedStatement] = field(default_factory=list)

    def __call__(self, sql_text: str, tables_referenced: tuple[str, ...]) -> AdmittedStatement:
        result = run_admission_gates(sql_text, list(tables_referenced), self.tenant_id,
                                        self.estimated_cost_inr, self.cost_cap)
        if not result.admitted:
            raise AdmissionRejected(result.gate, result.reason, sql_text)
        statement = AdmittedStatement(result.sql_text, result.row_cap)
        self.admitted.append(statement)
        return statement
