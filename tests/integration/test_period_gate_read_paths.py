"""The read paths consult the period lock, corpus/09 section 5.

tests/integration/test_period_transitions_wired.py covers the write side --
which events drive a period between states. This file covers the read side:
what each surface does with the state a period is actually in.

corpus/09 section 5 annotates two states with what they unlock, and those
annotations are the whole gate:

    MAPPED       "metrics computable, statements assemble"
    RECONCILED   "pack may be generated"

So the tests below assert two different thresholds, not one. Every statement,
operating and overview surface, and Ask's metric intents, open at MAPPED. The
management pack opens one state later, at RECONCILED.

The routes are called as plain functions with a Session and the tenant tuple
their dependencies would have supplied, exactly as
test_period_transitions_wired.py already calls freeze_run/reconcile/lock --
there is no HTTP client in this repo's test suite.

Needs live Postgres (see tests/conftest.py) -- skips cleanly otherwise.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from src.api.deps.auth import Session
from src.api.routes.overview import get_overview_tiles
from src.api.routes.reports import GenerateRequest, generate_report
from src.api.routes.statements import get_balance_sheet, get_pnl
from src.config.loader import load_registry
from src.quality.period_gate import (
    PACK_REPORTABLE,
    STATEMENTS_REPORTABLE,
    PeriodNotReportable,
    months_in_range,
    resolve_period_reportability,
)
from src.quality.period_state import get_current_period_lock, lock_period, restate_period
from src.reports.pack import generate_pack
from src.semantic.ask import ask
from src.semantic.model_client import StubModelClient
from tests.helpers import advance_periods_to_reconciled, ingest_manufacturer, run_and_freeze_mapping

ENTITY_ID = 1
SESSION = Session(user_id="pytest-analyst", org_id="org_pytest", role="spequla_analyst")
PERIOD = "2025-03"
PERIOD_START, PERIOD_END = date(2025, 3, 1), date(2025, 3, 31)
QUESTION = "What was our revenue last month?"


def _ir(period_key: str = PERIOD) -> dict:
    return {"intent": "metric_value", "metric": "net_revenue",
              "period": {"type": "month", "value": period_key}}


def _ask(conn, schema, tenant_id, ir: dict | None = None, question: str = QUESTION):
    client = StubModelClient({question: ("metric_value", ir or _ir())})
    return ask(conn, schema, tenant_id, ENTITY_ID, question, client, load_registry(),
                  user_id="pytest", role="client_finance_lead", tenant_profile="manufacturing")


def _validated(conn, schema, tenant_id):
    """Ingest + freeze the mapping. Every period lands at VALIDATED: the GL
    load validates them, and freeze_mapping_version is called directly here
    rather than through POST /mapping/runs/{id}/freeze, which is what would
    take them on to MAPPED."""
    ingest_manufacturer(conn, schema, tenant_id, ENTITY_ID)
    version_id, _summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, ENTITY_ID,
                                                              effective_from=date(2022, 4, 1))
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, PERIOD).status == "validated"
    return version_id, freeze


def _mapped(conn, schema, tenant_id):
    """VALIDATED -> MAPPED for every period the frozen version governs, via
    the same call POST /mapping/runs/{id}/freeze makes."""
    from src.quality.period_state import map_periods_for_mapping_version
    version_id, freeze = _validated(conn, schema, tenant_id)
    map_periods_for_mapping_version(conn, schema, tenant_id, ENTITY_ID, version_id,
                                        freeze_passed=freeze.passed, coverage_pct=freeze.coverage_pct)
    conn.commit()
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, PERIOD).status == "mapped"
    return version_id, freeze


def _reconciled(conn, schema, tenant_id):
    version_id, freeze = _validated(conn, schema, tenant_id)
    reached = advance_periods_to_reconciled(conn, schema, tenant_id, ENTITY_ID, version_id, freeze, [PERIOD])
    assert reached[PERIOD] == "reconciled", reached
    return version_id, freeze


# --------------------------------------------------------------------------
# The gate's own vocabulary
# --------------------------------------------------------------------------

def test_the_two_reportable_sets_are_corpus_09_section_5s_annotations():
    """Read literally off the diagram, and asserted here so a later edit that
    quietly widens either set fails."""
    assert STATEMENTS_REPORTABLE == ("mapped", "reconciled", "locked", "restated")
    assert PACK_REPORTABLE == ("reconciled", "locked")
    # 'restated' is readable and not packable, per OQ-010's resolution.
    assert "restated" in STATEMENTS_REPORTABLE
    assert "restated" not in PACK_REPORTABLE
    # 'open' and 'validated' are in neither, which is the gate itself.
    for state in ("open", "validated"):
        assert state not in STATEMENTS_REPORTABLE and state not in PACK_REPORTABLE


def test_a_date_range_expands_to_every_month_it_touches():
    """A P&L asked for a range is gated on all of it, not on its endpoints."""
    assert months_in_range(date(2025, 1, 1), date(2025, 3, 31)) == ["2025-01", "2025-02", "2025-03"]
    assert months_in_range(date(2025, 1, 15), date(2025, 2, 3)) == ["2025-01", "2025-02"]
    assert months_in_range(date(2024, 12, 1), date(2025, 1, 31)) == ["2024-12", "2025-01"]
    assert months_in_range(date(2025, 3, 4), date(2025, 3, 9)) == ["2025-03"]
    with pytest.raises(ValueError):
        months_in_range(date(2025, 3, 1), date(2025, 2, 1))


# --------------------------------------------------------------------------
# Below MAPPED: every numeric surface refuses
# --------------------------------------------------------------------------

def test_statements_refuse_a_validated_period_and_name_its_status(conn, tenant):
    tenant_id, schema = tenant
    _validated(conn, schema, tenant_id)

    with pytest.raises(HTTPException) as pnl_exc:
        get_pnl(period_start=PERIOD_START, period_end=PERIOD_END, profile="manufacturing",
                   entity_id=ENTITY_ID, session=SESSION, tenant_ctx=(conn, tenant_id, schema))
    assert pnl_exc.value.status_code == 422
    assert "'validated'" in pnl_exc.value.detail, pnl_exc.value.detail
    assert PERIOD in pnl_exc.value.detail

    with pytest.raises(HTTPException) as bs_exc:
        get_balance_sheet(as_of=PERIOD_END, entity_id=ENTITY_ID, session=SESSION,
                             tenant_ctx=(conn, tenant_id, schema))
    assert bs_exc.value.status_code == 422
    assert "'validated'" in bs_exc.value.detail


def test_overview_tiles_refuse_a_validated_period(conn, tenant):
    tenant_id, schema = tenant
    _validated(conn, schema, tenant_id)
    with pytest.raises(HTTPException) as exc:
        get_overview_tiles(period=PERIOD, entity_id=ENTITY_ID, session=SESSION,
                              tenant_ctx=(conn, tenant_id, schema))
    assert exc.value.status_code == 422
    assert "'validated'" in exc.value.detail


def test_a_pnl_range_is_refused_when_any_month_inside_it_is_unreportable(conn, tenant):
    """The reason first_unreportable walks the whole range: a quarter whose
    middle month is unreadable produces one set of totals, and the gap would
    vanish into them."""
    tenant_id, schema = tenant
    version_id, freeze = _validated(conn, schema, tenant_id)
    # 2023-11 and 2024-01 reconcile; 2023-12 cannot (defect #4's unbalanced
    # trial balance), so the quarter containing it must refuse.
    reached = advance_periods_to_reconciled(conn, schema, tenant_id, ENTITY_ID, version_id, freeze,
                                                ["2023-11", "2023-12", "2024-01"])
    assert reached["2023-11"] == "reconciled" and reached["2024-01"] == "reconciled"
    assert reached["2023-12"] == "open"

    with pytest.raises(HTTPException) as exc:
        get_pnl(period_start=date(2023, 11, 1), period_end=date(2024, 1, 31), profile="manufacturing",
                   entity_id=ENTITY_ID, session=SESSION, tenant_ctx=(conn, tenant_id, schema))
    assert exc.value.status_code == 422
    assert "2023-12" in exc.value.detail

    # ...and the sound months on either side are served on their own.
    for start, end in ((date(2023, 11, 1), date(2023, 11, 30)), (date(2024, 1, 1), date(2024, 1, 31))):
        served = get_pnl(period_start=start, period_end=end, profile="manufacturing", entity_id=ENTITY_ID,
                            session=SESSION, tenant_ctx=(conn, tenant_id, schema))
        assert served["lines"]


def test_ask_refuses_a_validated_period_naming_status_and_unmapped_value(conn, tenant):
    """corpus/07 section 6's period_not_reportable class requires both
    figures. This is the class, not a generic 'unavailable'."""
    tenant_id, schema = tenant
    _validated(conn, schema, tenant_id)

    response = _ask(conn, schema, tenant_id)
    assert response.status == "refused"
    assert response.citation is None
    assert response.refusal.refusal_class == "period_not_reportable"
    assert "'validated'" in response.refusal.reason
    assert "unmapped value is Rs" in response.refusal.reason
    assert response.refusal.nearest_supported_question


def test_the_unmapped_value_in_a_refusal_is_never_the_placeholders_zero(conn, tenant):
    """A VALIDATED period's lock row points at the ingestion-time placeholder
    mapping version, which has no map_account rows -- summing suspense.unmapped
    through it returns Rs 0. Reporting "unmapped value is Rs 0" while refusing
    a period FOR being unmapped is a fabricated number in the one refusal whose
    job is to state that figure (CLAUDE.md section 3.4). The value must come
    from the version that governs the period."""
    tenant_id, schema = tenant
    version_id, _freeze = _validated(conn, schema, tenant_id)

    lock = get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, PERIOD)
    assert lock.mapping_version_id != version_id, (
        "premise: a validated period carries the placeholder, not the frozen version"
    )
    with conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM "{schema}".map_account WHERE mapping_version_id = %s',
                       (lock.mapping_version_id,))
        assert cur.fetchone()[0] == 0, "premise: the placeholder version has no map_account rows"

    reportability = resolve_period_reportability(conn, schema, tenant_id, ENTITY_ID, PERIOD,
                                                       STATEMENTS_REPORTABLE)
    assert not reportability.reportable
    # Resolved through the governing version instead. This dataset maps above
    # the 98% freeze threshold with a real residual, so the figure is a real,
    # non-zero rupee amount rather than the placeholder's zero.
    assert reportability.unmapped_value_inr is not None
    assert reportability.unmapped_value_unavailable_reason is None
    assert reportability.unmapped_value_inr > 0


def test_the_unmapped_value_is_a_stated_reason_when_no_mapping_version_covers_the_period(conn, tenant):
    """The other half: with no approved mapping version there is no universe
    to measure unmapped value against, and the refusal says so rather than
    printing a figure it does not have."""
    tenant_id, schema = tenant
    ingest_manufacturer(conn, schema, tenant_id, ENTITY_ID)  # loaded, never mapped

    reportability = resolve_period_reportability(conn, schema, tenant_id, ENTITY_ID, PERIOD,
                                                       STATEMENTS_REPORTABLE)
    assert not reportability.reportable
    assert reportability.unmapped_value_inr is None
    assert "no approved mapping version" in reportability.unmapped_value_unavailable_reason

    response = _ask(conn, schema, tenant_id)
    assert response.refusal.refusal_class == "period_not_reportable"
    assert "not computable" in response.refusal.reason
    assert "Rs None" not in response.refusal.reason
    assert "Rs 0" not in response.refusal.reason


# --------------------------------------------------------------------------
# At MAPPED: statements, tiles and Ask serve. The pack still does not.
# --------------------------------------------------------------------------

def test_at_mapped_statements_and_tiles_serve_and_the_tiles_badge_the_status(conn, tenant):
    """corpus/09 section 5: MAPPED is "metrics computable, statements
    assemble". corpus/10's GQ-001 names the failure mode as "uses an
    unreconciled period WITHOUT badging" -- so serving a mapped period is
    correct, and every number it serves carries 'mapped' as its
    reconciliation status."""
    tenant_id, schema = tenant
    _mapped(conn, schema, tenant_id)

    pnl = get_pnl(period_start=PERIOD_START, period_end=PERIOD_END, profile="manufacturing",
                     entity_id=ENTITY_ID, session=SESSION, tenant_ctx=(conn, tenant_id, schema))
    assert pnl["lines"]

    # The balance sheet is read before defect #4's one-sided INR 12,500
    # journal (2023-12). A balance sheet is cumulative, so every as_of after
    # that month is refused by corpus/08 section 5's own balancing gate --
    # correctly, and independently of this one. Asserting it here at a date
    # the ledger still balances is what keeps this test about the period
    # gate; test_a_pnl_range_is_refused_when_any_month_inside_it_is_
    # unreportable covers what the period gate does with 2023-12 itself.
    bs = get_balance_sheet(as_of=date(2023, 11, 30), entity_id=ENTITY_ID, session=SESSION,
                              tenant_ctx=(conn, tenant_id, schema))
    assert bs["balances"] is True

    tiles = get_overview_tiles(period=PERIOD, entity_id=ENTITY_ID, session=SESSION,
                                  tenant_ctx=(conn, tenant_id, schema))
    assert tiles["reconciliation_status"] == "mapped"
    cited = [t for row in tiles["rows"] for t in row["tiles"] if t["status"] == "ok"]
    assert cited, "a mapped period should resolve at least one tile"
    for tile in cited:
        assert tile["citation"]["reconciliation_status"] == "mapped", (
            "an unreconciled period's numbers must carry that status on every citation -- "
            "GQ-001's named failure mode is serving them unbadged"
        )

    response = _ask(conn, schema, tenant_id)
    assert response.status == "ok", response.refusal.reason if response.refusal else response.result
    assert response.citation is not None


def test_the_pack_refuses_at_mapped_and_generates_at_reconciled(conn, tenant):
    """corpus/09 section 5 puts "pack may be generated" one state later than
    "statements assemble", and the pack service enforces it for every caller,
    not only for POST /reports/generate."""
    tenant_id, schema = tenant
    version_id, freeze = _mapped(conn, schema, tenant_id)
    config = load_registry()

    with pytest.raises(PeriodNotReportable) as exc:
        generate_pack(conn, schema, tenant_id, ENTITY_ID, "manufacturing", PERIOD, config,
                         generated_by="pytest")
    assert exc.value.reportability.status == "mapped"
    assert "'mapped'" in str(exc.value)

    # ...and the endpoint renders that as a 422 rather than a 500.
    with pytest.raises(HTTPException) as http_exc:
        generate_report(GenerateRequest(period=PERIOD, entity_id=ENTITY_ID, profile="manufacturing"),
                           session=SESSION, tenant_ctx=(conn, tenant_id, schema))
    assert http_exc.value.status_code == 422
    assert "'mapped'" in http_exc.value.detail

    # One state on, the same call succeeds.
    reached = advance_periods_to_reconciled(conn, schema, tenant_id, ENTITY_ID, version_id, freeze, [PERIOD])
    assert reached[PERIOD] == "reconciled"
    artefact = generate_report(GenerateRequest(period=PERIOD, entity_id=ENTITY_ID, profile="manufacturing"),
                                  session=SESSION, tenant_ctx=(conn, tenant_id, schema))
    assert artefact["period_key"] == PERIOD


# --------------------------------------------------------------------------
# LOCKED serves both; RESTATED serves statements and not the pack
# --------------------------------------------------------------------------

def test_a_locked_period_is_reportable_for_both_thresholds(conn, tenant):
    tenant_id, schema = tenant
    self_version, _freeze = _reconciled(conn, schema, tenant_id)
    current = get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, PERIOD)
    lock_period(conn, schema, tenant_id, ENTITY_ID, PERIOD, current.mapping_version_id, locked_by="pytest-analyst")
    conn.commit()

    for required in (STATEMENTS_REPORTABLE, PACK_REPORTABLE):
        assert resolve_period_reportability(conn, schema, tenant_id, ENTITY_ID, PERIOD, required).reportable

    pnl = get_pnl(period_start=PERIOD_START, period_end=PERIOD_END, profile="manufacturing",
                     entity_id=ENTITY_ID, session=SESSION, tenant_ctx=(conn, tenant_id, schema))
    assert pnl["lines"]


def test_a_restated_period_serves_statements_and_refuses_the_pack(conn, tenant):
    """OQ-010's resolution, which corpus/09 section 5 does not itself state:
    RESTATED reads like MAPPED and packs like nothing. Refusing it on the
    statement surfaces would hide the corrected number and leave the
    superseded one as the last thing anybody saw; letting it into a pack
    would sign (D-039) over a delta nobody has explained yet."""
    tenant_id, schema = tenant
    _reconciled(conn, schema, tenant_id)
    current = get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, PERIOD)
    lock_period(conn, schema, tenant_id, ENTITY_ID, PERIOD, current.mapping_version_id, locked_by="pytest-analyst")
    restate_period(conn, schema, tenant_id, ENTITY_ID, PERIOD, current.mapping_version_id,
                      restatement_reason="pytest: backdated entry found touching a locked period")
    conn.commit()
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, PERIOD).status == "restated"

    # Readable on the statement threshold, and the P&L actually serves.
    assert resolve_period_reportability(conn, schema, tenant_id, ENTITY_ID, PERIOD,
                                              STATEMENTS_REPORTABLE).reportable
    pnl = get_pnl(period_start=PERIOD_START, period_end=PERIOD_END, profile="manufacturing",
                     entity_id=ENTITY_ID, session=SESSION, tenant_ctx=(conn, tenant_id, schema))
    assert pnl["lines"]

    # Refused on the pack threshold, with the refusal stating the split
    # rather than citing an open question.
    reportability = resolve_period_reportability(conn, schema, tenant_id, ENTITY_ID, PERIOD, PACK_REPORTABLE)
    assert not reportability.reportable
    assert "signed against a locked period" in reportability.detail()

    with pytest.raises(PeriodNotReportable) as exc:
        generate_pack(conn, schema, tenant_id, ENTITY_ID, "manufacturing", PERIOD, load_registry(),
                         generated_by="pytest")
    assert exc.value.reportability.status == "restated"

    with pytest.raises(HTTPException) as http_exc:
        generate_report(GenerateRequest(period=PERIOD, entity_id=ENTITY_ID, profile="manufacturing"),
                           session=SESSION, tenant_ctx=(conn, tenant_id, schema))
    assert http_exc.value.status_code == 422
    assert "'restated'" in http_exc.value.detail


# --------------------------------------------------------------------------
# What is deliberately NOT gated
# --------------------------------------------------------------------------

def test_data_health_answers_for_a_period_every_other_intent_refuses(conn, tenant):
    """The screen that explains why you are gated cannot itself be gated."""
    tenant_id, schema = tenant
    _validated(conn, schema, tenant_id)

    question = "Is March reconciled?"
    client = StubModelClient({question: ("data_health", {"intent": "data_health",
                                                             "period": {"type": "month", "value": PERIOD}})})
    response = ask(conn, schema, tenant_id, ENTITY_ID, question, client, load_registry(),
                      user_id="pytest", role="client_finance_lead", tenant_profile="manufacturing")
    assert response.status == "ok", response.refusal.reason if response.refusal else None
    assert response.result.value["status"] == "validated"

    # ...while a metric for the same period refuses.
    assert _ask(conn, schema, tenant_id).status == "refused"


def test_definition_lookup_is_not_gated(conn, tenant):
    """corpus/07 section 4: "Registry lookup, returns the resolved contract.
    No SQL runs." There is no period in it to gate."""
    tenant_id, schema = tenant
    _validated(conn, schema, tenant_id)

    question = "How do you calculate DSO for us?"
    client = StubModelClient({question: ("definition_lookup", {"intent": "definition_lookup", "metric": "dso"})})
    response = ask(conn, schema, tenant_id, ENTITY_ID, question, client, load_registry(),
                      user_id="pytest", role="client_finance_lead", tenant_profile="manufacturing")
    assert response.status == "ok"


def test_a_trend_labels_each_unreportable_month_rather_than_refusing_the_window(conn, tenant):
    """metric_trend returns a value per month, so an unreportable month is
    reported in place -- the window around it is still answered, and nothing
    is silently dropped. Contrast the statement routes, where the output is
    one set of totals."""
    tenant_id, schema = tenant
    version_id, freeze = _validated(conn, schema, tenant_id)
    # 2023-12 is defect #4's unbalanced month and is held at OPEN by its
    # blocking exception -- the naturally occurring unreportable month, in a
    # window whose neighbours are fine. (Note that advancing ANY period runs
    # map_periods_for_mapping_version, which maps every period the frozen
    # version governs, so an unadvanced month is MAPPED, not VALIDATED --
    # only a genuinely broken one stays behind.)
    reached = advance_periods_to_reconciled(conn, schema, tenant_id, ENTITY_ID, version_id, freeze,
                                                ["2023-11", "2023-12", "2024-01"])
    assert reached["2023-11"] == "reconciled" and reached["2024-01"] == "reconciled"
    assert reached["2023-12"] == "open"

    question = "Show revenue for these months."
    ir = {"intent": "metric_trend", "metric": "net_revenue",
            "period": {"type": "custom_range", "value": "q3",
                         "resolved_range": ["2023-11-01", "2024-01-31"]}}
    client = StubModelClient({question: ("metric_trend", ir)})
    response = ask(conn, schema, tenant_id, ENTITY_ID, question, client, load_registry(),
                      user_id="pytest", role="client_finance_lead", tenant_profile="manufacturing")

    assert response.status == "ok"
    by_period = {row["period"]: row for row in response.result.series}
    assert by_period["2023-11"]["status"] == "ok" and by_period["2023-11"]["value"] is not None
    assert by_period["2024-01"]["status"] == "ok"
    # The broken month is labelled rather than omitted -- the answer around
    # it stands, and the gap in it is stated.
    assert by_period["2023-12"]["status"] == "refused"
    assert by_period["2023-12"]["value"] is None
    assert "'open'" in by_period["2023-12"]["reason"]


def test_a_trend_whose_every_month_is_unreportable_refuses_outright(conn, tenant):
    tenant_id, schema = tenant
    _validated(conn, schema, tenant_id)

    question = "Show revenue for these months."
    ir = {"intent": "metric_trend", "metric": "net_revenue",
            "period": {"type": "custom_range", "value": "q4",
                         "resolved_range": ["2024-01-01", "2024-03-31"]}}
    client = StubModelClient({question: ("metric_trend", ir)})
    response = ask(conn, schema, tenant_id, ENTITY_ID, question, client, load_registry(),
                      user_id="pytest", role="client_finance_lead", tenant_profile="manufacturing")

    assert response.status == "refused"
    assert response.refusal.refusal_class == "period_not_reportable"
    # The per-month detail is still carried behind the refusal.
    assert len(response.result.series) == 3
    assert all(row["status"] == "refused" for row in response.result.series)


def test_forecasting_is_not_period_gated(conn, tenant):
    """corpus/13 states no period-status precondition for the forecast
    engine, and nothing here invents one. A projection is explicitly not a
    reported actual, so corpus/09 section 5's annotations do not reach it.

    Asserted structurally rather than by running a projection: the forecast
    module must not import the gate at all, so a later edit that adds one
    without a corpus sentence behind it fails here."""
    import pathlib
    forecasting = pathlib.Path("src/forecasting")
    assert forecasting.is_dir()
    offenders = [str(p) for p in forecasting.rglob("*.py") if "period_gate" in p.read_text()]
    assert not offenders, f"forecasting must not consult the period gate (corpus/13 states none): {offenders}"
