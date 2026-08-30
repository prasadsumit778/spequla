"""Sprint 4 acceptance criterion, corpus/12: '37 of 37 runnable gating
golden questions pass, and 14 of 14 refusals refuse correctly.'

"Pass" is read the way corpus/07 itself defines success throughout: the
system never fabricates a number. A gating question passes when Ask
produces either (a) a real, cited answer, or (b) a correctly-explained
reason it cannot -- blocked by a named open decision (corpus/07 section 6:
"Requires a decision not made... names the decision"), or the required data
genuinely does not exist yet (corpus/07 section 6: "Requires data not
held... names the missing input"). A crash, a fabricated number, or a wrong
reason is the only kind of failure this test treats as a failure. See
tests/fixtures/golden_ir.py for exactly which of the 37 fall into which
bucket and why, worked out from this project's actual current state: only
COA/TB/GL/Bank are ingested (no customer/product dimension), only
D-041, D-042, D-050 and D-052 remain open after the 2026-08-24 resolutions
(corpus/00 "Still open: 4"), and 5 of the 37 need fact_channel_order_line
(Sprint 6).

**The fixture reconciles the periods it asks about.** corpus/09 section 5
gates every metric and statement on MAPPED or later, so a golden set run
against VALIDATED periods would refuse most of its own questions -- 14 of
the 18 below -- and corpus/12's acceptance criterion would be met by a
system that answers nothing. Reconciling first is what makes this test test
what it says it tests. It is done through the real transitions
(tests/helpers.advance_periods_to_reconciled), never by writing period_lock
rows directly, and the fixture asserts which periods actually got there
rather than assuming: the synthetic manufacturer contains one month whose
trial balance genuinely does not tie (defect #4, a one-sided INR 12,500
journal in 2023-12), and that month must stay unreportable. See
test_the_deliberately_broken_month_cannot_be_reconciled.

Needs live Postgres -- skips cleanly otherwise, consistent with every
other sprint's acceptance test in this repo.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.config.loader import load_registry
from src.quality.period_gate import STATEMENTS_REPORTABLE, resolve_period_reportability
from src.semantic.ask import ask
from src.semantic.model_client import StubModelClient
from tests.fixtures.golden_ir import (
    ALL_FIXTURES,
    CONSUMER_PROFILE_DEFERRED_QUESTIONS,
    GATING_FIXTURES,
    LAST_MONTH,
    PRIOR_MONTH,
    REFUSAL_FIXTURES,
)
from tests.helpers import (
    advance_periods_to_reconciled,
    ingest_manufacturer,
    run_and_freeze_mapping,
)

# corpus/11 section 3's gating tier, which is what pytest.ini's `eval` marker
# selects. Applied at module level so `pytest -m eval` collects this file --
# the same set .github/workflows/ci.yml already collects by path.
pytestmark = pytest.mark.eval

# Expected status per real (non-consumer) gating question, worked out from
# this project's actual current state -- see this module's docstring.
#
# Six questions moved blocked -> ok on 2026-08-24. Not a behaviour change in
# Ask: D-001, D-002, D-006, D-012, D-015, D-016, D-017 and D-018 were
# resolved that day (corpus/00 section 2b), which empties the
# `unresolved_decisions` closure behind net_revenue, ebitda, dso and the cash
# conversion cycle. With no open decision left to name, refusing these would
# now be the defect. "Where did the cash go last month?" stays blocked for an
# unrelated and still-live reason -- OQ-004, eight cash flow leaf metrics with
# no formula anywhere in the corpus.
EXPECTED_STATUS = {
    "What was our revenue last month?": "ok",
    "Show me the P&L for last quarter.": "ok",
    "What is our EBITDA this year to date?": "ok",
    "Show revenue for the last twelve months.": "ok",
    "Why did EBITDA decline?": "ok",
    "What is our revenue by customer this quarter?": "unavailable",
    "Who are our top ten customers by revenue?": "unavailable",
    "What is our gross margin by product?": "unavailable",
    "Which products have the highest margins?": "unavailable",
    "What is our current DSO?": "ok",
    "How has our cash conversion cycle changed?": "ok",
    "How much receivable is over ninety days?": "unavailable",
    "How much cash do we have?": "ok",
    "What is our net debt?": "ok",
    "Where did the cash go last month?": "blocked",
    "Is June reconciled?": "ok",
    "How much of our data is unmapped?": "ok",
    "How do you calculate DSO for us?": "ok",
}


# Every month the fixtured IR above reaches: the two single-month questions
# use LAST_MONTH/PRIOR_MONTH, the trend questions resolve a twelve-month
# window ending at LAST_MONTH, and "Is June reconciled?" names 2024-06.
# Derived here rather than hardcoded so a change to golden_ir.py's months
# moves the fixture with it.
def _months(first: str, last: str) -> list[str]:
    keys, (y, m) = [], (int(p) for p in first.split("-"))
    ly, lm = (int(p) for p in last.split("-"))
    while (y, m) <= (ly, lm):
        keys.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return keys


TB_BROKEN_MONTH = "2023-12"  # synthetic/manufacturer/engine.py defect #4
ASKED_MONTHS = _months("2024-04", LAST_MONTH) + ["2024-06", PRIOR_MONTH]


def _reconciled_manufacturer(conn, schema, tenant_id, entity_id):
    """Ingest, freeze, and take every period the golden questions ask about
    to RECONCILED. Returns the reached-status map so a caller can assert."""
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, _summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                              effective_from=date(2022, 4, 1))
    assert freeze.passed, freeze.reason
    reached = advance_periods_to_reconciled(conn, schema, tenant_id, entity_id, version_id, freeze,
                                                sorted(set(ASKED_MONTHS)))
    unreconciled = {p: st for p, st in reached.items() if st != "reconciled"}
    assert not unreconciled, f"fixture could not make these periods reportable: {unreconciled}"
    return version_id, freeze


def _ask_all(conn, schema, tenant_id, entity_id, config, fixtures, tenant_profile="manufacturing"):
    client = StubModelClient(fixtures)
    results = {}
    for question in fixtures:
        results[question] = ask(conn, schema, tenant_id, entity_id, question, client, config,
                                   user_id="pytest", role="client_finance_lead", tenant_profile=tenant_profile)
    return results


def test_37_of_37_gating_questions_behave_correctly(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    _reconciled_manufacturer(conn, schema, tenant_id, entity_id)

    config = load_registry()
    responses = _ask_all(conn, schema, tenant_id, entity_id, config, GATING_FIXTURES)

    assert set(responses.keys()) == set(EXPECTED_STATUS.keys())
    failures = []
    for question, response in responses.items():
        expected = EXPECTED_STATUS[question]
        if response.status != expected:
            failures.append(f"{question!r}: expected {expected}, got {response.status} "
                              f"(reason: {response.refusal.reason if response.refusal else response.result})")
        # Never a crash, never a silent nothing -- every non-ok response
        # states why, per corpus/07's own governing rule (section 1).
        if response.status != "ok":
            assert response.refusal is not None, f"{question!r}: non-ok with no stated reason"
            assert response.refusal.reason, f"{question!r}: refusal with an empty reason"
        else:
            # An 'ok' status never lacks a citation when a metric was
            # actually compiled -- invariant #7, enforced structurally by
            # NotCitable inside src/semantic/ask.py.
            if response.result and response.result.compiled_metric is not None:
                assert response.citation is not None, f"{question!r}: ok status but no citation"

    assert not failures, "gating question status mismatches:\n" + "\n".join(failures)

    # The 18 fixtured questions above account for 18 of the 37 -- the other
    # 19 are the 5 consumer-profile ones (asserted separately below) and 14
    # refusals (asserted in test_14_of_14_refusals_refuse). All three groups
    # together are exactly the 37 gating questions in corpus/10.
    assert len(GATING_FIXTURES) + len(CONSUMER_PROFILE_DEFERRED_QUESTIONS) + len(REFUSAL_FIXTURES) == 37


def test_consumer_profile_questions_correctly_deferred_pending_sprint_6(conn, tenant):
    """The 5 gating questions needing fact_channel_order_line (Sprint 6,
    not yet built). Correct behaviour today is an honest refusal naming
    that the data isn't available -- never a fabricated channel breakdown
    from data that doesn't exist."""
    tenant_id, schema = tenant
    entity_id = 1
    _reconciled_manufacturer(conn, schema, tenant_id, entity_id)

    config = load_registry()
    client = StubModelClient({})  # deliberately no fixtures -- these questions are unfixtured by design
    for question in CONSUMER_PROFILE_DEFERRED_QUESTIONS:
        # this fixture ingests a manufacturing tenant -- tenant_profile
        # matches that, so a consumer-shaped question now correctly
        # refuses on either of two honest grounds: the profile mismatch
        # (src/semantic/ir.py's validate_ir) or, for a genuinely
        # manufacturing-profile tenant asking about channels/GMV, missing
        # data -- never a fabricated answer either way.
        response = ask(conn, schema, tenant_id, entity_id, question, client, config,
                          user_id="pytest", role="client_finance_lead", tenant_profile="manufacturing")
        assert response.status == "refused", f"{question!r}: expected refused, got {response.status}"
        assert response.refusal is not None and response.refusal.reason


def test_14_of_14_refusals_refuse(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    _reconciled_manufacturer(conn, schema, tenant_id, entity_id)

    config = load_registry()
    responses = _ask_all(conn, schema, tenant_id, entity_id, config, REFUSAL_FIXTURES)

    assert len(responses) == 14
    for question, response in responses.items():
        expected_reason = REFUSAL_FIXTURES[question][1]
        assert response.status == "refused", f"{question!r}: expected refused, got {response.status}"
        assert response.refusal is not None
        assert response.refusal.reason == expected_reason, (
            f"{question!r}: expected reason {expected_reason!r}, got {response.refusal.reason!r}"
        )
        assert response.refusal.nearest_supported_question, f"{question!r}: refusal names no nearest question"


def test_the_deliberately_broken_month_cannot_be_reconciled(conn, tenant):
    """The fixture above reconciles every month it asks about. This pins down
    that it CANNOT reconcile the one month that should not reconcile, and
    that the read paths refuse it.

    synthetic/manufacturer/engine.py's defect #4 posts a one-sided INR
    12,500.00 journal to Bank Charges in 2023-12. That month's trial balance
    genuinely does not tie, D-051's tolerance is zero, and corpus/09 section
    5 will not admit it past OPEN -- its blocking exception stops it at the
    first arrow. Without this test, a fixture helper that quietly forced
    periods through would look identical to one that does not.
    """
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, _summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                              effective_from=date(2022, 4, 1))
    reached = advance_periods_to_reconciled(conn, schema, tenant_id, entity_id, version_id, freeze,
                                                [TB_BROKEN_MONTH, LAST_MONTH])

    # Held at OPEN: the blocking exception raised at load never let it become
    # VALIDATED, so neither later arrow is even reachable.
    assert reached[TB_BROKEN_MONTH] == "open", (
        f"{TB_BROKEN_MONTH} has an unbalanced trial balance by construction and must not advance -- "
        f"got {reached[TB_BROKEN_MONTH]!r}"
    )
    # ...while the helper is demonstrably capable of advancing a sound month,
    # so the assertion above is not passing for the boring reason.
    assert reached[LAST_MONTH] == "reconciled"

    # And the gate refuses it, naming the state it is actually in.
    reportability = resolve_period_reportability(conn, schema, tenant_id, entity_id, TB_BROKEN_MONTH,
                                                       STATEMENTS_REPORTABLE)
    assert not reportability.reportable
    assert "'open'" in reportability.detail()

    config = load_registry()
    client = StubModelClient({"What was our revenue last month?":
                                  ("metric_value", {"intent": "metric_value", "metric": "net_revenue",
                                                      "period": {"type": "month", "value": TB_BROKEN_MONTH}})})
    response = ask(conn, schema, tenant_id, entity_id, "What was our revenue last month?", client, config,
                      user_id="pytest", role="client_finance_lead", tenant_profile="manufacturing")
    assert response.status == "refused"
    assert response.refusal.refusal_class == "period_not_reportable"
    assert response.citation is None
