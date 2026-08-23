"""Structural correctness tests for the synthetic manufacturer generator.

Implements corpus/11 section 8's acceptance criterion "the synthetic dataset
regenerates deterministically from a seed," and proves the generator's own
internal correctness (GL balances, TB ties to GL) before any ingestion code
touches it, per the plan's verification section.
"""
from decimal import Decimal

import pytest

from synthetic.defects import DEFECTS
from synthetic.manufacturer.engine import build_company

DEFECT_TB_IMBALANCE_MONTH = 8


@pytest.fixture(scope="module")
def company():
    return build_company(seed=42)


def test_deterministic_from_seed():
    a = build_company(seed=42)
    b = build_company(seed=42)
    assert a.gl_rows == b.gl_rows
    assert a.sales_rows == b.sales_rows


def test_400_ledgers(company):
    assert len(company.coa) == 400


def test_36_months(company):
    assert len(company.months) == 36


def test_gl_balances_every_month_except_the_seeded_defect(company):
    for i in range(36):
        dr = sum(Decimal(r["debit"] or "0") for r in company.gl_rows[i])
        cr = sum(Decimal(r["credit"] or "0") for r in company.gl_rows[i])
        if i == DEFECT_TB_IMBALANCE_MONTH:
            assert dr - cr != 0, "defect #4 month should NOT balance"
        else:
            assert dr - cr == 0, f"month {i} does not balance: dr={dr} cr={cr}"


def test_tb_ties_to_gl_every_month(company):
    for i in range(36):
        gl_dr = sum(Decimal(r["debit"] or "0") for r in company.gl_rows[i])
        gl_cr = sum(Decimal(r["credit"] or "0") for r in company.gl_rows[i])
        tb_dr = sum(Decimal(r["debit_movement"]) for r in company.tb_rows[i])
        tb_cr = sum(Decimal(r["credit_movement"]) for r in company.tb_rows[i])
        assert gl_dr == tb_dr
        assert gl_cr == tb_cr


def test_all_thirteen_defects_present_except_consumer_only_one(company):
    logged = {e["defect_id"] for e in company.defect_log.entries}
    # Defect 12 (consumer line, zero COGS) belongs to the consumer dataset only.
    assert logged == {d.id for d in DEFECTS if d.id != 12}


def test_synthetic_labelled_company_name():
    from synthetic.manufacturer.profile import COMPANY_NAME
    assert "SYNTHETIC" in COMPANY_NAME
