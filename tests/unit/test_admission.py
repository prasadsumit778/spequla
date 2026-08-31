"""Unit tests for src/semantic/admission.py's seven gates -- pure, no DB."""
from decimal import Decimal

import pytest

from src.semantic.admission import (
    COST_CAP_INR_PER_QUERY,
    ROW_CAP,
    AdmissionRejected,
    gate_1_parse,
    gate_2_read_only,
    gate_3_table_allowlist,
    gate_4_tenant_predicate,
    gate_5_pii_exclusion,
    gate_6_cost_estimate,
    gate_7_row_cap,
    run_admission_gates,
)
from src.semantic.compiler import leaf_amount_statements

VALID_SQL = 'SELECT SUM(amount_base) FROM "tenant_x".fact_gl_entry WHERE tenant_id = %s'


def test_gate_1_accepts_select():
    gate_1_parse(VALID_SQL)  # must not raise


def test_gate_1_rejects_non_select():
    try:
        gate_1_parse("some garbage text")
        assert False
    except AdmissionRejected as e:
        assert e.gate == "parse"


def test_gate_1_rejects_unbalanced_parens():
    try:
        gate_1_parse("SELECT SUM(amount_base FROM x")
        assert False
    except AdmissionRejected as e:
        assert e.gate == "parse"


def test_gate_2_accepts_select():
    gate_2_read_only(VALID_SQL)


def test_gate_2_rejects_insert():
    try:
        gate_2_read_only("INSERT INTO fact_gl_entry VALUES (1)")
        assert False
    except AdmissionRejected as e:
        assert e.gate == "read_only"


def test_gate_2_rejects_drop():
    try:
        gate_2_read_only("SELECT 1; DROP TABLE fact_gl_entry")
        assert False
    except AdmissionRejected as e:
        assert e.gate == "read_only"


def test_gate_3_accepts_canonical_table():
    gate_3_table_allowlist(VALID_SQL, ['"tenant_x".fact_gl_entry'])


def test_gate_3_rejects_non_canonical_table():
    try:
        gate_3_table_allowlist("SELECT * FROM app.token_map", ['app.token_map'])
        assert False
    except AdmissionRejected as e:
        assert e.gate == "table_allowlist"


def test_gate_4_rejects_missing_tenant_predicate():
    try:
        gate_4_tenant_predicate("SELECT * FROM fact_gl_entry", "tenant-abc")
        assert False
    except AdmissionRejected as e:
        assert e.gate == "tenant_predicate"


def test_gate_4_accepts_present_tenant_predicate():
    gate_4_tenant_predicate(VALID_SQL, "tenant-abc")


def test_gate_5_rejects_forbidden_table():
    try:
        gate_5_pii_exclusion("SELECT * FROM app.token_map", ["app.token_map"])
        assert False
    except AdmissionRejected as e:
        assert e.gate == "pii_exclusion"


def test_gate_5_accepts_canonical_table():
    gate_5_pii_exclusion(VALID_SQL, ['"tenant_x".fact_gl_entry'])


def test_gate_7_applies_a_limit_when_none_present():
    sql, row_cap = gate_7_row_cap("SELECT 1 FROM x")
    assert f"LIMIT {ROW_CAP}" in sql.upper()
    # The cap is returned alongside the text, not left to be re-parsed out of
    # it: the executor compares the rows it got against this number to tell a
    # complete result from a truncated one (compiler.py's RowCapTruncated).
    assert row_cap == ROW_CAP


def test_gate_7_leaves_existing_limit_alone():
    sql, row_cap = gate_7_row_cap("SELECT 1 FROM x LIMIT 5")
    assert sql.upper().count("LIMIT") == 1
    assert row_cap is None, "gate 7 applied no cap of its own, so it reports none"


def test_gate_7_does_not_reject():
    # corpus/07 section 7 states gate 7 as "Row cap. Applied" -- it rewrites
    # and returns, it never raises. If it rejected, it would reject every
    # statement the compiler emits, since none carries a LIMIT of its own.
    for sql in ("SELECT 1 FROM x", "SELECT 1 FROM x LIMIT 5", "SELECT 1 FROM x;"):
        gate_7_row_cap(sql)  # must not raise


def test_run_admission_gates_admits_valid_query():
    result = run_admission_gates(VALID_SQL, ['"tenant_x".fact_gl_entry'], "tenant-abc")
    assert result.admitted
    assert result.sql_text is not None
    assert "LIMIT" in result.sql_text.upper()


def test_run_admission_gates_rejects_and_names_the_gate():
    result = run_admission_gates("DROP TABLE x", [], "tenant-abc")
    assert not result.admitted
    assert result.gate is not None
    assert result.reason is not None


def test_run_admission_gates_rejects_pii_table():
    # Caught by gate 3 (table allowlist) before gate 5 (PII exclusion) ever
    # runs, since token_map is in neither -- gate 5 exists as defence in
    # depth for exactly the scenario where the allowlist is ever mistakenly
    # widened; see test_gate_5_rejects_forbidden_table for that gate in
    # isolation.
    result = run_admission_gates(
        'SELECT * FROM app.token_map WHERE tenant_id = %s', ["app.token_map"], "tenant-abc",
    )
    assert not result.admitted
    assert result.gate in ("table_allowlist", "pii_exclusion")


# ---------------------------------------------------------------------------
# Part C, 2026-08-31: the gate bodies. Each class below covers what its gate
# claimed but did not do. Every case is a shape that PASSED before.
# ---------------------------------------------------------------------------

class TestGate1ParsesRatherThanPatternMatches:
    def test_a_second_statement_after_a_semicolon_is_rejected(self):
        # Passed intact before: nothing looked for a statement separator.
        try:
            gate_1_parse("SELECT 1 FROM x; SELECT pg_sleep(60)")
            assert False
        except AdmissionRejected as e:
            assert e.gate == "parse"
            assert "statements" in e.reason

    def test_a_trailing_semicolon_is_not_a_second_statement(self):
        gate_1_parse("SELECT 1 FROM x;")  # must not raise

    def test_a_parenthesis_inside_a_string_literal_is_not_counted(self):
        # Rejected before: the count ran over raw text, so a smiley in a
        # narration read as an unbalanced query.
        gate_1_parse("SELECT 1 FROM t WHERE narration = ':-('")

    def test_genuinely_unbalanced_parentheses_still_reject(self):
        try:
            gate_1_parse("SELECT SUM(amount_base FROM x")
            assert False
        except AdmissionRejected as e:
            assert e.gate == "parse"

    def test_it_does_not_claim_to_validate_grammar(self):
        # sqlparse is a tokenizer, not a grammar. This string is not valid
        # SQL and gate 1 admits it -- asserted so the docstring's disclaimer
        # is load-bearing rather than decorative, and so that anyone who
        # later makes gate 1 a real parser finds this test and updates it.
        gate_1_parse("SELECT FROM WHERE GROUP")


class TestGate2IsAnAllowlistFirst:
    @pytest.mark.parametrize("sql", [
        "MERGE INTO fact_gl_entry USING s ON x",
        "CALL some_procedure()",
        "DO $$ BEGIN END $$",
        "SET ROLE postgres",
        "EXPLAIN SELECT 1 FROM x",
    ])
    def test_statements_the_old_denylist_missed(self, sql):
        # Every one of these passed gate 2 before: none of their leading
        # keywords was on the list.
        try:
            gate_2_read_only(sql)
            assert False, f"{sql!r} was admitted as read-only"
        except AdmissionRejected as e:
            assert e.gate == "read_only"

    def test_a_filesystem_function_inside_a_legitimate_select_is_rejected(self):
        # Type SELECT, so the allowlist half admits it. This is what the
        # denylist half is still for.
        try:
            gate_2_read_only("SELECT pg_read_file('/etc/passwd') FROM dim_date")
            assert False
        except AdmissionRejected as e:
            assert e.gate == "read_only"

    def test_a_cte_is_still_a_read(self):
        gate_2_read_only('WITH c AS (SELECT 1 FROM "t".dim_date) SELECT * FROM c')

    def test_a_keyword_inside_a_string_literal_is_not_a_keyword(self):
        # Rejected before as DDL: the scan ran over raw text.
        gate_2_read_only("SELECT 1 FROM t WHERE narration = 'CREATE a new invoice'")

    def test_every_statement_in_the_submission_is_checked_not_just_the_first(self):
        try:
            gate_2_read_only("SELECT 1; DROP TABLE fact_gl_entry")
            assert False
        except AdmissionRejected as e:
            assert e.gate == "read_only", "a gate must reject on its own grounds, not lean on gate 1 having run"

    def test_the_real_compiled_statements_are_admitted(self):
        for sql in leaf_amount_statements("tenant_x", 3, "period_sum"):
            if isinstance(sql, str):
                gate_2_read_only(sql)


class TestGate3ReadsTheSql:
    def test_a_forbidden_table_in_the_sql_is_caught_even_when_undeclared(self):
        # THE hole: "a query touching app.token_map passes both gates if the
        # caller simply doesn't list it" (RISKS.md section 1).
        try:
            gate_3_table_allowlist("SELECT * FROM app.token_map WHERE tenant_id = %s", [])
            assert False, "an undeclared forbidden table was admitted"
        except AdmissionRejected as e:
            assert e.gate == "table_allowlist"

    def test_a_table_hidden_in_a_subquery_is_found(self):
        try:
            gate_3_table_allowlist(
                'SELECT (SELECT x FROM app.audit_log) FROM "t".dim_date WHERE tenant_id = %s',
                ['"t".dim_date'])
            assert False
        except AdmissionRejected as e:
            assert e.gate == "table_allowlist"

    def test_reading_an_allowlisted_table_the_caller_did_not_declare_is_still_rejected(self):
        # Both tables are canonical. The defect is the mismatch: what a
        # query touches and what its compiler says it touches must agree.
        try:
            gate_3_table_allowlist(
                'SELECT a FROM "t".fact_gl_entry f JOIN "t".map_account m ON 1=1 WHERE tenant_id = %s',
                ['"t".fact_gl_entry'])
            assert False
        except AdmissionRejected as e:
            assert e.gate == "table_allowlist"
            assert "map_account" in e.reason

    def test_over_declaring_is_not_an_error(self):
        gate_3_table_allowlist(VALID_SQL, ['"tenant_x".fact_gl_entry', '"tenant_x".dim_date'])

    def test_the_real_compiled_statement_is_admitted(self):
        amounts, load_runs, tables = leaf_amount_statements("tenant_x", 2, "period_sum")
        for sql in (amounts, load_runs):
            gate_3_table_allowlist(sql, list(tables))


class TestGate4RequiresAPredicateNotASubstring:
    def test_a_tenant_id_in_the_select_list_is_not_a_predicate(self):
        # Passed before: the substring is present, there is no WHERE at all.
        try:
            gate_4_tenant_predicate("SELECT tenant_id FROM fact_gl_entry", "tenant-abc")
            assert False, "a query with no WHERE clause was admitted"
        except AdmissionRejected as e:
            assert e.gate == "tenant_predicate"

    def test_a_tenant_id_scoping_only_a_subquery_is_not_a_predicate(self):
        try:
            gate_4_tenant_predicate(
                "SELECT * FROM t WHERE x IN (SELECT y FROM z WHERE tenant_id = %s)", "tenant-abc")
            assert False, "a subquery-scoped predicate was admitted for the outer statement"
        except AdmissionRejected as e:
            assert e.gate == "tenant_predicate"

    def test_a_tenant_id_in_a_comment_is_not_a_predicate(self):
        try:
            gate_4_tenant_predicate("SELECT * FROM t /* tenant_id */ WHERE x = 1", "tenant-abc")
            assert False
        except AdmissionRejected as e:
            assert e.gate == "tenant_predicate"

    def test_an_outer_predicate_alongside_a_subquery_is_accepted(self):
        gate_4_tenant_predicate(
            "SELECT * FROM t WHERE tenant_id = %s AND x IN (SELECT y FROM z)", "tenant-abc")

    def test_a_literal_tenant_that_is_not_this_one_is_rejected(self):
        # The tripwire: a compiler that formats a tenant id into SQL rather
        # than binding it. Cannot fire against today's compiler, which is
        # the point of having it.
        try:
            gate_4_tenant_predicate("SELECT a FROM t WHERE tenant_id = 'other-tenant'", "tenant-abc")
            assert False
        except AdmissionRejected as e:
            assert e.gate == "tenant_predicate"
            assert "literal" in e.reason

    def test_a_literal_tenant_that_is_this_one_is_accepted(self):
        gate_4_tenant_predicate("SELECT a FROM t WHERE tenant_id = 'tenant-abc'", "tenant-abc")

    def test_the_real_compiled_statements_carry_a_bound_predicate(self):
        amounts, load_runs, _ = leaf_amount_statements("tenant_x", 2, "period_sum")
        for sql in (amounts, load_runs):
            gate_4_tenant_predicate(sql, "tenant-abc")


class TestGate5ReadsTheSql:
    def test_a_forbidden_table_in_the_sql_is_caught_even_when_undeclared(self):
        try:
            gate_5_pii_exclusion("SELECT * FROM app.token_map WHERE tenant_id = %s", [])
            assert False
        except AdmissionRejected as e:
            assert e.gate == "pii_exclusion"

    def test_the_declared_list_is_still_checked_as_defence_in_depth(self):
        try:
            gate_5_pii_exclusion(VALID_SQL, ["app.token_map"])
            assert False
        except AdmissionRejected as e:
            assert e.gate == "pii_exclusion"

    def test_a_confidential_column_is_NOT_caught(self):
        # Asserting a KNOWN GAP, deliberately. corpus/07 section 7 gate 5
        # says "no column outside the model-reachable views" -- those views
        # do not exist (the repo's only view is exception_current, revoked
        # from model_reachable), so there is no column list to check
        # against and none was invented. OPEN_QUESTIONS.md OQ-020.
        #
        # This test passes today because the check is absent. It exists so
        # the gap is visible in the suite rather than only in a docstring,
        # and so whoever builds those views finds this test and inverts it.
        gate_5_pii_exclusion(
            'SELECT ma.source_account_name FROM "t".map_account ma WHERE ma.tenant_id = %s',
            ['"t".map_account'])


class TestGate6CostEstimate:
    """Gate 6's first tests. It was absent from this module's import list
    entirely, so none of its branches had ever been executed by the suite.

    The gate is still not wired: src/semantic/ask.py passes no cost estimate
    because no ModelClient reports token usage (OPEN_QUESTIONS.md OQ-003,
    still open). These test the logic that will run when one does -- no cost
    figure is fabricated to make it look connected."""

    def test_an_estimate_over_the_cap_is_rejected(self):
        try:
            gate_6_cost_estimate(Decimal("5.01"))
            assert False, "a query costing more than D-066's cap was admitted"
        except AdmissionRejected as e:
            assert e.gate == "cost_estimate"
            assert "5" in e.reason

    def test_an_estimate_under_the_cap_is_admitted(self):
        gate_6_cost_estimate(Decimal("4.99"))

    def test_the_declared_cap_is_D_066s_five_rupees(self):
        assert COST_CAP_INR_PER_QUERY == Decimal("5")

    def test_exactly_the_cap_is_admitted(self):
        # Pinning current behaviour and flagging an ambiguity rather than
        # resolving one: corpus/07 section 7 words gate 6 as "Under Rs 5 per
        # query", which excludes 5; D-066's own text (corpus/00, via OQ-003)
        # words it as a cap, which includes it. The body uses `>`, so exactly
        # 5.00 passes. Not changed here -- moving a declared threshold on a
        # reading of a preposition is CLAUDE.md section 3.2's prohibition.
        gate_6_cost_estimate(Decimal("5"))

    def test_no_estimate_never_rejects(self):
        # The live state, per OQ-003: nothing upstream produces a figure, so
        # None is what this gate actually receives on every call today. It
        # must pass rather than fail closed -- there is nothing to reject on.
        gate_6_cost_estimate(None)

    def test_no_cap_never_rejects(self):
        gate_6_cost_estimate(Decimal("1000"), cap=None)


class TestGate7TopLevelLimit:
    def test_a_limit_inside_a_subquery_does_not_count_as_capped(self):
        # Passed before: the regex matched the nested LIMIT, so the outer
        # result went out uncapped -- the one case where gate 7 silently
        # applied nothing.
        sql, row_cap = gate_7_row_cap("SELECT * FROM (SELECT x FROM t LIMIT 5) s")
        assert row_cap == ROW_CAP
        assert sql.rstrip().endswith(f"LIMIT {ROW_CAP}")

    def test_a_top_level_limit_is_left_alone(self):
        sql, row_cap = gate_7_row_cap("SELECT 1 FROM x LIMIT 5")
        assert row_cap is None
        assert sql.upper().count("LIMIT") == 1


def test_all_seven_gates_admit_the_real_compiled_statement():
    """End to end over run_admission_gates, on the statement the compiler
    actually emits. Every gate got stricter in Part C; this is the check
    that stricter did not mean broken."""
    amounts, load_runs, tables = leaf_amount_statements("tenant_x", 4, "period_sum")
    for sql in (amounts, load_runs):
        result = run_admission_gates(sql, list(tables), "tenant-abc")
        assert result.admitted, f"gate {result.gate}: {result.reason}"
        assert result.row_cap == ROW_CAP
        assert result.sql_text.rstrip().endswith(f"LIMIT {ROW_CAP}")
