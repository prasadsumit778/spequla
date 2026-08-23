"""The full consumer contribution margin ladder, corpus/03 section 7 and
corpus/08 section 4.1, built from fact_channel_order_line (sprint 6) rather
than Sprint 5's fact_gl_entry-only placeholder in src/reports/pnl.py.

**Why two sources, not one.** fact_channel_order_line is the operational
truth (per order, per channel, per revenue model) but carries no cost-of-
goods, marketing or corporate-overhead field at all -- those live only in
the books (fact_gl_entry). corpus/04's own note on the relationship between
the two tables: "They are deliberately not merged. The books are the
accounting truth, the order file is the operational truth, and the gap
between them is reported as a residual rather than resolved by picking a
winner." This module follows that split literally: GMV, discount, and
net revenue by revenue model come from the order file (the only place
revenue_model, commission_earned etc. exist); COGS, marketing and
corporate overhead come from the GL (the only place those classes exist).
compute_order_file_to_books_residual reports the resulting gap, never
resolves it.

**D-061, applied without exception.** Marketplace lines contribute to GMV
(memo only) and to revenue via commission_earned + advertising_earned +
platform_fee_earned -- gross_amount (their GMV) never enters net_revenue,
gross_margin or any subtotal below it. Buyout lines use net_amount, already
discount-adjusted at generation (see corpus/04 section 3.5's own comment on
the two columns), so `Discount` is shown as its own disclosed line item
without being re-subtracted from net_revenue a second time.

**D-062, applied without exception.** corporate_overhead is a single
entity-level GL figure (opex.admin_general + opex.employee_cost, matching
statement_lines.py's existing consumer taxonomy choice) subtracted once,
after CM2. There is no channel, product or business-unit dimension on this
figure anywhere in this module -- 'never allocated' is enforced by never
having a per-dimension corporate_overhead value to allocate from in the
first place, not by a rule that discards one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from src.reports.query import class_movements

# D-004 + D-014: commission and payment-gateway/COD fees borne are COGS-side
# ("a cost above gross profit"), buyout lines only -- marketplace lines have
# no cost of goods by definition (D-061).
_CHANNEL_COMMISSION_COGS_FIELDS = ("commission_amount", "payment_fee")
# D-060/D-020: fulfilment sits in operating cost above CM1, not COGS.
_FULFILMENT_OPERATING_COST_FIELDS = ("shipping_cost",)

# GL-sourced classes (fact_channel_order_line has no field for any of these).
_GL_COGS_CLASSES = ["cogs.raw_material"]
_GL_OPERATING_COST_CM1_CLASSES = ["opex.selling_distribution"]  # servicing/offline manpower/rent
_GL_MARKETING_CLASSES = ["opex.marketing_advertising"]
_GL_CORPORATE_OVERHEAD_CLASSES = ["opex.admin_general", "opex.employee_cost"]


@dataclass
class ConsumerLadderResult:
    period_start: date
    period_end: date
    gmv_total: Decimal = Decimal("0")
    gmv_by_model: dict[str, Decimal] = field(default_factory=dict)  # memo only -- never summed into revenue
    discount: Decimal = Decimal("0")
    net_revenue: Decimal = Decimal("0")
    net_revenue_by_model: dict[str, Decimal] = field(default_factory=dict)
    cogs: Decimal = Decimal("0")
    gross_margin: Decimal = Decimal("0")
    gross_margin_pct: Decimal | None = None
    operating_cost_cm1: Decimal = Decimal("0")
    cm1: Decimal = Decimal("0")
    cm1_pct: Decimal | None = None
    marketing: Decimal = Decimal("0")
    cm2: Decimal = Decimal("0")
    cm2_pct: Decimal | None = None
    corporate_overhead: Decimal = Decimal("0")
    ebitda: Decimal = Decimal("0")
    unmapped_value_inr: Decimal = Decimal("0")


def _order_line_aggregates(conn, schema: str, tenant_id: str, entity_id: int,
                              date_from: date, date_to: date) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT revenue_model, '
            f'       SUM(gross_amount), SUM(discount_amount), SUM(net_amount), '
            f'       SUM(commission_earned), SUM(advertising_earned), SUM(platform_fee_earned), '
            f'       SUM(commission_amount), SUM(payment_fee), SUM(shipping_cost) '
            f'FROM "{schema}".fact_channel_order_line '
            f'WHERE tenant_id = %s AND entity_id = %s AND is_current AND event_date BETWEEN %s AND %s '
            f'GROUP BY revenue_model',
            (tenant_id, entity_id, date_from, date_to),
        )
        return cur.fetchall()


def compute_consumer_ladder(order_aggregates: list[tuple], gl_movements: dict[str, Decimal],
                                period_start: date, period_end: date) -> ConsumerLadderResult:
    """Pure: takes the order-file aggregates (one row per revenue_model,
    matching _order_line_aggregates's shape) and the GL class movements
    (matching src/reports/query.class_movements's shape), computes the
    full ladder. Split out from the DB-fetching wrapper so the D-061/D-062
    arithmetic is unit-testable without a live connection, same pattern as
    src/reports/pnl.py."""
    result = ConsumerLadderResult(period_start=period_start, period_end=period_end)

    channel_commission_cogs = Decimal("0")
    fulfilment_operating_cost = Decimal("0")

    for row in order_aggregates:
        (revenue_model, gross_amount, discount_amount, net_amount, commission_earned, advertising_earned,
          platform_fee_earned, commission_amount, payment_fee, shipping_cost) = row
        gross_amount = gross_amount or Decimal("0")
        result.gmv_total += gross_amount
        result.gmv_by_model[revenue_model] = result.gmv_by_model.get(revenue_model, Decimal("0")) + gross_amount

        if revenue_model == "buyout":
            revenue = net_amount or Decimal("0")
            result.discount += discount_amount or Decimal("0")
            channel_commission_cogs += (commission_amount or Decimal("0")) + (payment_fee or Decimal("0"))
            fulfilment_operating_cost += shipping_cost or Decimal("0")
        else:  # marketplace, D-061: revenue is commission + advertising + platform fee, NEVER the GMV
            revenue = (commission_earned or Decimal("0")) + (advertising_earned or Decimal("0")) \
                       + (platform_fee_earned or Decimal("0"))
            # marketplace COGS is none by definition -- nothing added to channel_commission_cogs here

        result.net_revenue += revenue
        result.net_revenue_by_model[revenue_model] = result.net_revenue_by_model.get(revenue_model, Decimal("0")) + revenue

    gl_cogs = sum((gl_movements.get(c, Decimal("0")) for c in _GL_COGS_CLASSES), Decimal("0"))
    result.cogs = gl_cogs + channel_commission_cogs
    result.gross_margin = result.net_revenue - result.cogs
    result.gross_margin_pct = (result.gross_margin / result.net_revenue) if result.net_revenue else None

    gl_opex_cm1 = sum((gl_movements.get(c, Decimal("0")) for c in _GL_OPERATING_COST_CM1_CLASSES), Decimal("0"))
    result.operating_cost_cm1 = gl_opex_cm1 + fulfilment_operating_cost
    result.cm1 = result.gross_margin - result.operating_cost_cm1
    result.cm1_pct = (result.cm1 / result.net_revenue) if result.net_revenue else None

    result.marketing = sum((gl_movements.get(c, Decimal("0")) for c in _GL_MARKETING_CLASSES), Decimal("0"))
    result.cm2 = result.cm1 - result.marketing
    result.cm2_pct = (result.cm2 / result.net_revenue) if result.net_revenue else None

    # D-062: never allocated -- one entity-level figure, subtracted once, no dimension to allocate by.
    result.corporate_overhead = sum((gl_movements.get(c, Decimal("0")) for c in _GL_CORPORATE_OVERHEAD_CLASSES),
                                        Decimal("0"))
    result.ebitda = result.cm2 - result.corporate_overhead

    result.unmapped_value_inr = abs(gl_movements.get("suspense.unmapped", Decimal("0")))
    return result


def assemble_consumer_ladder(conn, schema: str, tenant_id: str, entity_id: int, mapping_version_id: int,
                                 period_start: date, period_end: date) -> ConsumerLadderResult:
    order_aggregates = _order_line_aggregates(conn, schema, tenant_id, entity_id, period_start, period_end)
    gl_movements = class_movements(conn, schema, tenant_id, entity_id, mapping_version_id, period_start, period_end)
    return compute_consumer_ladder(order_aggregates, gl_movements, period_start, period_end)


@dataclass
class OrderFileToBooksResidual:
    period_start: date
    period_end: date
    order_file_buyout_revenue: Decimal
    books_revenue: Decimal
    residual: Decimal


def compute_order_file_to_books_residual(order_file_buyout_revenue: Decimal,
                                             books_revenue_product_sales: Decimal,
                                             period_start: date, period_end: date) -> OrderFileToBooksResidual:
    """corpus/04 section 3.5's note: 'the gap between them is reported as a
    residual rather than resolved by picking a winner.' Compared against
    the order file's BUYOUT revenue only -- marketplace commission revenue
    has its own separate GL ledger (not revenue.product_sales) in this
    company's books, so comparing it against product_sales would conflate
    two different revenue streams rather than measure the genuine
    order-file-vs-books gap on the same one. Never resolved: this function
    only reports the number, nothing here decides which source is right."""
    residual = order_file_buyout_revenue - books_revenue_product_sales
    return OrderFileToBooksResidual(period_start, period_end, order_file_buyout_revenue,
                                        books_revenue_product_sales, residual)


def assemble_order_file_to_books_residual(conn, schema: str, tenant_id: str, entity_id: int,
                                              mapping_version_id: int, period_start: date,
                                              period_end: date) -> OrderFileToBooksResidual:
    order_aggregates = _order_line_aggregates(conn, schema, tenant_id, entity_id, period_start, period_end)
    order_file_buyout_revenue = sum(
        (row[3] or Decimal("0") for row in order_aggregates if row[0] == "buyout"), Decimal("0"))  # net_amount
    gl_movements = class_movements(conn, schema, tenant_id, entity_id, mapping_version_id, period_start, period_end)
    books_revenue = -gl_movements.get("revenue.product_sales", Decimal("0"))  # Cr-negative -> presentation-positive
    return compute_order_file_to_books_residual(order_file_buyout_revenue, books_revenue, period_start, period_end)
