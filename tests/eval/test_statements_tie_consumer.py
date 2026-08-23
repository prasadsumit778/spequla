"""Sprint 2 acceptance criterion, consumer profile: the CM ladder ties to
the synthetic reference set and the balance sheet balances.
"""
from datetime import date
from decimal import Decimal

import pytest

from src.reports.balance_sheet import assemble_balance_sheet
from src.reports.pnl import assemble_consumer_cm_ladder
from src.ingest.calendar import month_end
from tests.helpers import ingest_consumer, run_and_freeze_mapping


@pytest.mark.eval
def test_consumer_cm_ladder_ties_and_balance_sheet_balances(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    data = ingest_consumer(conn, schema, tenant_id, entity_id)
    version_id, summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id, date(2025, 4, 1))

    assert freeze.passed, f"freeze gate failed: {freeze.reason}"
    # The consumer COA is small (23 ledgers) and every one of them has an
    # exact rule (src/mapping/rules.py) -- coverage should be at or near 100%.
    assert freeze.coverage_pct >= Decimal("0.98")

    period_start, period_end = data.months[0], month_end(data.months[-1])
    ladder = assemble_consumer_cm_ladder(conn, schema, tenant_id, entity_id, version_id, period_start, period_end)

    # -- Independent reference computed directly from the in-memory GL rows,
    # grouped by ledger name (not through the mapping engine under test).
    ref_gross = Decimal("0")
    ref_gst = Decimal("0")
    ref_discount = Decimal("0")
    ref_cogs = Decimal("0")             # includes marketplace commission borne, D-004
    ref_operating_cost = Decimal("0")   # fulfilment + servicing
    ref_marketing = Decimal("0")
    ref_overhead = Decimal("0")         # admin + employee

    channel_ledgers = {"Sales - Own Website", "Sales - Marketplace Amazon", "Sales - Marketplace Flipkart",
                         "Sales - Quick Commerce Blinkit", "Sales - Owned Retail"}
    for rows in data.gl_rows.values():
        for r in rows:
            name = r["account_name"]
            debit, credit = Decimal(r["debit"] or "0"), Decimal(r["credit"] or "0")
            if name in channel_ledgers:
                ref_gross += credit - debit
            elif name == "GST Output Payable":
                ref_gst += credit - debit
            elif name == "Discount Allowed":
                ref_discount += debit - credit
            elif name in ("COGS - Finished Goods", "Marketplace Commission Borne"):
                ref_cogs += debit - credit
            elif name in ("Fulfilment Cost", "Servicing Cost"):
                ref_operating_cost += debit - credit
            elif name == "Marketing & Advertising":
                ref_marketing += debit - credit
            elif name in ("Corporate Overhead", "Employee Cost", "Admin Expenses"):
                ref_overhead += debit - credit

    assert ladder.subtotals["gross_revenue"] == ref_gross
    assert ladder.lines["GST"] == ref_gst
    assert ladder.subtotals["gmv"] == ref_gross + ref_gst
    assert ladder.lines["Discount"] == ref_discount
    assert ladder.subtotals["net_revenue"] == ref_gross - ref_discount
    assert ladder.lines["Cost of goods sold"] == ref_cogs
    assert ladder.subtotals["gross_margin"] == (ref_gross - ref_discount) - ref_cogs
    assert ladder.lines["Operating cost"] == ref_operating_cost
    assert ladder.subtotals["cm1"] == ladder.subtotals["gross_margin"] - ref_operating_cost
    assert ladder.lines["Marketing"] == ref_marketing
    assert ladder.subtotals["cm2"] == ladder.subtotals["cm1"] - ref_marketing
    assert ladder.lines["Corporate overhead"] == ref_overhead
    assert ladder.subtotals["ebitda"] == ladder.subtotals["cm2"] - ref_overhead

    bs = assemble_balance_sheet(conn, schema, tenant_id, entity_id, version_id, period_end)
    assert bs.balances, (
        f"balance sheet does not balance: assets={bs.total_assets} "
        f"vs liabilities+equity={bs.total_liabilities_and_equity}"
    )
    assert bs.total_assets == bs.total_liabilities_and_equity
