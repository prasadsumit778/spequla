"""Admission control runs BEFORE execution, and the caller runs what it returns.

corpus/07 section 2's stage table puts admission control at stage 7 and
execution at stage 8. Until 2026-08-31 src/semantic/ask.py did the reverse:
`_execute_as_model_reachable` at line 135, `run_admission_gates` at line 151.
A rejection suppressed the RESPONSE, sixteen lines after the query it was
meant to stop had already been to Postgres and come back. Gate 7's row-capped
SQL was returned into `AdmissionResult.sql_text`, which had no consumer
anywhere in the repo, so D-067's LIMIT 10000 was computed and discarded.

No test in this repo imported both `ask` and `admission`, so nothing covered
the ordering. This file does.

**Every assertion here is on the execution path, not on the response
status.** A rejected query that returns status="rejected" while still having
run is exactly the bug that was here, and it passes any status-only test. So
these tests wrap the live connection in a spy that records the literal SQL
handed to `cursor.execute`, and assert against that log.

What "rejected" guarantees, precisely (see admission.AdmissionGate): no
statement reaches Postgres without passing all seven gates first. NOT that
zero statements ran -- a derived metric is a tree, gated statement by
statement as it is walked, and the ungated metadata lookups
(metric_definition, mapping_version) run ahead of any of it by the boundary
drawn in src/semantic/statements.py. test_earlier_statements_were_admitted
pins that distinction down so nobody later reads a stronger promise into it.

Needs live Postgres (see tests/conftest.py) -- skips cleanly otherwise.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.config.loader import load_registry
from src.semantic import admission as admission_module
from src.semantic.admission import ROW_CAP, AdmissionGate, AdmissionRejected, run_admission_gates
from src.semantic.ask import ask
from src.semantic.compiler import compile_metric
from src.semantic.model_client import StubModelClient
from tests.helpers import advance_periods_to_reconciled, ingest_manufacturer, run_and_freeze_mapping

QUESTION = "What was our revenue last month?"
METRIC = "net_revenue"

# The join every leaf metric read goes through. Distinctive enough to pick
# the compiled query out of a spy log that also holds metadata lookups.
LEAF_FRAGMENT = "JOIN"
FACT_TABLE = "fact_gl_entry"


class SpyConnection:
    """Delegates everything to the real connection and records the literal
    SQL string every `cursor.execute` receives.

    Wrapping the connection rather than patching the compiler is deliberate:
    the question these tests ask is "what did Postgres receive", and the
    honest place to answer it is the last object before Postgres."""

    def __init__(self, real):
        self._real = real
        self.executed: list[str] = []

    def cursor(self, *a, **kw):
        return _SpyCursor(self._real.cursor(*a, **kw), self.executed)

    def __getattr__(self, name):
        return getattr(self._real, name)

    def statements_touching(self, fragment: str) -> list[str]:
        return [sql for sql in self.executed if fragment in sql]


class _SpyCursor:
    def __init__(self, real, log: list[str]):
        self._real = real
        self._log = log

    def __enter__(self):
        self._real.__enter__()
        return self

    def __exit__(self, *exc):
        return self._real.__exit__(*exc)

    def execute(self, sql, params=None, *a, **kw):
        self._log.append(sql if isinstance(sql, str) else str(sql))
        return self._real.execute(sql, params, *a, **kw)

    def __getattr__(self, name):
        return getattr(self._real, name)

    def __iter__(self):
        return iter(self._real)


def _last_gl_month(conn, schema: str, tenant_id: str, entity_id: int) -> str:
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT max(event_date) FROM "{schema}".fact_gl_entry '
            f'WHERE tenant_id = %s AND entity_id = %s AND is_current',
            (tenant_id, entity_id),
        )
        last = cur.fetchone()[0]
    return f"{last.year:04d}-{last.month:02d}"


def _reconciled_last_month(conn, schema, tenant_id, entity_id) -> str:
    """A period that clears the period gate, so what happens next is about
    admission control and nothing else."""
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, _summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                              effective_from=date(2022, 4, 1))
    assert freeze.passed, freeze.reason
    loaded_month = _last_gl_month(conn, schema, tenant_id, entity_id)
    reached = advance_periods_to_reconciled(conn, schema, tenant_id, entity_id, version_id, freeze,
                                                [loaded_month])
    assert reached[loaded_month] == "reconciled", reached
    return loaded_month


def _ir(period_key: str) -> dict:
    return {"intent": "metric_value", "metric": METRIC,
              "period": {"type": "month", "value": period_key}}


def _ask_through_spy(spy, schema, tenant_id, entity_id, config):
    period_key = _last_gl_month(spy, schema, tenant_id, entity_id)
    client = StubModelClient({QUESTION: ("metric_value", _ir(period_key))})
    spy.executed.clear()
    return ask(spy, schema, tenant_id, entity_id, QUESTION, client, config,
                  user_id="pytest", role="client_finance_lead", tenant_profile="manufacturing")


def test_a_rejected_query_never_reaches_the_database(conn, tenant, monkeypatch):
    """The headline. Gate 3 is made to reject the leaf read, and the
    assertion is that Postgres never saw it -- not that the response said
    so."""
    tenant_id, schema = tenant
    entity_id = 1
    _reconciled_last_month(conn, schema, tenant_id, entity_id)
    config = load_registry()
    spy = SpyConnection(conn)

    # Withdraw fact_gl_entry from the allowlist. Nothing else changes: the
    # compiler still builds the same statement, and the only question is
    # whether it runs. Patching the allowlist rather than the gate function
    # keeps the whole seven-gate path in play.
    monkeypatch.setattr(admission_module, "CANONICAL_TABLE_ALLOWLIST",
                          admission_module.CANONICAL_TABLE_ALLOWLIST - {FACT_TABLE})

    response = _ask_through_spy(spy, schema, tenant_id, entity_id, config)

    assert response.status == "rejected", response.result
    assert response.admission is not None and response.admission["gate"] == "table_allowlist"

    # THE assertion: no statement touching the fact table was executed.
    leaked = [sql for sql in spy.executed if FACT_TABLE in sql]
    assert leaked == [], (
        f"admission control rejected the query, but {len(leaked)} statement(s) reading "
        f"{FACT_TABLE} still reached Postgres -- the gate is running after execution again. "
        f"First: {leaked[0][:200] if leaked else ''}"
    )


def test_earlier_statements_were_admitted_even_though_the_query_was_rejected(conn, tenant, monkeypatch):
    """The exact scope of the guarantee, pinned so it cannot quietly widen.

    Statements DO run before the rejection -- the ungated metadata lookups
    that resolve which mapping version and which parameters to compile
    against. What must never run is a gated statement that has not passed
    the gates. Asserting the weaker, true property here is the point: a test
    claiming "nothing ran" would be asserting something the design does not
    provide, and would be quietly deleted the first time it failed."""
    tenant_id, schema = tenant
    entity_id = 1
    _reconciled_last_month(conn, schema, tenant_id, entity_id)
    config = load_registry()
    spy = SpyConnection(conn)
    monkeypatch.setattr(admission_module, "CANONICAL_TABLE_ALLOWLIST",
                          admission_module.CANONICAL_TABLE_ALLOWLIST - {FACT_TABLE})

    response = _ask_through_spy(spy, schema, tenant_id, entity_id, config)
    assert response.status == "rejected"

    assert spy.executed, "the metadata lookups ahead of compilation do run -- see statements.py"
    assert any("mapping_version" in sql for sql in spy.executed)
    assert not any(FACT_TABLE in sql for sql in spy.executed)


def test_the_executed_statement_is_the_capped_one_gate_7_returned(conn, tenant):
    """D-067's LIMIT 10000, previously computed and discarded, is now the
    text that runs. Asserted against what Postgres received."""
    tenant_id, schema = tenant
    entity_id = 1
    _reconciled_last_month(conn, schema, tenant_id, entity_id)
    config = load_registry()
    spy = SpyConnection(conn)

    response = _ask_through_spy(spy, schema, tenant_id, entity_id, config)
    assert response.status == "ok", response.refusal.reason if response.refusal else response.result

    leaf_statements = [sql for sql in spy.executed if FACT_TABLE in sql and LEAF_FRAGMENT in sql]
    assert leaf_statements, "no leaf read reached the database at all -- the premise of this test is gone"
    for sql in leaf_statements:
        assert f"LIMIT {ROW_CAP}" in sql, (
            f"gate 7 returned a capped statement and the executor ran an uncapped one: {sql[:200]}"
        )


def test_the_recorded_sql_is_the_capped_sql(conn, tenant):
    """The record follows the cap. What the query_log and the "view SQL"
    panel show has to be the text that ran, not the text submitted to the
    gates."""
    tenant_id, schema = tenant
    entity_id = 1
    _reconciled_last_month(conn, schema, tenant_id, entity_id)
    config = load_registry()
    spy = SpyConnection(conn)

    response = _ask_through_spy(spy, schema, tenant_id, entity_id, config)
    assert response.status == "ok"

    gated = [s for s in response.result.executed_sql if s.gated]
    assert gated
    for statement in gated:
        assert f"LIMIT {ROW_CAP}" in statement.sql
        assert statement.sql in spy.executed, "a recorded statement that Postgres never received"


def test_every_gated_statement_that_ran_had_been_admitted(conn, tenant):
    """The invariant in its general form: for a derived metric, whose tree
    issues many statements, each gated statement that reached Postgres
    passes the gates when replayed through them."""
    tenant_id, schema = tenant
    entity_id = 1
    period_key = _reconciled_last_month(conn, schema, tenant_id, entity_id)
    config = load_registry()
    spy = SpyConnection(conn)

    # ebitda: eight metric nodes, five leaves -- ten gated statements, not one.
    gate = AdmissionGate(tenant_id=tenant_id)
    compiled = compile_metric(spy, schema, tenant_id, entity_id, "ebitda", period_key, config,
                                 admission=gate)
    assert compiled.status == "ok", compiled.reason

    gated = [s for s in compiled.executed_sql if s.gated]
    assert len(gated) > 1, "a derived metric must record more than one leaf statement"
    for statement in gated:
        replayed = run_admission_gates(statement.sql, list(statement.tables), tenant_id)
        assert replayed.admitted, f"an executed statement does not pass the gates: {replayed.reason}"
        assert statement.sql in spy.executed


def test_the_gate_counts_what_it_admitted(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    period_key = _reconciled_last_month(conn, schema, tenant_id, entity_id)
    config = load_registry()

    gate = AdmissionGate(tenant_id=tenant_id)
    compile_metric(conn, schema, tenant_id, entity_id, "ebitda", period_key, config, admission=gate)
    assert len(gate.admitted) > 1, "ebitda's five leaves issue two statements each"
    assert all(s.row_cap == ROW_CAP for s in gate.admitted), "every leaf read carries D-067's cap"


def test_a_rejection_raises_out_of_the_compiler_rather_than_being_swallowed(conn, tenant, monkeypatch):
    """compile_metric itself must not catch AdmissionRejected and turn it
    into a blocked/undefined CompiledMetric. A rejection is a safety
    decision, not a metric outcome, and collapsing it into one would let it
    be reported as "this metric is unavailable" -- which reads like missing
    data rather than a refused query."""
    tenant_id, schema = tenant
    entity_id = 1
    period_key = _reconciled_last_month(conn, schema, tenant_id, entity_id)
    config = load_registry()
    monkeypatch.setattr(admission_module, "CANONICAL_TABLE_ALLOWLIST",
                          admission_module.CANONICAL_TABLE_ALLOWLIST - {FACT_TABLE})

    with pytest.raises(AdmissionRejected) as raised:
        compile_metric(conn, schema, tenant_id, entity_id, METRIC, period_key, config,
                          admission=AdmissionGate(tenant_id=tenant_id))
    assert raised.value.gate == "table_allowlist"
    assert FACT_TABLE in raised.value.sql_text


def test_a_deterministic_caller_with_no_gate_is_unaffected(conn, tenant):
    """The monthly pack and the overview tiles pass no admission hook, are
    unreachable by any model, and must keep executing uncapped SQL exactly
    as before -- the gates are the Ask surface's."""
    tenant_id, schema = tenant
    entity_id = 1
    period_key = _reconciled_last_month(conn, schema, tenant_id, entity_id)
    config = load_registry()
    spy = SpyConnection(conn)
    spy.executed.clear()

    compiled = compile_metric(spy, schema, tenant_id, entity_id, METRIC, period_key, config)
    assert compiled.status == "ok", compiled.reason
    leaf_statements = [sql for sql in spy.executed if FACT_TABLE in sql and LEAF_FRAGMENT in sql]
    assert leaf_statements
    assert not any("LIMIT" in sql.upper() for sql in leaf_statements)
