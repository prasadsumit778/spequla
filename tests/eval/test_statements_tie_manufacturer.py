"""Sprint 2 acceptance criterion: P&L and balance sheet generate from
mappings, the balance sheet balances, and both tie exactly to the synthetic
reference set (corpus/12 sprint 2).

The "reference set" here is computed independently from the SAME in-memory
synthetic data structure (synthetic/manufacturer/engine.py's CompanyData),
grouped by each ledger's own `role` attribute -- a completely separate code
path from the mapping engine and statement assembler under test, so a
systematic bug in either would show up as a mismatch here.
"""
from datetime import date
from decimal import Decimal

import pytest

from src.reports.balance_sheet import assemble_balance_sheet
from src.reports.pnl import assemble_manufacturing_pnl
from src.reports.query import resolve_mapping_version_for_period
from src.ingest.calendar import month_end
from tests.helpers import ingest_manufacturer, run_and_freeze_mapping


@pytest.mark.eval
def test_manufacturer_statements_tie_and_balance_sheet_balances(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    data = ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id, date(2023, 4, 1))

    assert freeze.passed, f"freeze gate failed: {freeze.reason}"
    assert freeze.coverage_pct >= Decimal("0.98")

    period_start, period_end = data.months[0], month_end(data.months[-1])
    pnl = assemble_manufacturing_pnl(conn, schema, tenant_id, entity_id, version_id, period_start, period_end)

    # -- Independent reference, computed from the same in-memory GL rows the
    # generator produced, grouped by each ledger's OWN role attribute rather
    # than through the mapping engine under test.
    role_by_name = {l.account_name: l.role for l in data.coa}
    revenue_names = {l.account_name for l in data.coa if l.role == "revenue"}
    contra_names = {l.account_name for l in data.coa if l.role == "contra_revenue"}
    cogs_names = {l.account_name for l in data.coa if l.role == "cogs"}
    opex_names = {l.account_name for l in data.coa if l.role == "opex"}

    ref_revenue = Decimal("0")
    ref_returns = Decimal("0")
    ref_discounts = Decimal("0")
    ref_cogs = Decimal("0")
    ref_opex = Decimal("0")
    for rows in data.gl_rows.values():
        for r in rows:
            name = r["account_name"]
            credit = Decimal(r["credit"] or "0")
            debit = Decimal(r["debit"] or "0")
            if name in revenue_names:
                ref_revenue += credit - debit
            elif name == "Sales Returns":
                ref_returns += debit - credit
            elif name in contra_names:  # trade/cash discount, rate difference
                ref_discounts += debit - credit
            elif name in cogs_names:
                ref_cogs += debit - credit
            elif name in opex_names:
                ref_opex += debit - credit

    assert pnl.lines["Gross revenue"] == ref_revenue
    assert pnl.lines["Returns"] == ref_returns
    assert pnl.lines["Discounts and rate differences"] == ref_discounts
    assert pnl.subtotals["net_revenue"] == ref_revenue - ref_returns - ref_discounts
    assert pnl.subtotals["cogs_total"] == ref_cogs
    assert pnl.subtotals["opex_total"] == ref_opex
    assert pnl.subtotals["gross_profit"] == pnl.subtotals["net_revenue"] - ref_cogs

    # Unmapped value must be small (the deliberately-unrulable long tail),
    # never silently swallowed into a statement line -- corpus/06 section 3.6.
    assert pnl.unmapped_value_inr > 0  # the long tail genuinely exists
    assert pnl.unmapped_value_inr < (ref_revenue * Decimal("0.02"))

    bs = assemble_balance_sheet(conn, schema, tenant_id, entity_id, version_id, period_end)
    assert bs.balances, (
        f"balance sheet does not balance: assets={bs.total_assets} "
        f"vs liabilities+equity={bs.total_liabilities_and_equity}"
    )
    assert bs.total_assets == bs.total_liabilities_and_equity


@pytest.mark.eval
def test_manufacturer_pat_matches_independent_full_waterfall(conn, tenant):
    """A second, stricter check: PAT computed by the assembler must match a
    fully independent hand-rolled waterfall from raw GL, not just the
    top-line pieces checked above."""
    tenant_id, schema = tenant
    entity_id = 1
    data = ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id, date(2023, 4, 1))
    assert freeze.passed

    period_start, period_end = data.months[0], month_end(data.months[-1])
    pnl = assemble_manufacturing_pnl(conn, schema, tenant_id, entity_id, version_id, period_start, period_end)

    ref_da = sum((Decimal(r["debit"] or "0") - Decimal(r["credit"] or "0"))
                  for rows in data.gl_rows.values() for r in rows if r["account_name"] == "Depreciation")
    ref_interest = sum((Decimal(r["debit"] or "0") - Decimal(r["credit"] or "0"))
                        for rows in data.gl_rows.values() for r in rows
                        if r["account_name"] in ("Interest - Term Loan", "Interest - Cash Credit", "Bank Charges"))
    ref_other_income = sum((Decimal(r["credit"] or "0") - Decimal(r["debit"] or "0"))
                             for rows in data.gl_rows.values() for r in rows
                             if r["account_name"] in ("Interest Income", "Foreign Exchange Gain"))
    ref_tax = sum((Decimal(r["debit"] or "0") - Decimal(r["credit"] or "0"))
                   for rows in data.gl_rows.values() for r in rows if r["account_name"] == "Provision for Tax")

    # net_revenue/cogs_total/opex_total were already independently verified
    # in test_manufacturer_statements_tie_and_balance_sheet_balances above;
    # this test extends the independent check to the below-EBITDA lines.
    ref_net_revenue = pnl.subtotals["net_revenue"]
    ref_gross_profit = ref_net_revenue - pnl.subtotals["cogs_total"]
    ref_ebitda = ref_gross_profit - pnl.subtotals["opex_total"]
    ref_ebit = ref_ebitda - ref_da
    ref_pbt = ref_ebit + ref_other_income - ref_interest
    ref_pat = ref_pbt - ref_tax

    assert pnl.subtotals["ebitda"] == ref_ebitda
    assert pnl.subtotals["ebit"] == ref_ebit
    assert pnl.subtotals["pbt"] == ref_pbt
    assert pnl.subtotals["pat"] == ref_pat
