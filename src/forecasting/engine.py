"""The forecast projection, corpus/13 section 3. Pure function: baseline +
drivers -> a year-by-year P&L. Deterministic and formula-driven, the same
posture as the semantic compiler -- nothing here is a model call, and no
number is produced that isn't traceable to either an observed baseline
figure or a driver the user supplied. A component with no baseline and no
driver is reported as a gap (`ForecastResult.gaps`), never silently zeroed
or defaulted, the same not_configured discipline as
src/semantic/bridges.py and src/reports/cashflow.py.

Store-cohort mechanics mirror synthetic/apparel/stores.py's gestation ramp
(corpus/13 section 2), at annual rather than monthly granularity since a
driver's stores_added_per_year and a cost driver's gp_margin_path are both
per-year inputs -- there is no reason for the engine to track a finer grain
than its own inputs support. Existing stores (already open as of the
baseline) and new stores (opened during the forecast) are modelled
separately and combined, exactly as the source financial model this spec is
derived from does (corpus/13 section 1): existing stores grow at the
like-for-like rate from their OBSERVED current blended run-rate
(baseline.store_sales_per_format_annual); new stores ramp up from the
driver's year1_avg_annual_sales_inr, since they have no observed history to
grow from.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from src.forecasting.baseline import Baseline
from src.forecasting.drivers import ForecastDrivers, StoreFormatDrivers

# Annual-granularity restatement of synthetic/apparel/stores.py's two-year
# monthly gestation ramp (12mo -> 0.55, 24mo -> 0.80): a new store's first
# forecast year operates at 55% of its mature run-rate, second year at 80%,
# third year onward at full rate, compounding at the like-for-like growth
# rate from there. corpus/13 section 2 is the shared authority both this
# and the synthetic generator implement.
NEW_STORE_GESTATION_RAMP = [Decimal("0.55"), Decimal("0.80")]

# corpus/13 section 3.3: franchise commission applies to every format except
# COCO (company-owned, company-operated -- no franchise party in the
# relationship at all). This is a structural fact about what a format MEANS,
# not a per-company assumption, so it is not a driver field a user sets.
FRANCHISE_COMMISSION_EXEMPT_FORMAT = "COCO"


@dataclass
class YearResult:
    year_index: int  # 1-based forecast year
    existing_store_revenue: Decimal = Decimal("0")
    new_store_revenue: Decimal = Decimal("0")
    store_revenue_by_format: dict[str, Decimal] = field(default_factory=dict)
    online_revenue_by_channel: dict[str, Decimal] = field(default_factory=dict)
    total_revenue: Decimal = Decimal("0")
    category_mix: dict[str, Decimal] = field(default_factory=dict)
    gross_margin_pct: Decimal | None = None
    cogs: Decimal | None = None
    gross_profit: Decimal | None = None
    store_rent: Decimal | None = None
    store_personnel: Decimal | None = None
    franchise_commission: Decimal | None = None
    online_commission: Decimal = Decimal("0")
    online_ad_spend: Decimal = Decimal("0")
    company_overhead: Decimal | None = None
    ebitda: Decimal | None = None


@dataclass
class ForecastResult:
    baseline_as_of: date
    years: list[YearResult] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)  # components not computable from what was supplied

    @property
    def configured(self) -> bool:
        return not self.gaps


def _new_store_cohort_annual_sales(years_since_opening: int, year1_avg_annual_sales: Decimal,
                                       price_growth: Decimal, customer_growth: Decimal) -> Decimal:
    if years_since_opening <= 0:
        return Decimal("0")
    idx = years_since_opening - 1
    if idx < len(NEW_STORE_GESTATION_RAMP):
        return year1_avg_annual_sales * NEW_STORE_GESTATION_RAMP[idx]
    years_mature = idx - len(NEW_STORE_GESTATION_RAMP)
    lfl = (Decimal("1") + price_growth) * (Decimal("1") + customer_growth)
    return year1_avg_annual_sales * (lfl ** years_mature)


def _project_store_revenue(baseline: Baseline, drivers: ForecastDrivers, year_idx: int,
                               store_drivers_by_format: dict[str, StoreFormatDrivers],
                               gaps: list[str]) -> tuple[Decimal, Decimal, dict[str, Decimal]]:
    """(existing_store_revenue, new_store_revenue, revenue_by_format) for
    one forecast year."""
    existing_total = Decimal("0")
    new_total = Decimal("0")
    by_format: dict[str, Decimal] = {}

    counts_by_format = baseline.store_count_by_format()
    all_formats = set(counts_by_format) | set(store_drivers_by_format)
    for fmt in all_formats:
        fmt_driver = store_drivers_by_format.get(fmt)
        fmt_total = Decimal("0")

        existing_count = counts_by_format.get(fmt, 0)
        if existing_count:
            observed_run_rate = baseline.store_sales_per_format_annual.get(fmt)
            if observed_run_rate is None:
                gaps.append(f"existing {fmt} stores: no observed baseline sales run-rate for this format")
            elif fmt_driver is None:
                gaps.append(f"existing {fmt} stores: no like-for-like growth driver supplied for this format")
            else:
                lfl = ((Decimal("1") + fmt_driver.existing_store_price_growth_yoy)
                        * (Decimal("1") + fmt_driver.existing_store_customer_growth_yoy)) ** year_idx
                year_revenue = observed_run_rate * existing_count * lfl
                existing_total += year_revenue
                fmt_total += year_revenue

        if fmt_driver is not None:
            for cohort_year, n_added in enumerate(fmt_driver.stores_added_per_year, start=1):
                if n_added <= 0:
                    continue
                years_since_opening = year_idx - cohort_year + 1
                per_store = _new_store_cohort_annual_sales(
                    years_since_opening, fmt_driver.year1_avg_annual_sales_inr,
                    fmt_driver.existing_store_price_growth_yoy, fmt_driver.existing_store_customer_growth_yoy)
                cohort_revenue = per_store * n_added
                new_total += cohort_revenue
                fmt_total += cohort_revenue

        if fmt_total > 0:
            by_format[fmt] = fmt_total

    return existing_total, new_total, by_format


def _project_online_revenue(baseline: Baseline, drivers: ForecastDrivers, year_idx: int,
                                gaps: list[str]) -> dict[str, Decimal]:
    driver_by_channel = {d.channel_name: d for d in drivers.online_channels}
    out: dict[str, Decimal] = {}
    for channel in baseline.online_channels:
        d = driver_by_channel.get(channel.channel_name)
        if d is None:
            gaps.append(f"online channel {channel.channel_name!r}: no growth driver supplied")
            continue
        monthly_orders = channel.monthly_orders * ((Decimal("1") + d.orders_growth_yoy) ** year_idx)
        aov = channel.aov * ((Decimal("1") + d.price_growth_yoy) ** year_idx)
        out[channel.channel_name] = monthly_orders * 12 * aov
    return out


def project(baseline: Baseline, drivers: ForecastDrivers) -> ForecastResult:
    result = ForecastResult(baseline_as_of=baseline.as_of)
    store_drivers_by_format = {d.store_format: d for d in drivers.store_formats}

    for year_idx in range(1, drivers.forecast_years + 1):
        year_gaps: list[str] = []
        existing_rev, new_rev, by_format = _project_store_revenue(
            baseline, drivers, year_idx, store_drivers_by_format, year_gaps)
        online_by_channel = _project_online_revenue(baseline, drivers, year_idx, year_gaps)

        total_revenue = existing_rev + new_rev + sum(online_by_channel.values(), Decimal("0"))
        yr = YearResult(
            year_index=year_idx, existing_store_revenue=existing_rev, new_store_revenue=new_rev,
            store_revenue_by_format=by_format, online_revenue_by_channel=online_by_channel,
            total_revenue=total_revenue,
        )

        yr.category_mix = _project_category_mix(baseline, drivers, year_idx)

        margin_path = drivers.costs.gp_margin_path
        if year_idx - 1 < len(margin_path):
            yr.gross_margin_pct = margin_path[year_idx - 1]
            yr.cogs = total_revenue * (Decimal("1") - yr.gross_margin_pct)
            yr.gross_profit = total_revenue - yr.cogs
        else:
            year_gaps.append(f"year {year_idx}: gp_margin_path has no entry for this year")

        store_count_projected = sum(baseline.store_count_by_format().values()) + sum(
            sum(d.stores_added_per_year[:year_idx]) for d in drivers.store_formats)

        if baseline.store_rent_per_store_annual is not None:
            yr.store_rent = (baseline.store_rent_per_store_annual
                                * ((Decimal("1") + drivers.costs.store_rent_growth_yoy) ** year_idx)
                                * store_count_projected)
        else:
            year_gaps.append(f"year {year_idx}: no observed baseline store rent to grow forward")

        if baseline.store_personnel_per_store_annual is not None:
            yr.store_personnel = (baseline.store_personnel_per_store_annual
                                     * ((Decimal("1") + drivers.costs.store_personnel_growth_yoy) ** year_idx)
                                     * store_count_projected)
        else:
            year_gaps.append(f"year {year_idx}: no observed baseline store personnel cost to grow forward")

        commissionable_revenue = sum(
            (rev for fmt, rev in by_format.items() if fmt != FRANCHISE_COMMISSION_EXEMPT_FORMAT), Decimal("0"))
        yr.franchise_commission = commissionable_revenue * drivers.costs.franchise_commission_rate

        online_revenue_total = sum(online_by_channel.values(), Decimal("0"))
        yr.online_commission = online_revenue_total * drivers.costs.online_commission_rate
        yr.online_ad_spend = online_revenue_total * drivers.costs.online_ad_spend_pct_of_sales

        if baseline.company_overhead_annual is not None:
            yr.company_overhead = (baseline.company_overhead_annual
                                      * ((Decimal("1") + drivers.costs.ho_cost_growth_yoy) ** year_idx))
        else:
            year_gaps.append(f"year {year_idx}: no observed baseline company overhead to grow forward")

        if not year_gaps and yr.gross_profit is not None:
            store_costs = (yr.store_rent or Decimal("0")) + (yr.store_personnel or Decimal("0")) + \
                            (yr.franchise_commission or Decimal("0"))
            online_costs = yr.online_commission + yr.online_ad_spend
            yr.ebitda = yr.gross_profit - store_costs - online_costs - (yr.company_overhead or Decimal("0"))

        result.years.append(yr)
        result.gaps.extend(year_gaps)

    return result


def _project_category_mix(baseline: Baseline, drivers: ForecastDrivers, year_idx: int) -> dict[str, Decimal]:
    if not baseline.category_mix:
        return {}
    if drivers.product_mix is None:
        return dict(baseline.category_mix)  # held flat -- no target supplied, nothing invented
    frac = min(Decimal(year_idx) / Decimal(drivers.product_mix.convergence_years), Decimal("1"))
    out: dict[str, Decimal] = {}
    categories = set(baseline.category_mix) | set(drivers.product_mix.target_mix)
    for cat in categories:
        start = baseline.category_mix.get(cat, Decimal("0"))
        target = drivers.product_mix.target_mix.get(cat, start)
        out[cat] = start + (target - start) * frac
    return out
