"""The core simulation for the synthetic consumer brand: builds a small GL/TB
(the books) and the Consumer Sales order file independently enough that a
genuine, unexplained residual exists between them, per corpus/11 section 2.3
and corpus/02 section 3 ("the gap between them is reported as a residual
without explanation"). Seeds defect #12 (a line with revenue and zero COGS).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from synthetic.common import Rng, fiscal_year_of, money, month_end, month_range, period_key
from synthetic.defects import DEFECTS
from synthetic.consumer import profile

ITEMS = [
    ("CI-1001", "Cold Brew Concentrate 500ml", "Beverages"),
    ("CI-1002", "Herbal Green Tea 100g", "Beverages"),
    ("CI-1003", "Protein Bar Box of 6", "Snacks"),
    ("CI-1004", "Organic Muesli 500g", "Breakfast"),
    ("CI-1005", "Cold Pressed Almond Oil 200ml", "Wellness"),
    ("CI-1006", "Ayurvedic Immunity Kit", "Wellness"),
    ("CI-1007", "Reusable Steel Bottle 750ml", "Lifestyle"),
    ("CI-1008", "Brightleaf Data Insights Subscription", "Digital"),  # defect #12: zero COGS by design
]

COA_LEDGERS = [
    ("Sales - Own Website", "Sales Accounts", "Income", "revenue"),
    ("Sales - Marketplace Amazon", "Sales Accounts", "Income", "revenue"),
    ("Sales - Marketplace Flipkart", "Sales Accounts", "Income", "revenue"),
    ("Sales - Quick Commerce Blinkit", "Sales Accounts", "Income", "revenue"),
    ("Sales - Owned Retail", "Sales Accounts", "Income", "revenue"),
    ("Sales Returns", "Sales Accounts", "Income", "contra_revenue"),
    ("Discount Allowed", "Sales Accounts", "Income", "contra_revenue"),
    ("COGS - Finished Goods", "Cost of Goods Sold", "Expense", "cogs"),
    ("Fulfilment Cost", "Operating Cost", "Expense", "opex_cm1"),
    ("Servicing Cost", "Operating Cost", "Expense", "opex_cm1"),
    ("Marketplace Commission Borne", "Operating Cost", "Expense", "opex_cm1"),
    ("Marketing & Advertising", "Marketing", "Expense", "marketing"),
    ("Marketplace Revenue Earned", "Sales Accounts", "Income", "revenue"),
    ("Corporate Overhead", "Corporate", "Expense", "overhead"),
    ("Employee Cost", "Corporate", "Expense", "overhead"),
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
class ConsumerCompanyData:
    coa: list[Ledger]
    months: list[date]
    gl_rows: dict[int, list[dict]]
    order_rows: dict[int, list[dict]]
    tb_rows: dict[int, list[dict]]
    defect_log: DefectLog


class VoucherCounter:
    def __init__(self):
        self._n = itertools.count(1)

    def next(self, prefix: str, d: date) -> str:
        return f"{prefix}/{d.strftime('%y%m')}/{next(self._n):04d}"


def build_consumer_company(seed: int) -> ConsumerCompanyData:
    rng = Rng(seed + 1)  # distinct stream from the manufacturer, still deterministic
    coa = [Ledger(f"{5000+i}", name, group, atype, role) for i, (name, group, atype, role) in enumerate(COA_LEDGERS)]
    coa_by_name = {l.account_name: l for l in coa}
    months = month_range(profile.FISCAL_START, profile.N_MONTHS)
    vseq = VoucherCounter()
    defect_log = DefectLog()

    gl_rows: dict[int, list[dict]] = {i: [] for i in range(len(months))}
    order_rows: dict[int, list[dict]] = {i: [] for i in range(len(months))}
    tb_rows: dict[int, list[dict]] = {i: [] for i in range(len(months))}

    channel_ledger = {
        "Own Website": coa_by_name["Sales - Own Website"],
        "Marketplace - Amazon": coa_by_name["Sales - Marketplace Amazon"],
        "Marketplace - Flipkart": coa_by_name["Sales - Marketplace Flipkart"],
        "Quick Commerce - Blinkit": coa_by_name["Sales - Quick Commerce Blinkit"],
        "Owned Retail - Store1": coa_by_name["Sales - Owned Retail"],
    }
    channel_weight = {c[0]: w for c, w in zip(profile.CHANNELS, [Decimal("0.30"), Decimal("0.25"),
                                                                     Decimal("0.20"), Decimal("0.15"), Decimal("0.10")])}
    seasonal = {4: 0.95, 5: 0.92, 6: 0.95, 7: 1.0, 8: 1.0, 9: 1.05, 10: 1.2, 11: 1.15, 12: 1.1, 1: 0.9, 2: 0.9, 3: 1.1}

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

    DEFECT_ZERO_COGS_MONTH = 6
    pending_returns: list[tuple] = []  # (return_month_idx, order_row)
    seen_customers: set[str] = set()  # first appearance -> 'acquisition', repeat -> 'retention'

    for month_idx, d in enumerate(months):
        gmv_target = money((profile.ANNUAL_GMV / 12) * Decimal(str(seasonal[d.month])) *
                             Decimal(str(1 + rng.uniform(-0.05, 0.05))))

        debtors = coa_by_name["Sundry Debtors"]
        bank = coa_by_name["Cash and Bank - Current A/c"]
        gst_output = coa_by_name["GST Output Payable"]
        cogs_ledger = coa_by_name["COGS - Finished Goods"]
        inventory = coa_by_name["Inventory - Finished Goods"]

        month_channel_net: dict[str, Decimal] = {}
        # channel_commission_model drives the GL treatment below (COGS vs a
        # commission-borne expense, D-004) -- a channel-fee concept, not
        # D-061's revenue_model. Brightleaf owns this inventory on every one
        # of these channels (it has its own COGS/Inventory ledgers), so
        # D-061's revenue_model on the order-file row is 'buyout' for all of
        # them regardless of which channel_commission_model applies to the
        # channel-fee cost side. Genuine D-061 marketplace-model rows (where
        # Brightleaf is the platform, not the seller) are generated
        # separately below, in the Brightleaf Marketplace vertical.
        for channel_name, channel_sub, channel_commission_model in profile.CHANNELS:
            channel_gmv = money(gmv_target * channel_weight[channel_name])
            n_orders = rng.randint(15, 30)
            channel_net_for_gl = Decimal("0")
            channel_gross_for_gl = Decimal("0")
            channel_discount_for_gl = Decimal("0")
            for _ in range(n_orders):
                item_code, item_name, category = rng.choice(ITEMS)
                is_zero_cogs_item = item_code == "CI-1008"
                qty = rng.randint(1, 4)
                unit_price = Decimal(str(rng.uniform(150, 1800)))
                gross = money(unit_price * qty)
                discount = money(gross * Decimal(str(rng.uniform(0, 0.15))))
                net_amount = money(gross - discount)
                shipping_charged = money(Decimal(str(rng.uniform(0, 60))))
                commission = money(net_amount * Decimal("0.18")) if channel_commission_model == "marketplace" else Decimal("0")
                shipping_cost = money(Decimal(str(rng.uniform(30, 90))))
                payment_fee = money(net_amount * Decimal(str(rng.uniform(0.01, 0.02))))

                order_date = d + timedelta(days=rng.randint(0, 27))
                order_id = f"ORD-{order_date.strftime('%y%m%d')}{rng.randint(1000, 9999)}"
                is_return = rng.random() < 0.06
                return_date = None
                if is_return:
                    # Defect: returns arrive in a LATER period than the sale.
                    lag_days = rng.randint(20, 55)
                    return_date = order_date + timedelta(days=lag_days)

                customer_code = f"CUST{rng.randint(1000, 4999)}"
                order_type = "retention" if customer_code in seen_customers else "acquisition"
                seen_customers.add(customer_code)

                row = {
                    "order_id": order_id, "order_date": order_date.isoformat(),
                    "channel": channel_name, "channel_sub": channel_sub,
                    "customer_code": customer_code,
                    "item_code": item_code, "item_name": item_name, "quantity": str(qty),
                    "gross_amount": str(gross), "discount_amount": str(discount),
                    "net_amount": str(net_amount), "shipping_charged": str(shipping_charged),
                    "commission_amount": str(commission), "shipping_cost": str(shipping_cost),
                    "payment_fee": str(payment_fee), "return_flag": "Yes" if is_return else "No",
                    "return_date": return_date.isoformat() if return_date else "",
                    "return_reason": (rng.choice(["Size issue", "Damaged in transit", "Not as described",
                                                    "Changed mind"]) if is_return else ""),
                    "settlement_date": (order_date + timedelta(days=rng.randint(7, 21))).isoformat(),
                    "revenue_model": "buyout", "order_type": order_type,
                    "commission_earned": "0.00", "advertising_earned": "0.00", "platform_fee_earned": "0.00",
                }
                order_rows[month_idx].append(row)

                if month_idx == DEFECT_ZERO_COGS_MONTH and is_zero_cogs_item and not any(
                        e["defect_id"] == 12 for e in defect_log.entries):
                    defect_log.record(12, month=period_key(d), order_id=order_id, item_code=item_code,
                                        note="Revenue with zero COGS -- correct for a digital product, must not raise an anomaly")

                channel_net_for_gl += net_amount
                channel_gross_for_gl += gross
                channel_discount_for_gl += discount

            month_channel_net[channel_name] = channel_net_for_gl

            # GL revenue voucher for this channel, independent of the order
            # file's own totals by a small residual noise factor -- this is
            # the deliberate books-vs-order-file gap, per corpus/02 section 3.
            # Per corpus/08 section 4.1's ladder (GMV -> less GST -> Gross
            # revenue -> less Discount -> Net revenue): GMV is the GST-inclusive
            # transacted value computed on the pre-discount gross, so GST here
            # is booked on gross_channel, not on the post-discount taxable
            # value -- a deliberate, self-consistent choice for this fictional
            # company's books (not a real-world GST rule), made so the ladder's
            # own arithmetic (GMV - GST = Gross revenue) holds exactly.
            noise = Decimal(str(1 + rng.uniform(-0.06, 0.06)))
            gl_gross = money(channel_gross_for_gl * noise)
            gl_discount = money(channel_discount_for_gl * noise)
            gl_net = money(gl_gross - gl_discount)
            gl_tax = money(gl_gross * profile.GST_RATE)
            ledger = channel_ledger[channel_name]
            discount_ledger = coa_by_name["Discount Allowed"]
            channel_commission_model = next(rm for cn, cs, rm in profile.CHANNELS if cn == channel_name)
            lines = [
                (debtors, gl_net + gl_tax, Decimal(0)),
                (discount_ledger, gl_discount, Decimal(0)),
                (ledger, Decimal(0), gl_gross),
                (gst_output, Decimal(0), gl_tax),
            ]
            post(month_idx, "Sales", "SV", d, lines, f"Sales booked for {channel_name}, {period_key(d)}")

            if channel_commission_model == "buyout":
                cogs_amt = money(gl_net * Decimal("0.42"))
                post(month_idx, "Journal", "JV", d,
                     [(cogs_ledger, cogs_amt, Decimal(0)), (inventory, Decimal(0), cogs_amt)],
                     f"COGS for {channel_name}, {period_key(d)}")
            else:
                commission_amt = money(gl_net * Decimal("0.18"))
                post(month_idx, "Journal", "JV", d,
                     [(coa_by_name["Marketplace Commission Borne"], commission_amt, Decimal(0)),
                      (coa_by_name["Marketplace Payable"], Decimal(0), commission_amt)],
                     f"Marketplace commission, {channel_name}, {period_key(d)}")

        # Brightleaf Marketplace: a genuine D-061 marketplace-revenue-model
        # vertical, distinct from the channel-fee "marketplace" tag above.
        # Here Brightleaf is the platform -- third-party sellers list and
        # transact, Brightleaf never owns that inventory, and per D-061
        # revenue is commission_earned + advertising_earned +
        # platform_fee_earned, never the GMV itself. This is what the
        # acceptance test (marketplace GMV never summed into revenue) needs
        # real data for -- the channel-fee "marketplace" rows above are all
        # tagged revenue_model='buyout' and do not exercise this path.
        n_marketplace_orders = rng.randint(40, 70)
        marketplace_earned_total = Decimal("0")
        for _ in range(n_marketplace_orders):
            item_code, item_name, category = rng.choice(ITEMS)
            qty = rng.randint(1, 3)
            unit_price = Decimal(str(rng.uniform(150, 1800)))
            third_party_gmv = money(unit_price * qty)  # the SELLER's revenue, not ours
            commission_earned = money(third_party_gmv * Decimal(str(rng.uniform(0.08, 0.15))))
            advertising_earned = money(third_party_gmv * Decimal(str(rng.uniform(0.005, 0.02))))
            platform_fee_earned = money(Decimal(str(rng.uniform(5, 25))))  # flat per-order listing fee

            order_date = d + timedelta(days=rng.randint(0, 27))
            order_id = f"MKT-{order_date.strftime('%y%m%d')}{rng.randint(1000, 9999)}"
            customer_code = f"CUST{rng.randint(1000, 4999)}"
            order_type = "retention" if customer_code in seen_customers else "acquisition"
            seen_customers.add(customer_code)

            order_rows[month_idx].append({
                "order_id": order_id, "order_date": order_date.isoformat(),
                "channel": "Brightleaf Marketplace", "channel_sub": "THIRD-PARTY-SELLER",
                "customer_code": customer_code,
                "item_code": item_code, "item_name": item_name, "quantity": str(qty),
                "gross_amount": str(third_party_gmv), "discount_amount": "0.00",
                "net_amount": "0.00",  # revenue_model='marketplace' uses the *_earned columns, not net_amount
                "shipping_charged": "0.00", "commission_amount": "0.00", "shipping_cost": "0.00",
                "payment_fee": "0.00", "return_flag": "No", "return_date": "", "return_reason": "",
                "settlement_date": (order_date + timedelta(days=rng.randint(7, 21))).isoformat(),
                "revenue_model": "marketplace", "order_type": order_type,
                "commission_earned": str(commission_earned), "advertising_earned": str(advertising_earned),
                "platform_fee_earned": str(platform_fee_earned),
            })
            marketplace_earned_total += commission_earned + advertising_earned + platform_fee_earned

        if marketplace_earned_total > 0:
            marketplace_gst = money(marketplace_earned_total * profile.GST_RATE)
            post(month_idx, "Sales", "SV", d,
                 [(bank, marketplace_earned_total + marketplace_gst, Decimal(0)),
                  (coa_by_name["Marketplace Revenue Earned"], Decimal(0), marketplace_earned_total),
                  (gst_output, Decimal(0), marketplace_gst)],
                 f"Marketplace platform revenue earned, {period_key(d)}")

        # collections (simplified: settled same-month via bank, netting debtors)
        total_gross_receivable = sum(
            (Decimal(r["net_amount"]) + money(Decimal(r["net_amount"]) * profile.GST_RATE)
              for r in order_rows[month_idx]), Decimal("0"))
        collected = money(total_gross_receivable * Decimal(str(rng.uniform(0.85, 0.98))))
        if collected > 0:
            post(month_idx, "Receipt", "RC", d, [(bank, collected, Decimal(0)), (debtors, Decimal(0), collected)],
                 f"Collections, {period_key(d)}")

        # opex, marketing, overhead
        opex_target = money(gmv_target * Decimal("0.06"))
        marketing_target = money(gmv_target * Decimal("0.09"))
        overhead_target = money(gmv_target * Decimal("0.05"))
        bank2 = coa_by_name["Cash and Bank - Current A/c"]
        fulfilment_amt = money(opex_target * Decimal("0.5"))
        servicing_amt = money(opex_target - fulfilment_amt)  # exact complement, no independent-rounding gap
        post(month_idx, "Payment", "JV", d,
             [(coa_by_name["Fulfilment Cost"], fulfilment_amt, Decimal(0)),
              (coa_by_name["Servicing Cost"], servicing_amt, Decimal(0)),
              (bank2, Decimal(0), opex_target)],
             f"Operating cost, {period_key(d)}")
        post(month_idx, "Payment", "JV", d,
             [(coa_by_name["Marketing & Advertising"], marketing_target, Decimal(0)), (bank2, Decimal(0), marketing_target)],
             f"Marketing spend, {period_key(d)}")
        employee_amt = money(overhead_target * Decimal("0.6"))
        admin_amt = money(overhead_target - employee_amt)  # exact complement
        post(month_idx, "Payment", "JV", d,
             [(coa_by_name["Employee Cost"], employee_amt, Decimal(0)),
              (coa_by_name["Admin Expenses"], admin_amt, Decimal(0)),
              (bank2, Decimal(0), overhead_target)],
             f"Corporate overhead, {period_key(d)}")

    _build_tb(tb_rows, gl_rows, coa, months)

    return ConsumerCompanyData(coa=coa, months=months, gl_rows=gl_rows, order_rows=order_rows,
                                  tb_rows=tb_rows, defect_log=defect_log)


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
