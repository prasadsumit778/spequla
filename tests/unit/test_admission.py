"""Unit tests for src/semantic/admission.py's seven gates -- pure, no DB."""
from src.semantic.admission import (
    AdmissionRejected,
    gate_1_parse,
    gate_2_read_only,
    gate_3_table_allowlist,
    gate_4_tenant_predicate,
    gate_5_pii_exclusion,
    gate_7_row_cap,
    run_admission_gates,
)

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
    result = gate_7_row_cap("SELECT 1 FROM x")
    assert "LIMIT" in result.upper()


def test_gate_7_leaves_existing_limit_alone():
    result = gate_7_row_cap("SELECT 1 FROM x LIMIT 5")
    assert result.count("LIMIT") == 1 or result.upper().count("LIMIT") == 1


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
