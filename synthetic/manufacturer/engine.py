"""The core simulation for the synthetic manufacturer: builds GL, Sales
Register, Purchase Register, Bank, AR/AP ageing, Inventory, MFG Production and
the Trial Balance as one internally consistent whole, then seeds all 13
defects from synthetic/defects.py.

Every voucher this module posts is individually balanced (sum(debit) ==
sum(credit) within the voucher), which is what makes "GL that balances
exactly every period" (corpus/11 section 2.1) true by construction -- except
in the one month where defect #4 deliberately breaks it.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from synthetic.common import Rng, fiscal_year_of, money, month_end, month_range, period_key
from synthetic.defects import DEFECTS
from synthetic.manufacturer import profile
from synthetic.manufacturer.coa import Ledger, build_coa
from synthetic.manufacturer.parties import (
    Customer, Item, Vendor, build_customers, build_items, build_rm_items, build_vendors,
)

CHANNEL_FROM_LEDGER = [
    ("Distributor", "Distributor"), ("Export", "Export"), ("Retail", "Retail"),
]


@dataclass
class Invoice:
    invoice_no: str
    invoice_date: date
    customer: Customer
    due_date: date
    payment_date: date
    invoice_total: Decimal
    is_credit_note: bool = False


@dataclass
class Bill:
    bill_no: str
    bill_date: date
    vendor: Vendor
    due_date: date
    payment_date: date
    bill_total: Decimal


@dataclass
class DefectLog:
    entries: list[dict] = field(default_factory=list)

    def record(self, defect_id: int, **detail):
        self.entries.append({"defect_id": defect_id, **detail})


@dataclass
class CompanyData:
    coa: list[Ledger]
    customers: list[Customer]
    vendors: list[Vendor]
    items: list[Item]
    rm_items: list[Item]
    months: list[date]
    gl_rows: dict[int, list[dict]]           # month_idx -> GL rows for that month's file
    sales_rows: dict[int, list[dict]]
    purchase_rows: dict[int, list[dict]]
    bank_rows: dict[int, list[dict]]
    ar_ageing_rows: dict[int, list[dict]]
    ap_ageing_rows: dict[int, list[dict]]
    inventory_rows: dict[int, list[dict]]
    mfg_rows: dict[int, list[dict]]
    tb_rows: dict[int, list[dict]]
    defect_log: DefectLog
    header_overrides: dict[str, list[str]]     # e.g. {"GL": [...]} for the defect #6 month file


class VoucherCounter:
    def __init__(self):
        self._n = itertools.count(1)

    def next(self, prefix: str, d: date) -> str:
        fy = fiscal_year_of(d)
        return f"{prefix}/{fy - 1 - 2000:02d}-{fy - 2000:02d}/{next(self._n):04d}"


def _channel_for(ledger_name: str) -> str:
    n = ledger_name.lower()
    if "export" in n:
        return "Export"
    if "distributor" in n:
        return "Distributor"
    if "retail" in n:
        return "Retail"
    return "Direct"


def build_company(seed: int) -> CompanyData:
    rng = Rng(seed)
    coa = build_coa(rng)
    coa_by_code = {l.account_code: l for l in coa}
    coa_by_name = {l.account_name: l for l in coa}
    debtors_ledger = coa_by_name["Sundry Debtors"]
    customers = build_customers(rng)
    vendors = build_vendors(rng)
    items = build_items()
    rm_items = build_rm_items()
    months = month_range(profile.FISCAL_START, profile.N_MONTHS)

    revenue_ledgers = [l for l in coa if l.role == "revenue" and l.late_arrival_month is None]
    late_ledger = next(l for l in coa if l.late_arrival_month is not None)
    rm_ledgers = [l for l in coa if l.account_name in ("RM - HR Coil", "RM - CR Coil", "RM - Zinc Ingot", "Packing Material")]
    direct_cogs_ledgers = [l for l in coa if l.role == "cogs" and l not in rm_ledgers]
    opex_ledgers = [l for l in coa if l.role == "opex"]
    tail_ledgers = [l for l in coa if l.role in ("tail", "suspense")]

    # Deterministic weights: skewed so a handful of ledgers dominate value,
    # per corpus/11 section 2.1 ("around 40 ledgers carrying the great
    # majority of value").
    def skewed_weights(n: int) -> list[Decimal]:
        raw = sorted((rng.random() ** 3 for _ in range(n)), reverse=True)
        total = sum(raw) or 1.0
        return [Decimal(str(x / total)) for x in raw]

    rev_weights = skewed_weights(len(revenue_ledgers))
    rm_weights = skewed_weights(len(rm_ledgers))
    direct_cogs_weights = skewed_weights(len(direct_cogs_ledgers))
    opex_weights = skewed_weights(len(opex_ledgers))

    seasonal = {4: 0.95, 5: 0.90, 6: 0.95, 7: 1.00, 8: 1.00, 9: 1.05,
                10: 1.15, 11: 1.10, 12: 1.05, 1: 0.95, 2: 0.95, 3: 1.15}

    vseq = VoucherCounter()
    defect_log = DefectLog()
    suspense_ledgers = [l for l in coa if l.role == "suspense"]
    defect_log.record(10, ledger_codes=[l.account_code for l in suspense_ledgers],
                        ledger_names=[l.account_name for l in suspense_ledgers],
                        note="Twelve ledgers with no clean canonical class -- destined for suspense.unmapped")

    gl_rows: dict[int, list[dict]] = {i: [] for i in range(len(months))}
    sales_rows: dict[int, list[dict]] = {i: [] for i in range(len(months))}
    purchase_rows: dict[int, list[dict]] = {i: [] for i in range(len(months))}
    bank_rows: dict[int, list[dict]] = {i: [] for i in range(len(months))}
    ar_ageing_rows: dict[int, list[dict]] = {i: [] for i in range(len(months))}
    ap_ageing_rows: dict[int, list[dict]] = {i: [] for i in range(len(months))}
    inventory_rows: dict[int, list[dict]] = {i: [] for i in range(len(months))}
    mfg_rows: dict[int, list[dict]] = {i: [] for i in range(len(months))}
    tb_rows: dict[int, list[dict]] = {i: [] for i in range(len(months))}

    open_invoices: list[Invoice] = []
    open_bills: list[Bill] = []
    running_bank_balance = Decimal("50000000")  # opening cash position, arbitrary but fixed
    ledger_balances: dict[str, Decimal] = {l.account_code: Decimal("0") for l in coa}  # Dr positive, Cr negative, cumulative

    def post(month_idx: int, voucher_type: str, prefix: str, d: date, lines: list[tuple], narration: str,
              party_name: str | None = None, cost_centre: str | None = None, entry_date: date | None = None,
              voucher_no: str | None = None):
        """lines: list of (ledger, debit, credit). Posts a balanced voucher."""
        vno = voucher_no or vseq.next(prefix, d)
        for i, (ledger, debit, credit) in enumerate(lines, start=1):
            gl_rows[month_idx].append({
                "voucher_no": vno, "voucher_type": voucher_type,
                "voucher_date": d.isoformat(),
                "entry_date": (entry_date or d).isoformat(),
                "line_no": i, "account_code": ledger.account_code, "account_name": ledger.account_name,
                "debit": str(money(debit)) if debit else "",
                "credit": str(money(credit)) if credit else "",
                "narration": narration, "cost_centre": cost_centre or "",
                "party_name": party_name or "", "is_cancelled": "No",
            })
            ledger_balances[ledger.account_code] += Decimal(debit or 0) - Decimal(credit or 0)
        return vno

    # -------------------------------------------------------------- items --
    item_base_rate = {it.code: Decimal(str(rng.uniform(45000, 78000))) for it in items}
    rm_base_rate = {it.code: Decimal(str(rng.uniform(38000, 62000))) for it in rm_items}

    DEFECT_TB_IMBALANCE_MONTH = 8
    DEFECT_BANK_MISSING_MONTH = 14
    DEFECT_DUPLICATE_VOUCHER_MONTH = 5
    DEFECT_SCHEMA_HASH_MONTH = 22
    DEFECT_DUAL_UOM_MONTH = 25
    DEFECT_ORPHAN_CREDIT_NOTE_MONTH = 12
    DEFECT_MARGIN_SIGN_FLIP_MONTH = 27
    DEFECT_DIV0_MONTH = 16
    DEFECT_ABSORPTION_VARIANCE_MONTH = 29
    DEFECT_BACKDATED_EVENT_MONTH = 10
    DEFECT_BACKDATED_ENTRY_MONTH = 33

    absorption_ledger = coa_by_name["Absorption Variance"]
    rm_ledger_by_name = {l.account_name: l for l in rm_ledgers}

    # ---------------------------------------------------------- main loop --
    for month_idx, d in enumerate(months):
        fy_index = (fiscal_year_of(d) - fiscal_year_of(months[0]))
        growth = (1 + profile.YOY_GROWTH) ** fy_index
        base_monthly = (profile.ANNUAL_REVENUE_Y1 / 12) * Decimal(str(growth)) * Decimal(str(seasonal[d.month]))
        noise = Decimal(str(1 + rng.uniform(-0.04, 0.04)))
        monthly_revenue_target = money(base_monthly * noise)

        # ---- revenue: allocate across ledgers, generate Sales Register ----
        month_invoices: list[Invoice] = []
        active_ledgers = list(revenue_ledgers)
        weights = list(rev_weights)
        if month_idx >= late_ledger.late_arrival_month:
            active_ledgers = active_ledgers + [late_ledger]
            LATE_SHARE = Decimal("0.07")
            weights = [w * (1 - LATE_SHARE) for w in rev_weights] + [LATE_SHARE]
            if month_idx == late_ledger.late_arrival_month:
                defect_log.record(5, month=period_key(d), ledger=late_ledger.account_name,
                                    note="Ledger appears mid-year carrying large value")

        for ledger, weight in zip(active_ledgers, weights):
            rev_amt = money(monthly_revenue_target * weight)
            if rev_amt <= 0:
                continue
            n_invoices = rng.randint(2, 6)
            channel = _channel_for(ledger.account_name)
            splits = _split_amount(rng, rev_amt, n_invoices)
            ledger_taxable = Decimal("0")
            ledger_tax = Decimal("0")
            ledger_invoice_total = Decimal("0")
            for amt in splits:
                if amt <= 0:
                    continue
                cust = rng.choice(customers)
                itm = rng.choice(items)
                qty = money(Decimal(str(rng.uniform(2, 40))))
                rate_val = item_base_rate[itm.code] * Decimal(str(rng.uniform(0.92, 1.08)))

                # Defect #9: margin sign flip -- force an abnormally low rate.
                is_flip = (month_idx == DEFECT_MARGIN_SIGN_FLIP_MONTH and itm.code == items[6].code
                           and not any(e["defect_id"] == 9 for e in defect_log.entries))
                if is_flip:
                    rate_val = rate_val * Decimal("0.35")
                    defect_log.record(9, month=period_key(d), item_code=itm.code,
                                        note=f"{itm.name} sold at ~35%% of its normal rate this month -- a margin sign flip")

                gross = money(qty * rate_val)
                discount = money(gross * Decimal(str(rng.uniform(0, 0.03))))
                taxable = money(gross - discount)
                # Rescale this line to fit the ledger's monthly allocation.
                if gross:
                    scale = amt / gross if gross else Decimal("1")
                else:
                    scale = Decimal("1")
                qty = money(qty * scale)
                gross = money(gross * scale)
                discount = money(discount * scale)
                taxable = money(taxable * scale)
                tax = money(taxable * profile.GST_RATE)
                invoice_total = money(taxable + tax)

                invoice_no = vseq.next("SI", d)
                invoice_date = d + timedelta(days=rng.randint(0, 27))
                due_date = invoice_date + timedelta(days=cust.credit_days)
                delay = rng.choice([-3, 0, 2, 5, 10, 20, 45, 70]) if rng.random() < 0.85 else rng.randint(60, 120)
                payment_date = due_date + timedelta(days=delay)

                rate_cell = str(rate_val.quantize(Decimal("0.01")))
                # Defect #11: #DIV/0! cell in an uploaded spreadsheet.
                if (month_idx == DEFECT_DIV0_MONTH and not any(e["defect_id"] == 11 for e in defect_log.entries)
                        and rng.random() < 0.3):
                    rate_cell = "#DIV/0!"
                    defect_log.record(11, month=period_key(d), invoice_no=invoice_no,
                                        note="rate cell corrupted to #DIV/0!")

                sales_rows[month_idx].append({
                    "invoice_no": invoice_no, "invoice_date": invoice_date.isoformat(),
                    "customer_code": cust.code, "customer_name": cust.name,
                    "item_code": itm.code, "item_name": itm.name,
                    "quantity": str(qty), "uom": itm.uom, "rate": rate_cell,
                    "gross_amount": str(gross), "discount_amount": str(discount),
                    "taxable_value": str(taxable), "tax_amount": str(tax),
                    "invoice_total": str(invoice_total), "channel": channel,
                    "dispatch_date": invoice_date.isoformat(), "is_credit_note": "No",
                })
                inv = Invoice(invoice_no, invoice_date, cust, due_date, payment_date, invoice_total)
                month_invoices.append(inv)
                ledger_taxable += taxable
                ledger_tax += tax
                ledger_invoice_total += invoice_total

            # -- credit notes: ~1 per active ledger every few months --
            if rng.random() < 0.25:
                cust = rng.choice(customers)
                cn_taxable = money(rev_amt * Decimal(str(rng.uniform(0.005, 0.02))))
                cn_tax = money(cn_taxable * profile.GST_RATE)
                cn_total = money(cn_taxable + cn_tax)
                cn_no = vseq.next("CN", d)
                cn_date = d + timedelta(days=rng.randint(0, 27))
                sales_rows[month_idx].append({
                    "invoice_no": cn_no, "invoice_date": cn_date.isoformat(),
                    "customer_code": cust.code, "customer_name": cust.name,
                    "item_code": rng.choice(items).code, "item_name": "",
                    "quantity": "1", "uom": "MT", "rate": str(cn_taxable),
                    "gross_amount": str(cn_taxable), "discount_amount": "0",
                    "taxable_value": str(cn_taxable), "tax_amount": str(cn_tax),
                    "invoice_total": str(cn_total), "channel": channel,
                    "dispatch_date": "", "is_credit_note": "Yes",
                })
                # Credit notes net down the ledger's GL revenue posting; they
                # are not tracked as AR items since they are settled at
                # source, not collected later.
                ledger_taxable -= cn_taxable
                ledger_tax -= cn_tax
                ledger_invoice_total -= cn_total

            # One aggregated GL revenue voucher per ledger per month --
            # exactly what the Sales Register rows just generated for this
            # ledger sum to, so GL ties to the register by construction.
            if ledger_invoice_total != 0:
                gst_output = coa_by_name["GST Output Payable"]
                post(month_idx, "Sales", "SV", d,
                     [(debtors_ledger, ledger_invoice_total, Decimal(0)),
                      (ledger, Decimal(0), ledger_taxable),
                      (gst_output, Decimal(0), ledger_tax)],
                     f"Sales booked for {ledger.account_name}, {period_key(d)}",
                     cost_centre=ledger.parent_group[:12])

        # ------------------------------------------------- Defect #8 ------
        if month_idx == DEFECT_ORPHAN_CREDIT_NOTE_MONTH:
            cust = rng.choice(customers)
            orphan_no = "SI/ORPHAN/0001"
            cn_taxable = money(Decimal("125000"))
            cn_tax = money(cn_taxable * profile.GST_RATE)
            sales_rows[month_idx].append({
                "invoice_no": orphan_no, "invoice_date": d.isoformat(),
                "customer_code": cust.code, "customer_name": cust.name,
                "item_code": items[0].code, "item_name": items[0].name,
                "quantity": "1", "uom": "MT", "rate": str(cn_taxable),
                "gross_amount": str(cn_taxable), "discount_amount": "0",
                "taxable_value": str(cn_taxable), "tax_amount": str(cn_tax),
                "invoice_total": str(money(cn_taxable + cn_tax)), "channel": "Direct",
                "dispatch_date": "", "is_credit_note": "Yes",
            })
            defect_log.record(8, month=period_key(d), invoice_no=orphan_no,
                                note="Credit note references no matching original invoice -- no reason code derivable")

        # ---- purchases: RM ledgers, generate Purchase Register ----------
        cogs_target = money(monthly_revenue_target * (1 - profile.GROSS_MARGIN_TARGET))
        rm_budget = money(cogs_target * Decimal("0.55"))
        for ledger, weight in zip(rm_ledgers, rm_weights):
            amt = money(rm_budget * weight)
            if amt <= 0:
                continue
            rm_item = _rm_item_for_ledger(ledger.account_name, rm_items)
            n_bills = rng.randint(1, 3)
            bill_lines = []
            for amt_part in _split_amount(rng, amt, n_bills):
                if amt_part <= 0:
                    continue
                vendor = rng.choice(vendors)
                rate_val = rm_base_rate.get(rm_item.code, Decimal("50000")) * Decimal(str(rng.uniform(0.9, 1.15)))

                # Defect #13: absorption variance masking a real margin fall --
                # a genuine RM cost spike this month.
                if month_idx == DEFECT_ABSORPTION_VARIANCE_MONTH and ledger.account_name == "RM - HR Coil":
                    rate_val = rate_val * Decimal("1.22")

                qty = money(amt_part / rate_val) if rate_val else Decimal("0")
                taxable = money(qty * rate_val)
                tax = money(taxable * profile.GST_RATE)
                bill_total = money(taxable + tax)
                bill_no = vseq.next("PB", d)
                bill_date = d + timedelta(days=rng.randint(0, 27))
                due_date = bill_date + timedelta(days=30 if vendor.is_msme else 45)
                delay = rng.choice([-2, 0, 3, 8, 15]) if rng.random() < 0.9 else rng.randint(30, 60)
                payment_date = due_date + timedelta(days=delay)
                purchase_rows[month_idx].append({
                    "bill_no": bill_no, "bill_date": bill_date.isoformat(),
                    "vendor_code": vendor.code, "vendor_name": vendor.name,
                    "item_code": rm_item.code, "item_name": rm_item.name, "expense_account": "",
                    "quantity": str(qty), "uom": rm_item.uom, "rate": str(rate_val.quantize(Decimal("0.01"))),
                    "taxable_value": str(taxable), "tax_amount": str(tax), "bill_total": str(bill_total),
                    "is_msme_vendor": "Yes" if vendor.is_msme else "No",
                })
                bill_lines.append(Bill(bill_no, bill_date, vendor, due_date, payment_date, bill_total))
            open_bills.extend(bill_lines)
            month_taxable = sum((money(Decimal(r["taxable_value"])) for r in purchase_rows[month_idx]
                                   if r["item_code"] == rm_item.code and r["bill_date"].startswith(period_key(d))),
                                  Decimal("0"))
            month_tax = sum((money(Decimal(r["tax_amount"])) for r in purchase_rows[month_idx]
                               if r["item_code"] == rm_item.code and r["bill_date"].startswith(period_key(d))),
                              Decimal("0"))
            if month_taxable or month_tax:
                gst_input = coa_by_name["GST Input Credit"]
                creditors = coa_by_name["Sundry Creditors"]
                post(month_idx, "Purchase", "PJ", d,
                     [(ledger, month_taxable, Decimal(0)), (gst_input, month_tax, Decimal(0)),
                      (creditors, Decimal(0), month_taxable + month_tax)],
                     f"Purchases booked for {ledger.account_name}, {period_key(d)}", cost_centre="PROC")

        # -------------------- direct-post COGS ledgers (paid via bank) ----
        direct_budget = money(cogs_target - rm_budget)
        direct_lines = []
        for ledger, weight in zip(direct_cogs_ledgers, direct_cogs_weights):
            if ledger.account_name == "Absorption Variance":
                continue  # handled explicitly below
            amt = money(direct_budget * weight * Decimal(str(rng.uniform(0.9, 1.1))))
            if amt > 0:
                direct_lines.append((ledger, amt, Decimal(0)))
        variance_amt = Decimal("0")
        if month_idx == DEFECT_ABSORPTION_VARIANCE_MONTH:
            # Offset the RM cost spike above with a large favourable variance
            # credit, so period-level gross margin looks unremarkable despite
            # the real cost increase -- the D-017 manufacturing trap.
            variance_amt = money(direct_budget * Decimal("0.18"))
            direct_lines.append((absorption_ledger, Decimal(0), variance_amt))
            defect_log.record(13, month=period_key(d),
                                note="RM - HR Coil rate spiked 22%% this month; Absorption Variance credit "
                                     "offsets it in the GL total, hiding the real margin fall")
        elif rng.random() < 0.5:
            small_variance = money(direct_budget * Decimal(str(rng.uniform(-0.01, 0.01))))
            if small_variance > 0:
                direct_lines.append((absorption_ledger, small_variance, Decimal(0)))
            elif small_variance < 0:
                direct_lines.append((absorption_ledger, Decimal(0), -small_variance))
        if direct_lines:
            bank = coa_by_name["Cash and Bank - HDFC Current A/c"]
            total_dr = sum(l[1] for l in direct_lines)
            total_cr = sum(l[2] for l in direct_lines)
            net = total_dr - total_cr
            lines = list(direct_lines) + [(bank, Decimal(0), net)] if net > 0 else list(direct_lines) + [(bank, -net, Decimal(0))]
            post(month_idx, "Payment", "JV", d, lines, f"Direct COGS costs, {period_key(d)}", cost_centre="PLANT")

        # --------------------------------------------------------- opex --
        opex_target = money(monthly_revenue_target * profile.OPEX_PCT_OF_REVENUE)
        opex_lines = []
        for ledger, weight in zip(opex_ledgers, opex_weights):
            amt = money(opex_target * weight * Decimal(str(rng.uniform(0.9, 1.1))))
            if amt > 0:
                opex_lines.append((ledger, amt, Decimal(0)))
        if opex_lines:
            bank = coa_by_name["Cash and Bank - ICICI Current A/c"]
            total = sum(l[1] for l in opex_lines)
            post(month_idx, "Payment", "JV", d, opex_lines + [(bank, Decimal(0), total)],
                 f"Operating expenses, {period_key(d)}", cost_centre="ADMIN")

        # ------------------------------------------------- below EBITDA --
        dep = money(Decimal("2500000") * Decimal(str(1 + fy_index * 0.05)))
        post(month_idx, "Journal", "JV", d,
             [(coa_by_name["Depreciation"], dep, Decimal(0)),
              (coa_by_name["Accumulated Depreciation"], Decimal(0), dep)],
             f"Depreciation for {period_key(d)}")

        interest = money(Decimal("1400000") * Decimal(str(1 - fy_index * 0.03)))
        bank_charges = money(Decimal(str(rng.uniform(8000, 25000))))
        bank2 = coa_by_name["Cash and Bank - HDFC Current A/c"]
        post(month_idx, "Payment", "JV", d,
             [(coa_by_name["Interest - Term Loan"], interest, Decimal(0)),
              (coa_by_name["Bank Charges"], bank_charges, Decimal(0)),
              (bank2, Decimal(0), interest + bank_charges)],
             f"Finance costs, {period_key(d)}")

        other_income = money(Decimal(str(rng.uniform(50000, 200000))))
        post(month_idx, "Receipt", "JV", d,
             [(bank2, other_income, Decimal(0)), (coa_by_name["Interest Income"], Decimal(0), other_income)],
             f"Other income, {period_key(d)}")

        # tax accrual: rough 25% of an estimated monthly PBT proxy
        pbt_proxy = monthly_revenue_target - cogs_target - opex_target - dep - interest
        tax_amt = money(max(pbt_proxy, Decimal(0)) * Decimal("0.25"))
        if tax_amt > 0:
            post(month_idx, "Journal", "JV", d,
                 [(coa_by_name["Provision for Tax"], tax_amt, Decimal(0)),
                  (coa_by_name["Provisions"], Decimal(0), tax_amt)],
                 f"Tax provision, {period_key(d)}")

        # --------------------------------------------------- tail ledgers -
        active_tail = rng.sample(tail_ledgers, k=min(len(tail_ledgers), rng.randint(15, 35)))
        if active_tail:
            bank3 = coa_by_name["Cash and Bank - ICICI Current A/c"]
            tail_lines = []
            for ledger in active_tail:
                amt = money(Decimal(str(rng.uniform(500, 40000))))
                tail_lines.append((ledger, amt, Decimal(0)))
            total = sum(l[1] for l in tail_lines)
            post(month_idx, "Payment", "JV", d, tail_lines + [(bank3, Decimal(0), total)],
                 f"Sundry small expenses, {period_key(d)}", cost_centre="MISC")

        # ---- collections and payments (AR/AP settle, driving Bank lines) --
        collected_this_month = [inv for inv in open_invoices + month_invoices
                                   if period_key(inv.payment_date) == period_key(d) and not inv.is_credit_note]
        open_invoices = [inv for inv in open_invoices + month_invoices if inv not in collected_this_month]
        paid_bills_this_month = [b for b in open_bills if period_key(b.payment_date) == period_key(d)]
        open_bills = [b for b in open_bills if b not in paid_bills_this_month]

        collections_total = sum((inv.invoice_total for inv in collected_this_month), Decimal("0"))
        payments_total = sum((b.bill_total for b in paid_bills_this_month), Decimal("0"))
        debtors = coa_by_name["Sundry Debtors"]
        creditors = coa_by_name["Sundry Creditors"]
        bank4 = coa_by_name["Cash and Bank - HDFC Current A/c"]
        if collections_total > 0:
            post(month_idx, "Receipt", "RC", d, [(bank4, collections_total, Decimal(0)), (debtors, Decimal(0), collections_total)],
                 f"Collections from customers, {period_key(d)}")
        if payments_total > 0:
            post(month_idx, "Payment", "PY", d, [(creditors, payments_total, Decimal(0)), (bank4, Decimal(0), payments_total)],
                 f"Payments to vendors, {period_key(d)}")

        # -------------------------------------------------- Bank lines ---
        if month_idx != DEFECT_BANK_MISSING_MONTH:
            running_bank_balance = _write_bank_lines(
                bank_rows[month_idx], d, collected_this_month, paid_bills_this_month,
                running_bank_balance, rng, month_idx=month_idx,
            )
        else:
            defect_log.record(3, month=period_key(d), note="Bank file missing entirely for this month")

        # -------------------------------------------------- ageing -------
        me = month_end(d)
        for inv in open_invoices:
            if inv.invoice_date <= me:
                ar_ageing_rows[month_idx].append({
                    "as_at_date": me.isoformat(), "customer_code": inv.customer.code,
                    "customer_name": inv.customer.name, "invoice_no": inv.invoice_no,
                    "invoice_date": inv.invoice_date.isoformat(), "due_date": inv.due_date.isoformat(),
                    "outstanding_amount": str(inv.invoice_total), "credit_days": inv.customer.credit_days,
                })
        for b in open_bills:
            if b.bill_date <= me:
                ap_ageing_rows[month_idx].append({
                    "as_at_date": me.isoformat(), "vendor_code": b.vendor.code,
                    "vendor_name": b.vendor.name, "bill_no": b.bill_no,
                    "bill_date": b.bill_date.isoformat(), "due_date": b.due_date.isoformat(),
                    "outstanding_amount": str(b.bill_total),
                })

        # -------------------------------------------------- inventory ----
        _write_inventory_rows(inventory_rows[month_idx], me, rm_items, items, rng, month_idx)

        # ---------------------------------------------- MFG production ---
        _write_mfg_rows(mfg_rows[month_idx], d, items, rm_items, rng, month_idx,
                          dual_uom_month=DEFECT_DUAL_UOM_MONTH, defect_log=defect_log)

    # -------------------------------------------- Defect #2: duplicate ---
    m = DEFECT_DUPLICATE_VOUCHER_MONTH
    sale_rows_this_month = [r for r in gl_rows[m] if r["voucher_type"] == "Sales"]
    if sale_rows_this_month:
        target_vno = sale_rows_this_month[0]["voucher_no"]
        original = [r for r in gl_rows[m] if r["voucher_no"] == target_vno]
        dup_vno = target_vno + "-DUP"
        for r in original:
            dup = dict(r)
            dup["voucher_no"] = dup_vno
            gl_rows[m].append(dup)
        defect_log.record(2, month=period_key(months[m]), original_voucher=target_vno, duplicate_voucher=dup_vno,
                            note="Same content, different voucher id -- a duplicate upload/duplicate voucher run")

    # -------------------------------------------- Defect #4: TB imbalance
    m = DEFECT_TB_IMBALANCE_MONTH
    imbalance_ledger = coa_by_name["Bank Charges"]
    gl_rows[m].append({
        "voucher_no": vseq.next("JV", months[m]), "voucher_type": "Journal",
        "voucher_date": months[m].isoformat(), "entry_date": months[m].isoformat(),
        "line_no": 1, "account_code": imbalance_ledger.account_code, "account_name": imbalance_ledger.account_name,
        "debit": "12500.00", "credit": "", "narration": "One-sided adjustment (unbalanced by design)",
        "cost_centre": "", "party_name": "", "is_cancelled": "No",
    })
    defect_log.record(4, month=period_key(months[m]), note="Trial balance fails to balance by INR 12,500.00 this month")

    # ------------------------------------------ Defect #1: backdated batch
    event_month = months[DEFECT_BACKDATED_EVENT_MONTH]
    entry_month = months[DEFECT_BACKDATED_ENTRY_MONTH]
    debtors = coa_by_name["Sundry Debtors"]
    discount_ledger = coa_by_name["Trade Discount Allowed"]
    backdated_amt = Decimal("340000.00")
    vno = vseq.next("JV", event_month)
    for ledger, debit, credit in [(discount_ledger, backdated_amt, Decimal(0)), (debtors, Decimal(0), backdated_amt)]:
        gl_rows[DEFECT_BACKDATED_EVENT_MONTH].append({
            "voucher_no": vno, "voucher_type": "Journal",
            "voucher_date": event_month.isoformat(), "entry_date": entry_month.isoformat(),
            "line_no": 1 if credit == 0 else 2, "account_code": ledger.account_code, "account_name": ledger.account_name,
            "debit": str(debit) if debit else "", "credit": str(credit) if credit else "",
            "narration": "Backdated discount adjustment, posted late against a prior period",
            "cost_centre": "", "party_name": "", "is_cancelled": "No",
        })
    defect_log.record(1, event_month=period_key(event_month), entry_month=period_key(entry_month),
                        voucher_no=vno, note="entry_date is 23 months after event_date; touches an already-locked period")

    # -------------------------------------------------- Defect #6 headers -
    defect_log.record(6, month=period_key(months[DEFECT_SCHEMA_HASH_MONTH]),
                        note="GL export column headers change for this month's file only; "
                             "synthetic/manufacturer/write.py renames 'narration' to 'remarks' when writing it")

    # -------------------------------------------------------------- TB ---
    _build_tb(tb_rows, gl_rows, coa, months)

    return CompanyData(
        coa=coa, customers=customers, vendors=vendors, items=items, rm_items=rm_items, months=months,
        gl_rows=gl_rows, sales_rows=sales_rows, purchase_rows=purchase_rows, bank_rows=bank_rows,
        ar_ageing_rows=ar_ageing_rows, ap_ageing_rows=ap_ageing_rows, inventory_rows=inventory_rows,
        mfg_rows=mfg_rows, tb_rows=tb_rows, defect_log=defect_log,
        header_overrides={"schema_hash_defect_month": DEFECT_SCHEMA_HASH_MONTH},
    )


# ---------------------------------------------------------------- helpers --

def _split_amount(rng: Rng, total: Decimal, n: int) -> list[Decimal]:
    if n <= 1 or total <= 0:
        return [total]
    cuts = sorted(Decimal(str(rng.uniform(0.05, 0.95))) for _ in range(n - 1))
    bounds = [Decimal(0)] + cuts + [Decimal(1)]
    return [money(total * (bounds[i + 1] - bounds[i])) for i in range(n)]


def _rm_item_for_ledger(ledger_name: str, rm_items: list[Item]) -> Item:
    mapping = {"RM - HR Coil": "hr_coil", "RM - CR Coil": "cr_coil",
                "RM - Zinc Ingot": "zinc_ingot", "Packing Material": "packing"}
    fam = mapping.get(ledger_name)
    return next((it for it in rm_items if it.family == fam), rm_items[0])


def _write_bank_lines(rows: list[dict], d: date, collected, paid, running_balance: Decimal,
                        rng: Rng, month_idx: int) -> Decimal:
    account_ref = "HDFC-4471"
    events = []
    for inv in collected:
        events.append((inv.payment_date, inv.invoice_total, Decimal(0), f"NEFT CR {inv.customer.name.upper()} HDFC0000123"))
    for b in paid:
        events.append((b.payment_date, Decimal(0), b.bill_total, f"NEFT DR {b.vendor.name.upper()} HDFC0000456"))
    # A handful of reconciling items with no exact books counterpart --
    # unpresented instruments and direct bank charges not yet booked, per
    # corpus/09 section 3.2's modelled differences.
    for _ in range(rng.randint(1, 3)):
        amt = money(Decimal(str(rng.uniform(500, 15000))))
        events.append((d + timedelta(days=rng.randint(0, 27)), Decimal(0), amt, "BANK CHARGES - NOT YET BOOKED"))
    events.sort(key=lambda e: e[0])
    for txn_date, debit, credit, desc in events:
        running_balance = running_balance + debit - credit
        rows.append({
            "bank_account_ref": account_ref, "txn_date": txn_date.isoformat(), "value_date": txn_date.isoformat(),
            "description": desc, "reference": f"UTRN{txn_date.strftime('%y%m%d')}{rng.randint(1000, 9999)}",
            "debit": str(money(debit)) if debit else "0", "credit": str(money(credit)) if credit else "0",
            "running_balance": str(money(running_balance)),
        })
    return running_balance


def _write_inventory_rows(rows: list[dict], me: date, rm_items, items, rng: Rng, month_idx: int):
    for it in rm_items:
        qty = money(Decimal(str(rng.uniform(80, 250))))
        value = money(qty * Decimal(str(rng.uniform(38000, 62000))))
        rows.append({
            "as_at_date": me.isoformat(), "item_code": it.code, "item_name": it.name,
            "item_category": it.category, "stock_type": "Raw material" if it.family != "packing" else "Packing",
            "location": "Plant 1", "closing_qty": str(qty), "uom": it.uom, "closing_value": str(value),
            "valuation_method": "Weighted average",
        })
    rows.append({
        "as_at_date": me.isoformat(), "item_code": "WIP-GEN", "item_name": "Work in Progress",
        "item_category": "WIP", "stock_type": "WIP", "location": "Plant 1",
        "closing_qty": str(money(Decimal(str(rng.uniform(10, 40))))), "uom": "MT",
        "closing_value": str(money(Decimal(str(rng.uniform(3000000, 9000000))))),
        "valuation_method": "Weighted average",
    })
    for it in items:
        qty = money(Decimal(str(rng.uniform(5, 60))))
        value = money(qty * Decimal(str(rng.uniform(45000, 78000))))
        rows.append({
            "as_at_date": me.isoformat(), "item_code": it.code, "item_name": it.name,
            "item_category": it.category, "stock_type": "Finished goods", "location": "Plant 1",
            "closing_qty": str(qty), "uom": it.uom, "closing_value": str(value),
            "valuation_method": "Weighted average",
        })


def _write_mfg_rows(rows: list[dict], d: date, items, rm_items, rng: Rng, month_idx: int,
                      dual_uom_month: int, defect_log: DefectLog):
    for it in items:
        produced = money(Decimal(str(rng.uniform(30, 90))))
        rejected = money(produced * Decimal(str(rng.uniform(0.01, 0.04))))
        uom = it.uom
        # Defect #7: a product family with two units of measure.
        if month_idx == dual_uom_month and it.code == items[0].code:
            uom = "KG"
            defect_log.record(7, month=period_key(d), item_code=it.code,
                                note=f"{it.name} recorded in KG this month; declared family UOM is MT elsewhere")
        rows.append({
            "period": (d.replace(day=28)).isoformat(), "plant_or_line": rng.choice(["Rolling Line 1", "Rolling Line 2"]),
            "item_code": it.code, "item_name": it.name, "qty_produced": str(produced), "qty_rejected": str(rejected),
            "uom": uom, "input_qty": str(money(produced * Decimal(str(rng.uniform(1.02, 1.08))))), "input_uom": it.uom,
            "available_hours": "720", "running_hours": str(rng.randint(560, 700)),
            "power_units": str(rng.randint(80000, 160000)),
        })


def _build_tb(tb_rows, gl_rows, coa, months):
    running_balance = {l.account_code: Decimal("0") for l in coa}
    for month_idx, d in enumerate(months):
        opening = dict(running_balance)
        debit_mv = {code: Decimal("0") for code in running_balance}
        credit_mv = {code: Decimal("0") for code in running_balance}
        for row in gl_rows[month_idx]:
            code = row["account_code"]
            debit_mv[code] += Decimal(row["debit"] or "0")
            credit_mv[code] += Decimal(row["credit"] or "0")
            running_balance[code] += Decimal(row["debit"] or "0") - Decimal(row["credit"] or "0")
        for l in coa:
            code = l.account_code
            if opening[code] == 0 and debit_mv[code] == 0 and credit_mv[code] == 0 and running_balance[code] == 0:
                continue
            tb_rows[month_idx].append({
                "period_end": month_end(d).isoformat(), "account_code": code, "account_name": l.account_name,
                "opening_balance": str(money(opening[code])), "debit_movement": str(money(debit_mv[code])),
                "credit_movement": str(money(credit_mv[code])), "closing_balance": str(money(running_balance[code])),
            })
