"""Deleting a saved scenario is an archive, corpus/13 section 4 and
CLAUDE.md invariant 4.

The Forecasting screen offers "Delete" on a saved scenario. What that must
mean here is: gone from the list, no longer runnable, and still on disk --
because forecast_run.scenario_id points at the assumptions that produced a
stored projection. If the row could be removed, a past run would be left
asserting numbers with no record of what was assumed to get them. That is
the plausible-wrong-number failure mode this system exists to prevent.
"""
import json
from decimal import Decimal as D

import pytest

from src.forecasting.drivers import CostDrivers, ForecastDrivers, OnlineChannelDrivers
from src.forecasting.scenario import (archive_scenario, create_scenario, get_run, get_scenario,
                                          list_scenarios)

ENTITY_ID = 1


def _drivers(commission: str) -> ForecastDrivers:
    """A minimal, deliberately distinguishable assumption set. Every figure
    is synthetic and only has to survive a round trip -- no projection is
    computed in this test."""
    return ForecastDrivers(
        forecast_years=2,
        online_channels=[OnlineChannelDrivers(
            channel_name="Marketplace - synthetic",
            orders_growth_yoy=D("0.25"), price_growth_yoy=D("0.025"),
        )],
        costs=CostDrivers(
            store_personnel_growth_yoy=D("0.07"), store_rent_growth_yoy=D("0.06"),
            franchise_commission_rate=D("0.10"), ho_cost_growth_yoy=D("0.075"),
            online_commission_rate=D(commission), online_ad_spend_pct_of_sales=D("0.075"),
            gp_margin_path=[D("0.55"), D("0.57")],
        ),
    )


def test_archived_scenario_leaves_the_list_but_not_the_database(conn, tenant):
    tenant_id, schema = tenant
    keep = create_scenario(conn, schema, tenant_id, ENTITY_ID, "keep me", "pytest-analyst", _drivers("0.16"))
    drop = create_scenario(conn, schema, tenant_id, ENTITY_ID, "delete me", "pytest-analyst", _drivers("0.18"))

    assert {s["scenario_id"] for s in list_scenarios(conn, schema, tenant_id, ENTITY_ID)} == {keep, drop}

    archive_scenario(conn, schema, tenant_id, ENTITY_ID, drop, "pytest-analyst")

    listed = list_scenarios(conn, schema, tenant_id, ENTITY_ID)
    assert [s["scenario_id"] for s in listed] == [keep], "the archived scenario must not be listed"

    # Gone from the screen, still on disk, with its assumptions unchanged.
    name, drivers = get_scenario(conn, schema, tenant_id, ENTITY_ID, drop, include_archived=True)
    assert name == "delete me"
    assert drivers.costs.online_commission_rate == D("0.18")

    with conn.cursor() as cur:
        cur.execute(f'SELECT archived_by FROM "{schema}".forecast_scenario WHERE scenario_id=%s', (drop,))
        assert cur.fetchone()[0] == "pytest-analyst", "who archived it is part of the record"


def test_archived_scenario_cannot_be_read_or_run(conn, tenant):
    """get_scenario is the single door run_scenario goes through, so an
    archived assumption set is not projectable -- a stale browser tab that
    still shows the row cannot produce a forecast from it."""
    tenant_id, schema = tenant
    scenario_id = create_scenario(conn, schema, tenant_id, ENTITY_ID, "gone", "pytest-analyst", _drivers("0.16"))
    archive_scenario(conn, schema, tenant_id, ENTITY_ID, scenario_id, "pytest-analyst")

    with pytest.raises(ValueError):
        get_scenario(conn, schema, tenant_id, ENTITY_ID, scenario_id)


def test_archiving_twice_fails_loudly(conn, tenant):
    """"Already archived" and "archived just now" must not look the same to
    the caller -- the API turns this into a 404, not a silent success."""
    tenant_id, schema = tenant
    scenario_id = create_scenario(conn, schema, tenant_id, ENTITY_ID, "once", "pytest-analyst", _drivers("0.16"))
    archive_scenario(conn, schema, tenant_id, ENTITY_ID, scenario_id, "pytest-analyst")

    with pytest.raises(ValueError):
        archive_scenario(conn, schema, tenant_id, ENTITY_ID, scenario_id, "pytest-analyst")


def test_archiving_another_tenants_scenario_is_refused(conn, tenant):
    tenant_id, schema = tenant
    scenario_id = create_scenario(conn, schema, tenant_id, ENTITY_ID, "mine", "pytest-analyst", _drivers("0.16"))

    with pytest.raises(ValueError):
        archive_scenario(conn, schema, "00000000-0000-0000-0000-000000000000", ENTITY_ID,
                             scenario_id, "pytest-attacker")

    assert [s["scenario_id"] for s in list_scenarios(conn, schema, tenant_id, ENTITY_ID)] == [scenario_id]


def test_a_run_survives_its_scenario_being_archived(conn, tenant):
    """The reason this is an archive and not a DELETE. The run row is
    written directly here rather than via run_scenario: what is under test
    is the survival of the reference, not the projection arithmetic (that is
    tests/unit/test_forecasting_engine.py's job)."""
    tenant_id, schema = tenant
    scenario_id = create_scenario(conn, schema, tenant_id, ENTITY_ID, "ran once", "pytest-analyst", _drivers("0.16"))

    with conn.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{schema}".forecast_run '
            f'(scenario_id, tenant_id, entity_id, baseline_period_end, baseline_snapshot, computed_result, '
            f' gaps, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING run_id',
            (scenario_id, tenant_id, ENTITY_ID, "2026-03-31", json.dumps({"synthetic": True}),
             json.dumps({"synthetic": True, "years": []}), json.dumps([]), "pytest-analyst"),
        )
        run_id = cur.fetchone()[0]

    archive_scenario(conn, schema, tenant_id, ENTITY_ID, scenario_id, "pytest-analyst")

    run = get_run(conn, schema, tenant_id, ENTITY_ID, run_id)
    assert run["scenario_id"] == scenario_id, "an archived scenario must not orphan the run it produced"
    name, _drivers_back = get_scenario(conn, schema, tenant_id, ENTITY_ID, scenario_id, include_archived=True)
    assert name == "ran once", "the run's provenance must still resolve to a named assumption set"
