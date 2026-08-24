# SPEQULA REPORT AND STATEMENT SPECIFICATION

**File 08 of 12. Status: draft 1. Modelled on my construction of a good pack, not on a real one.**
Implements: architecture document sections 22 (report generation) and 33 (product surfaces).

> **Revised 20 August 2026 against a real consumer MIS.** The consumer layout in section 4 is now modelled on a pack a CFO in this segment actually receives, not on my construction. The manufacturing layout remains my construction and carries the original caveat: layout conventions in this segment are habitual, a pack that looks unfamiliar gets read less, and one real manufacturing pack would improve it the same way.
>
> One finding worth carrying: the reference MIS contains no balance sheet, no cash flow and no working capital analysis at all. D-064 keeps all three in the SPEQULA pack, which means the pack offers something the incumbent MIS does not. That is a claim to test in pilot one, not to assume.

---

## 1. The governing principle

**Not a chatbot with a dashboard bolted on.** The default surface is the numbers. Ask is a tool inside that surface, the way search is inside a spreadsheet. This was settled in file 02 section 9.

Three consequences that shape every screen below:

1. **Every number is clickable.** Click through to the metric definition, the query, the rows and the source file. This is the trust mechanism, and it is what makes a promoter believe the second number after checking the first.
2. **State is always visible.** Last synced, reconciliation status and unmapped rupee value sit on the screen permanently, not behind a menu. A user should never have to go looking for a reason to distrust a figure.
3. **Uncertainty is a badge with a reason, never a percentage.** "Unreconciled: bank statement for July not received." "Estimated: 4 accounts unmapped, ₹21 lakh of value." "Inferential: no decomposition supports this." A number the user cannot audit does not appear without one of these.

---

## 2. Screens in P0

| Screen | Purpose | P0 |
|---|---|---|
| Company onboarding | Entity, fiscal calendar, profile, users | Yes |
| Data upload and sources | File drop, sync state, first-load status | Yes |
| Data health | Freshness, completeness, reconciliation, exception queue | Yes |
| Mapping review | Value-sorted queue, approve, version, freeze | Yes |
| Financial overview | Headline metrics and the statements | Yes |
| Statements | P&L, balance sheet, cash flow | Yes |
| Ask | Question, answer, chart, citation, view SQL | Yes |
| Metric definitions | Browse, override, version, approve | Yes |
| Reports | Generate, review, sign, export | Yes |
| Settings and permissions | Roles, access, audit log | Yes |
| Management dashboard, configurable | | No, P1 |
| Forecast, scenarios, insights, alerts | | No, P1 |

Ten screens. Anything not on this list is not in the first release.

---

## 3. Financial overview

The landing screen. One page, no scrolling on a laptop.

**Header strip, always present.** Company, entity, period selector, basis (accrual or cash), and three state indicators: last synced timestamp per source, reconciliation status for the selected period, and unmapped value in rupees.

**Metric tiles.** Nine, in three rows of three.

| Row | Tiles |
|---|---|
| Profitability | Net revenue, gross margin %, EBITDA |
| Position | Cash, net debt, working capital |
| Efficiency | DSO, DIO, DPO |

Each tile shows the value, the change against the prior month, the change against the same month last year, and a twelve-month sparkline. Where the metric is a ratio, the change is in basis points. Where it is currency, the change is in both rupees and percent.

**A tile for an unreconciled period is badged and shows the reason.** It is not hidden and it is not blank, because a promoter who sees a blank tile assumes the product is broken rather than that the data is incomplete.

**Below the tiles.** A revenue and gross margin chart over twelve months, and the current period's largest movement with its deterministic decomposition. In P0 that decomposition is displayed as a bridge with no narration attached.

---

## 4. Profit and loss

Two layouts. The profile determines which one renders. They are not variants of one template; the consumer statement is a contribution margin ladder and the manufacturing statement is a cost-structure P&L.

### 4.1 Consumer layout, the CM ladder

```
GMV
  memo   of which marketplace model                     [volume, not revenue]
  memo   of which buyout model
  less   GST
= Gross revenue
  less   Discount
= Net revenue
  less   Cost of goods sold                             [buyout lines only]
= Gross margin
         Gross margin %
  less   Operating cost
           Servicing cost
           Fulfilment
           Offline manpower
           Offline rent and operational
= CM1
         CM1 %
  less   Marketing
           Acquisition
           Retention
           Brand
= CM2
         CM2 %                                          [the headline number]
  less   Corporate overhead                             [never allocated]
= EBITDA
         EBITDA %
```

**Every line above CM2 is segmented** by the company's chosen dimension: product and channel by default, business unit where D-063 applies. Corporate overhead and EBITDA are entity-level only, because the overhead is deliberately unallocated.

**Marketplace GMV is shown as a memo, never summed into revenue.** Under the marketplace model revenue is commission plus advertising earnings plus platform fee, and the GMV flowing through is a volume statistic belonging to someone else's inventory.

**A line with 100 percent gross margin is not an error.** A data or insights product inside a consumer company genuinely has no COGS, and the anomaly check must not flag it.

### 4.2 Manufacturing layout

**Rows.** Assembled from `statement_line` on `dim_account`, in this order:

```
Gross revenue
  less  Returns
  less  Discounts and rate differences
= Net revenue
  less  Cost of goods sold
          Raw material
          Packing material
          Freight
          Other direct cost
          Absorption variance                    [manufacturing, if standard costing]
= Gross profit
        Gross margin %
  less  Operating expenses
          Employee cost
          Direct labour                          [D-016, resolved 2026-08-24: opex, not COGS]
          Power and fuel                         [D-015, resolved 2026-08-24: opex, not COGS]
          Marketing and advertising
          Selling and distribution
          Rent
          Repairs and maintenance
          Professional fees
          Travel
          Administration and general
          Owner remuneration                     [shown as its own line, always]
          Related party charges                  [shown as its own line, always]
          Other
= EBITDA
        EBITDA margin %
  memo  Adjusted EBITDA                          [only if add-backs are declared]
  less  Depreciation and amortisation
= EBIT
  add   Other income
  less  Finance cost
= Profit before tax
  less  Tax
= Profit after tax
```

**Owner remuneration and related party charges are always separate lines,** even when small. Burying them inside employee cost and rent is what makes an EBITDA add-back a manual hunt every quarter, and it is the first thing a buyer or lender asks to see broken out.

**Columns.** Selected period, prior period, prior year same period, and year to date with its prior year comparative. Variance columns in rupees and percent against each comparative. Budget and forecast columns exist in the layout and are empty in P0.

**Drilldowns, three levels.** Statement line to the canonical classes inside it, to the source ledgers inside those, to the journal lines inside those. Every level shows the mapping version that produced the classification.

**Rounding.** Governed by D-056. The default until it is resolved is rupees in lakhs with one decimal for statement detail, crores for headline tiles, and negatives in brackets rather than with a minus sign.

---

## 5. Balance sheet

Standard grouped presentation: current assets, non-current assets, current liabilities, non-current liabilities, equity. Restricted cash is a separate line from free cash. Bill discounting is a separate line within debt, not merged, for the reason in file 06 section 3.5.

**Columns.** Period end, prior month end, prior year end, with movement columns.

**Two hard gates.** The balance sheet must balance, and a non-balancing balance sheet is not displayed at all. And `closing_cash` from the cash flow statement must equal `cash` on the balance sheet exactly. Either failure sends the period to the exception queue and blocks the pack.

---

## 6. Cash flow

Indirect method, standard three-section presentation, starting from profit before tax. The direct-method view derived from `fact_bank_txn` is shown alongside as a check, clearly labelled as a check and not as the statement.

The working capital section is itemised by component: receivables movement, inventory movement, payables movement, other operating. A promoter reading a cash flow statement is almost always trying to answer "where did the money go", and a single working capital line does not answer it.

---

## 7. Monthly management pack

Your original brief listed eleven sections. Three of them depend on capabilities that are P1. The P0 pack is eight sections.

| # | Section | Content | Source | P0 |
|---|---|---|---|---|
| 1 | Cover and control page | Period, basis, reconciliation status, data freshness per source, unmapped value, mapping version, metric versions, snapshot id, preparer, reviewer, sign-off date | Automatic | Yes |
| 2 | Executive summary | Six to eight bullet points. **Written by a human in P0** | Human | Yes |
| 3 | Financial summary | Headline metrics with month, year and year-to-date comparatives | Automatic | Yes |
| 4 | Revenue analysis | Consumer: GMV, net revenue and the CM ladder by channel and product, with acquisition and retention split. Manufacturing: revenue by customer and product with the price, volume and mix bridge per D-059 | Automatic | Yes |
| 5 | Margin analysis | Gross margin bridge, cost line movements, absorption variance where applicable | Automatic | Yes |
| 6 | Working capital | DSO, DIO, DPO, CCC with trends, receivable and payable ageing, inventory ageing, rupee impact of each day of movement | Automatic | Yes |
| 7 | Cash | Cash movement, borrowing position, facility utilisation | Automatic | Yes |
| 8 | Statements | Full P&L, balance sheet and cash flow with comparatives | Automatic | Yes |
| 9 | Data quality appendix | Open exceptions, unmapped value, reconciliation residuals, anything the reader should know before trusting a figure | Automatic | Yes |
| 10 | Forecast | | | No, P1 |
| 11 | Key insights and recommended actions | | | No, P1 |

**Section 1 is not a formality.** A pack that states its own reconciliation status and data freshness on the cover is making a claim about its own reliability, and that claim is the product. A pack without it is just a nicer-looking version of what the CA already sends.

**Section 2 is written by hand in pilot one.** Three reasons: you need a target voice before a model can imitate one, edits per pack is meaningless without a hand-written baseline, and writing it yourself is how you learn what the pack is actually failing to explain.

**Section 9 goes in the pack, not just on a screen.** A management pack that quietly omits its own known gaps is the thing this whole architecture exists to prevent.

---

## 8. Chart rules

Rules first. A model never selects a chart in P0. Anything the rules cannot handle falls back to a table, which is always a correct answer.

| Question shape | Chart |
|---|---|
| One metric over time | Line |
| One metric over time, split by a dimension | Stacked bar, or small multiples above four series |
| Change between two periods, additive | Waterfall bridge |
| Concentration across entities | Pareto |
| Single value against a target or comparative | KPI tile with delta |
| Two metrics, correlation asked | Scatter |
| Anything else | Table |

**Store the specification, not the picture.** A chart is a JSON spec, so the same answer renders identically in the app, in a PDF pack and in an email. A chart that exists only as pixels cannot be re-rendered at a prior snapshot, which breaks reproducibility.

---

## 9. Provenance on every output

Every generated report stores, and re-rendering reproduces exactly:

- the snapshot id and knowledge-time cut
- every metric version used
- the mapping version
- data freshness per source at generation time
- reconciliation status per check
- the model name and version used for any narrated text
- the reviewer who signed it

**Re-rendering a March pack in September reproduces the March pack**, including numbers that have since been restated. The restatement is visible as a separate comparison, never as a silent change to a document someone already acted on.

---

## 10. Sign-off

| Output | Gate |
|---|---|
| Daily cash and collections view | None. Factual only |
| Financial overview screen | None. Badged where unreconciled |
| Ask answers | None in-app. Reviewer before anything leaves the company |
| Monthly management pack | Mandatory human sign-off, named reviewer |
| Anything sent to a lender, board or investor | Mandatory, and the reviewer is named on the document |

A pack cannot be signed while a blocking exception is open for the period. The reviewer can override with a written reason, which is logged and appears in section 9 of the pack itself.

---

## 11. Acceptance criteria

| Criterion | Test |
|---|---|
| P&L, balance sheet and cash flow tie to the client's own trial balance exactly | Hard gate, file 02 section 10 |
| Balance sheet balances, always | Blocking check |
| Cash flow closing cash equals balance sheet cash, exactly | Blocking check |
| Every number in the pack is traceable to source rows | Sampled test |
| Re-rendering a signed pack reproduces it exactly | Regression test, file 11 |
| The pack cannot generate while a blocking exception is open, without a logged override | Integration test |
| Owner remuneration and related party charges appear as separate lines | Layout test |
| Every chart is a stored spec, not an image | Structural test |
| Section 9 is present in every generated pack | Structural test |

---

## 12. Open dependencies

| Item | Effect |
|---|---|
| A real **manufacturing** management pack | Section 4.2 stays my construction. The consumer layout in 4.1 is now modelled on a real pack |
| D-055 Schedule III or management layout | Statement presentation |
| D-056 units and rounding | Every displayed figure. The reference MIS uses crores with one decimal at corporate level and absolute rupees at business unit level, which is worth matching |
| D-057 mandatory comparison set | Column layout on all three statements |
| ~~D-024~~ | **Resolved:** non-recurring, above 0.25% of annual revenue, named approval. The adjusted EBITDA memo line appears only where add-backs are declared |
| ~~PVM convention~~ | **Resolved as D-059:** volume at prior-period price, price at current-period volume, mix as the reported residual |
| VERIFY[V-002] Schedule III division | V-001 closed as AS, so Division I applies. Still needs a CA to confirm the presentation detail |
