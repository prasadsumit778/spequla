"""Ask never answers with a number that has no citation behind it.

CLAUDE.md invariant 7: "Every displayed number carries a citation that
resolves to source rows. A number without one is not displayed. Not badged,
not greyed out. Not displayed." corpus/07 section 6: a question whose data
the system does not hold is refused as "requires data not held", naming the
missing input.

**Two guards now stand between a question and a number, in this order**, and
this file pins down both of them and the order:

  1. The period gate (src/quality/period_gate.py, corpus/09 section 5) --
     may this PERIOD be read at all?
  2. The citation guard (src/semantic/citation.py, corpus/07 section 8) --
     does this METRIC resolve to source rows?

Until 2026-08-31 there was only the second, and this file exercised it by
asking about a month that had not been ingested. That case now stops at the
first guard instead, and correctly so: corpus/07 section 6 puts "any metric
for an unreconciled or unmapped period" in the period_not_reportable class,
and a month with no data is unmapped. That case is kept below, asserting its
new and correct classification.

The citation guard is not thereby untested, and must not be -- a guard
nothing reaches is a guard that has stopped working without telling anyone.
It is exercised here on the case that reaches it in production: a fully
RECONCILED period, and a metric with genuinely nothing behind it.
`inventory` is that metric, and structurally rather than incidentally. Its
contract is gl_class(asset.inventory_rm|wip|fg|packing_stores), the
synthetic manufacturer's chart of accounts does contain all four stock
ledgers -- and synthetic/manufacturer/engine.py's voucher engine posts to
none of them. Every ledger it names (coa_by_name[...]) is a debtor,
creditor, bank, tax, depreciation, interest or provision account; there is
no stock movement voucher anywhere in the generator. So the metric compiles,
successfully, to a real Decimal over zero rows, in a period that is
otherwise entirely reportable -- an ordinary shape for a real client too,
whose ledger exists but whose stock movements arrive from somewhere the
system does not yet ingest. That is derived from the generator, not recorded
from a run (CLAUDE.md section 9).

Nothing here is stubbed except intent/IR generation (StubModelClient, as
every Ask test does -- no ModelClient is wired up yet).

Needs live Postgres (see tests/conftest.py) -- skips cleanly otherwise.
"""
from __future__ import annotations

from datetime import date

from src.config.loader import load_registry
from src.semantic.ask import ask
from src.semantic.compiler import compile_metric
from src.semantic.model_client import StubModelClient
from tests.helpers import advance_periods_to_reconciled, ingest_manufacturer, run_and_freeze_mapping

UNLOADED_QUESTION = "What was our revenue in the month after our last data?"
LOADED_QUESTION = "What was our revenue in our last loaded month?"
UNCITABLE_QUESTION = "How much inventory do we hold?"

# gl_class(asset.inventory_rm|wip|fg|packing_stores). The synthetic
# manufacturer's four stock ledgers never receive a voucher -- see this
# module's docstring.
UNCITABLE_METRIC = "inventory"


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


def _ir(period_key: str, metric: str = "net_revenue") -> dict:
    return {"intent": "metric_value", "metric": metric,
              "period": {"type": "month", "value": period_key}}


def _reconciled_last_month(conn, schema: str, tenant_id: str, entity_id: int) -> str:
    """Ingest, freeze, and take the last loaded month to RECONCILED so the
    period gate is satisfied and whatever happens next is about the metric,
    not about the period."""
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, _summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                              effective_from=date(2022, 4, 1))
    assert freeze.passed, freeze.reason
    loaded_month = _last_gl_month(conn, schema, tenant_id, entity_id)
    reached = advance_periods_to_reconciled(conn, schema, tenant_id, entity_id, version_id, freeze,
                                                [loaded_month])
    assert reached[loaded_month] == "reconciled", reached
    return loaded_month


def test_a_metric_with_no_source_rows_is_unavailable_not_ok(conn, tenant):
    """The citation guard, on a period that clears the period gate."""
    tenant_id, schema = tenant
    entity_id = 1
    loaded_month = _reconciled_last_month(conn, schema, tenant_id, entity_id)
    config = load_registry()

    # The premise: this metric really does compile, successfully, to a real
    # Decimal -- over no rows at all. Without this the assertions below would
    # pass for the uninteresting reason that the metric simply failed.
    compiled = compile_metric(conn, schema, tenant_id, entity_id, UNCITABLE_METRIC, loaded_month, config)
    assert compiled.status == "ok", compiled.reason
    assert compiled.value is not None
    assert compiled.row_count == 0

    client = StubModelClient({UNCITABLE_QUESTION: ("metric_value", _ir(loaded_month, UNCITABLE_METRIC))})
    response = ask(conn, schema, tenant_id, entity_id, UNCITABLE_QUESTION, client, config,
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
    # number was withheld or why. And specifically NOT the period's fault:
    # the period is reconciled, so this must not be a period refusal.
    assert UNCITABLE_METRIC in response.refusal.reason
    assert "no source rows" in response.refusal.reason
    assert loaded_month in response.refusal.reason


def test_an_unreportable_period_is_refused_before_the_citation_guard(conn, tenant):
    """The period gate, and its precedence over the citation guard.

    The month after the last loaded one has no period_lock row at all, so it
    is OPEN. Both guards would refuse it; corpus/07 section 6's "period not
    reportable" is the one that applies, and it must state the reconciliation
    status and the unmapped rupee value rather than the metric's row count.
    """
    tenant_id, schema = tenant
    entity_id = 1
    loaded_month = _reconciled_last_month(conn, schema, tenant_id, entity_id)
    unloaded_month = _month_after(loaded_month)
    config = load_registry()

    client = StubModelClient({UNLOADED_QUESTION: ("metric_value", _ir(unloaded_month))})
    response = ask(conn, schema, tenant_id, entity_id, UNLOADED_QUESTION, client, config,
                      user_id="pytest", role="client_finance_lead", tenant_profile="manufacturing")

    assert response.status == "refused"
    assert response.citation is None
    assert response.refusal is not None
    assert response.refusal.refusal_class == "period_not_reportable"
    assert unloaded_month in response.refusal.reason
    assert "'open'" in response.refusal.reason
    # corpus/07 section 6 requires this class to state the unmapped rupee
    # value. An approved mapping version covers this month (it is inside the
    # version's effective window; there are simply no facts), so the figure
    # is real and is reported.
    assert "unmapped value is Rs" in response.refusal.reason
    # Never the placeholder-derived zero -- see period_gate._unmapped_value.
    assert "Rs None" not in response.refusal.reason
    assert response.refusal.nearest_supported_question


def test_the_same_question_for_a_loaded_month_still_answers_with_a_citation(conn, tenant):
    """The other half of both gates: neither branch may swallow a metric that
    IS backed by rows, in a period that IS reportable. Same question shape,
    same intent -- this one answers."""
    tenant_id, schema = tenant
    entity_id = 1
    loaded_month = _reconciled_last_month(conn, schema, tenant_id, entity_id)
    config = load_registry()

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
