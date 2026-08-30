"""Sprint 6 acceptance criteria, per your own instruction: 'marketplace GMV
is never summed into revenue, a 100 percent gross margin line raises no
anomaly, and corporate overhead is never allocated.'

Needs live Postgres -- skips cleanly otherwise, same posture as every other
sprint's acceptance test in this repo.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.quality.checks import check_margin_sign_flip
from src.reports.consumer_ladder import assemble_consumer_ladder
from src.reports.manufacturing_operating import assemble_manufacturing_operating_metrics
from tests.helpers import (
    ingest_consumer,
    ingest_consumer_channel_orders,
    ingest_manufacturer,
    ingest_manufacturer_production,
    run_and_freeze_mapping,
    seed_dim_channel,
)

# corpus/11 section 3's gating tier, which is what pytest.ini's `eval` marker
# selects. Applied at module level so `pytest -m eval` collects this file --
# the same set .github/workflows/ci.yml already collects by path.
pytestmark = pytest.mark.eval


def test_marketplace_gmv_never_summed_into_revenue_live(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    seed_dim_channel(conn, schema, tenant_id, entity_id, "consumer")

    # ingest_consumer loads COA + all 12 months of GL, which the ladder's
    # GL-sourced lines (COGS, marketing, corporate overhead) and the
    # mapping freeze both need; the SAME data object's order_rows feed
    # fact_channel_order_line so both sources describe one fixture.
    data = ingest_consumer(conn, schema, tenant_id, entity_id)
    ingest_consumer_channel_orders(conn, schema, tenant_id, entity_id, data, month_idx=0)
    run_and_freeze_mapping(conn, schema, tenant_id, entity_id, effective_from=date(2025, 4, 1))

    d = data.months[0]
    period_start = d.replace(day=1)
    from src.reports.query import resolve_mapping_version_for_period
    from calendar import monthrange
    period_end = d.replace(day=monthrange(d.year, d.month)[1])
    mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, period_end)

    ladder = assemble_consumer_ladder(conn, schema, tenant_id, entity_id, mapping_version_id,
                                          period_start, period_end)

    assert ladder.gmv_by_model.get("marketplace", Decimal("0")) > 0, "fixture must contain real marketplace GMV"
    marketplace_gmv = ladder.gmv_by_model["marketplace"]
    # the acceptance test itself: marketplace's own GMV must not appear
    # anywhere inside marketplace's own contribution to net_revenue -- that
    # contribution is only the commission/ads/platform-fee earned, an
    # independently-computed figure from the raw order rows, not a fraction
    # or snapshot of net_revenue itself (CLAUDE.md section 9: never assert
    # against a snapshot of current behaviour).
    expected_marketplace_revenue = _sum_of_marketplace_earned(data.order_rows[0])
    assert expected_marketplace_revenue > 0, "fixture must contain real marketplace earnings"
    assert ladder.net_revenue_by_model["marketplace"] == expected_marketplace_revenue
    assert ladder.net_revenue_by_model["marketplace"] < marketplace_gmv


def _sum_of_marketplace_earned(order_rows) -> Decimal:
    total = Decimal("0")
    for r in order_rows:
        if r["revenue_model"] == "marketplace":
            total += Decimal(r["commission_earned"]) + Decimal(r["advertising_earned"]) + Decimal(r["platform_fee_earned"])
    return total


def test_100_pct_gross_margin_line_raises_no_anomaly_live(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    seed_dim_channel(conn, schema, tenant_id, entity_id, "consumer")

    from synthetic.consumer.engine import build_consumer_company
    data = build_consumer_company(seed=42)
    ingest_consumer_channel_orders(conn, schema, tenant_id, entity_id, data, month_idx=0)
    ingest_consumer_channel_orders(conn, schema, tenant_id, entity_id, data, month_idx=1)

    period_key = f"{data.months[1].year:04d}-{data.months[1].month:02d}"
    prior_period_key = f"{data.months[0].year:04d}-{data.months[0].month:02d}"

    candidates = check_margin_sign_flip(conn, schema, tenant_id, entity_id, period_key, prior_period_key)
    # the Brightleaf Marketplace channel runs at 100% gross margin every
    # month by construction (D-061: no COGS for the marketplace model) --
    # its margin is always positive, never flips sign, and must not appear
    # in the candidates the anomaly check raises.
    with conn.cursor() as cur:
        cur.execute(f'SELECT channel_key FROM "{schema}".dim_channel WHERE tenant_id=%s AND source_record_id=%s',
                       (tenant_id, "marketplace"))
        marketplace_channel_key = cur.fetchone()[0]
    flagged_channels = {int(c.object_ref) for c in candidates}
    assert marketplace_channel_key not in flagged_channels


def test_corporate_overhead_never_allocated_live(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    seed_dim_channel(conn, schema, tenant_id, entity_id, "consumer")

    data = ingest_consumer(conn, schema, tenant_id, entity_id)
    ingest_consumer_channel_orders(conn, schema, tenant_id, entity_id, data, month_idx=0)
    run_and_freeze_mapping(conn, schema, tenant_id, entity_id, effective_from=date(2025, 4, 1))

    d = data.months[0]
    period_start = d.replace(day=1)
    from calendar import monthrange
    period_end = d.replace(day=monthrange(d.year, d.month)[1])
    from src.reports.query import resolve_mapping_version_for_period
    mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, period_end)

    ladder = assemble_consumer_ladder(conn, schema, tenant_id, entity_id, mapping_version_id,
                                          period_start, period_end)
    assert isinstance(ladder.corporate_overhead, Decimal)
    assert ladder.corporate_overhead > 0
    # structural: there is no channel- or product-keyed corporate overhead
    # anywhere on the result to have been allocated from.
    assert not hasattr(ladder, "corporate_overhead_by_channel")
    assert not hasattr(ladder, "corporate_overhead_by_product")


def test_mixed_uom_blocks_manufacturing_per_unit_metrics_live(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    seed_dim_channel(conn, schema, tenant_id, entity_id, "manufacturing")

    data = ingest_manufacturer(conn, schema, tenant_id, entity_id)
    dual_uom_months = {e["month"] for e in data.defect_log.entries if e.get("defect_id") == 7}
    dual_uom_month_idx = next(i for i, mv in enumerate(data.months)
                                 if f"{mv.year:04d}-{mv.month:02d}" in dual_uom_months)
    assert dual_uom_month_idx != 0, "test assumes an earlier month establishes the declared_uom baseline first"
    # Month 0 first, to establish dim_product.declared_uom -- the defect
    # IS the mismatch against a prior baseline, so the baseline must exist
    # before the defect month is loaded, exactly the real-world sequence
    # (declared_uom is stamped from whichever uom arrives first).
    ingest_manufacturer_production(conn, schema, tenant_id, entity_id, data, month_idx=0)
    ingest_manufacturer_production(conn, schema, tenant_id, entity_id, data, month_idx=dual_uom_month_idx)
    run_and_freeze_mapping(conn, schema, tenant_id, entity_id, effective_from=date(2022, 4, 1))

    d = data.months[dual_uom_month_idx]
    period_key = f"{d.year:04d}-{d.month:02d}"
    from calendar import monthrange
    period_start, period_end = d.replace(day=1), d.replace(day=monthrange(d.year, d.month)[1])
    from src.reports.query import resolve_mapping_version_for_period
    from src.quality.checks import check_mixed_uom
    mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, period_end)

    mixed_uom_candidates = check_mixed_uom(conn, schema, tenant_id, entity_id, period_key)
    assert len(mixed_uom_candidates) >= 1, "the seeded dual-uom defect month must produce at least one exception"
    mixed_uom_keys = {int(c.object_ref) for c in mixed_uom_candidates}

    product_results, _entity = assemble_manufacturing_operating_metrics(
        conn, schema, tenant_id, entity_id, mapping_version_id, period_key, period_start, period_end, mixed_uom_keys,
    )
    blocked = [r for r in product_results if r.product_key in mixed_uom_keys]
    assert blocked, "the defect product must appear in the product results"
    for r in blocked:
        assert r.status == "blocked"
        assert r.yield_pct is None
        assert r.rejection_pct is None
