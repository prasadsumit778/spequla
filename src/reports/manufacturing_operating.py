"""Manufacturing operating layer, corpus/03 section 6. "These are MANAGEMENT
concepts throughout. None has a statutory definition and every one of them
varies by plant."

Per-product, computed from fact_production_output (sprint 6) plus the GL
classes already declared in statement_lines.py. D-041 governs every one of
these: "nothing computes without" a single declared unit per product, so
each function here refuses (returns status='blocked') for a product with an
open mixed-uom exception rather than averaging across incompatible units --
the caller passes in which products are blocked
(src/quality/checks.check_mixed_uom's result for the period), this module
does not query exceptions itself.

**rm_cost_per_unit and conversion_cost_per_unit are entity-level, not
per-product, despite corpus/03 section 6 listing 'plant, product' as their
dimensions.** fact_gl_entry carries no product_key -- raw material and
conversion cost are booked to a cost ledger, never to a specific SKU -- so
a per-product split of those GL totals does not exist in what this system
ingests. Splitting the entity-level total across products by, say, their
share of volume produced would be inventing an allocation convention the
corpus never states (CLAUDE.md section 3.2), exactly the kind of made-up
number this system exists to refuse to produce. These two metrics are
reported once, for the whole entity, using entity-level volume_produced as
the denominator; yield_pct and rejection_pct genuinely are per-product
(fact_production_output carries its own product_key and quantities row by
row) and are computed at that grain.

Two of corpus/03 section 6's named metrics are not computed here at all,
and say so rather than approximate:
  - `realisation_per_unit` needs `volume_sold` (sum of fact_invoice_line
    quantity), and fact_invoice_line has no ingestion pipeline built --
    same UNAVAILABLE_DIMENSIONS-shaped gap as customer/product breakdown
    on the Ask surface.
  - `capacity_utilisation_pct` needs a practical-capacity figure that has
    no field anywhere in fact_production_output and is governed by D-042
    (capacity basis: installed/rated/practical), one of the company-
    specific open decisions -- there is nothing to divide by.
`conversion_cost_per_unit`'s formula names four components (power, direct
labour, consumables, factory overhead); only three have a declared
canonical class in statement_lines.py (cogs.power_fuel, cogs.direct_labour,
cogs.stores_consumables) -- factory_overhead has none, so the entity-level
figure is a disclosed partial sum, not silently treated as complete.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from src.reports.query import class_movements

_RM_COST_CLASSES = ["cogs.raw_material"]
_CONVERSION_COST_CLASSES = ["cogs.power_fuel", "cogs.direct_labour", "cogs.stores_consumables"]


@dataclass
class ProductOperatingResult:
    """Per-product: yield, rejection, volume. rm/conversion cost per unit
    are NOT on this dataclass -- see EntityOperatingResult, module
    docstring."""
    product_key: int
    product_name: str
    status: str  # 'ok' | 'blocked'
    reason: str | None = None
    uom: str | None = None
    volume_produced: Decimal | None = None
    qty_rejected: Decimal | None = None
    yield_pct: Decimal | None = None
    rejection_pct: Decimal | None = None
    realisation_per_unit: None = None                 # always unavailable, see module docstring
    realisation_per_unit_unavailable_reason: str = (
        "needs volume_sold from fact_invoice_line, which has no ingestion pipeline")
    capacity_utilisation_pct: None = None              # always unavailable, see module docstring
    capacity_utilisation_unavailable_reason: str = (
        "needs a practical-capacity figure; D-042 (capacity basis) is open and no field for it exists")


@dataclass
class EntityOperatingResult:
    """Entity-level: rm_cost_per_unit and conversion_cost_per_unit, computed
    once against total volume_produced across all products -- see module
    docstring for why these cannot be split by product. status is 'blocked'
    whenever the entity's products do not share one common uom -- summing
    qty_produced across tonnes and pieces would itself be D-041's forbidden
    average-across-incompatible-units, just moved up one level from
    per-product to entity-wide."""
    period_key: str
    status: str  # 'ok' | 'blocked'
    reason: str | None = None
    common_uom: str | None = None
    total_volume_produced: Decimal | None = None
    rm_cost_per_unit: Decimal | None = None
    conversion_cost_per_unit: Decimal | None = None
    conversion_cost_components: list[str] = field(default_factory=lambda: list(_CONVERSION_COST_CLASSES))


def _fetch_production_rows(conn, schema: str, tenant_id: str, entity_id: int,
                              period_key: str) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT fp.product_key, dp.source_item_name, fp.uom, '
            f'       SUM(fp.qty_produced), SUM(fp.qty_rejected), SUM(fp.input_qty) '
            f'FROM "{schema}".fact_production_output fp '
            f'JOIN "{schema}".dim_product dp ON dp.product_key = fp.product_key AND dp.is_current '
            f'WHERE fp.tenant_id = %s AND fp.entity_id = %s AND fp.is_current AND fp.period_key = %s '
            f'GROUP BY fp.product_key, dp.source_item_name, fp.uom',
            (tenant_id, entity_id, period_key),
        )
        return cur.fetchall()


def compute_product_operating_metrics(product_key: int, product_name: str, uom: str,
                                          qty_produced: Decimal, qty_rejected: Decimal, input_qty: Decimal | None,
                                          is_uom_mismatched: bool) -> ProductOperatingResult:
    """Pure. D-041: a product with a mixed-uom exception open for the
    period refuses every per-unit figure -- yield and rejection are both
    per-unit metrics, not just the ones that look like it."""
    if is_uom_mismatched:
        return ProductOperatingResult(
            product_key=product_key, product_name=product_name, status="blocked",
            reason=f"D-041: {product_name!r} has more than one unit of measure recorded this period -- "
                     f"per-unit metrics refuse to compute rather than average across incompatible units",
        )

    result = ProductOperatingResult(product_key=product_key, product_name=product_name, status="ok", uom=uom,
                                        volume_produced=qty_produced, qty_rejected=qty_rejected)
    total_output = qty_produced + qty_rejected
    result.rejection_pct = (qty_rejected / total_output) if total_output else None
    result.yield_pct = (qty_produced / input_qty) if input_qty else None
    return result


def compute_entity_operating_metrics(period_key: str, ok_products: list[tuple[str, Decimal]],
                                         rm_cost_value: Decimal,
                                         conversion_cost_value: Decimal) -> EntityOperatingResult:
    """Pure. ok_products: (uom, qty_produced) for every product that is NOT
    D-041-blocked this period. Refuses (status='blocked') unless every one
    of them shares the same uom -- see EntityOperatingResult's docstring."""
    if not ok_products:
        return EntityOperatingResult(period_key=period_key, status="blocked",
                                         reason="no unblocked production this period")
    distinct_uoms = {uom for uom, _qty in ok_products}
    if len(distinct_uoms) > 1:
        return EntityOperatingResult(
            period_key=period_key, status="blocked",
            reason=f"products this period use {len(distinct_uoms)} different units of measure "
                     f"({sorted(distinct_uoms)}) -- an entity-level per-unit figure would average "
                     f"across incompatible units, the same thing D-041 forbids per product",
        )
    common_uom = next(iter(distinct_uoms))
    total_volume_produced = sum((qty for _uom, qty in ok_products), Decimal("0"))
    return EntityOperatingResult(
        period_key=period_key, status="ok", common_uom=common_uom, total_volume_produced=total_volume_produced,
        rm_cost_per_unit=(rm_cost_value / total_volume_produced) if total_volume_produced else None,
        conversion_cost_per_unit=(conversion_cost_value / total_volume_produced) if total_volume_produced else None,
    )


def assemble_manufacturing_operating_metrics(conn, schema: str, tenant_id: str, entity_id: int,
                                                 mapping_version_id: int, period_key: str,
                                                 period_start: date, period_end: date,
                                                 mixed_uom_product_keys: set[int]
                                                 ) -> tuple[list[ProductOperatingResult], EntityOperatingResult]:
    """mixed_uom_product_keys: the product_keys with an open D-041 exception
    for this period (src/quality/checks.check_mixed_uom's result, passed in
    rather than queried here so this stays a simple orchestrator)."""
    rows = _fetch_production_rows(conn, schema, tenant_id, entity_id, period_key)
    gl_movements = class_movements(conn, schema, tenant_id, entity_id, mapping_version_id, period_start, period_end)
    rm_cost_total = sum((gl_movements.get(c, Decimal("0")) for c in _RM_COST_CLASSES), Decimal("0"))
    conversion_cost_total = sum((gl_movements.get(c, Decimal("0")) for c in _CONVERSION_COST_CLASSES), Decimal("0"))

    product_results = [
        compute_product_operating_metrics(product_key, product_name, uom, qty_produced, qty_rejected, input_qty,
                                              is_uom_mismatched=product_key in mixed_uom_product_keys)
        for product_key, product_name, uom, qty_produced, qty_rejected, input_qty in rows
    ]
    ok_products = [(uom, qty_produced) for product_key, _name, uom, qty_produced, _rej, _inp in rows
                     if product_key not in mixed_uom_product_keys]
    entity_result = compute_entity_operating_metrics(period_key, ok_products, rm_cost_total, conversion_cost_total)
    return product_results, entity_result
