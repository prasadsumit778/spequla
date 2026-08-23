"""Pure-arithmetic tests for the sprint 6 consumer CM ladder, corpus/03
section 7 and corpus/08 section 4.1. No DB needed -- operates on hand-built
order-aggregate tuples and a GL movements dict, same shapes
assemble_consumer_ladder's DB-fetching wrapper would produce."""
from datetime import date
from decimal import Decimal

from src.reports.consumer_ladder import compute_consumer_ladder

D = Decimal
PS, PE = date(2026, 4, 1), date(2026, 4, 30)

# order_aggregates row shape: (revenue_model, gross_amount, discount_amount,
# net_amount, commission_earned, advertising_earned, platform_fee_earned,
# commission_amount, payment_fee, shipping_cost)


def test_marketplace_gmv_never_summed_into_revenue():
    order_aggregates = [
        ("buyout", D("100000"), D("5000"), D("95000"), D("0"), D("0"), D("0"), D("2000"), D("1000"), D("3000")),
        ("marketplace", D("500000"), D("0"), D("0"), D("40000"), D("8000"), D("2000"), D("0"), D("0"), D("0")),
    ]
    r = compute_consumer_ladder(order_aggregates, {}, PS, PE)
    assert r.gmv_total == D("600000")            # both models' GMV, memo only
    assert r.gmv_by_model["marketplace"] == D("500000")
    # net revenue is buyout's net_amount PLUS marketplace's earned components --
    # the 500,000 marketplace GMV must not appear anywhere in this sum.
    assert r.net_revenue == D("95000") + D("40000") + D("8000") + D("2000")
    assert r.net_revenue == D("145000")
    assert D("500000") not in (r.net_revenue,)  # the GMV figure itself never equals revenue


def test_marketplace_line_has_zero_cogs_and_full_margin_raises_no_anomaly():
    # a channel that is ENTIRELY marketplace-model: no COGS field is ever
    # summed for it (D-061: "COGS: none, gross margin effectively 100%").
    order_aggregates = [
        ("marketplace", D("200000"), D("0"), D("0"), D("18000"), D("3000"), D("1000"), D("0"), D("0"), D("0")),
    ]
    r = compute_consumer_ladder(order_aggregates, {}, PS, PE)
    assert r.cogs == D("0")
    assert r.net_revenue == D("22000")
    assert r.gross_margin == r.net_revenue           # 100% margin, by construction
    assert r.gross_margin_pct == D("1")               # not flagged, not clamped, not hidden -- just correct


def test_corporate_overhead_is_a_single_unallocated_figure():
    # D-062: never allocated. There is no per-channel or per-product
    # corporate_overhead anywhere on the result -- it is one Decimal.
    order_aggregates = [
        ("buyout", D("100000"), D("0"), D("100000"), D("0"), D("0"), D("0"), D("0"), D("0"), D("0")),
    ]
    gl_movements = {"opex.admin_general": D("8000"), "opex.employee_cost": D("12000")}
    r = compute_consumer_ladder(order_aggregates, gl_movements, PS, PE)
    assert isinstance(r.corporate_overhead, Decimal)
    assert r.corporate_overhead == D("20000")
    assert r.ebitda == r.cm2 - D("20000")


def test_buyout_discount_disclosed_but_not_double_subtracted():
    # net_amount already reflects gross - discount at the source, so
    # discount is shown as its own line without being subtracted again.
    order_aggregates = [
        ("buyout", D("100000"), D("15000"), D("85000"), D("0"), D("0"), D("0"), D("0"), D("0"), D("0")),
    ]
    r = compute_consumer_ladder(order_aggregates, {}, PS, PE)
    assert r.discount == D("15000")
    assert r.net_revenue == D("85000")  # not 85000 - 15000


def test_channel_commission_and_payment_fee_are_cogs_buyout_only():
    # D-004 + D-014: commission borne and payment/COD fees sit in COGS for
    # buyout lines; shipping sits in operating cost (D-060), not COGS.
    order_aggregates = [
        ("buyout", D("100000"), D("0"), D("100000"), D("0"), D("0"), D("0"), D("4000"), D("1500"), D("2500")),
    ]
    r = compute_consumer_ladder(order_aggregates, {}, PS, PE)
    assert r.cogs == D("4000") + D("1500")     # commission_amount + payment_fee
    assert r.operating_cost_cm1 == D("2500")     # shipping_cost only
