"""Reads the forecast engine's starting point off real mapped canonical
facts, corpus/13 section 4. Nothing here computes a forecast -- this module
only observes what already happened, the same read-only posture as
src/reports/query.py, which it's built on.

Per-store-per-format cost detail (e.g. "COCO stores' rent specifically")
is NOT split out here even though corpus/13's mechanics distinguish it by
format: opex.store_rent/opex.store_personnel are single canonical classes
covering every format's stores together (corpus/06 section 3.3), so a
format-level split would be an invented allocation, not an observed fact --
same reasoning src/reports/manufacturing_operating.py already documents for
why it doesn't split company-wide cost by product. Baseline reports a
blended per-store average instead; engine.py applies it uniformly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from src.reports.pnl import compute_consumer_cm_ladder
from src.reports.query import class_movements
from src.semantic.formula import natural_positive


@dataclass
class BaselineStore:
    store_code: str
    store_format: str
    opening_date: date


@dataclass
class BaselineOnlineChannel:
    channel_name: str
    monthly_orders: Decimal
    aov: Decimal


@dataclass
class Baseline:
    as_of: date
    trailing_months: int
    stores: list[BaselineStore] = field(default_factory=list)
    online_channels: list[BaselineOnlineChannel] = field(default_factory=list)
    category_mix: dict[str, Decimal] = field(default_factory=dict)
    store_sales_per_format_annual: dict[str, Decimal] = field(default_factory=dict)
    store_rent_per_store_annual: Decimal | None = None
    store_personnel_per_store_annual: Decimal | None = None
    franchise_commission_annual: Decimal | None = None
    company_overhead_annual: Decimal | None = None
    net_revenue_annual: Decimal | None = None
    gp_margin: Decimal | None = None

    @property
    def active_store_count(self) -> int:
        return len(self.stores)

    def store_count_by_format(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self.stores:
            counts[s.store_format] = counts.get(s.store_format, 0) + 1
        return counts


def _read_active_stores(conn, schema: str, tenant_id: str, entity_id: int) -> list[BaselineStore]:
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT source_record_id, store_format, opening_date FROM "{schema}".dim_location '
            f"WHERE tenant_id=%s AND entity_id=%s AND is_current AND status='active' "
            f'AND store_format IS NOT NULL',
            (tenant_id, entity_id),
        )
        return [BaselineStore(store_code=code, store_format=fmt, opening_date=opening)
                  for code, fmt, opening in cur.fetchall()]


def _read_online_channels(conn, schema: str, tenant_id: str, entity_id: int,
                              date_from: date, date_to: date, trailing_months: int) -> list[BaselineOnlineChannel]:
    """One row per distinct channel with any order-line activity in the
    trailing window whose channel does NOT resolve to a store (a store
    channel's location_key is set; an online channel's is NULL) --
    deliberately not classified into a tier1/tier2/own_site taxonomy here,
    see drivers.py's OnlineChannelDrivers docstring.

    Grouped by channel_sub, NOT dim_channel.channel_name: dim_channel only
    has one row per D-046 canonical TYPE (src/ingest/canonical.py's
    resolve_channel_key resolves every "Marketplace - X" name to the SAME
    'marketplace' dim_channel row), so grouping by channel_name would
    silently merge every marketplace into one bucket. channel_sub is where
    the actual per-marketplace/per-site identity lives on the order line."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT f.channel_sub, COUNT(*) AS orders, '
            f'       COALESCE(SUM(f.net_amount), 0) AS net_total '
            f'FROM "{schema}".fact_channel_order_line f '
            f'WHERE f.tenant_id=%s AND f.entity_id=%s AND f.is_current '
            f'AND f.event_date BETWEEN %s AND %s AND f.location_key IS NULL '
            f'GROUP BY f.channel_sub',
            (tenant_id, entity_id, date_from, date_to),
        )
        out = []
        for channel_sub, orders, net_total in cur.fetchall():
            if orders == 0 or not channel_sub:
                continue
            monthly_orders = Decimal(orders) / Decimal(trailing_months)
            aov = (net_total / orders) if orders else Decimal("0")
            out.append(BaselineOnlineChannel(channel_name=channel_sub, monthly_orders=monthly_orders, aov=aov))
        return out


def _read_store_sales_per_format(conn, schema: str, tenant_id: str, entity_id: int,
                                      date_from: date, date_to: date, trailing_months: int) -> dict[str, Decimal]:
    """Observed annualised sales per store, by format -- an existing store's
    forecast growth (corpus/13 section 2) compounds forward from this, not
    from a user-supplied number, since it's a fact about this company's own
    stores, not an assumption. Joins the order file (net_amount, operational
    truth) rather than the GL (booked, accounting truth) -- consistent with
    how store cohorts are defined in the first place, off dim_location."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT dl.store_format, COUNT(DISTINCT dl.location_key) AS n_stores, '
            f'       COALESCE(SUM(f.net_amount), 0) AS net_total '
            f'FROM "{schema}".fact_channel_order_line f '
            f'JOIN "{schema}".dim_location dl ON dl.location_key = f.location_key '
            f'WHERE f.tenant_id=%s AND f.entity_id=%s AND f.is_current AND dl.is_current '
            f'AND f.event_date BETWEEN %s AND %s AND dl.store_format IS NOT NULL '
            f'GROUP BY dl.store_format',
            (tenant_id, entity_id, date_from, date_to),
        )
        scale = Decimal(12) / Decimal(trailing_months)
        return {fmt: (net_total / n_stores) * scale for fmt, n_stores, net_total in cur.fetchall() if n_stores > 0}


def _read_category_mix(conn, schema: str, tenant_id: str, entity_id: int,
                           date_from: date, date_to: date) -> dict[str, Decimal]:
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT dp.category, COALESCE(SUM(f.net_amount), 0) '
            f'FROM "{schema}".fact_channel_order_line f '
            f'JOIN "{schema}".dim_product dp ON dp.product_key = f.product_key '
            f'WHERE f.tenant_id=%s AND f.entity_id=%s AND f.is_current '
            f'AND f.event_date BETWEEN %s AND %s AND dp.category IS NOT NULL '
            f'GROUP BY dp.category',
            (tenant_id, entity_id, date_from, date_to),
        )
        rows = {category: total for category, total in cur.fetchall() if total > 0}
    total = sum(rows.values(), Decimal("0"))
    if total <= 0:
        return {}
    return {category: (amount / total) for category, amount in rows.items()}


def read_baseline(conn, schema: str, tenant_id: str, entity_id: int, mapping_version_id: int,
                     as_of: date, trailing_months: int = 12) -> Baseline:
    """The forecast's starting point: active stores as of today, and
    trailing-`trailing_months` run-rates for cost and margin, read off the
    mapped canonical model at mapping_version_id. Any figure the trailing
    window has no data for stays None -- engine.py must not proceed on a
    component with no baseline, same as it must not on a missing driver."""
    date_from = as_of - timedelta(days=30 * trailing_months)
    baseline = Baseline(as_of=as_of, trailing_months=trailing_months)

    baseline.stores = _read_active_stores(conn, schema, tenant_id, entity_id)
    baseline.store_sales_per_format_annual = _read_store_sales_per_format(
        conn, schema, tenant_id, entity_id, date_from, as_of, trailing_months)
    baseline.online_channels = _read_online_channels(
        conn, schema, tenant_id, entity_id, date_from, as_of, trailing_months)
    baseline.category_mix = _read_category_mix(conn, schema, tenant_id, entity_id, date_from, as_of)

    movements = class_movements(conn, schema, tenant_id, entity_id, mapping_version_id, date_from, as_of)
    scale = Decimal(12) / Decimal(trailing_months)

    def annualised(canonical_class: str) -> Decimal | None:
        raw = movements.get(canonical_class)
        if raw is None:
            return None
        return natural_positive(canonical_class, raw) * scale

    store_count = baseline.active_store_count
    rent_total = annualised("opex.store_rent")
    personnel_total = annualised("opex.store_personnel")
    baseline.store_rent_per_store_annual = (rent_total / store_count) if rent_total and store_count else None
    baseline.store_personnel_per_store_annual = (
        personnel_total / store_count) if personnel_total and store_count else None
    baseline.franchise_commission_annual = annualised("opex.franchise_commission")

    ho = annualised("opex.employee_cost") or Decimal("0")
    warehouse = annualised("cogs.fulfilment") or Decimal("0")
    admin = annualised("opex.admin_general") or Decimal("0")
    overhead = ho + warehouse + admin
    baseline.company_overhead_annual = overhead if overhead > 0 else None

    ladder = compute_consumer_cm_ladder(movements, date_from, as_of)
    net_revenue = ladder.subtotals.get("net_revenue")
    baseline.net_revenue_annual = (net_revenue * scale) if net_revenue else None
    baseline.gp_margin = ladder.subtotals.get("gross_margin_pct")

    return baseline
