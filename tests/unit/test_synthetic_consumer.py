"""Structural correctness tests for the synthetic consumer dataset generator,
per corpus/11 section 2.3."""
from decimal import Decimal

import pytest

from synthetic.consumer.engine import build_consumer_company


@pytest.fixture(scope="module")
def company():
    return build_consumer_company(seed=42)


def test_deterministic_from_seed():
    a = build_consumer_company(seed=42)
    b = build_consumer_company(seed=42)
    assert a.gl_rows == b.gl_rows
    assert a.order_rows == b.order_rows


def test_12_months(company):
    assert len(company.months) == 12


def test_gl_balances_every_month(company):
    for i in range(12):
        dr = sum(Decimal(r["debit"] or "0") for r in company.gl_rows[i])
        cr = sum(Decimal(r["credit"] or "0") for r in company.gl_rows[i])
        assert dr - cr == 0, f"month {i} does not balance: dr={dr} cr={cr}"


def test_tb_ties_to_gl_every_month(company):
    for i in range(12):
        gl_dr = sum(Decimal(r["debit"] or "0") for r in company.gl_rows[i])
        gl_cr = sum(Decimal(r["credit"] or "0") for r in company.gl_rows[i])
        tb_dr = sum(Decimal(r["debit_movement"]) for r in company.tb_rows[i])
        tb_cr = sum(Decimal(r["credit_movement"]) for r in company.tb_rows[i])
        assert gl_dr == tb_dr
        assert gl_cr == tb_cr


def test_both_revenue_models_present(company):
    channels = {r["channel"] for rows in company.order_rows.values() for r in rows}
    assert "Own Website" in channels          # buyout
    assert "Marketplace - Amazon" in channels  # marketplace


def test_returns_arrive_in_a_later_period_than_the_sale(company):
    from datetime import date
    found = False
    for rows in company.order_rows.values():
        for r in rows:
            if r["return_flag"] == "Yes":
                order_d = date.fromisoformat(r["order_date"])
                return_d = date.fromisoformat(r["return_date"])
                assert return_d > order_d
                if (return_d.year, return_d.month) != (order_d.year, order_d.month):
                    found = True
    assert found, "expected at least one return crossing into a later calendar month"


def test_order_file_does_not_tie_exactly_to_books(company):
    order_total = sum(Decimal(r["net_amount"]) for rows in company.order_rows.values() for r in rows)
    gl_revenue = sum(
        Decimal(r["credit"] or "0")
        for rows in company.gl_rows.values()
        for r in rows
        if r["voucher_type"] == "Sales" and r["account_name"].startswith("Sales -")
    )
    assert order_total != gl_revenue


def test_defect_12_zero_cogs_logged(company):
    assert any(e["defect_id"] == 12 for e in company.defect_log.entries)
