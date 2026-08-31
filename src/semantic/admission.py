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

from src.semantic.statements import AdmittedStatement

CANONICAL_TABLE_ALLOWLIST = {
    "fact_gl_entry", "fact_bank_txn", "dim_account", "dim_date", "dim_entity",
    "map_account", "mapping_version", "period_lock", "reconciliation_run",
}

# corpus/07 section 7 gate 2: "No DDL, no DML, no functions that touch the
# filesystem." Read-only means exactly SELECT (and WITH ... SELECT, a CTE).
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|"
    r"pg_read_file|pg_ls_dir|lo_import|lo_export|dblink)\b",
    re.IGNORECASE,
)

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
    stripped = sql_text.strip()
    if not stripped:
        raise AdmissionRejected("parse", "empty SQL text")
    if not re.match(r"^\s*(SELECT|WITH)\b", stripped, re.IGNORECASE):
        raise AdmissionRejected("parse", "does not start with SELECT or WITH -- not a valid read query")
    if stripped.count("(") != stripped.count(")"):
        raise AdmissionRejected("parse", "unbalanced parentheses")


def gate_2_read_only(sql_text: str) -> None:
    match = _FORBIDDEN_KEYWORDS.search(sql_text)
    if match:
        raise AdmissionRejected("read_only", f"forbidden keyword {match.group(0)!r} -- read-only queries only")


def gate_3_table_allowlist(sql_text: str, tables_referenced: list[str]) -> None:
    for table in tables_referenced:
        bare = table.split(".")[-1].strip('"')
        if bare not in CANONICAL_TABLE_ALLOWLIST:
            raise AdmissionRejected("table_allowlist", f"{table!r} is not a canonical table or approved view")


def gate_4_tenant_predicate(sql_text: str, tenant_id: str) -> None:
    if "tenant_id" not in sql_text:
        raise AdmissionRejected("tenant_predicate", "no tenant_id predicate present in the compiled SQL")
    if tenant_id not in sql_text and "%s" not in sql_text:
        raise AdmissionRejected("tenant_predicate", "tenant_id predicate present but not bound to this tenant")


def gate_5_pii_exclusion(sql_text: str, tables_referenced: list[str]) -> None:
    for table in tables_referenced:
        bare = table.split(".")[-1].strip('"')
        if bare in FORBIDDEN_TABLES:
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
    distinction is not optional."""
    if re.search(r"\bLIMIT\s+\d+", sql_text, re.IGNORECASE):
        return sql_text, None
    return f"{sql_text.rstrip().rstrip(';')} LIMIT {ROW_CAP}", ROW_CAP


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
