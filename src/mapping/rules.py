"""The rule library.

Implements corpus/06 section 4 step 2 ("apply exact rules: known patterns
matched against a rule library that grows with every company") and section
4.1's derived_channel/derived_geo extraction from ledger names ("Sales -
Retail (Delhi)" carries a channel and a geography that exist nowhere else in
the source system, corpus/06 section 2).

This is exact-match only, per your instruction to build the mapping engine
without the AI proposal step (corpus/06 section 4 step 3) -- every rule here
is a literal, case-normalised match against a known ledger name, not a
pattern-guessing heuristic. It currently covers every material ledger in
both synthetic companies (see synthetic/manufacturer/coa.py and
synthetic/consumer/engine.py), because a real rule library is built by
reviewing a real chart of accounts once and it grows from there -- this is
that first review, done against the only charts of accounts that exist so
far. It deliberately does NOT cover the ~330 procedurally-generated tail
ledgers or the twelve corpus/11-seeded suspense ledgers in the manufacturer
dataset: per corpus/06 section 4.4, "ledger name is uninformative... proposed
as suspense.unmapped" is the CORRECT behaviour for that long tail, not a gap
to fill.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    source_account_name: str  # matched case-insensitively, whitespace-normalised
    canonical_class: str
    notes: str = ""


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).lower()


# --------------------------------------------------------------- manufacturer
_MANUFACTURER_RULES = [
    # Revenue
    Rule("Sales - Direct (North)", "revenue.product_sales"),
    Rule("SALES - DIRECT (SOUTH)", "revenue.product_sales"),
    Rule("Sales-Direct(East)", "revenue.product_sales"),
    Rule("Sales - Direct (West)", "revenue.product_sales"),
    Rule("Sales - Distributor (North)", "revenue.product_sales"),
    Rule("Sales - Distributor (South)", "revenue.product_sales"),
    Rule("sales - distributor (west)", "revenue.product_sales"),
    Rule("Export Sales - USA", "revenue.export_sales"),
    Rule("Export Sales - EU", "revenue.export_sales"),
    Rule("Sales - Retail (Delhi)", "revenue.product_sales"),
    Rule("Sales - Retail (Mumbai)", "revenue.product_sales"),
    Rule("Sales - New Region (Pune)", "revenue.product_sales", "defect #5: arrives mid-year"),
    Rule("Job Work Income", "revenue.job_work"),
    Rule("Scrap Sales", "revenue.scrap_sales"),
    Rule("Freight Recovered", "revenue.other_operating"),
    # Contra-revenue
    Rule("Sales Returns", "contra_revenue.sales_returns"),
    Rule("Trade Discount Allowed", "contra_revenue.trade_discount"),
    Rule("Rate Difference - Customers", "contra_revenue.rate_difference"),
    Rule("Cash Discount Allowed", "contra_revenue.cash_discount"),
    # COGS
    Rule("RM - HR Coil", "cogs.raw_material"),
    Rule("RM - CR Coil", "cogs.raw_material"),
    Rule("RM - Zinc Ingot", "cogs.raw_material"),
    Rule("Packing Material", "cogs.packing_material"),
    Rule("Stores & Consumables", "cogs.stores_consumables"),
    Rule("Direct Labour - Plant 1", "cogs.direct_labour"),
    Rule("Direct Labour - Plant 2", "cogs.direct_labour"),
    Rule("Power & Fuel", "cogs.power_fuel"),
    Rule("Job Work Charges Paid", "cogs.job_work_charges"),
    Rule("Freight Inward", "cogs.freight_inward"),
    Rule("Freight Outward", "cogs.freight_outward"),
    Rule("Absorption Variance", "cogs.absorption_variance", "JUDGEMENT CLASS"),
    # Opex
    Rule("Salary & Wages - Admin", "opex.employee_cost"),
    Rule("Rent - Corporate Office", "opex.rent"),
    Rule("Repairs & Maintenance", "opex.repairs_maintenance"),
    Rule("Travelling Expenses", "opex.travel"),
    Rule("Professional Fees", "opex.professional_fees"),
    Rule("Marketing & Advertising", "opex.marketing_advertising"),
    Rule("Selling & Distribution Exp", "opex.selling_distribution"),
    Rule("Administrative Expenses", "opex.admin_general"),
    Rule("Insurance", "opex.insurance"),
    Rule("Rates & Taxes", "opex.rates_taxes"),
    Rule("Provision for Bad Debts", "opex.provision_baddebt"),
    Rule("CSR Expenses", "opex.csr_donation"),
    Rule("Director Remuneration", "opex.owner_remuneration", "JUDGEMENT CLASS"),
    Rule("Rent Paid - Related Party", "opex.related_party_charges", "JUDGEMENT CLASS"),
    # Below EBITDA
    Rule("Depreciation", "da.depreciation"),
    Rule("Interest - Term Loan", "finance_cost.interest_debt"),
    Rule("Interest - Cash Credit", "finance_cost.interest_debt"),
    Rule("Bank Charges", "finance_cost.bank_charges"),
    Rule("Interest Income", "other_income.interest_income"),
    Rule("Foreign Exchange Gain", "other_income.fx_gain"),
    Rule("Provision for Tax", "tax.current"),
    # Balance sheet
    Rule("Cash and Bank - HDFC Current A/c", "asset.cash_bank"),
    Rule("Cash and Bank - ICICI Current A/c", "asset.cash_bank"),
    Rule("Cash in Hand", "asset.cash_bank"),
    Rule("Sundry Debtors", "asset.trade_receivable"),
    Rule("Raw Material Stock", "asset.inventory_rm"),
    Rule("WIP Stock", "asset.inventory_wip"),
    Rule("Finished Goods Stock", "asset.inventory_fg"),
    Rule("Packing Material Stock", "asset.inventory_packing_stores"),
    Rule("Advance to Suppliers", "asset.advance_supplier"),
    Rule("Prepaid Expenses", "asset.prepaid"),
    Rule("GST Input Credit", "asset.statutory_receivable"),
    Rule("Gross Block - Plant & Machinery", "asset.fixed_asset_gross"),
    Rule("Accumulated Depreciation", "asset.accumulated_depreciation"),
    Rule("Capital WIP", "asset.capital_wip"),
    Rule("Sundry Creditors", "liability.trade_payable"),
    Rule("Advance from Customers", "liability.advance_customer"),
    Rule("GST Output Payable", "liability.statutory_payable"),
    Rule("TDS Payable", "liability.statutory_payable"),
    Rule("Salary Payable", "liability.employee_payable"),
    Rule("Provisions", "liability.provision"),
    Rule("Term Loan - Bank", "liability.debt_term"),
    Rule("Cash Credit - Bank", "liability.debt_working_capital"),
    Rule("Unsecured Loan - Director", "liability.debt_related_party", "JUDGEMENT CLASS"),
    Rule("Share Capital", "equity.share_capital"),
    Rule("Reserves & Surplus", "equity.reserves"),
]

# ------------------------------------------------------------------- consumer
# Taxonomy notes: corpus/06 section 3's classes were built with a
# manufacturing bias and do not have a dedicated "cost of finished goods
# resold" or "servicing cost" class -- corpus/06 itself is explicit that the
# taxonomy is "PROVISIONAL, version 0" and will need classes added once a
# real chart of accounts is seen (section 3 preamble). Rather than invent a
# new canonical class (which CLAUDE.md section 3.1 forbids), these two use
# the closest existing class, noted below. "Corporate Overhead" and "Admin
# Expenses" both map to opex.admin_general deliberately -- corpus/05a's own
# corporate_overhead contract defines it as the SUM of opex.admin_general
# (plus professional_fees/insurance/rates_taxes), so collapsing both ledgers
# into that one class and presenting their sum as "Corporate overhead" in the
# consumer statement (src/reports/statement_lines.py) is exactly what the
# metric contract already specifies, not an approximation.
_CONSUMER_RULES = [
    Rule("Sales - Own Website", "revenue.product_sales"),
    Rule("Sales - Marketplace Amazon", "revenue.product_sales"),
    Rule("Sales - Marketplace Flipkart", "revenue.product_sales"),
    Rule("Sales - Quick Commerce Blinkit", "revenue.product_sales"),
    Rule("Sales - Owned Retail", "revenue.product_sales"),
    Rule("Sales Returns", "contra_revenue.sales_returns"),
    Rule("Discount Allowed", "contra_revenue.trade_discount"),
    Rule("COGS - Finished Goods", "cogs.raw_material",
          "Closest existing class for 'cost of finished goods resold' -- corpus/06 has no dedicated "
          "trading-COGS class; see module docstring"),
    Rule("Fulfilment Cost", "cogs.fulfilment"),
    Rule("Servicing Cost", "opex.selling_distribution",
          "Closest existing class -- corpus/06 has no dedicated 'servicing' class despite corpus/05a's "
          "operating_cost_cm1 contract naming servicing_cost as a declared CM1 cost; see module docstring"),
    Rule("Marketplace Commission Borne", "contra_revenue.commission_marketplace",
          "D-004 resolved: commission borne is a cost above gross profit, i.e. COGS-side, not a CM1/marketing item"),
    Rule("Marketing & Advertising", "opex.marketing_advertising"),
    Rule("Corporate Overhead", "opex.admin_general"),
    Rule("Employee Cost", "opex.employee_cost"),
    Rule("Admin Expenses", "opex.admin_general"),
    Rule("Cash and Bank - Current A/c", "asset.cash_bank"),
    Rule("Sundry Debtors", "asset.trade_receivable"),
    Rule("Inventory - Finished Goods", "asset.inventory_fg"),
    Rule("GST Input Credit", "asset.statutory_receivable"),
    Rule("Sundry Creditors", "liability.trade_payable"),
    Rule("GST Output Payable", "liability.statutory_payable"),
    Rule("Marketplace Payable", "liability.trade_payable"),
    Rule("Share Capital", "equity.share_capital"),
    Rule("Reserves & Surplus", "equity.reserves"),
]

def _build_rule_index(rules: list[Rule]) -> dict[str, Rule]:
    """Both synthetic companies happen to share some generic ledger names
    (e.g. 'Sundry Debtors', 'Share Capital') -- that's expected, not a
    collision, as long as they resolve to the same class. A genuine conflict
    (same normalised name, different class) is a real rule-library bug and
    fails loudly rather than silently picking one."""
    index: dict[str, Rule] = {}
    for rule in rules:
        key = _norm(rule.source_account_name)
        if key in index and index[key].canonical_class != rule.canonical_class:
            raise RuntimeError(
                f"conflicting rules for ledger name {rule.source_account_name!r}: "
                f"{index[key].canonical_class!r} vs {rule.canonical_class!r}"
            )
        index[key] = rule
    return index


ALL_RULES: dict[str, Rule] = _build_rule_index(_MANUFACTURER_RULES + _CONSUMER_RULES)


def match_exact_rule(source_account_name: str) -> Rule | None:
    return ALL_RULES.get(_norm(source_account_name))


# ------------------------------------------------------- channel/geo extraction
_CHANNEL_KEYWORDS = {
    "direct": "direct", "distributor": "distributor", "retail": "retail",
    "export": "export", "new region": "direct",
}
_BRACKET_RE = re.compile(r"\(([^)]+)\)\s*$")


def extract_channel_geo(source_account_name: str) -> tuple[str | None, str | None]:
    """'Sales - Retail (Delhi)' -> ('retail', 'Delhi'), per corpus/06 section 2's
    worked example. Returns (None, None) where the ledger name carries neither."""
    name_lower = source_account_name.lower()
    channel = next((v for k, v in _CHANNEL_KEYWORDS.items() if k in name_lower), None)

    geo = None
    m = _BRACKET_RE.search(source_account_name)
    if m:
        geo = m.group(1).strip()
    elif "(" in source_account_name and ")" in source_account_name:
        # Handles the no-space variant, e.g. "Sales-Direct(East)".
        m2 = re.search(r"\(([^)]+)\)", source_account_name)
        if m2:
            geo = m2.group(1).strip()

    return channel, geo
