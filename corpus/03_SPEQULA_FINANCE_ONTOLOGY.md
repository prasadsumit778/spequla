# SPEQULA FINANCE ONTOLOGY

**File 03 of 12. Status: draft 1. Blocked in part by VERIFY[V-001].**
Implements: architecture document section 8 (semantic and metric layer), the definitional half.
File 05 turns these definitions into machine-readable metric contracts. This file is the human-readable authority; where the two disagree, this file is corrected and file 05 is regenerated, never the reverse.

---

## 1. How to read this file

### The three categories

Every concept below is one of three things, and confusing them is the single largest source of argument between a finance team and an FP&A tool.

| Category | Meaning | Can a company override it? |
|---|---|---|
| **STANDARD** | Defined by accounting standards or by universal practice. There is one right answer | No. An override here means the books are wrong, not the definition |
| **CONVENTION** | Universally used, but with several accepted variants, all defensible | Yes, per company. One variant must be declared |
| **MANAGEMENT** | A management construct with no statutory definition at all | Yes, per company, and expect them to differ |

A number labelled STANDARD that disagrees with the audited accounts is a bug. A number labelled CONVENTION or MANAGEMENT that disagrees is a configuration question.

### Field meanings

- **Formula** uses `metric.x` to reference another concept in this file, never a table or column. Concepts resolve to source tables only in file 05.
- **Source** names the canonical fact table in file 04 that the value derives from.
- **Grain** is the finest time period at which the concept is meaningful.
- **Aggregation** is how the concept combines across periods or dimensions. `ratio_of_sums` means the numerator and denominator are each summed first and then divided. This is stated explicitly on every ratio because averaging ratios is the most common metric bug in existence, and the quarterly gross margin is not the average of three monthly gross margins.
- **Dimensions** lists what the concept can be sliced by. A concept with no dimension list is entity-level only.
- **Decisions** lists the open items in file 00 that must be resolved before this concept can be computed for a real company.

### Sign conventions, applied everywhere without exception

1. Revenue and income are stored positive. Costs and expenses are stored positive. The statement layout applies the sign, not the data.
2. In `fact_gl_entry`, debits are positive and credits are negative in `amount_base`. Everything else derives from that.
3. Balance sheet assets are positive, liabilities and equity are negative in raw storage, and presented positive in the statement layer.
4. A movement that consumes cash is negative in the cash flow statement.
5. Percentages are stored as fractions. Basis points are computed, never stored.

### Currency

Every monetary fact stores three things: `amount_txn` in the transaction currency, `amount_base` in INR, and the rate with its source. The base amount is what every metric uses. Nothing in the metric layer ever performs a currency conversion; conversion happens once, at staging.

### Cash versus accrual

Both views exist. They are never blended in a single statement, chart or answer. Every output states which basis it is on. A promoter thinking in cash and a set of books on accrual is a normal situation, and the product's job is to show both and explain the difference, not to reconcile them into one number.

---

## 2. Profit and loss

### 2.1 Revenue

| Concept | Category | Definition | Formula | Unit | Source | Grain | Dimensions | Aggregation |
|---|---|---|---|---|---|---|---|---|
| `gross_revenue` | CONVENTION | Invoiced value of goods and services before any deduction, excluding indirect tax | Sum of invoice line taxable value, plus other operating income classified as revenue | INR | `fact_invoice_line`, `fact_gl_entry` | Day | entity, customer, product, channel, geo, cost_centre | sum |
| `returns` | STANDARD | Value of goods returned by customers | Sum of credit note lines classified as return | INR | `fact_invoice_line` where `is_credit_note` and reason is return | Day | as above | sum |
| `discounts` | CONVENTION | Deductions granted to the customer | Sum of discount amount on invoice lines, plus credit notes classified as discount or rate difference | INR | `fact_invoice_line` | Day | as above | sum |
| `net_revenue` | CONVENTION | Revenue after all customer-facing deductions. The base for every margin ratio | `metric.gross_revenue - metric.returns - metric.discounts - [other declared deductions]` | INR | derived | Day | as above | sum |

**Alternative definitions in circulation.** Whether GST is included (it should not be, but Tally ledgers are sometimes booked inclusive). Whether marketplace commission is netted here or shown as a cost. Whether scheme and rebate accruals are a revenue deduction or an opex line. Whether shipping recovered from the customer is revenue or a contra-cost. Whether sell-in to a franchisee or sell-out to the consumer is "revenue".

**Override:** allowed and expected. The deduction list is declared per company and frozen with a version.

**Decisions:** D-001, D-002, D-003, D-004, D-005, D-006, D-007, D-008, D-009, D-010.

> A note on why this is four concepts rather than one. Almost every margin dispute in a mid-market company traces back to two people using the word "revenue" for different numbers. Storing gross, the deductions and net separately, and forcing every metric to name which one it uses, removes the dispute rather than settling it.

### 2.2 Cost and gross profit

| Concept | Category | Definition | Formula | Unit | Source | Grain | Dimensions | Aggregation |
|---|---|---|---|---|---|---|---|---|
| `cogs` | CONVENTION | Cost of goods sold or services delivered | Opening stock plus purchases plus direct conversion cost less closing stock, or GL accounts mapped to the COGS class | INR | `fact_gl_entry`, `fact_inventory_position` | Month | entity, product, channel, cost_centre | sum |
| `gross_profit` | STANDARD | Net revenue less cost of goods sold | `metric.net_revenue - metric.cogs` | INR | derived | Month | as above | sum |
| `gross_margin_pct` | STANDARD | Gross profit as a proportion of net revenue | `metric.gross_profit / metric.net_revenue` | fraction | derived | Month | as above | **ratio_of_sums** |

**Alternative definitions.** The COGS boundary is the least standardised line in Indian mid-market accounts. Contested items: freight outward, freight inward, primary and secondary packing, power and fuel, direct labour, payment gateway fees, warehouse and fulfilment cost, and inventory write-downs. Standard versus actual costing changes both the number and whether absorption variance is visible.

**Override:** allowed. The COGS account class list is declared per company.

**Decisions:** D-011 through D-020.

> **The manufacturing trap.** If a company runs standard costing and absorption variance is posted below gross profit, a real fall in margin can be entirely invisible in the gross margin line. D-017 exists to force this into the open. Where absorption variance exists, the pack shows gross margin twice: before and after variance.

### 2.3 Operating expense and EBITDA

| Concept | Category | Definition | Formula | Unit | Source | Grain | Dimensions | Aggregation |
|---|---|---|---|---|---|---|---|---|
| `opex` | CONVENTION | Operating expenses excluding cost of goods sold, depreciation, amortisation, interest and tax | Sum of GL accounts mapped to opex classes | INR | `fact_gl_entry` | Month | entity, cost_centre, department | sum |
| `ebitda` | MANAGEMENT | Earnings before interest, tax, depreciation and amortisation | `metric.gross_profit - metric.opex` | INR | derived | Month | entity, business_unit | sum |
| `ebitda_margin_pct` | MANAGEMENT | EBITDA over net revenue | `metric.ebitda / metric.net_revenue` | fraction | derived | Month | as above | **ratio_of_sums** |
| `adjusted_ebitda` | MANAGEMENT | EBITDA after declared, itemised add-backs | `metric.ebitda + sum(declared add-backs)` | INR | derived | Month | entity | sum |
| `da` | STANDARD | Depreciation and amortisation for the period | Sum of GL accounts mapped to the D&A class | INR | `fact_gl_entry` | Month | entity, cost_centre | sum |
| `ebit` | STANDARD | Operating profit after depreciation and amortisation | `metric.ebitda - metric.da` | INR | derived | Month | entity | sum |
| `interest_expense` | STANDARD | Finance cost for the period | GL accounts mapped to finance cost | INR | `fact_gl_entry` | Month | entity | sum |
| `other_income` | STANDARD | Non-operating income | GL accounts mapped to other income | INR | `fact_gl_entry` | Month | entity | sum |
| `pbt` | STANDARD | Profit before tax | `metric.ebit + metric.other_income - metric.interest_expense` | INR | derived | Month | entity | sum |
| `tax_expense` | STANDARD | Current plus deferred tax | GL accounts mapped to tax | INR | `fact_gl_entry` | Month | entity | sum |
| `pat` | STANDARD | Profit after tax | `metric.pbt - metric.tax_expense` | INR | derived | Month | entity | sum |

**Alternative definitions.** EBITDA has no statutory definition at all, which is why it is labelled MANAGEMENT even though everyone treats it as standard. The live variants: before or after other income; with or without owner remuneration added back; with or without related-party rent normalised; with or without one-off items; and under Ind AS, whether lease rentals appear as opex or as depreciation plus interest, which mechanically inflates EBITDA relative to AS. The last of these is settled for this system: AS applies, so lease rentals are opex and sit inside EBITDA.

**Override:** allowed for `opex` classification, `adjusted_ebitda` add-backs and the other-income treatment. Not allowed for `ebit`, `pbt` or `pat`, which are arithmetic.

**Rule, no exceptions:** `ebitda` and `adjusted_ebitda` are separate concepts and are never blended. Any pack showing an adjusted figure shows the unadjusted figure adjacent to it and itemises every add-back.

**Decisions:** D-021 through D-027, all resolved. D-026 resolved to lease rentals expensed in full, following the closure of VERIFY[V-001] as AS.

---

## 3. Balance sheet

| Concept | Category | Definition | Formula | Unit | Source | Grain | Aggregation |
|---|---|---|---|---|---|---|---|
| `cash` | CONVENTION | Cash and bank balances available to the business | Sum of GL accounts mapped to cash and bank, per the declared inclusion rule | INR | `fact_gl_entry`, `fact_bank_txn` | Day | period_end |
| `restricted_cash` | CONVENTION | Balances not freely available: margin money, lien-marked deposits | Sum of accounts mapped to restricted | INR | `fact_gl_entry` | Day | period_end |
| `accounts_receivable` | STANDARD | Amounts due from customers for goods and services delivered | Sum of open AR items, or the AR control account | INR | `fact_ar_open`, `fact_gl_entry` | Day | period_end |
| `inventory` | STANDARD | Value of stock held, at the declared valuation basis | Sum of closing value across stock types | INR | `fact_inventory_position` | Day | period_end |
| `other_current_assets` | STANDARD | Advances, prepaid, deposits, statutory balances | Mapped GL classes | INR | `fact_gl_entry` | Day | period_end |
| `fixed_assets_net` | STANDARD | Gross block less accumulated depreciation | Mapped GL classes | INR | `fact_gl_entry` | Day | period_end |
| `accounts_payable` | STANDARD | Amounts due to suppliers | Sum of open AP items, or the AP control account | INR | `fact_ap_open`, `fact_gl_entry` | Day | period_end |
| `debt` | CONVENTION | Interest-bearing borrowings, per the declared inclusion rule | Mapped GL classes | INR | `fact_gl_entry` | Day | period_end |
| `net_debt` | MANAGEMENT | Debt less free cash | `metric.debt - metric.cash` | INR | derived | Day | period_end |
| `other_current_liabilities` | STANDARD | Statutory dues, provisions, customer advances | Mapped GL classes | INR | `fact_gl_entry` | Day | period_end |
| `equity` | STANDARD | Share capital plus reserves and surplus | Mapped GL classes | INR | `fact_gl_entry` | Day | period_end |
| `net_worth` | STANDARD | Equity attributable to shareholders | `metric.equity` | INR | derived | Day | period_end |

**Aggregation note.** Every balance sheet concept is a stock, not a flow. It has a value at a point in time and is never summed across periods. The registry enforces this with `time_logic: period_end`, and a query that attempts to sum a stock across months is rejected by the compiler rather than answered.

**Alternative definitions.** Whether cash includes fixed deposits and margin money. Whether current maturities of long-term debt, bill discounting, LC acceptances and related-party loans count as debt. Whether customer advances net against AR or sit as a liability. Whether unbilled revenue and retention money are inside AR.

**Override:** allowed for `cash`, `debt` and the AR and inventory inclusion rules. Not allowed for the accounting identity: assets always equal liabilities plus equity, and a balance sheet that does not balance is not displayed.

**Decisions:** D-029, D-032, D-033, D-034, D-035, D-036, D-037, D-018.

> **D-036 deserves separate attention.** Treating bill discounting as a reduction of receivables rather than as borrowing improves DSO and hides leverage simultaneously. It is common, it is defensible under some presentations, and a CFO will notice immediately which one you chose. Choose the honest one and disclose it.

---

## 4. Cash flow

The MVP produces the indirect method, because it derives from the P&L and balance sheet we already have. A direct-method view derives from `fact_bank_txn` and is shown alongside as a check, not as the primary statement.

| Concept | Category | Definition | Formula | Unit | Grain |
|---|---|---|---|---|---|
| `working_capital_change` | STANDARD | Cash effect of movements in operating working capital | Negative of: change in AR, plus change in inventory, less change in AP, less change in other operating balances | INR | Month |
| `operating_cash_flow` | STANDARD | Cash generated from operations | `metric.pbt + metric.da + metric.interest_expense - metric.other_income + metric.working_capital_change - taxes_paid` | INR | Month |
| `capex` | CONVENTION | Investment in fixed assets | Additions to gross block, or cash paid for capital assets | INR | Month |
| `investing_cash_flow` | STANDARD | Cash used in or generated from investing | `-metric.capex + asset_disposals + investment_movements` | INR | Month |
| `financing_cash_flow` | STANDARD | Cash from borrowings and equity, less repayment and interest | `debt_drawn - debt_repaid + equity_raised - dividends - interest_paid` | INR | Month |

**OQ-004, resolved 2026-08-24.** Of the eight formula terms above with no prior definition, two are now specified as balance-sheet deltas, using classes the taxonomy already carries:

- `investment_movements` = the cash-flow-signed period delta of `asset.investment` (closing less opening; an increase is a use of cash)
- `equity_raised` = the cash-flow-signed period delta of `equity.share_capital` (closing less opening; an increase is a source of cash)

The remaining six (`taxes_paid`, `asset_disposals`, `debt_drawn`, `debt_repaid`, `dividends`, `interest_paid`) stay explicitly undefined, not by oversight: `debt_drawn`/`debt_repaid` cannot be recovered from `debt`'s single net period-end balance if both a draw and a repayment happened in the same month, and `taxes_paid`/`dividends`/`interest_paid`/`asset_disposals` have no corresponding payable-side or gross-movement canonical class (no `liability.tax_payable`, `liability.dividend_payable` or `liability.interest_payable` exists in the taxonomy, and `asset.fixed_asset_gross` carries only a net addition-less-disposal movement) to derive an accrual adjustment or gross figure from. `investing_cash_flow`, `financing_cash_flow`, `operating_cash_flow` (still missing `taxes_paid`) and therefore `closing_cash` remain not fully computable, and the cash flow statement still does not display per the mandatory check below -- see `src/reports/cashflow.py`.
| `net_cash_movement` | STANDARD | Total change in cash for the period | `metric.operating_cash_flow + metric.investing_cash_flow + metric.financing_cash_flow` | INR | Month |
| `closing_cash` | STANDARD | Cash at the end of the period | `opening_cash + metric.net_cash_movement` | INR | Month |
| `free_cash_flow` | MANAGEMENT | Cash available after maintaining the asset base | `metric.operating_cash_flow - metric.capex` | INR | Month |

**The mandatory check.** `closing_cash` computed from the cash flow statement must equal `cash` computed from the balance sheet, exactly. This is not a tolerance. If they differ, the cash flow statement is not displayed and the difference goes to the exception queue. This single check catches more mapping errors than any other in the system, because it fails whenever a balance sheet movement has been misclassified.

**Sign convention.** An increase in receivables or inventory is a use of cash and is therefore negative. An increase in payables is a source of cash and is positive. Applied without exception.

**Decisions:** D-037. Interest paid versus interest expense differ where interest is accrued but unpaid; the cash flow uses paid, the P&L uses expense, and the difference sits in other current liabilities.

---

## 5. Working capital

| Concept | Category | Definition | Formula | Unit | Grain | Aggregation |
|---|---|---|---|---|---|---|
| `dso` | CONVENTION | Days sales outstanding: how long customers take to pay | `metric.accounts_receivable / metric.[declared revenue base] * days_in_period` | days | Month | **ratio_of_sums** |
| `dpo` | CONVENTION | Days payable outstanding | `metric.accounts_payable / metric.[declared cost base] * days_in_period` | days | Month | **ratio_of_sums** |
| `dio` | CONVENTION | Days inventory outstanding | `metric.inventory / metric.cogs * days_in_period` | days | Month | **ratio_of_sums** |
| `ccc` | CONVENTION | Cash conversion cycle | `metric.dso + metric.dio - metric.dpo` | days | Month | derived from components, never averaged |
| `working_capital` | CONVENTION | Operating working capital | `metric.accounts_receivable + metric.inventory - metric.accounts_payable` | INR | Month | period_end |

**Alternative definitions, and this is where it matters most.** DSO alone has at least six defensible forms: period-end or average receivables, gross or net revenue, 365 or 360 days, and a countback method that ages receivables against actual sales rather than using a simple ratio. They produce visibly different numbers on the same books.

The rule for SPEQULA: **match the number the promoter already computes in his head.** A technically superior definition that disagrees with what he has tracked for ten years costs you the conversation. Record which one he uses, use it, and show the alternative alongside only if he asks.

**Override:** allowed and expected on all five. The declared basis is stamped on every displayed value.

**Decisions:** D-028, D-030, D-031.

> **Do not average these across periods.** Quarterly DSO is quarterly receivables over quarterly revenue times ninety-one days. It is not the mean of three monthly DSOs. The registry enforces `ratio_of_sums` on every one of them.

---

## 6. Manufacturing operating layer

These are MANAGEMENT concepts throughout. None has a statutory definition and every one of them varies by plant.

| Concept | Definition | Formula | Unit | Source | Grain | Dimensions |
|---|---|---|---|---|---|---|
| `volume_sold` | Quantity sold in the declared unit | Sum of invoice line quantity | declared unit | `fact_invoice_line` | Day | product, customer, geo |
| `volume_produced` | Good output in the declared unit | Sum of `qty_produced` | declared unit | `fact_production_output` | Day | plant, line, product |
| `realisation_per_unit` | Average net price achieved | `metric.net_revenue / metric.volume_sold` | INR per unit | derived | Month | product, customer, channel, geo |
| `rm_cost_per_unit` | Raw material cost per unit of output | `raw_material_consumed_value / metric.volume_produced` | INR per unit | derived | Month | plant, product |
| `conversion_cost_per_unit` | Non-material cost of production per unit | `(power + direct_labour + consumables + factory_overhead) / metric.volume_produced` | INR per unit | derived | Month | plant, line |
| `capacity_utilisation_pct` | Output against practical capacity | `metric.volume_produced / practical_capacity` | fraction | derived | Month | plant, line | 
| `yield_pct` | Good output against input | `metric.volume_produced / input_quantity` | fraction | `fact_production_output` | Day | plant, line, product |
| `rejection_pct` | Rejected output against total output | `qty_rejected / (qty_produced + qty_rejected)` | fraction | `fact_production_output` | Day | plant, line, product |
| `absorption_variance` | Difference between absorbed and actual factory overhead | `absorbed_overhead - actual_overhead` | INR | `fact_gl_entry` | Month | plant |

**The unit problem.** `realisation_per_unit`, `yield_pct` and every per-unit cost are meaningless unless one consistent unit is declared per product family. A plant that reports some products in tonnes and others in pieces cannot have a single realisation number, and the product must refuse to compute one rather than producing an average of incompatible units. **DECISION-REQUIRED[D-041]** is not optional configuration; nothing in this section computes without it.

**Not in the MVP:** OEE, which requires machine-level availability, performance and quality data that these companies rarely have in a usable form. Consumption norm variance against BOM, which is P1.

**Decisions:** D-041 through D-045, D-017.

---

## 7. Consumer and retail operating layer

**Revised 20 August 2026 against a real consumer MIS.** The earlier version of this section was wrong in three ways: it omitted GMV, it started the statement at gross revenue, and it specified a single contribution margin. All three are corrected below.

### 7.1 The contribution margin ladder

A consumer P&L is not a statutory P&L with a margin line bolted on. It is a ladder, and each rung answers a different question.

```
GMV                          what the customer transacted, GST inclusive
  less  GST                  D-001 answered structurally: the tax is an explicit line
= Gross revenue
  less  Discount
= Net revenue
  less  COGS
= Gross margin               is the product itself profitable
  less  Operating cost       servicing, fulfilment, offline manpower and rent (D-060)
= CM1                        do the unit economics work before marketing
  less  Marketing            brand and performance both (D-023)
= CM2                        is marketing paying back
  less  Corporate overhead   never allocated to a unit or channel (D-062)
= EBITDA
```

**Why CM1 and CM2 are two concepts and not one.** A business can have healthy CM1 and deeply negative CM2, which means the product works and the customer acquisition does not. That is an entirely different problem from negative CM1, which means the product does not work at any volume. A single contribution margin number cannot distinguish them, and the distinction is the whole point of the statement.

| Concept | Category | Definition | Formula | Unit | Aggregation |
|---|---|---|---|---|---|
| `gmv` | MANAGEMENT | Customer-facing transacted value, inclusive of GST | Sum of order line gross amount | INR | sum |
| `gst_on_gmv` | STANDARD | Tax removed to reach gross revenue | Sum of order line tax | INR | sum |
| `operating_cost_cm1` | MANAGEMENT | Servicing, fulfilment, offline manpower, offline rent | Declared class list | INR | sum |
| `cm1` | MANAGEMENT | Gross margin less operating cost, before marketing | `metric.gross_profit - metric.operating_cost_cm1` | INR | sum |
| `cm1_pct` | MANAGEMENT | CM1 over net revenue | `metric.cm1 / metric.net_revenue` | fraction | **ratio_of_sums** |
| `cm2` | MANAGEMENT | CM1 less all marketing | `metric.cm1 - metric.marketing_spend` | INR | sum |
| `cm2_pct` | MANAGEMENT | CM2 over net revenue. The headline unit economics figure | `metric.cm2 / metric.net_revenue` | fraction | **ratio_of_sums** |
| `corporate_overhead` | MANAGEMENT | Unallocated central cost between CM2 and EBITDA | Declared class list | INR | sum |

### 7.2 Two revenue models, not one

D-061. A single consumer company commonly runs both, and they are different definitions rather than variants of one.

| | Marketplace model | Buyout model |
|---|---|---|
| Who owns the inventory | The seller does, not you | You do |
| Revenue is | Commission earned, plus advertising earnings, plus platform fee | GMV less discount less GST |
| COGS | None. Gross margin is effectively 100 percent | Cost of the goods sold |
| GMV | Flows through you but is not your revenue | Is your top line |

**Never sum GMV across the two models and call it revenue.** Marketplace GMV is a volume statistic; buyout GMV is a revenue base. A company running both will report a combined GMV figure, and the product must state which portion is which whenever it does.

A third case appears: a line with revenue and no COGS at all, such as a data or insights product. Gross margin of 100 percent is correct there and is not a data error. The anomaly check must not flag it.

### 7.3 Volume and efficiency

| Concept | Definition | Formula | Unit | Aggregation |
|---|---|---|---|---|
| `orders` | Distinct orders placed | Count distinct order id | count | sum |
| `aov` | Average order value | `metric.net_revenue / metric.orders` | INR | ratio_of_sums |
| `return_rate_pct` | Value returned over value sold | Returned value over gross revenue | fraction | ratio_of_sums |
| `channel_commission` | Commission, platform and payment fees borne | Sum of order line commission and payment fee | INR | sum |
| `marketing_spend` | All advertising and promotion | Declared class list | INR | sum |
| `marketing_cost_per_order` | Marketing per order, split by order type | `metric.marketing_spend / metric.orders` | INR per order | ratio_of_sums |
| `roas` | Net revenue per rupee of marketing | `metric.net_revenue / metric.marketing_spend` | ratio | ratio_of_sums |

**Acquisition versus retention.** Where the order file tags an order as acquisition or retention, `marketing_cost_per_order` splits on that dimension, and acquisition cost per new order is the CAC analogue. This partially reverses the earlier claim in section 10 that CAC is out of reach: it is out of reach when orders are untagged and available when they are tagged. It is still not a customer-level lifetime metric, and LTV remains out of scope.

### 7.4 Offline retail drivers

Stores, footfall, conversion percentage and AOV. Store revenue splits between the sampling or core line and the ecommerce fulfilment line where the store also serves online orders. Offline manpower and rent sit above CM1, per D-060, which is why an offline channel can show healthy gross margin and negative CM1.

### 7.5 Segmentation

D-063. A business unit dimension exists on every consumer fact and metric, but it is optional. The default segmentation for a consumer company is product and channel. Where a company genuinely runs distinct business lines with different revenue models, the business unit dimension carries them and corporate overhead stays unallocated below CM2.

**Decisions:** D-004, D-005, D-007, D-014, D-020, D-023, D-046, D-047, D-049, D-060, D-061, D-062, D-063.

## 8. Comparison and variance vocabulary

| Concept | Definition |
|---|---|
| `mom` | Current period against the immediately preceding period |
| `yoy` | Current period against the same period in the prior fiscal year |
| `ytd` | Cumulative from the fiscal year start (April, per D-038) to the current period |
| `vs_budget` | Against the approved budget version for the period. P1 |
| `vs_forecast` | Against the named forecast version for the period. P1 |
| `variance_absolute` | Actual less comparison base, in currency |
| `variance_pct` | Variance absolute over the comparison base. Undefined and displayed as such when the base is zero |
| `variance_bps` | For ratio metrics only. Difference in fractions multiplied by ten thousand. Never applied to a currency metric |

**Price, volume and mix.** Decomposing a revenue or margin movement into price, volume and mix components is arithmetic, but there is more than one standard allocation of the interaction term and they give different answers. The convention is declared once, globally, in file 05 and applied everywhere. Until it is declared, the system reports the total movement and the components it can compute unambiguously, and states that the decomposition is unavailable rather than silently choosing a convention.

**The rule that governs every explanation.** If the components of a decomposition do not sum to the total movement within a rounding tolerance, the system stops and reports the discrepancy. It does not present a partial decomposition as if it explained the whole change.

---

## 9. Language rules for anything generated

These bind the commentary layer when it arrives in P1, and they bind the analyst writing commentary by hand in pilot one.

| Wording | Permitted when | Label |
|---|---|---|
| "X fell 300 bps" | Computed from a validated query | Factual |
| "driven by Y" | A decomposition attributes the majority of the movement to Y, and the components sum | Factual |
| "coincided with Y" | Y moved in the same period but no decomposition links them | Inferential |
| "likely because Y" | A cited document or a stated management input supports it | Inferential |
| "will continue" | Never. That is a forecast and it belongs in a forecast object with an error band | Blocked |
| "improved" or "deteriorated" | Only where the direction of goodness is unambiguous. Inventory days falling is not automatically good | Use with care |

---

## 10. What is deliberately absent

| Concept | Why it is not here |
|---|---|
| LTV and cohort retention | Require customer identity resolution that does not exist in P0. CAC has a partial substitute where orders are tagged acquisition or retention, per section 7.3 |
| OEE | Requires machine data these companies rarely hold usably |
| Segment or business-unit profitability | Requires allocation rules, and allocation is a policy decision, not a calculation. P1, and every allocated number will be shown twice: before and after allocation |
| Any consolidated group metric | Multi-entity is out of P0 |
| Any Ind AS-specific concept: right-of-use assets, expected credit loss, contract assets | **VERIFY[V-001] closed: AS, not Ind AS.** These concepts are permanently out of the MVP ontology. Lease rentals are expensed in full per D-026 |
| Deferred revenue, MRR, ARR, churn | No SaaS pilot in scope |
| Any valuation metric | Different product |

---

## 11. Where this file is incomplete, and why

This file had 58 unresolved dependencies on file 00. Fifty-two of the corpus's 64 decisions are now resolved as global defaults, recorded in file 00 section 2b. Twelve remain open, eleven of them per-company. Rather than pick defaults silently, the concepts above name the decisions they depend on and file 05 will not compile a metric whose governing decision is unresolved.

Two areas are structurally incomplete and will stay that way until external input arrives:

1. **RESOLVED. VERIFY[V-001] closed on 20 August 2026: AS, not Ind AS.** D-026 resolves to lease rentals expensed in full. This should still be reconfirmed with a CA per company at onboarding, because a company approaching the net worth threshold will transition, and the transition changes EBITDA mechanically.

2. **The per-company deduction and COGS inclusion lists.** The debt inclusion list is now settled globally by D-035. These are genuinely company-specific and no amount of research produces them. They come from the accounting policy conversation in file 00, one company at a time, and they are the reason the override chain exists.
