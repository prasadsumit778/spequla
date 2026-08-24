"""Tests for the forecast projection, corpus/13 section 3."""
from datetime import date
from decimal import Decimal

from src.forecasting.baseline import Baseline, BaselineOnlineChannel, BaselineStore
from src.forecasting.drivers import CostDrivers, ForecastDrivers, OnlineChannelDrivers, StoreFormatDrivers
from src.forecasting.engine import project

D = Decimal


def _minimal_costs(years: int) -> CostDrivers:
    return CostDrivers(
        store_personnel_growth_yoy=D("0.07"), store_rent_growth_yoy=D("0.06"),
        franchise_commission_rate=D("0.10"), ho_cost_growth_yoy=D("0.075"),
        online_commission_rate=D("0.16"), online_ad_spend_pct_of_sales=D("0.075"),
        gp_margin_path=[D("0.55")] * years,
    )


def test_new_store_gestation_ramp_shows_up_in_year_by_year_revenue():
    """A single new COCO store added in forecast year 1: year 1 revenue
    should be a fraction of the mature run-rate, year 2 a larger fraction,
    year 3 the full (compounded) rate -- corpus/13 section 2."""
    baseline = Baseline(as_of=date(2026, 4, 1), trailing_months=12)  # no existing stores
    drivers = ForecastDrivers(
        forecast_years=3,
        store_formats=[StoreFormatDrivers(
            store_format="COCO", stores_added_per_year=[1, 0, 0],
            year1_avg_annual_sales_inr=D("20000000"),
            existing_store_price_growth_yoy=D("0.04"), existing_store_customer_growth_yoy=D("0.02"),
        )],
        costs=_minimal_costs(3),
    )
    result = project(baseline, drivers)
    assert len(result.years) == 3
    y1, y2, y3 = result.years
    assert y1.new_store_revenue == D("20000000") * D("0.55")
    assert y2.new_store_revenue == D("20000000") * D("0.80")
    # Year 3 is the first year at the full mature rate -- like-for-like
    # growth starts compounding from year 4 onward (years_mature=0 in year 3).
    assert y3.new_store_revenue == D("20000000")
    # monotonically increasing, since gestation only ramps up
    assert y1.new_store_revenue < y2.new_store_revenue < y3.new_store_revenue


def test_existing_stores_grow_from_observed_baseline_not_from_driver_input():
    baseline = Baseline(
        as_of=date(2026, 4, 1), trailing_months=12,
        stores=[BaselineStore(store_code="COCO-001", store_format="COCO", opening_date=date(2020, 1, 1))],
        store_sales_per_format_annual={"COCO": D("18000000")},
    )
    drivers = ForecastDrivers(
        forecast_years=2,
        store_formats=[StoreFormatDrivers(
            store_format="COCO", stores_added_per_year=[0, 0],
            year1_avg_annual_sales_inr=D("99999999"),  # deliberately different -- must not be used for THIS store
            existing_store_price_growth_yoy=D("0.05"), existing_store_customer_growth_yoy=D("0.03"),
        )],
        costs=_minimal_costs(2),
    )
    result = project(baseline, drivers)
    lfl_y1 = D("1.05") * D("1.03")
    assert result.years[0].existing_store_revenue == D("18000000") * lfl_y1
    assert result.years[0].new_store_revenue == D("0")


def test_missing_driver_for_observed_channel_is_a_disclosed_gap_not_a_fabricated_number():
    baseline = Baseline(
        as_of=date(2026, 4, 1), trailing_months=12,
        online_channels=[BaselineOnlineChannel(channel_name="Marketplace - Myntra",
                                                   monthly_orders=D("500"), aov=D("1400"))],
    )
    drivers = ForecastDrivers(forecast_years=1, online_channels=[], costs=_minimal_costs(1))
    result = project(baseline, drivers)
    assert result.years[0].online_revenue_by_channel == {}
    assert result.configured is False
    assert any("Marketplace - Myntra" in g for g in result.gaps)


def test_online_channel_projects_when_driver_supplied():
    baseline = Baseline(
        as_of=date(2026, 4, 1), trailing_months=12,
        online_channels=[BaselineOnlineChannel(channel_name="Own Website", monthly_orders=D("100"), aov=D("1000"))],
    )
    drivers = ForecastDrivers(
        forecast_years=1,
        online_channels=[OnlineChannelDrivers(channel_name="Own Website",
                                                  orders_growth_yoy=D("0.20"), price_growth_yoy=D("0.05"))],
        costs=_minimal_costs(1),
    )
    result = project(baseline, drivers)
    expected = (D("100") * D("1.20")) * 12 * (D("1000") * D("1.05"))
    assert result.years[0].online_revenue_by_channel["Own Website"] == expected


def test_franchise_commission_excludes_coco_but_applies_to_other_formats():
    baseline = Baseline(
        as_of=date(2026, 4, 1), trailing_months=12,
        stores=[BaselineStore(store_code="COCO-001", store_format="COCO", opening_date=date(2020, 1, 1)),
                 BaselineStore(store_code="COFO-001", store_format="COFO", opening_date=date(2020, 1, 1))],
        store_sales_per_format_annual={"COCO": D("10000000"), "COFO": D("10000000")},
    )
    lfl_driver = dict(existing_store_price_growth_yoy=D("0"), existing_store_customer_growth_yoy=D("0"))
    drivers = ForecastDrivers(
        forecast_years=1,
        store_formats=[
            StoreFormatDrivers(store_format="COCO", stores_added_per_year=[0],
                                  year1_avg_annual_sales_inr=D("1"), **lfl_driver),
            StoreFormatDrivers(store_format="COFO", stores_added_per_year=[0],
                                  year1_avg_annual_sales_inr=D("1"), **lfl_driver),
        ],
        costs=_minimal_costs(1),
    )
    result = project(baseline, drivers)
    yr = result.years[0]
    # Only COFO's 10,000,000 is commissionable; COCO's is exempt.
    assert yr.franchise_commission == D("10000000") * D("0.10")


def test_no_gaps_when_everything_is_supplied():
    baseline = Baseline(
        as_of=date(2026, 4, 1), trailing_months=12,
        stores=[BaselineStore(store_code="COCO-001", store_format="COCO", opening_date=date(2020, 1, 1))],
        store_sales_per_format_annual={"COCO": D("10000000")},
        store_rent_per_store_annual=D("3000000"), store_personnel_per_store_annual=D("4000000"),
        company_overhead_annual=D("40000000"),
    )
    drivers = ForecastDrivers(
        forecast_years=1,
        store_formats=[StoreFormatDrivers(
            store_format="COCO", stores_added_per_year=[0], year1_avg_annual_sales_inr=D("1"),
            existing_store_price_growth_yoy=D("0.04"), existing_store_customer_growth_yoy=D("0.02"))],
        costs=_minimal_costs(1),
    )
    result = project(baseline, drivers)
    assert result.configured is True
    assert result.years[0].ebitda is not None
