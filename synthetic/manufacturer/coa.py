"""Chart of accounts generator for the synthetic manufacturer.

Implements corpus/11 section 2.1: "Around 400 ledgers... free text,
inconsistent casing, embedded channel and geography in brackets,
abbreviations, a handful of ledgers named things like 'Misc 3'... around 40
ledgers carrying the great majority of value, a long tail carrying almost
none." Also seeds defect #5 (a ledger appearing mid-year with large value),
defect #10 (twelve ledgers fitting no canonical class), per
synthetic/defects.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from synthetic.common import Rng

# (source_account_name, parent_group, account_type, canonical_class-ish role)
# These ~85 ledgers are the "material" ones -- roughly 40 of them will carry
# the great majority of value once amounts are posted; the rest of the ~400
# is a procedurally generated long tail of near-zero ledgers.
REVENUE_LEDGERS = [
    ("Sales - Direct (North)", "Sales Accounts", "Income"),
    ("SALES - DIRECT (SOUTH)", "Sales Accounts", "Income"),
    ("Sales-Direct(East)", "Sales Accounts", "Income"),
    ("Sales - Direct (West)", "Sales Accounts", "Income"),
    ("Sales - Distributor (North)", "Sales Accounts", "Income"),
    ("Sales - Distributor (South)", "Sales Accounts", "Income"),
    ("sales - distributor (west)", "Sales Accounts", "Income"),
    ("Export Sales - USA", "Sales Accounts", "Income"),
    ("Export Sales - EU", "Sales Accounts", "Income"),
    ("Sales - Retail (Delhi)", "Sales Accounts", "Income"),
    ("Sales - Retail (Mumbai)", "Sales Accounts", "Income"),
    ("Job Work Income", "Sales Accounts", "Income"),
    ("Scrap Sales", "Sales Accounts", "Income"),
    ("Freight Recovered", "Sales Accounts", "Income"),
]
CONTRA_REVENUE_LEDGERS = [
    ("Sales Returns", "Sales Accounts", "Income"),
    ("Trade Discount Allowed", "Sales Accounts", "Income"),
    ("Rate Difference - Customers", "Sales Accounts", "Income"),
    ("Cash Discount Allowed", "Sales Accounts", "Income"),
]
COGS_LEDGERS = [
    ("RM - HR Coil", "Direct Materials", "Expense"),
    ("RM - CR Coil", "Direct Materials", "Expense"),
    ("RM - Zinc Ingot", "Direct Materials", "Expense"),
    ("Packing Material", "Direct Materials", "Expense"),
    ("Stores & Consumables", "Factory Expenses", "Expense"),
    ("Direct Labour - Plant 1", "Factory Expenses", "Expense"),
    ("Direct Labour - Plant 2", "Factory Expenses", "Expense"),
    ("Power & Fuel", "Factory Expenses", "Expense"),
    ("Job Work Charges Paid", "Factory Expenses", "Expense"),
    ("Freight Inward", "Factory Expenses", "Expense"),
    ("Freight Outward", "Selling Expenses", "Expense"),
    ("Absorption Variance", "Factory Expenses", "Expense"),
]
OPEX_LEDGERS = [
    ("Salary & Wages - Admin", "Indirect Expenses", "Expense"),
    ("Rent - Corporate Office", "Indirect Expenses", "Expense"),
    ("Repairs & Maintenance", "Indirect Expenses", "Expense"),
    ("Travelling Expenses", "Indirect Expenses", "Expense"),
    ("Professional Fees", "Indirect Expenses", "Expense"),
    ("Marketing & Advertising", "Indirect Expenses", "Expense"),
    ("Selling & Distribution Exp", "Indirect Expenses", "Expense"),
    ("Administrative Expenses", "Indirect Expenses", "Expense"),
    ("Insurance", "Indirect Expenses", "Expense"),
    ("Rates & Taxes", "Indirect Expenses", "Expense"),
    ("Provision for Bad Debts", "Indirect Expenses", "Expense"),
    ("CSR Expenses", "Indirect Expenses", "Expense"),
    ("Director Remuneration", "Indirect Expenses", "Expense"),
    ("Rent Paid - Related Party", "Indirect Expenses", "Expense"),
]
BELOW_EBITDA_LEDGERS = [
    ("Depreciation", "Depreciation", "Expense"),
    ("Interest - Term Loan", "Finance Costs", "Expense"),
    ("Interest - Cash Credit", "Finance Costs", "Expense"),
    ("Bank Charges", "Finance Costs", "Expense"),
    ("Interest Income", "Indirect Income", "Income"),
    ("Foreign Exchange Gain", "Indirect Income", "Income"),
    ("Provision for Tax", "Duties & Taxes", "Expense"),
]
BS_LEDGERS = [
    ("Cash and Bank - HDFC Current A/c", "Bank Accounts", "Asset"),
    ("Cash and Bank - ICICI Current A/c", "Bank Accounts", "Asset"),
    ("Cash in Hand", "Cash-in-Hand", "Asset"),
    ("Sundry Debtors", "Sundry Debtors", "Asset"),
    ("Raw Material Stock", "Stock-in-Hand", "Asset"),
    ("WIP Stock", "Stock-in-Hand", "Asset"),
    ("Finished Goods Stock", "Stock-in-Hand", "Asset"),
    ("Packing Material Stock", "Stock-in-Hand", "Asset"),
    ("Advance to Suppliers", "Loans & Advances (Asset)", "Asset"),
    ("Prepaid Expenses", "Current Assets", "Asset"),
    ("GST Input Credit", "Duties & Taxes", "Asset"),
    ("Gross Block - Plant & Machinery", "Fixed Assets", "Asset"),
    ("Accumulated Depreciation", "Fixed Assets", "Asset"),
    ("Capital WIP", "Fixed Assets", "Asset"),
    ("Sundry Creditors", "Sundry Creditors", "Liability"),
    ("Advance from Customers", "Current Liabilities", "Liability"),
    ("GST Output Payable", "Duties & Taxes", "Liability"),
    ("TDS Payable", "Duties & Taxes", "Liability"),
    ("Salary Payable", "Current Liabilities", "Liability"),
    ("Provisions", "Current Liabilities", "Liability"),
    ("Term Loan - Bank", "Secured Loans", "Liability"),
    ("Cash Credit - Bank", "Secured Loans", "Liability"),
    ("Unsecured Loan - Director", "Unsecured Loans", "Liability"),
    ("Share Capital", "Capital Account", "Equity"),
    ("Reserves & Surplus", "Capital Account", "Equity"),
]

TAIL_PREFIXES = [
    "Misc", "Sundry Exp", "Office Exp", "Freight Petty", "Bank Charges Petty",
    "Courier Exp", "Stationery", "Vehicle Running", "Local Conveyance",
    "Business Promotion", "Water Charges", "Electricity - Branch",
    "AMC Charges", "Testing Charges", "Consultancy - One Time", "Donation",
]
TAIL_SUFFIXES = ["", " 2", " 3", " - Plant", " (Old)", " A/c", " - HO", " - Regional"]
SUSPENSE_TAIL_NAMES = [  # defect #10: twelve ledgers fitting no canonical class cleanly
    "Suspense A/c", "Old Balance b/f", "Round Off", "Misc Adjustment",
    "TBD Ledger", "Unclassified Receipt", "Unclassified Payment",
    "Clearing A/c", "Reconciliation Diff", "Old Vendor Adjustment",
    "Legacy Entry", "System Migration Diff",
]


@dataclass
class Ledger:
    account_code: str
    account_name: str
    parent_group: str
    account_type: str
    opening_balance_month0: object = None  # set later once postings are known
    opening_dr_cr: str = "Dr"
    cost_centre: str | None = None
    is_active: str = "Yes"
    role: str = "tail"  # 'revenue' | 'contra_revenue' | 'cogs' | 'opex' | 'below_ebitda' | 'bs' | 'tail' | 'suspense'
    late_arrival_month: int | None = None  # defect #5: None unless this ledger arrives mid-year


def build_coa(rng: Rng, target_total: int = 400) -> list[Ledger]:
    ledgers: list[Ledger] = []
    code = 4000

    def add(rows, role):
        nonlocal code
        for name, group, atype in rows:
            code += 1
            ledgers.append(Ledger(f"{code}", name, group, atype, role=role))

    add(REVENUE_LEDGERS, "revenue")
    add(CONTRA_REVENUE_LEDGERS, "contra_revenue")
    add(COGS_LEDGERS, "cogs")
    add(OPEX_LEDGERS, "opex")
    add(BELOW_EBITDA_LEDGERS, "below_ebitda")
    add(BS_LEDGERS, "bs")

    # Defect #10: twelve ledgers that fit no canonical class cleanly (suspense).
    for name in SUSPENSE_TAIL_NAMES:
        code += 1
        ledgers.append(Ledger(f"{code}", name, "Suspense", "Expense", role="suspense"))

    # Defect #5: one ledger that appears mid-year carrying large value.
    code += 1
    late_ledger = Ledger(f"{code}", "Sales - New Region (Pune)", "Sales Accounts", "Income",
                          role="revenue", late_arrival_month=19)
    ledgers.append(late_ledger)

    # Long tail: near-zero ledgers, procedurally named with the realism corpus/11
    # asks for -- free text, inconsistent casing, abbreviations, "Misc 3".
    n_tail = max(0, target_total - len(ledgers))
    seen_names = {l.account_name for l in ledgers}
    misc_counter = 0
    while len(ledgers) < target_total:
        prefix = rng.choice(TAIL_PREFIXES)
        suffix = rng.choice(TAIL_SUFFIXES)
        if prefix == "Misc":
            misc_counter += 1
            name = f"Misc {misc_counter}"
        else:
            name = f"{prefix}{suffix}"
        if rng.random() < 0.15:
            name = name.upper()
        elif rng.random() < 0.15:
            name = name.lower().replace(" ", "")
        if name in seen_names:
            continue
        seen_names.add(name)
        code += 1
        ledgers.append(Ledger(f"{code}", name, "Indirect Expenses", "Expense", role="tail"))

    return ledgers
