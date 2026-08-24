"""The core simulation for the synthetic apparel retailer: store-cohort
offline revenue (synthetic/apparel/stores.py) plus channel-tier online
revenue, built independently of each other and of the order file vs. the
books (same deliberate books-vs-order-file residual as
synthetic/consumer/engine.py), five years of monthly history.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from synthetic.apparel import profile, stores as stores_mod
from synthetic.common import Rng, money, month_end, month_range, period_key

COA_LEDGERS = [
    ("Sales - COCO Stores", "Sales Accounts", "Income", "revenue"),
    ("Sales - COFO Stores", "Sales Accounts", "Income", "revenue"),
    ("Sales - FOCO Stores", "Sales Accounts", "Income", "revenue"),
    ("Sales - FOFO Stores", "Sales Accounts", "Income", "revenue"),
    ("Sales - Marketplace Myntra", "Sales Accounts", "Income", "revenue"),
    ("Sales - Marketplace Ajio", "Sales Accounts", "Income", "revenue"),
    ("Sales - Marketplace Nykaa", "Sales Accounts", "Income", "revenue"),
    ("Sales - Marketplace Flipkart", "Sales Accounts", "Income", "revenue"),
    ("Sales - Own Website", "Sales Accounts", "Income", "revenue"),
    ("Sales Returns", "Sales Accounts", "Income", "contra_revenue"),
    ("Discount Allowed", "Sales Accounts", "Income", "contra_revenue"),
    ("COGS - Finished Goods", "Cost of Goods Sold", "Expense", "cogs"),
    ("Store Rent, CAM & Utilities", "Store Operating Cost", "Expense", "store_rent"),
    ("Store Personnel Cost", "Store Operating Cost", "Expense", "store_personnel"),
    ("Franchise Commission", "Store Operating Cost", "Expense", "franchise_commission"),
    ("Marketplace Commission Borne", "Online Operating Cost", "Expense", "opex_cm1"),
    ("Online Advertising Spend", "Marketing", "Expense", "marketing"),
    ("HO Employee Cost", "Corporate", "Expense", "overhead"),
    ("Warehouse Cost", "Corporate", "Expense", "overhead"),
    ("Admin Expenses", "Corporate", "Expense", "overhead"),
    ("Cash and Bank - Current A/c", "Bank Accounts", "Asset", "bs"),
    ("Sundry Debtors", "Sundry Debtors", "Asset", "bs"),
    ("Inventory - Finished Goods", "Stock-in-Hand", "Asset", "bs"),
    ("GST Input Credit", "Duties & Taxes", "Asset", "bs"),
    ("Sundry Creditors", "Sundry Creditors", "Liability", "bs"),
    ("GST Output Payable", "Duties & Taxes", "Liability", "bs"),
    ("Marketplace Payable", "Sundry Creditors", "Liability", "bs"),
    ("Share Capital", "Capital Account", "Equity", "bs"),
    ("Reserves & Surplus", "Capital Account", "Equity", "bs"),
]

SALES_LEDGER_BY_FORMAT = {
    "COCO": "Sales - COCO Stores", "COFO": "Sales - COFO Stores",
    "FOCO": "Sales - FOCO Stores", "FOFO": "Sales - FOFO Stores",
}
SALES_LEDGER_BY_ONLINE_CHANNEL = {
    "Marketplace - Myntra": "Sales - Marketplace Myntra", "Marketplace - Ajio": "Sales - Marketplace Ajio",
    "Marketplace - Nykaa": "Sales - Marketplace Nykaa", "Marketplace - Flipkart": "Sales - Marketplace Flipkart",
    "Own Website": "Sales - Own Website",
}
# A couple of representative SKUs per category, not full-transaction realism.
_SKU_SUFFIXES = ["Classic", "Premium", "Signature"]


@dataclass
class Ledger:
    account_code: str
    account_name: str
    parent_group: str
    account_type: str
    role: str


@dataclass
class DefectLog:
    entries: list[dict] = field(default_factory=list)

    def record(self, defect_id: int, **detail):
        self.entries.append({"defect_id": defect_id, **detail})


@dataclass
class ApparelCompanyData:
    coa: list[Ledger]
    months: list[date]
    stores: list
    gl_rows: dict[int, list[dict]]
    order_rows: dict[int, list[dict]]
    tb_rows: dict[int, list[dict]]
    store_rows: list[dict]
    defect_log: DefectLog


class VoucherCounter:
    def __init__(self):
        self._n = itertools.count(1)

    def next(self, prefix: str, d: date) -> str:
        return f"{prefix}/{d.strftime('%y%m')}/{next(self._n):04d}"


def _interp(start: Decimal, end: Decimal, month_idx: int, n_months: int) -> Decimal:
    frac = Decimal(month_idx) / Decimal(max(n_months - 1, 1))
    return start + (end - start) * frac


def _category_mix(month_idx: int) -> list[tuple[str, str, str, Decimal]]:
    """(category, occasion_type, price_band, weight) for this month, linearly
    interpolated between profile.CATEGORY_MIX_START and _TARGET."""
    out = []
    for name, occasion, band in profile.CATEGORIES:
        w = _interp(profile.CATEGORY_MIX_START[name], profile.CATEGORY_MIX_TARGET[name],
                     month_idx, profile.N_MONTHS)
        out.append((name, occasion, band, w))
    return out


def _weighted_choice(rng: Rng, choices: list[tuple], weights: list[Decimal]):
    total = sum(weights)
    r = Decimal(str(rng.uniform(0, float(total))))
    upto = Decimal("0")
    for choice, w in zip(choices, weights):
        upto += w
        if upto >= r:
            return choice
    return choices[-1]


def _sku_for_category(category: str) -> tuple[str, str]:
    # Python's hash() is per-process randomised for strings (PYTHONHASHSEED)
    # -- using it here would make the generator non-deterministic across
    # runs of the same seed, defeating corpus/11 section 2's whole point.
    # sum(ord(...)) is a stable, seed-independent stand-in.
    suffix = category[:3].upper()
    idx = _SKU_SUFFIXES[sum(ord(c) for c in category) % len(_SKU_SUFFIXES)]
    return f"SKU-{suffix}-01", f"{category} - {idx}"


def build_company(seed: int) -> ApparelCompanyData:
    rng = Rng(seed + 2)  # distinct stream from manufacturer (+1) and consumer (+1)
    coa = [Ledger(f"{7000+i}", name, group, atype, role) for i, (name, group, atype, role) in enumerate(COA_LEDGERS)]
    coa_by_name = {l.account_name: l for l in coa}
    months = month_range(profile.FISCAL_START, profile.N_MONTHS)
    vseq = VoucherCounter()
    defect_log = DefectLog()

    company_stores = stores_mod.build_stores(rng)

    gl_rows: dict[int, list[dict]] = {i: [] for i in range(len(months))}
    order_rows: dict[int, list[dict]] = {i: [] for i in range(len(months))}
    tb_rows: dict[int, list[dict]] = {i: [] for i in range(len(months))}

    debtors = coa_by_name["Sundry Debtors"]
    bank = coa_by_name["Cash and Bank - Current A/c"]
    gst_output = coa_by_name["GST Output Payable"]
    cogs_ledger = coa_by_name["COGS - Finished Goods"]
    inventory = coa_by_name["Inventory - Finished Goods"]
    discount_ledger = coa_by_name["Discount Allowed"]
    creditors = coa_by_name["Sundry Creditors"]

    seasonal = {4: 0.92, 5: 0.90, 6: 0.92, 7: 0.95, 8: 0.97, 9: 1.05, 10: 1.25, 11: 1.2, 12: 1.05,
                1: 0.9, 2: 0.9, 3: 1.05}

    def post(month_idx, voucher_type, prefix, d, lines, narration):
        vno = vseq.next(prefix, d)
        for i, (ledger, debit, credit) in enumerate(lines, start=1):
            gl_rows[month_idx].append({
                "voucher_no": vno, "voucher_type": voucher_type, "voucher_date": d.isoformat(),
                "entry_date": d.isoformat(), "line_no": i, "account_code": ledger.account_code,
                "account_name": ledger.account_name, "debit": str(money(debit)) if debit else "",
                "credit": str(money(credit)) if credit else "", "narration": narration,
                "cost_centre": "", "party_name": "", "is_cancelled": "No",
            })
        return vno

    def make_order_row(order_id, order_date, channel, channel_sub, item_code, item_name,
                          qty, gross, discount, net, commission, order_type):
        return {
            "order_id": order_id, "order_date": order_date.isoformat(), "channel": channel,
            "channel_sub": channel_sub, "customer_code": f"CUST{rng.randint(1000, 9999)}",
            "item_code": item_code, "item_name": item_name, "quantity": str(qty),
            "gross_amount": str(gross), "discount_amount": str(discount), "net_amount": str(net),
            "shipping_charged": "0.00", "commission_amount": str(commission), "shipping_cost": "0.00",
            "payment_fee": "0.00", "return_flag": "No", "return_date": "", "return_reason": "",
            "settlement_date": (order_date + timedelta(days=rng.randint(3, 14))).isoformat(),
            "revenue_model": "buyout", "order_type": order_type,
            "commission_earned": "0.00", "advertising_earned": "0.00", "platform_fee_earned": "0.00",
        }

    seen_customers: set[str] = set()

    # Running working-capital balances, corpus/13's baseline reader depends
    # on these staying realistic (DSO/DIO/DPO are balance / monthly-flow x
    # 365 -- a balance that only ever grows, never collected/paid/
    # replenished, compounds across 60 months into an unbounded, nonsensical
    # ratio). Each month collects/pays down MOST of the outstanding balance
    # (opening + this month's new activity), the same "high fraction, small
    # aging tail" shape real working capital has, rather than either fully
    # clearing to zero (unrealistic) or never clearing at all (the bug this
    # replaces, found 2026-08-24 running the forecast baseline against real
    # ingested data).
    outstanding_ar = Decimal("0")
    outstanding_trade_payable = Decimal("0")     # inventory purchases + franchise commission
    outstanding_marketplace_payable = Decimal("0")
    outstanding_inventory = Decimal("0")
    # Inventory is targeted at a stable multiple of the CURRENT month's COGS
    # flow rather than replenished by a fixed surplus per transaction --
    # a fixed surplus compounds every month across a 60-month horizon and
    # never converges, which is the same unbounded-balance bug this whole
    # section exists to avoid. Targeting a multiple of monthly COGS keeps
    # DIO converging to ~TARGET_INVENTORY_MONTHS_COVER x 30 days once the
    # ramp settles, growing with the business instead of running away from it.
    TARGET_INVENTORY_MONTHS_COVER = Decimal("2.5")

    for month_idx, d in enumerate(months):
        month_total_cogs = Decimal("0")
        gp_margin = _interp(profile.GP_MARGIN_START, profile.GP_MARGIN_END, month_idx, profile.N_MONTHS)
        mix = _category_mix(month_idx)
        mix_categories = [(name, occ, band) for name, occ, band, _w in mix]
        mix_weights = [w for _n, _o, _b, w in mix]

        # ---------------------------------------------------------- offline
        active = stores_mod.active_stores(company_stores, d)
        active_by_format: dict[str, list] = {f: [] for f in profile.STORE_FORMATS}
        for s in active:
            active_by_format[s.store_format].append(s)

        years_elapsed = Decimal(month_idx) / Decimal(12)
        for fmt in profile.STORE_FORMATS:
            fmt_stores = active_by_format[fmt]
            if not fmt_stores:
                continue
            fmt_sales = sum((stores_mod.store_monthly_sales(s, d, rng) for s in fmt_stores), Decimal("0"))
            fmt_sales = money(fmt_sales * Decimal(str(seasonal[d.month])))
            if fmt_sales <= 0:
                continue

            gross = money(fmt_sales / (Decimal("1") - profile.DISCOUNT_RATE))
            discount = money(gross * profile.DISCOUNT_RATE)
            net = money(gross - discount)
            tax = money(net * profile.GST_RATE)
            ledger = coa_by_name[SALES_LEDGER_BY_FORMAT[fmt]]
            post(month_idx, "Sales", "SV", d,
                 [(debtors, net + tax, Decimal(0)), (discount_ledger, discount, Decimal(0)),
                  (ledger, Decimal(0), gross), (gst_output, Decimal(0), tax)],
                 f"Store sales, {fmt}, {period_key(d)}")

            cogs_amt = money(net * (Decimal("1") - gp_margin))
            post(month_idx, "Journal", "JV", d,
                 [(cogs_ledger, cogs_amt, Decimal(0)), (inventory, Decimal(0), cogs_amt)],
                 f"COGS, {fmt} stores, {period_key(d)}")
            month_total_cogs += cogs_amt

            if profile.FRANCHISE_COMMISSION_APPLIES[fmt]:
                commission_amt = money(net * profile.FRANCHISE_COMMISSION_RATE)
                post(month_idx, "Journal", "JV", d,
                     [(coa_by_name["Franchise Commission"], commission_amt, Decimal(0)),
                      (creditors, Decimal(0), commission_amt)],
                     f"Franchise commission, {fmt}, {period_key(d)}")
                outstanding_trade_payable += commission_amt

            rent_annual = profile.STORE_RENT_PER_STORE_ANNUAL * (
                (Decimal("1") + profile.STORE_RENT_GROWTH_YOY) ** years_elapsed) * profile.STORE_RENT_SHARE[fmt]
            personnel_annual = profile.STORE_PERSONNEL_PER_STORE_ANNUAL * (
                (Decimal("1") + profile.STORE_PERSONNEL_GROWTH_YOY) ** years_elapsed) * profile.STORE_PERSONNEL_SHARE[fmt]
            rent_amt = money((rent_annual / 12) * len(fmt_stores))
            personnel_amt = money((personnel_annual / 12) * len(fmt_stores))
            lines = []
            if rent_amt > 0:
                lines.append((coa_by_name["Store Rent, CAM & Utilities"], rent_amt, Decimal(0)))
            if personnel_amt > 0:
                lines.append((coa_by_name["Store Personnel Cost"], personnel_amt, Decimal(0)))
            if lines:
                post(month_idx, "Payment", "JV", d, lines + [(bank, Decimal(0), rent_amt + personnel_amt)],
                     f"Store rent and personnel, {fmt}, {period_key(d)}")

            # Order-file rows: a handful of category-level tickets per store
            # per month, independently noised around the store's GL sales --
            # the deliberate books-vs-order-file gap, per corpus/02 section 3.
            channel_name = "Owned Retail" if fmt in ("COCO", "COFO") else "Franchise Retail"
            for s in fmt_stores:
                store_target = stores_mod.store_monthly_sales(s, d, rng)
                if store_target <= 0:
                    continue
                n_lines = rng.randint(2, 4)
                for _ in range(n_lines):
                    category, occasion, band = _weighted_choice(rng, mix_categories, mix_weights)
                    item_code, item_name = _sku_for_category(category)
                    line_net = money((store_target / n_lines) * Decimal(str(1 + rng.uniform(-0.15, 0.15))))
                    if line_net <= 0:
                        continue
                    line_gross = money(line_net / (Decimal("1") - profile.DISCOUNT_RATE))
                    line_discount = money(line_gross - line_net)
                    order_date = d + timedelta(days=rng.randint(0, 27))
                    order_id = f"ST-{s.store_code}-{order_date.strftime('%y%m%d')}{rng.randint(100, 999)}"
                    order_type = "retention" if s.store_code in seen_customers else "acquisition"
                    seen_customers.add(s.store_code)
                    order_rows[month_idx].append(make_order_row(
                        order_id, order_date, channel_name, s.store_code, item_code, item_name,
                        rng.randint(1, 3), line_gross, line_discount, line_net, Decimal("0"), order_type))

        # ----------------------------------------------------------- online
        for channel_name, channel_sub, tier in profile.ONLINE_CHANNELS:
            monthly_growth = (Decimal("1") + profile.ONLINE_ORDERS_GROWTH_YOY[tier]) ** (Decimal(1) / Decimal(12))
            n_orders = int(profile.ONLINE_STARTING_MONTHLY_ORDERS[tier] * (monthly_growth ** month_idx)
                             * Decimal(str(seasonal[d.month])))
            aov = profile.ONLINE_STARTING_AOV * (
                (Decimal("1") + profile.ONLINE_PRICE_GROWTH_YOY) ** years_elapsed)
            is_marketplace = tier in ("tier1", "tier2")

            channel_net_total = Decimal("0")
            channel_gross_total = Decimal("0")
            channel_discount_total = Decimal("0")
            channel_commission_total = Decimal("0")
            for _ in range(n_orders):
                category, occasion, band = _weighted_choice(rng, mix_categories, mix_weights)
                item_code, item_name = _sku_for_category(category)
                qty = rng.randint(1, 2)
                unit_price = money(aov * Decimal(str(rng.uniform(0.6, 1.4))) / qty)
                gross = money(unit_price * qty)
                discount = money(gross * Decimal(str(rng.uniform(0.02, float(profile.DISCOUNT_RATE) + 0.05))))
                net = money(gross - discount)
                commission = money(net * profile.ONLINE_COMMISSION_RATE) if is_marketplace else Decimal("0")

                order_date = d + timedelta(days=rng.randint(0, 27))
                order_id = f"ON-{channel_sub}-{order_date.strftime('%y%m%d')}{rng.randint(1000, 9999)}"
                customer_code = f"CUST{rng.randint(10000, 49999)}"
                order_type = "retention" if customer_code in seen_customers else "acquisition"
                seen_customers.add(customer_code)
                order_rows[month_idx].append(make_order_row(
                    order_id, order_date, channel_name, channel_sub, item_code, item_name,
                    qty, gross, discount, net, commission, order_type))

                channel_net_total += net
                channel_gross_total += gross
                channel_discount_total += discount
                channel_commission_total += commission

            if channel_gross_total <= 0:
                continue
            tax = money(channel_gross_total * profile.GST_RATE)
            ledger = coa_by_name[SALES_LEDGER_BY_ONLINE_CHANNEL[channel_name]]
            post(month_idx, "Sales", "SV", d,
                 [(debtors, money(channel_net_total) + tax, Decimal(0)),
                  (discount_ledger, money(channel_discount_total), Decimal(0)),
                  (ledger, Decimal(0), money(channel_gross_total)), (gst_output, Decimal(0), tax)],
                 f"Online sales, {channel_name}, {period_key(d)}")
            cogs_amt = money(channel_net_total * (Decimal("1") - gp_margin))
            post(month_idx, "Journal", "JV", d,
                 [(cogs_ledger, cogs_amt, Decimal(0)), (inventory, Decimal(0), cogs_amt)],
                 f"COGS, {channel_name}, {period_key(d)}")
            month_total_cogs += cogs_amt
            if channel_commission_total > 0:
                commission_amt = money(channel_commission_total)
                post(month_idx, "Journal", "JV", d,
                     [(coa_by_name["Marketplace Commission Borne"], commission_amt, Decimal(0)),
                      (coa_by_name["Marketplace Payable"], Decimal(0), commission_amt)],
                     f"Marketplace commission, {channel_name}, {period_key(d)}")
                outstanding_marketplace_payable += commission_amt
            ad_spend = money(channel_net_total * profile.ONLINE_AD_SPEND_PCT_OF_SALES)
            if ad_spend > 0:
                post(month_idx, "Payment", "JV", d,
                     [(coa_by_name["Online Advertising Spend"], ad_spend, Decimal(0)), (bank, Decimal(0), ad_spend)],
                     f"Online advertising, {channel_name}, {period_key(d)}")

        # ---------------------------------------------------- company-level
        ho_annual = profile.HO_EMPLOYEE_COST_START_ANNUAL * ((Decimal("1") + profile.HO_COST_GROWTH_YOY) ** years_elapsed)
        warehouse_annual = profile.WAREHOUSE_COST_START_ANNUAL * ((Decimal("1") + profile.HO_COST_GROWTH_YOY) ** years_elapsed)
        admin_annual = profile.ADMIN_COST_START_ANNUAL * ((Decimal("1") + profile.HO_COST_GROWTH_YOY) ** years_elapsed)
        ho_amt, wh_amt, admin_amt = money(ho_annual / 12), money(warehouse_annual / 12), money(admin_annual / 12)
        post(month_idx, "Payment", "JV", d,
             [(coa_by_name["HO Employee Cost"], ho_amt, Decimal(0)),
              (coa_by_name["Warehouse Cost"], wh_amt, Decimal(0)),
              (coa_by_name["Admin Expenses"], admin_amt, Decimal(0)),
              (bank, Decimal(0), ho_amt + wh_amt + admin_amt)],
             f"Corporate overhead, {period_key(d)}")

        # ---------------------------------------------- working capital settlement
        # Each of the three balances below is opening (whatever wasn't
        # cleared last month) plus this month's new activity, with a high
        # fraction collected/paid down and only a small aging tail carried
        # forward -- see the module-level comment above the month loop.
        if month_total_cogs > 0:
            target_inventory = money(month_total_cogs * TARGET_INVENTORY_MONTHS_COVER)
            purchase_amt = money(month_total_cogs + (target_inventory - outstanding_inventory) * Decimal("0.5"))
            purchase_amt = max(purchase_amt, money(month_total_cogs * Decimal("0.5")))
            post(month_idx, "Journal", "JV", d,
                 [(inventory, purchase_amt, Decimal(0)), (creditors, Decimal(0), purchase_amt)],
                 f"Inventory purchase, {period_key(d)}")
            outstanding_inventory += purchase_amt - month_total_cogs
            outstanding_trade_payable += purchase_amt

        total_receivable = sum(
            (Decimal(r["net_amount"]) + money(Decimal(r["net_amount"]) * profile.GST_RATE)
              for r in order_rows[month_idx]), Decimal("0"))
        outstanding_ar += total_receivable
        collected = money(outstanding_ar * Decimal(str(rng.uniform(0.90, 0.98))))
        if collected > 0:
            post(month_idx, "Receipt", "RC", d, [(bank, collected, Decimal(0)), (debtors, Decimal(0), collected)],
                 f"Collections, {period_key(d)}")
            outstanding_ar -= collected

        paid_creditors = money(outstanding_trade_payable * Decimal(str(rng.uniform(0.85, 0.95))))
        if paid_creditors > 0:
            post(month_idx, "Payment", "PY", d, [(creditors, paid_creditors, Decimal(0)), (bank, Decimal(0), paid_creditors)],
                 f"Payments to suppliers and franchise partners, {period_key(d)}")
            outstanding_trade_payable -= paid_creditors

        paid_marketplace = money(outstanding_marketplace_payable * Decimal(str(rng.uniform(0.85, 0.95))))
        if paid_marketplace > 0:
            post(month_idx, "Payment", "PY", d,
                 [(coa_by_name["Marketplace Payable"], paid_marketplace, Decimal(0)), (bank, Decimal(0), paid_marketplace)],
                 f"Marketplace payable settlement, {period_key(d)}")
            outstanding_marketplace_payable -= paid_marketplace

    _build_tb(tb_rows, gl_rows, coa, months)
    store_rows = [{
        "store_code": s.store_code, "store_name": s.store_name, "store_format": s.store_format,
        "city": s.city, "state": s.state, "site_type": s.site_type, "area_sqft": s.area_sqft,
        "opening_date": s.opening_date.isoformat(),
        "closure_date": s.closure_date.isoformat() if s.closure_date else "",
        "status": s.status,
    } for s in company_stores]

    return ApparelCompanyData(coa=coa, months=months, stores=company_stores, gl_rows=gl_rows,
                                  order_rows=order_rows, tb_rows=tb_rows, store_rows=store_rows,
                                  defect_log=defect_log)


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
