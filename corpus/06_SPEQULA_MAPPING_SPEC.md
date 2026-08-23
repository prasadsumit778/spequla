# SPEQULA MAPPING SPECIFICATION

**File 06 of 12. Status: draft 1. The taxonomy in section 3 is provisional until a real chart of accounts is in hand.**
Implements: architecture document section 9 (company-specific configuration) and the mapping half of section 10.
Companion: `06a_SPEQULA_COA_MAPPING_TEMPLATE.xlsx`.

---

## 1. Why this is the most important file in the corpus

Connectors are commodity work. Anyone can pull rows out of a system. The mapping layer is the bridge between one company's bespoke chart of accounts and a vocabulary that is the same across every customer, and it is the only reason the second customer costs less than the first.

It is also the largest single line item in onboarding cost. Your architecture document names two of the three company-killing risks in terms of this layer: onboarding takes eight weeks and never leverages, and the metric registry is skipped early so every company becomes bespoke code. Both are mapping failures.

**The economics.** A company with 900 ledgers will have roughly 40 that carry the great majority of the value. Review those first and the pilot produces numbers in days rather than weeks. The long tail sits in a suspense class, visible and quantified in rupees, until someone cares. This is why the review queue sorts by money and never by count, and why `map_account.period_value_inr` exists in file 04.

---

## 2. The mapping chain

Every mapping decision propagates through five layers. If any link is unclear, every number downstream of it is unexplainable.

```
SOURCE     Tally ledger "Sales - Retail (Delhi)"  under group "Sales Accounts"
             |
CANONICAL  canonical_class     = revenue.product_sales
           statement_section   = pnl
           statement_line      = gross_revenue
           derived_channel     = retail
           derived_geo         = north
           derived_cost_centre = (none)
             |
METRIC     net_revenue v1, which includes revenue.product_sales and nets credit notes
             |
REPORT     Monthly pack, page 2, "Revenue by channel"
             |
ANSWER     "Retail revenue grew 12 percent, offset by higher returns"
```

Note what the ledger name gave up: a channel and a geography that exist nowhere else in the source system. This is why `dim_account.source_account_name` is stored verbatim and never cleaned. "Sales - Retail (Delhi)" title-cased and stripped of its parenthetical is just "Sales Retail", and the geography is gone forever.

---

## 3. The canonical class taxonomy

**Provisional, version 0.** This taxonomy is my construction from general knowledge of Indian mid-market accounts. It has not yet absorbed a real 900-line chart of accounts and it will be wrong in ways that only real data reveals: classes that should be split, classes nobody uses, and ledgers that fit nowhere. Revise it against the first real trial balance before freezing, per file 02 section 11.

Naming is `section.class`, lowercase, dot-separated, stable forever. A class is never renamed, only deprecated with a successor.

### 3.1 Revenue and contra-revenue

| Class | Statement line | Notes |
|---|---|---|
| `revenue.product_sales` | gross_revenue | Domestic sale of goods |
| `revenue.service_income` | gross_revenue | |
| `revenue.job_work` | gross_revenue | Manufacturing. See D-010 |
| `revenue.export_sales` | gross_revenue | Held separate because the currency and incentive treatment differ |
| `revenue.scrap_sales` | gross_revenue or cogs credit | See D-009 |
| `revenue.other_operating` | gross_revenue | Freight recovered, packing recovered, where treated as revenue |
| `contra_revenue.sales_returns` | returns | |
| `contra_revenue.trade_discount` | discounts | |
| `contra_revenue.cash_discount` | discounts | |
| `contra_revenue.rate_difference` | discounts | Very common in distribution and manufacturing |
| `contra_revenue.scheme_rebate` | discounts or opex | See D-003 |
| `contra_revenue.commission_marketplace` | net_revenue or cogs | Consumer. See D-004 |
| `contra_revenue.shipping_recovered` | net_revenue or cogs credit | Consumer. See D-005 |

### 3.2 Cost of goods sold

| Class | Notes |
|---|---|
| `cogs.raw_material` | |
| `cogs.packing_material` | Primary and secondary may need splitting. See D-013 |
| `cogs.stores_consumables` | |
| `cogs.direct_labour` | Requires a cost-centre split that often does not exist. See D-016 |
| `cogs.power_fuel` | Manufacturing. See D-015 |
| `cogs.job_work_charges` | Subcontracting paid out |
| `cogs.freight_inward` | Capitalised into inventory or expensed. See D-012 |
| `cogs.freight_outward` | The most contested line in the taxonomy. See D-011 |
| `cogs.fulfilment` | Consumer warehousing and pick-pack. See D-020 |
| `cogs.payment_fees` | Consumer gateway and COD. See D-014 |
| `cogs.stock_adjustment` | Physical versus book differences, write-downs. See D-019 |
| `cogs.absorption_variance` | Standard costing only. See D-017 |

### 3.3 Operating expense

`opex.employee_cost`, `opex.rent`, `opex.repairs_maintenance`, `opex.travel`, `opex.professional_fees`, `opex.marketing_advertising`, `opex.selling_distribution`, `opex.admin_general`, `opex.insurance`, `opex.rates_taxes`, `opex.provision_baddebt`, `opex.csr_donation`, `opex.owner_remuneration`, `opex.related_party_charges`, `opex.other`.

Two of these exist purely so that add-backs are computable without a manual hunt: `opex.owner_remuneration` and `opex.related_party_charges`. See D-021 and D-022. Every other tool makes you find these by reading ledger names each quarter.

### 3.4 Below EBITDA

`da.depreciation`, `da.amortisation`, `finance_cost.interest_debt`, `finance_cost.bank_charges`, `finance_cost.interest_other`, `other_income.interest_income`, `other_income.fx_gain`, `other_income.misc_income`, `tax.current`, `tax.deferred`, `exceptional.one_off`.

`exceptional.one_off` is populated by human judgement against the threshold in D-024, never by an AI proposal. An item classified as exceptional changes EBITDA, and a model deciding that unsupervised is exactly the failure mode this architecture exists to prevent.

### 3.5 Balance sheet

**Assets:** `asset.cash_bank`, `asset.cash_restricted`, `asset.trade_receivable`, `asset.inventory_rm`, `asset.inventory_wip`, `asset.inventory_fg`, `asset.inventory_packing_stores`, `asset.advance_supplier`, `asset.prepaid`, `asset.statutory_receivable`, `asset.loans_advances`, `asset.deposit`, `asset.investment`, `asset.fixed_asset_gross`, `asset.accumulated_depreciation`, `asset.capital_wip`.

**Liabilities:** `liability.trade_payable`, `liability.advance_customer`, `liability.statutory_payable`, `liability.employee_payable`, `liability.provision`, `liability.debt_term`, `liability.debt_working_capital`, `liability.debt_current_maturity`, `liability.debt_related_party`, `liability.bill_discounting`, `liability.lease`, `liability.other_current`.

**Equity:** `equity.share_capital`, `equity.reserves`.

`liability.bill_discounting` is a separate class rather than folded into working capital debt precisely because D-036 exists. Keeping it separate means the decision can be changed later without a remapping exercise.

### 3.6 Suspense

`suspense.unmapped` is the destination for everything not yet classified. It is a real class with a real balance, it appears on the data health screen in rupees, and it is never zero-filled or hidden. A pack cannot be generated while `suspense.unmapped` exceeds the threshold in D-053.

---

## 4. How a mapping gets made

Six steps. The column that matters is who does it.

| Step | Who | Output |
|---|---|---|
| 1. Extract the chart of accounts | Deterministic | Every ledger, group and cost centre, with 12 months of movement and closing value |
| 2. Apply exact rules | Deterministic | Known patterns matched against a rule library that grows with every company |
| 3. Propose the remainder | AI | A canonical class per unmatched account, with a confidence and a stated reason |
| 4. Auto-accept the obvious | Deterministic | Only where rules matched exactly. Still logged, still reversible |
| 5. Queue everything else | Deterministic | Review UI, sorted by rupee value descending |
| 6. Human approves, freeze and version | Person | Mapping v1 written. Metrics unlock. Later edits create v2 with an effective date |

### 4.1 What the AI proposer receives and returns

It is given: the account name verbatim, the parent group, the account type, twelve months of movement and closing value, the company's industry, the canonical class list, and up to twenty approved mappings from other companies with similar account names.

It returns strict JSON validated against a schema. An invalid response is retried once and then queued as unproposed, never repaired by guessing.

```json
{
  "source_record_id": "TAL-4001",
  "proposals": [
    {
      "canonical_class": "revenue.product_sales",
      "statement_line": "gross_revenue",
      "confidence": 0.94,
      "reason": "Ledger sits under the Sales Accounts group, credit balance, monthly movement consistent with a revenue stream.",
      "derived_channel": "retail",
      "derived_geo": "north",
      "derived_reason": "Channel and geography extracted from the ledger name text."
    },
    {
      "canonical_class": "revenue.other_operating",
      "confidence": 0.04,
      "reason": "Possible if retail here refers to a recovery rather than a sale."
    }
  ],
  "flags": ["derived_attributes_present"]
}
```

**Three constraints on the model, all enforced by the schema and not by the prompt.**

1. `canonical_class` must be a member of the taxonomy. An invented class is a rejected parse, not a new class.
2. Confidence is a self-report and is treated as a sorting hint only. It never authorises an auto-accept on its own. Only an exact rule match can auto-accept.
3. The model never sees a real customer, vendor or employee name. It sees tokens. Ledger names are not tokenised because they are the whole signal, which is a deliberate accepted exposure and is stated in the data processing agreement.

### 4.2 Auto-accept

Auto-accept requires **all** of:

- an exact match against a rule in the rule library, not a model proposal;
- the account's period value below a declared rupee ceiling;
- no conflicting mapping in a prior approved version;
- the target class not being one of the judgement classes: `exceptional.one_off`, `opex.owner_remuneration`, `opex.related_party_charges`, `cogs.absorption_variance`, `liability.bill_discounting`, `liability.debt_related_party`.

Everything auto-accepted is logged with the rule that fired and is reversible in one action. Auto-accept is a speed optimisation for the long tail, never a substitute for review of anything material.

The rule library is the compounding asset here. Every human decision on a ledger name feeds it. After ten companies it should cover most of the tail; after a hundred it is the data moat that eventually justifies a fine-tuned model, which is a P3 activity and not before.

### 4.3 The review queue

Sorted by `period_value_inr` descending. Not by count, not alphabetically, not by confidence.

Each row shows: the ledger name verbatim, its parent group, twelve months of movement as a sparkline, the closing value, the proposed class, the model's stated reason, the running percentage of total value mapped, and the rupee amount still unmapped.

The reviewer can accept, change, split across classes, or defer to suspense. Every action is one keystroke and every action is logged with a timestamp and a name.

**The number that must be on screen at all times: unmapped value in rupees.** Not percentage, not count. A reviewer who has mapped 40 of 900 ledgers and sees "97.8 percent of value mapped, ₹2.1 Cr unmapped" knows exactly when to stop. That single display is what turns a two-week task into an afternoon.

### 4.4 Ambiguity, splits and exceptions

| Situation | Handling |
|---|---|
| Two classes plausible, neither dominant | Queued with both options shown. Never auto-resolved. The system offers a choice and never guesses |
| One ledger genuinely spans two classes | Split mapping with a declared basis, either a fixed percentage or a cost-centre rule. The basis is versioned like any other mapping |
| Ledger name is uninformative, for example "Misc 3" | Proposed as `suspense.unmapped` with the twelve-month pattern shown, so the reviewer can decide from behaviour rather than from the name |
| New ledger appears mid-year | Exception raised, queued by value. The period does not lock until it is mapped or explicitly deferred |
| Ledger disappears | Prior mapping retained. Facts already loaded keep their classification. The disappearance is logged, not acted on |
| An approved mapping is later found wrong | New version with an effective date. Prior reports keep rendering with the version they were built on. This is a restatement, not a correction |

**No mapping is ever silently changed and no fact is ever reclassified in place.** A fact row carries its `mapping_version_id`, so a March pack renders with the March mapping in perpetuity.

---

## 5. Item and channel mapping

Two smaller mapping surfaces, the same machinery.

**Item mapping,** `map_item`, groups source SKUs into canonical product categories and declares the unit of measure per product family. The unit declaration is not optional: per file 03 section 6, a product family with two units blocks every per-unit metric rather than averaging incompatible quantities. See D-041.

**Channel mapping,** `map_channel`, resolves source channel strings into the frozen channel taxonomy from D-046. Consumer profile only, and the mapping is often from a free-text field in an order file where the same marketplace appears under three spellings across three years.

Both follow propose, queue by value, human approve, version, freeze.

---

## 6. Versioning and effective dating

```
mapping_version
  version_no      1, 2, 3
  status          draft -> approved -> superseded
  effective_from  a date, not a timestamp. Mappings apply to accounting periods
  approved_by     a named person
  change_reason   free text, mandatory on any version after 1
```

Four rules:

1. **Metrics do not unlock until version 1 is approved.** Before that, the product shows the data health screen and the review queue, and no statement and no metric. This is deliberate: a half-mapped company producing partial statements is worse than a company producing none.
2. **A version is immutable once approved.** Changes create the next version.
3. **Effective dating is by accounting period.** A version effective from 1 April 2026 applies to April onwards; March renders with the prior version forever.
4. **Reversal is a new version, not a delete.** Nothing in the mapping chain is ever deleted.

---

## 7. Acceptance criteria

The mapping layer is done when all of these hold:

| Criterion | Test |
|---|---|
| Every account in the source chart is either mapped or explicitly in suspense | No account has a null classification |
| Mapped value covers at least 98 percent of period value | Coverage query on `map_account.period_value_inr` |
| Unmapped rupee value is displayed on the data health screen at all times | Manual check |
| Every mapping records who approved it, when, and on what basis | No approved row with a null `approved_by` |
| A prior signed pack re-renders identically after a mapping version change | Regression test in file 11 |
| No metric is served on an unapproved mapping version | Compilation gate test |
| Statements generated from mappings tie exactly to the client's own trial balance | The hard gate in file 02 section 10 |
| The review queue sorts by rupee value, descending | UI test |
| An AI proposal for a judgement class is never auto-accepted | Rule test against the six judgement classes |

---

## 8. Open dependencies

| Item | Effect if unresolved |
|---|---|
| A real chart of accounts | The taxonomy in section 3 stays provisional and will need revision after the first company |
| D-053 unmapped threshold | The gate between badging a metric and blocking it is undefined |
| D-041 unit of measure | Item mapping cannot freeze; per-unit metrics cannot compute |
| D-046 channel taxonomy | Channel mapping has no target vocabulary |
| D-024 one-off threshold | `exceptional.one_off` has no admission criterion |
| D-011, D-015, D-016, D-036 | Four of the highest-value ledgers in a typical manufacturer have no destination class |
| VERIFY[V-003] Tally export structure | Step 1, chart of accounts extraction, has no defined input for the Tally path |
