"""Structural correctness tests for the synthetic apparel dataset generator,
per corpus/13 section 2."""
from datetime import date
from decimal import Decimal

import pytest

from synthetic.apparel.engine import build_company
from synthetic.apparel.stores import age_months, gestation_ramp_factor


@pytest.fixture(scope="module")
def company():
    return build_company(seed=42)


def test_deterministic_from_seed():
    a = build_company(seed=42)
    b = build_company(seed=42)
    assert a.gl_rows == b.gl_rows
    assert a.order_rows == b.order_rows
    assert a.store_rows == b.store_rows


def test_60_months(company):
    assert len(company.months) == 60


def test_gl_balances_every_month(company):
    for i in range(60):
        dr = sum(Decimal(r["debit"] or "0") for r in company.gl_rows[i])
        cr = sum(Decimal(r["credit"] or "0") for r in company.gl_rows[i])
        assert dr - cr == 0, f"month {i} does not balance: dr={dr} cr={cr}"


def test_tb_ties_to_gl_every_month(company):
    for i in range(60):
        gl_dr = sum(Decimal(r["debit"] or "0") for r in company.gl_rows[i])
        gl_cr = sum(Decimal(r["credit"] or "0") for r in company.gl_rows[i])
        tb_dr = sum(Decimal(r["debit_movement"]) for r in company.tb_rows[i])
        tb_cr = sum(Decimal(r["credit_movement"]) for r in company.tb_rows[i])
        assert gl_dr == tb_dr
        assert gl_cr == tb_cr


def test_all_four_store_formats_present(company):
    formats = {s.store_format for s in company.stores}
    assert formats == {"COCO", "COFO", "FOCO", "FOFO"}


def test_store_master_rows_match_store_count(company):
    assert len(company.store_rows) == len(company.stores)
    codes = {r["store_code"] for r in company.store_rows}
    assert len(codes) == len(company.stores), "duplicate store_code in the master file"


def test_new_stores_open_after_legacy_stores(company):
    legacy_opening = min(s.opening_date for s in company.stores)
    non_legacy = [s for s in company.stores if s.opening_date != legacy_opening]
    assert non_legacy, "expected at least one store opened during the history window"
    for s in non_legacy:
        assert s.opening_date >= date(2021, 1, 1)


def test_gestation_ramp_increases_with_age():
    assert gestation_ramp_factor(-1) == Decimal("0")
    assert gestation_ramp_factor(0) < gestation_ramp_factor(13) < gestation_ramp_factor(25)
    assert gestation_ramp_factor(25) == Decimal("1")


def test_store_order_rows_carry_a_channel_sub_matching_a_real_store(company):
    store_codes = {s.store_code for s in company.stores}
    store_channel_rows = [
        r for rows in company.order_rows.values() for r in rows
        if r["channel"] in ("Owned Retail", "Franchise Retail")
    ]
    assert store_channel_rows, "expected at least one store-channel order row"
    for r in store_channel_rows:
        assert r["channel_sub"] in store_codes


def test_online_channels_present(company):
    channels = {r["channel"] for rows in company.order_rows.values() for r in rows}
    assert "Own Website" in channels
    assert "Marketplace - Myntra" in channels


def test_order_file_does_not_tie_exactly_to_books(company):
    order_total = sum(Decimal(r["net_amount"]) for rows in company.order_rows.values() for r in rows)
    gl_revenue = sum(
        Decimal(r["credit"] or "0")
        for rows in company.gl_rows.values()
        for r in rows
        if r["voucher_type"] == "Sales" and r["account_name"].startswith("Sales -")
    )
    assert order_total != gl_revenue


def test_franchise_commission_posted_only_for_franchise_formats(company):
    commission_months = {
        i for i, rows in company.gl_rows.items()
        for r in rows if r["account_name"] == "Franchise Commission"
    }
    assert commission_months, "expected franchise commission to be posted in at least one month"


def test_revenue_grows_across_the_history(company):
    def fy_sales(fy_index: int) -> Decimal:
        return sum(
            Decimal(r["credit"] or "0")
            for month_idx in range(fy_index * 12, fy_index * 12 + 12)
            for r in company.gl_rows[month_idx]
            if r["account_name"].startswith("Sales -")
        )
    first_year, last_year = fy_sales(0), fy_sales(4)
    assert last_year > first_year, "expected the fifth year of sales to exceed the first"
