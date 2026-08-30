"""Ask never answers with a number that has no citation behind it.

CLAUDE.md invariant 7: "Every displayed number carries a citation that
resolves to source rows. A number without one is not displayed. Not badged,
not greyed out. Not displayed." corpus/07 section 6: a question whose data
the system does not hold is refused as "requires data not held", naming the
missing input.

The case is ordinary, which is the point. Every period_sum metric resolves
to 0 over zero rows for a month that has not been ingested yet -- asking
"what was our revenue in June?" before June is loaded. src/semantic/
citation.py refuses to cite that; this test pins down what src/semantic/
ask.py then does with it, which until 2026-08-30 was to answer 'ok' with the
number and citation=None.

Nothing here is stubbed except intent/IR generation (StubModelClient, as
every Ask test does -- no ModelClient is wired up yet). The zero-row metric
is real: it compiles, successfully, against real ingested data.

Needs live Postgres (see tests/conftest.py) -- skips cleanly otherwise.
"""
from __future__ import annotations

from datetime import date

from src.config.loader import load_registry
from src.semantic.ask import ask
from src.semantic.compiler import compile_metric
from src.semantic.model_client import StubModelClient
from tests.helpers import ingest_manufacturer, run_and_freeze_mapping

UNLOADED_QUESTION = "What was our revenue in the month after our last data?"
LOADED_QUESTION = "What was our revenue in our last loaded month?"


def _month_after(period_key: str) -> str:
    year, month = (int(p) for p in period_key.split("-"))
    return f"{year + 1:04d}-01" if month == 12 else f"{year:04d}-{month + 1:02d}"


def _last_gl_month(conn, schema: str, tenant_id: str, entity_id: int) -> str:
    """Derived from the data, never hardcoded. synthetic/manufacturer/
    profile.py's FISCAL_START/N_MONTHS can move; tests/fixtures/golden_ir.py
    hardcoded a month and its comment is now stale against that profile."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT max(event_date) FROM "{schema}".fact_gl_entry '
            f'WHERE tenant_id = %s AND entity_id = %s AND is_current',
            (tenant_id, entity_id),
        )
        last = cur.fetchone()[0]
    return f"{last.year:04d}-{last.month:02d}"


def _ir(period_key: str) -> dict:
    return {"intent": "metric_value", "metric": "net_revenue",
              "period": {"type": "month", "value": period_key}}


def test_a_metric_with_no_source_rows_is_unavailable_not_ok(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    _version_id, _summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                               effective_from=date(2022, 4, 1))
    assert freeze.passed, freeze.reason

    config = load_registry()
    loaded_month = _last_gl_month(conn, schema, tenant_id, entity_id)
    unloaded_month = _month_after(loaded_month)

    # The premise: this metric really does compile, successfully, to a real
    # Decimal -- over no rows at all. Without this the assertions below would
    # pass for the uninteresting reason that the metric simply failed.
    compiled = compile_metric(conn, schema, tenant_id, entity_id, "net_revenue", unloaded_month, config)
    assert compiled.status == "ok", compiled.reason
    assert compiled.value is not None
    assert compiled.row_count == 0

    client = StubModelClient({UNLOADED_QUESTION: ("metric_value", _ir(unloaded_month))})
    response = ask(conn, schema, tenant_id, entity_id, UNLOADED_QUESTION, client, config,
                      user_id="pytest", role="client_finance_lead", tenant_profile="manufacturing")

    assert response.status == "unavailable", (
        f"a metric backed by zero rows must not be answered as 'ok' -- got {response.status} "
        f"with citation={response.citation}"
    )
    assert response.citation is None
    assert response.refusal is not None
    assert response.refusal.refusal_class == "requires_data_not_held"

    # The reason names the metric and says what is missing -- not a bare
    # "data not available", which would leave the reader unable to tell which
    # number was withheld or why.
    assert "net_revenue" in response.refusal.reason
    assert "no source rows" in response.refusal.reason
    assert unloaded_month in response.refusal.reason


def test_the_same_question_for_a_loaded_month_still_answers_with_a_citation(conn, tenant):
    """The other half of the gate: the new branch must not swallow a metric
    that IS backed by rows. Same question shape, same metric, one month
    earlier -- this one answers."""
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    _version_id, _summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                               effective_from=date(2022, 4, 1))
    assert freeze.passed, freeze.reason

    config = load_registry()
    loaded_month = _last_gl_month(conn, schema, tenant_id, entity_id)

    client = StubModelClient({LOADED_QUESTION: ("metric_value", _ir(loaded_month))})
    response = ask(conn, schema, tenant_id, entity_id, LOADED_QUESTION, client, config,
                      user_id="pytest", role="client_finance_lead", tenant_profile="manufacturing")

    assert response.status == "ok", (
        response.refusal.reason if response.refusal else response.result
    )
    assert response.refusal is None
    assert response.citation is not None
    assert response.citation["row_count"] > 0
    assert len(response.citation["source_files"]) > 0
