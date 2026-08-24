# SPEQULA FORECASTING SPEC

**File 13 of 13. Status: draft 1. Added 2026-08-24.**

Authority over: driver-based revenue and cost projection for the apparel/retail profile -- what a scenario is, what a driver is, and the formulas the forecast engine runs. Same standing as every other corpus file: the code cites this file's sections, and where code and this file disagree, this file is corrected and the code follows, never the reverse.

---

## 0. Why this file exists, and why now

`CLAUDE.md` section 10 lists "forecasting, scenario engine" as out of scope, gated in `corpus/02` section 5 on a specific trigger: *"Statements tie for three consecutive months."* No live pilot tenant exists yet, so that trigger has not fired in the way corpus/02 anticipated -- this file exists because the forecast engine was started deliberately ahead of it, against a synthetic dataset built for exactly this purpose, by founder decision (D-069, `corpus/00`). `CLAUDE.md` and `corpus/02` are updated in the same change that adds this file, so the corpus stays internally consistent rather than silently drifting from what the code actually does.

## 1. What this engine is, and is not

A deterministic, formula-driven projection: observed baseline facts (read off the canonical model, never invented) plus explicit driver assumptions (supplied by the user, never defaulted by the engine) produce a year-by-year operating P&L. Nothing here is a model call -- the same posture as the semantic compiler (`CLAUDE.md` invariant 1, "no model ever writes SQL"): no forecast number is produced that doesn't trace to either an observed figure or a driver the user typed in.

**Not built here:** valuation, DCF, IRR, exit multiples, WACC, a cap table, or any financing/investment-decision layer. This is an operating forecast for a management team, not an investment-banking model. A component with no matching baseline observation and no matching driver is reported as a gap (`ForecastResult.gaps`, `src/forecasting/engine.py`) -- never zeroed, never silently omitted, the same `not_configured` discipline as `src/semantic/bridges.py` and `src/reports/cashflow.py` (see `OPEN_QUESTIONS.md` OQ-004 for the same pattern applied to the cash flow statement).

## 2. Store-cohort mechanics (offline revenue)

Every retail store belongs to a **format**: `COCO` (company-owned, company-operated), `COFO` (company-owned, franchise-operated), `FOCO` (franchise-owned, company-operated), `FOFO` (franchise-owned, franchise-operated) -- standard Indian apparel-retail vocabulary, carried on `dim_location.store_format` (`corpus/04` section 3.10).

A store's revenue trajectory depends only on its format and how long it has been open:

- **Gestation ramp.** A new store does not open at full run-rate. `synthetic/apparel/stores.py` (data generation, monthly granularity) and `src/forecasting/engine.py` (projection, annual granularity) both implement the same two-stage ramp: the first year at 55% of the format's mature run-rate, the second year at 80%, the third year onward at 100%, growing from there. The two modules restate the same ramp at different granularities because a synthetic company's monthly GL needs monthly detail and a driver's `stores_added_per_year` is inherently annual -- there is no finer grain to project into.
- **Existing-store like-for-like growth.** Once past gestation, a store grows the way any mature retail store does: **price increase x customer-count increase**, compounded per year. Both rates are declared per format (`StoreFormatDrivers.existing_store_price_growth_yoy`, `.existing_store_customer_growth_yoy`) -- there is no SPEQULA-wide default; a company's own pricing and footfall trends are a property of that company's books, the same reasoning `corpus/00` gives for D-001/D-002/D-012 and the rest of the "properties of a specific company's own books" list.
- **Existing stores vs. new-store cohorts are modelled separately and summed**, exactly as the source financial model this spec is derived from does: existing stores grow forward from `baseline.store_sales_per_format_annual` (an **observed** blended run-rate across a format's currently-active stores, `src/forecasting/baseline.py`), because that figure is a fact about this company's own stores. New stores added during the forecast have no observed history, so they ramp up from `StoreFormatDrivers.year1_avg_annual_sales_inr` -- an **assumption**, not an observation. A engine that blended the two would either understate a mature portfolio's growth or overstate a green cohort's -- keeping them apart is what makes each half of the number honest about what it's based on.
- **Franchise commission** applies to every format except `COCO` -- a structural fact about what a format *means* (a COCO store has no franchise party in the relationship at all to pay a commission to), not a per-company assumption, so it is not a driver field. The rate itself (`CostDrivers.franchise_commission_rate`) is a real driver, since how much commission a company pays its franchise partners is very much a company-specific fact.

## 3. Driver taxonomy (`src/forecasting/drivers.py`)

Every field below is Pydantic-validated user input. None has a SPEQULA-supplied default.

| Model | Fields | Notes |
|---|---|---|
| `StoreFormatDrivers` | `store_format`, `stores_added_per_year` (one entry per forecast year), `year1_avg_annual_sales_inr`, `existing_store_price_growth_yoy`, `existing_store_customer_growth_yoy` | One entry per format the scenario models. A format present in the baseline but absent from the scenario's drivers surfaces as a gap, not a silently-flat projection. |
| `OnlineChannelDrivers` | `channel_name`, `orders_growth_yoy`, `price_growth_yoy` | `channel_name` matches a `fact_channel_order_line.channel_sub` value the baseline observed -- **not** `dim_channel.channel_name`, which only carries D-046's seven generic canonical types (every marketplace resolves to the same `marketplace` row; `channel_sub` is where a specific marketplace's identity actually lives). Deliberately **not** a fixed `tier1`/`tier2`/`own_site` enum either -- which marketplace counts as "tier 1" is a per-company judgement call this spec does not make; a user who wants several channels to share one growth assumption applies the same driver values to each channel by name. |
| `CostDrivers` | `store_personnel_growth_yoy`, `store_rent_growth_yoy`, `franchise_commission_rate`, `ho_cost_growth_yoy`, `online_commission_rate`, `online_ad_spend_pct_of_sales`, `gp_margin_path` (one fraction per forecast year) | `gp_margin_path` is a path, not a constant -- a real margin story is rarely flat (price increases, better vendor terms and higher full-price sell-through all move it over a multi-year horizon). |
| `ProductMixDrivers` | `target_mix` (category -> share, summing to 1), `convergence_years` | Optional. If omitted, the engine holds the observed baseline mix flat rather than inventing a target -- see `src/forecasting/engine.py::_project_category_mix`. |

## 4. Baseline (`src/forecasting/baseline.py`)

Read-only, the same posture as `src/reports/query.py`, which it's built on. Observes, over a trailing window (default twelve months) ending at `as_of`:

- Active stores (`dim_location` where `status='active'` and `store_format IS NOT NULL`), by format and vintage.
- **Blended** per-store annual rent and personnel cost (`opex.store_rent`, `opex.store_personnel`) -- these are single canonical classes covering every format's stores together (`corpus/06` section 3.3), so a per-format split would be an invented allocation, not an observed fact. The same reasoning `src/reports/manufacturing_operating.py` already documents for why it doesn't split company-wide cost by product.
- Observed per-format store sales run-rate, from the order file (`fact_channel_order_line` joined to `dim_location` via `location_key`), not the GL -- consistent with how a store cohort is defined in the first place.
- Distinct online channels active in the window, with monthly order count and AOV, from the order file directly.
- Category mix, from `fact_channel_order_line` joined to `dim_product.category`.
- Blended company overhead (`opex.employee_cost` + `cogs.fulfilment` [warehousing] + `opex.admin_general`), and gross margin, reusing `src/reports/pnl.py::compute_consumer_cm_ladder` rather than re-deriving margin logic.

## 5. Persistence (`src/forecasting/scenario.py`, `db/migrations/tenant/0022`)

A **scenario** is a named, saved driver-assumption set (`forecast_scenario`), append-only -- an edited assumption set is a new scenario row, never an `UPDATE`, the same discipline `CLAUDE.md` invariant 4 requires everywhere else. A **run** (`forecast_run`) snapshots the baseline and the computed result together at the moment it executed, so re-viewing a past run reads exactly what it produced that day, even if the canonical model has since been restated -- the same reproducibility contract `report_artefact` gives the monthly pack (`corpus/08` section 9).

## 6. What this spec deliberately leaves open

- Which canonical GL classes bear which store cost is a mapping-time decision (`corpus/06` section 3.3's `opex.store_rent`/`opex.store_personnel`/`opex.franchise_commission`), not a forecasting-time one.
- Balance sheet and cash flow projection: not built. This spec covers the operating P&L only (section 1).
- Scenario comparison / a scenario DAG (`corpus/02` section 5's own phrasing): not built. Each run stands alone; nothing here diffs two scenarios against each other yet.
