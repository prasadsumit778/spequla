"""Store master and cohort-vintage sales mechanics, corpus/13 section 2.

A store's expected monthly sales depend only on its format and how long it
has been open (its vintage cohort): a two-year gestation ramp from opening,
then full run-rate growing like any existing store. This is the mechanic a
real apparel-retail financial model uses for store-level revenue forecasting
(corpus/13 section 1), replicated here so the synthetic company's own history
has the same shape a forecast of it should recover.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from synthetic.apparel import profile
from synthetic.common import Rng, month_range


@dataclass
class Store:
    store_code: str
    store_name: str
    store_format: str
    city: str
    state: str
    site_type: str
    area_sqft: int
    opening_date: date
    closure_date: date | None
    status: str


def build_stores(rng: Rng) -> list[Store]:
    """One store per legacy slot plus one per planned addition
    (profile.LEGACY_STORE_COUNT, profile.STORE_ADDITIONS_BY_YEAR). Legacy
    stores open three years before FISCAL_START so they are fully mature
    (past the two-year gestation) at month 0 of the history window."""
    stores: list[Store] = []
    seq_by_format = {f: 0 for f in profile.STORE_FORMATS}

    def add_store(fmt: str, opening_date: date):
        seq_by_format[fmt] += 1
        city, state, _tier = rng.choice(profile.CITIES)
        store_code = f"{fmt}-{seq_by_format[fmt]:03d}"
        stores.append(Store(
            store_code=store_code,
            store_name=f"{profile.COMPANY_NAME.replace('SYNTHETIC ', '')} - {city} {store_code}",
            store_format=fmt,
            city=city, state=state,
            site_type=rng.choice(profile.SITE_TYPES),
            area_sqft=rng.randint(*profile.AREA_SQFT_RANGE),
            opening_date=opening_date,
            closure_date=None,
            status="active",
        ))

    legacy_opening = date(profile.FISCAL_START.year - 3, profile.FISCAL_START.month, 1)
    for fmt, count in profile.LEGACY_STORE_COUNT.items():
        for _ in range(count):
            add_store(fmt, legacy_opening)

    fy_starts = [date(profile.FISCAL_START.year + y, profile.FISCAL_START.month, 1) for y in range(5)]
    for fmt, additions_by_year in profile.STORE_ADDITIONS_BY_YEAR.items():
        for year_idx, n_added in enumerate(additions_by_year):
            for i in range(n_added):
                # Spread a year's additions across its 12 months rather than
                # opening them all on April 1st.
                month_offset = (i * 12) // max(n_added, 1)
                y, m = fy_starts[year_idx].year, fy_starts[year_idx].month + month_offset
                if m > 12:
                    y += 1
                    m -= 12
                add_store(fmt, date(y, m, 1))

    return stores


def age_months(store: Store, as_of: date) -> int:
    return (as_of.year - store.opening_date.year) * 12 + (as_of.month - store.opening_date.month)


def gestation_ramp_factor(age: int) -> Decimal:
    """corpus/13 section 2's two-year gestation: a store below its first
    threshold sells at a fraction of run-rate, ramps at the second, then
    sells at full run-rate. age < 0 means not yet opened -- factor 0."""
    if age < 0:
        return Decimal("0")
    for months, factor in profile.GESTATION_RAMP:
        if age < months:
            return factor
    return Decimal("1")


def mature_growth_multiplier(age: int) -> Decimal:
    """Once a store is past gestation, it grows like any existing store:
    price increase x customer-count increase, compounded per full year past
    maturity (corpus/13 section 2's existing-store like-for-like growth,
    applied to a store's own cohort rather than the portfolio average)."""
    years_past_maturity = max(0, (age - profile.GESTATION_RAMP[-1][0]) // 12)
    per_year = (Decimal("1") + profile.EXISTING_STORE_PRICE_GROWTH_YOY) * \
               (Decimal("1") + profile.EXISTING_STORE_CUSTOMER_GROWTH_YOY)
    return per_year ** years_past_maturity


def store_monthly_sales(store: Store, month_start: date, rng: Rng) -> Decimal:
    """Expected sales for one store in one month: format's mature run-rate,
    scaled by gestation ramp and post-maturity growth, divided across 12
    months, with a small independent noise term per store per month (real
    stores don't move in lockstep)."""
    age = age_months(store, month_start)
    if age < 0:
        return Decimal("0")
    annual_run_rate = profile.YEAR1_AVG_ANNUAL_SALES_INR[store.store_format]
    ramp = gestation_ramp_factor(age)
    growth = mature_growth_multiplier(age)
    noise = Decimal(str(1 + rng.uniform(-0.08, 0.08)))
    monthly = (annual_run_rate / 12) * ramp * growth * noise
    return monthly if monthly > 0 else Decimal("0")


def active_stores(stores: list[Store], month_start: date) -> list[Store]:
    return [s for s in stores if age_months(s, month_start) >= 0
              and (s.closure_date is None or s.closure_date > month_start)]
