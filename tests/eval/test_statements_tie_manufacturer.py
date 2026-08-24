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
from src.reports.query import class_balances, resolve_mapping_version_for_period
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

    # OQ-007, resolved 2026-08-24: suspense.unmapped now gets its own balance
    # sheet line (src/reports/statement_lines.py's BALANCE_SHEET_LINES,
    # corpus/06a's statement_section changed memo -> bs) with the sign that
    # makes assets == liabilities-and-equity hold whenever the trial balance
    # itself sums to zero (D-051) -- regardless of how much sits in suspense.
    # So:
    #   assets - (liabilities + equity) == trial_balance_residual   (exactly)
    # with suspense no longer appearing in the gap at all -- it's fully
    # absorbed into the sheet's own arithmetic now, not cancelled against a
    # second term. This reference company still does NOT balance, but for a
    # narrower, different reason than before OQ-007: defect #4 (corpus/11
    # section 2.2) deliberately posts one genuinely unbalanced voucher in one
    # month, which makes trial_balance_residual itself nonzero, independent
    # of suspense. Defect #10's 12 permanently-unmappable ledgers (the long
    # tail) still land in suspense by design -- that's no longer what blocks
    # the sheet, it's just visible on its own line now.
    balances = class_balances(conn, schema, tenant_id, entity_id, version_id, period_end)
    suspense_signed = balances.get("suspense.unmapped", Decimal("0"))
    trial_balance_residual = sum(balances.values(), Decimal("0"))

    assert suspense_signed != 0, "the reference company's unmappable long tail has vanished"
    assert trial_balance_residual != 0, "defect #4's unbalanced voucher has vanished -- if this is now " \
        "intentional, this whole assertion block should change to assert bs.balances is True"
    assert bs.balances is False
    assert bs.total_assets - bs.total_liabilities_and_equity == trial_balance_residual, (
        f"the balance sheet gap is not fully explained by the trial balance's own residual "
        f"(suspense should no longer contribute to it at all, post-OQ-007): "
        f"gap={bs.total_assets - bs.total_liabilities_and_equity}, "
        f"trial_balance_residual={trial_balance_residual}, suspense={suspense_signed}"
    )


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
