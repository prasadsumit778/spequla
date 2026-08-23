"""Canonical class -> presentation line, per profile.

Implements corpus/08 section 4.2 (manufacturing) verbatim row order, and the
consumer CM ladder's non-generic rungs (corpus/08 section 4.1) which need
their own assembly logic in pnl.py rather than a straight group-by, because
GMV and GST are computed from the SAME underlying flow (see pnl.py).

Sign per line follows corpus/03 section 1: revenue and income are stored
positive on the statement even though fact_gl_entry stores credits negative
("the statement layout applies the sign, not the data") -- REVENUE_SIGN
below is where that flip happens, once, so no assembly function repeats it.
"""
from __future__ import annotations

REVENUE_SIGN = -1  # flips fact_gl_entry's credit-negative into statement-positive
COST_SIGN = 1       # costs are already debit-positive; shown as-is, subtracted by the assembler

# ---------------------------------------------------------- manufacturing P&L
# (presentation_line, sign, ordinal) -- ordinal only controls display order
# within a section, per corpus/08 section 4.2's row order.
MANUFACTURING_PNL_LINES: dict[str, tuple[str, int, int]] = {
    "revenue.product_sales": ("Gross revenue", REVENUE_SIGN, 1),
    "revenue.service_income": ("Gross revenue", REVENUE_SIGN, 1),
    "revenue.job_work": ("Gross revenue", REVENUE_SIGN, 1),
    "revenue.export_sales": ("Gross revenue", REVENUE_SIGN, 1),
    "revenue.scrap_sales": ("Gross revenue", REVENUE_SIGN, 1),
    "revenue.other_operating": ("Gross revenue", REVENUE_SIGN, 1),
    "contra_revenue.sales_returns": ("Returns", COST_SIGN, 2),
    "contra_revenue.trade_discount": ("Discounts and rate differences", COST_SIGN, 3),
    "contra_revenue.cash_discount": ("Discounts and rate differences", COST_SIGN, 3),
    "contra_revenue.rate_difference": ("Discounts and rate differences", COST_SIGN, 3),
    "cogs.raw_material": ("Raw material", COST_SIGN, 10),
    "cogs.packing_material": ("Packing material", COST_SIGN, 11),
    "cogs.direct_labour": ("Direct labour", COST_SIGN, 12),
    "cogs.power_fuel": ("Power and fuel", COST_SIGN, 13),
    "cogs.freight_inward": ("Freight", COST_SIGN, 14),
    "cogs.freight_outward": ("Freight", COST_SIGN, 14),
    "cogs.stores_consumables": ("Other direct cost", COST_SIGN, 15),
    "cogs.job_work_charges": ("Other direct cost", COST_SIGN, 15),
    "cogs.payment_fees": ("Other direct cost", COST_SIGN, 15),
    "cogs.stock_adjustment": ("Other direct cost", COST_SIGN, 15),
    "cogs.fulfilment": ("Other direct cost", COST_SIGN, 15),
    "cogs.absorption_variance": ("Absorption variance", COST_SIGN, 16),
    "opex.employee_cost": ("Employee cost", COST_SIGN, 20),
    "opex.marketing_advertising": ("Marketing and advertising", COST_SIGN, 21),
    "opex.selling_distribution": ("Selling and distribution", COST_SIGN, 22),
    "opex.rent": ("Rent", COST_SIGN, 23),
    "opex.repairs_maintenance": ("Repairs and maintenance", COST_SIGN, 24),
    "opex.professional_fees": ("Professional fees", COST_SIGN, 25),
    "opex.travel": ("Travel", COST_SIGN, 26),
    "opex.admin_general": ("Administration and general", COST_SIGN, 27),
    "opex.owner_remuneration": ("Owner remuneration", COST_SIGN, 28),
    "opex.related_party_charges": ("Related party charges", COST_SIGN, 29),
    "opex.insurance": ("Other", COST_SIGN, 30),
    "opex.rates_taxes": ("Other", COST_SIGN, 30),
    "opex.provision_baddebt": ("Other", COST_SIGN, 30),
    "opex.csr_donation": ("Other", COST_SIGN, 30),
    "opex.other": ("Other", COST_SIGN, 30),
    "contra_revenue.scheme_rebate": ("Other", COST_SIGN, 30),  # D-003: treated as opex
    "da.depreciation": ("Depreciation and amortisation", COST_SIGN, 40),
    "da.amortisation": ("Depreciation and amortisation", COST_SIGN, 40),
    "other_income.interest_income": ("Other income", REVENUE_SIGN, 41),
    "other_income.fx_gain": ("Other income", REVENUE_SIGN, 41),
    "other_income.misc_income": ("Other income", REVENUE_SIGN, 41),
    "finance_cost.interest_debt": ("Finance cost", COST_SIGN, 42),
    "finance_cost.bank_charges": ("Finance cost", COST_SIGN, 42),
    "finance_cost.interest_other": ("Finance cost", COST_SIGN, 42),
    "tax.current": ("Tax", COST_SIGN, 43),
    "tax.deferred": ("Tax", COST_SIGN, 43),
}

# Which presentation lines make up which section of the layout, in order,
# per corpus/08 section 4.2's exact row sequence.
MANUFACTURING_SECTIONS = {
    "revenue": ["Gross revenue", "Returns", "Discounts and rate differences"],
    "cogs": ["Raw material", "Packing material", "Direct labour", "Power and fuel",
              "Freight", "Other direct cost", "Absorption variance"],
    "opex": ["Employee cost", "Marketing and advertising", "Selling and distribution", "Rent",
              "Repairs and maintenance", "Professional fees", "Travel", "Administration and general",
              "Owner remuneration", "Related party charges", "Other"],
    "below_ebitda": ["Depreciation and amortisation"],
    "below_ebit": ["Other income", "Finance cost"],
    "below_pbt": ["Tax"],
}

# --------------------------------------------------------------- balance sheet
# STANDARD textbook current/non-current classification (not a corpus-declared
# convention -- corpus/08 section 5 requires the grouping but does not
# enumerate which class is which). Does not affect whether the balance sheet
# balances, only how it's grouped for presentation.
BALANCE_SHEET_LINES: dict[str, tuple[str, str, int]] = {
    # (group, label, sign) -- assets positive, liabilities/equity negative in
    # raw storage per corpus/03 section 1; sign here flips to presentation-positive.
    "asset.cash_bank": ("current_assets", "Cash and bank", COST_SIGN),
    "asset.cash_restricted": ("current_assets", "Restricted cash", COST_SIGN),
    "asset.trade_receivable": ("current_assets", "Trade receivables", COST_SIGN),
    "asset.inventory_rm": ("current_assets", "Inventory", COST_SIGN),
    "asset.inventory_wip": ("current_assets", "Inventory", COST_SIGN),
    "asset.inventory_fg": ("current_assets", "Inventory", COST_SIGN),
    "asset.inventory_packing_stores": ("current_assets", "Inventory", COST_SIGN),
    "asset.advance_supplier": ("current_assets", "Other current assets", COST_SIGN),
    "asset.prepaid": ("current_assets", "Other current assets", COST_SIGN),
    "asset.statutory_receivable": ("current_assets", "Other current assets", COST_SIGN),
    "asset.loans_advances": ("current_assets", "Other current assets", COST_SIGN),
    "asset.deposit": ("non_current_assets", "Deposits", COST_SIGN),
    "asset.investment": ("non_current_assets", "Investments", COST_SIGN),
    "asset.fixed_asset_gross": ("non_current_assets", "Fixed assets, net", COST_SIGN),
    # Contra-asset: a natural CREDIT balance (negative amount_base), same
    # direction as fact_gl_entry already stores it -- COST_SIGN (no flip) is
    # correct here specifically so it nets AGAINST fixed_asset_gross's
    # positive balance instead of adding to it.
    "asset.accumulated_depreciation": ("non_current_assets", "Fixed assets, net", COST_SIGN),
    "asset.capital_wip": ("non_current_assets", "Capital work in progress", COST_SIGN),
    "liability.trade_payable": ("current_liabilities", "Trade payables", REVENUE_SIGN),
    "liability.advance_customer": ("current_liabilities", "Other current liabilities", REVENUE_SIGN),
    "liability.statutory_payable": ("current_liabilities", "Other current liabilities", REVENUE_SIGN),
    "liability.employee_payable": ("current_liabilities", "Other current liabilities", REVENUE_SIGN),
    "liability.provision": ("current_liabilities", "Other current liabilities", REVENUE_SIGN),
    "liability.debt_working_capital": ("current_liabilities", "Debt", REVENUE_SIGN),
    "liability.debt_current_maturity": ("current_liabilities", "Debt", REVENUE_SIGN),
    "liability.bill_discounting": ("current_liabilities", "Debt", REVENUE_SIGN),
    "liability.debt_term": ("non_current_liabilities", "Debt", REVENUE_SIGN),
    "liability.debt_related_party": ("non_current_liabilities", "Debt", REVENUE_SIGN),
    "liability.lease": ("non_current_liabilities", "Debt", REVENUE_SIGN),
    "liability.other_current": ("current_liabilities", "Other current liabilities", REVENUE_SIGN),
    "equity.share_capital": ("equity", "Share capital", REVENUE_SIGN),
    "equity.reserves": ("equity", "Reserves and surplus", REVENUE_SIGN),
}

# ------------------------------------------------------------ consumer ladder
# Which canonical classes feed which rung of corpus/08 section 4.1's ladder.
# GMV and GST are NOT simple group-by targets -- see pnl.assemble_consumer_cm_ladder.
CONSUMER_GROSS_REVENUE_CLASSES = ["revenue.product_sales"]
CONSUMER_GST_CLASSES = ["liability.statutory_payable"]  # this company's only statutory-payable ledger is GST Output
CONSUMER_DISCOUNT_CLASSES = ["contra_revenue.trade_discount"]
CONSUMER_COGS_CLASSES = ["cogs.raw_material", "contra_revenue.commission_marketplace"]  # D-004: commission borne is COGS-side
CONSUMER_OPERATING_COST_CM1_CLASSES = ["cogs.fulfilment", "opex.selling_distribution"]
CONSUMER_MARKETING_CLASSES = ["opex.marketing_advertising"]
CONSUMER_CORPORATE_OVERHEAD_CLASSES = ["opex.admin_general", "opex.employee_cost"]
