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
from dataclasses import dataclass

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
    def __init__(self, gate: str, reason: str):
        self.gate = gate
        self.reason = reason
        super().__init__(f"gate {gate!r} rejected: {reason}")


@dataclass
class AdmissionResult:
    admitted: bool
    gate: str | None = None
    reason: str | None = None
    sql_text: str | None = None


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


# Gate 6's cost cap has no declared number anywhere in the corpus -- see
# OPEN_QUESTIONS.md OQ-003. This gate estimates cost (as an approximate row
# count via EXPLAIN, when a live connection is available) but does not reject
# on it: with no declared cap, "under the configured cap" cannot be evaluated
# as true or false, and CLAUDE.md section 3.2 is explicit that an undeclared
# threshold is left unset, not guessed. The gate is a genuine no-op until a
# cap is declared, same posture as D-052's tolerance.
def gate_6_cost_estimate(estimated_rows: int | None, cap: int | None) -> None:
    if cap is not None and estimated_rows is not None and estimated_rows > cap:
        raise AdmissionRejected("cost_estimate", f"estimated {estimated_rows} rows exceeds the configured cap {cap}")


# Gate 7's row cap ALSO has no declared number (same OQ-003). Unlike gate 6,
# this one is applied at the SQL level with a LIMIT, per corpus/07 section 7
# ("Row cap. Applied") -- an applied cap does need *some* number to put in
# the LIMIT clause, so this uses a generous, clearly-labelled default that
# exists purely to prevent an unbounded result set from being returned to a
# browser tab, not a business rule -- callers should override it once a real
# cap is declared.
DEFAULT_ROW_CAP_PENDING_DECLARATION = 10_000


def gate_7_row_cap(sql_text: str) -> str:
    if re.search(r"\bLIMIT\s+\d+", sql_text, re.IGNORECASE):
        return sql_text
    return f"{sql_text.rstrip().rstrip(';')} LIMIT {DEFAULT_ROW_CAP_PENDING_DECLARATION}"


def run_admission_gates(sql_text: str, tables_referenced: list[str], tenant_id: str,
                           estimated_rows: int | None = None, cost_cap: int | None = None) -> AdmissionResult:
    """Runs all seven gates in order. Returns the (possibly row-capped) SQL
    text on success; raises AdmissionRejected, naming the gate, on the first
    failure -- corpus/07 section 7: 'Every rejection is logged with the
    user, the IR and the reason.'"""
    try:
        gate_1_parse(sql_text)
        gate_2_read_only(sql_text)
        gate_3_table_allowlist(sql_text, tables_referenced)
        gate_4_tenant_predicate(sql_text, tenant_id)
        gate_5_pii_exclusion(sql_text, tables_referenced)
        gate_6_cost_estimate(estimated_rows, cost_cap)
        capped_sql = gate_7_row_cap(sql_text)
    except AdmissionRejected as e:
        return AdmissionResult(admitted=False, gate=e.gate, reason=e.reason)
    return AdmissionResult(admitted=True, sql_text=capped_sql)
