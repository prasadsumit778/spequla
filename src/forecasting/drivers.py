"""Driver assumption schema for the forecast engine, corpus/13 section 3.

Every field here is a number the USER supplies -- never a default the engine
invents. corpus/13 documents the mechanics (what a store-format cohort
formula does with stores_added_per_year, what the gestation ramp does), not
the numbers themselves; there is no "typical apparel retailer" ceiling or
growth rate baked in anywhere in this module, on the same footing as
CLAUDE.md section 3.2's prohibition on inventing a threshold. A field left
unset stays unset (Decimal | None), and engine.py reports that component as
not computable rather than defaulting it -- the same not_configured
discipline as src/semantic/bridges.py and src/reports/cashflow.py.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

STORE_FORMATS = ("COCO", "COFO", "FOCO", "FOFO")


class StoreFormatDrivers(BaseModel):
    """One store format's expansion and like-for-like growth assumptions.
    corpus/13 section 2's cohort mechanics apply these per format."""
    model_config = ConfigDict(extra="forbid")

    store_format: Literal["COCO", "COFO", "FOCO", "FOFO"]
    stores_added_per_year: list[int] = Field(
        description="New stores of this format opened in forecast year 1, 2, 3 ... "
                      "one entry per forecast year, in order.")
    year1_avg_annual_sales_inr: Decimal = Field(
        gt=0, description="A new store's expected full run-rate annual sales once past gestation.")
    existing_store_price_growth_yoy: Decimal
    existing_store_customer_growth_yoy: Decimal

    @field_validator("stores_added_per_year")
    @classmethod
    def _no_negative_additions(cls, v: list[int]) -> list[int]:
        if any(n < 0 for n in v):
            raise ValueError("stores_added_per_year cannot contain a negative count")
        return v


class OnlineChannelDrivers(BaseModel):
    """One online channel's growth assumptions, corpus/13 section 3.2.

    channel_name matches a fact_channel_order_line.channel_sub value the
    baseline actually observed (baseline.py's Baseline.online_channels) --
    NOT dim_channel.channel_name, which only carries D-046's seven generic
    canonical types (every marketplace resolves to the same 'marketplace'
    dim_channel row); channel_sub is where a specific marketplace or site's
    identity actually lives on the order line. Deliberately a free-text
    match rather than a fixed tier1/tier2/own_site enum -- which marketplace
    counts as "tier 1" is a per-company judgement call this module does not
    make; a user who wants several channels to share one growth assumption
    applies the same driver values to each channel_sub, one entry per
    channel."""
    model_config = ConfigDict(extra="forbid")

    channel_name: str
    orders_growth_yoy: Decimal
    price_growth_yoy: Decimal


class CostDrivers(BaseModel):
    """Cost-line growth rates and the margin path, corpus/13 section 3.3.
    gp_margin_path has one entry per forecast year -- a path, not a single
    constant, since a real margin story is rarely flat (source data: margin
    expands over a multi-year horizon from price/vendor-term/sell-through
    effects, corpus/13 section 1)."""
    model_config = ConfigDict(extra="forbid")

    store_personnel_growth_yoy: Decimal
    store_rent_growth_yoy: Decimal
    franchise_commission_rate: Decimal
    ho_cost_growth_yoy: Decimal
    online_commission_rate: Decimal
    online_ad_spend_pct_of_sales: Decimal
    gp_margin_path: list[Decimal] = Field(description="One gross-margin fraction per forecast year.")


class ProductMixDrivers(BaseModel):
    """Category mix convergence, corpus/13 section 3.4. Optional: if omitted,
    the engine holds the baseline mix flat rather than inventing a target."""
    model_config = ConfigDict(extra="forbid")

    target_mix: dict[str, Decimal] = Field(description="Category -> target share of revenue, summing to 1.")
    convergence_years: int = Field(gt=0)

    @field_validator("target_mix")
    @classmethod
    def _mix_sums_to_one(cls, v: dict[str, Decimal]) -> dict[str, Decimal]:
        total = sum(v.values())
        if abs(total - Decimal("1")) > Decimal("0.01"):
            raise ValueError(f"target_mix must sum to 1 (within 1%), got {total}")
        return v


class ForecastDrivers(BaseModel):
    """The complete, named, user-editable assumption set for one scenario.
    corpus/13 section 3: every driver here is stored verbatim as supplied --
    a scenario is a record of what was assumed, not a computed artefact."""
    model_config = ConfigDict(extra="forbid")

    forecast_years: int = Field(gt=0, le=10)
    store_formats: list[StoreFormatDrivers] = Field(default_factory=list)
    online_channels: list[OnlineChannelDrivers] = Field(default_factory=list)
    costs: CostDrivers
    product_mix: ProductMixDrivers | None = None

    @field_validator("store_formats")
    @classmethod
    def _no_duplicate_formats(cls, v: list[StoreFormatDrivers]) -> list[StoreFormatDrivers]:
        formats = [d.store_format for d in v]
        if len(formats) != len(set(formats)):
            raise ValueError(f"duplicate store_format entries: {formats}")
        return v

    @field_validator("online_channels")
    @classmethod
    def _no_duplicate_channels(cls, v: list[OnlineChannelDrivers]) -> list[OnlineChannelDrivers]:
        names = [d.channel_name for d in v]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate channel_name entries: {names}")
        return v
