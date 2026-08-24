# SPEQULA OPEN DECISIONS REGISTER

**File 00 of 12. Status: draft 1, unresolved.**
Implements: nothing. This file exists so that no other file in the corpus invents a finance decision silently.

---

## 1. Why this file exists

Every other document in this corpus will contain definitions, formulas and defaults. Some of those are facts of accounting and are not negotiable. Others look identical on the page but are actually choices, and reasonable finance people pick differently. A specification that does not separate the two produces a system that computes a defensible-looking number using a convention the client never agreed to.

This register holds every one of those choices. Two marker types are used throughout the corpus, both greppable:

```
DECISION-REQUIRED[D-nnn]   a finance or product judgement call. Owner: Bhavya.
VERIFY[V-nnn]              an external fact I could not confirm. Owner: named per item.
```

**The corpus is not complete until every D is resolved and every V is confirmed.** Current counts are in section 2. Where a downstream file needs an unresolved decision, it carries the marker inline rather than picking one.

Three rules govern this file:

1. I do not resolve a D. I lay out the options and the consequence. You resolve it, or the client's finance lead does.
2. A resolved D is recorded with a date and a name, and becomes the global default in the metric registry. It can still be overridden per company, which is what the override chain in the metric registry is for.
3. A V is not resolved by me searching harder. It is resolved by someone touching the real thing: a live Tally installation, a real bank statement, a CA, a lawyer.

---

## 2. Counts

| | Total | Resolved | Open |
|---|---|---|---|
| DECISION-REQUIRED | 69 | 65 | 4 |
| VERIFY | 14 | 2 | 12 |

Fifty-nine is higher than the 35 to 50 I estimated. The overrun comes almost entirely from carrying two operating layers instead of one: sections G and H below are 10 decisions that would not exist if you had picked manufacturing alone.

**Priority.** Not all 59 block the build. The ones marked **P0-BLOCKING** must be resolved before the metric registry can be written. There were 29. Eighteen are now resolved, leaving 11, all listed in section 2b. The original 29 were: D-001, D-002, D-003, D-004, D-006, D-011, D-012, D-015, D-016, D-017, D-018, D-021, D-023, D-024, D-026, D-028, D-030, D-031, D-033, D-034, D-036, D-038, D-039, D-041, D-042, D-046, D-048, D-050, D-058. The rest can be resolved during pilot one and default to the option marked *(suggested)* in the meantime, with the default recorded as a decision rather than a silent assumption.

---

## 2b. RESOLVED

**Resolved 20 August 2026 by Bhavya Singhal, founder.** These are now global defaults, compiled into the metric registry and overridable per company through the chain in file 05. Five decisions (D-060 to D-064) were added after reviewing a real consumer MIS; the reasoning is in section L.

**D-065 to D-068 added 24 August 2026,** closing OQ-001, OQ-003 and OQ-005 (`OPEN_QUESTIONS.md`) -- gaps in the corpus that named a threshold's existence ("a declared rupee ceiling," "under the configured cap") without ever stating the number, or a policy area (tenant retention) with no decision id at all, discovered while implementing the mapping engine's auto-accept gate, Ask's admission control, and the tenant deletion path.

**D-069 added the same day**, a different kind of decision from the other four: not a corpus gap discovered mid-build, but a deliberate scope decision -- start the forecast engine (`CLAUDE.md` section 10, `corpus/02` section 5) ahead of its stated trigger, against a purpose-built synthetic apparel/retail dataset rather than a live pilot's tied statements. See `corpus/13`.

| ID | Resolution |
|---|---|
| **D-003** | Returns, trade discount, cash discount, rate difference. Scheme and rebate accruals excluded, treated as opex. |
| **D-004** | Commission borne is a cost above gross profit. Commission earned under the marketplace model is revenue. See D-061. |
| **D-011** | Opex for manufacturing, COGS for consumer. |
| **D-021** | No add-back by default. Adjusted EBITDA is a separate memo line, add-backs itemised. |
| **D-023** | All marketing sits in the CM1 to CM2 step. Never inside CM1, never inside corporate overhead. |
| **D-024** | Non-recurring, above 0.25% of annual revenue, named approval with a written reason. Never assigned by AI. |
| **D-026** | AS regime. Lease rentals expensed in full. |
| **D-028** | Period-end AR, net revenue, 365 days. Excludes unbilled and marketplace settlement. Does not net bill discounting. |
| **D-030** | On COGS, not purchases. Founder decision for CCC internal consistency. Switchable. Overstates payment days in inventory-build months. |
| **D-031** | On COGS. RM plus WIP plus FG for manufacturing, FG only for consumer. |
| **D-033** | Own line, never inside trade AR. |
| **D-034** | Free cash only. Restricted balances shown separately. |
| **D-036** | Debt, with the receivable retained. Not netted against AR. |
| **D-038** | April to March. |
| **D-039** | The SPEQULA analyst locks when the pack is signed, targeting the 15th of the following month. |
| **D-046** | Own website, marketplace (per marketplace), quick commerce (per platform), owned retail, franchise retail, distributor, exports. |
| **D-048** | Superseded by the CM1 and CM2 ladder. A single contribution margin metric no longer exists. |
| **D-051** | Zero. Settled, not open. |
| **D-053** | Block above 2% of period value, badge between 0.5% and 2%, silent below 0.5%. |
| **D-058** | Employees excluded from model-reachable views entirely. Customers and vendors tokenised, group/segment/category retained. |
| **D-059** | Volume at prior-period price, price at current-period volume, mix as residual. Residual always reported. |
| **D-060** | Servicing, fulfilment, offline manpower, offline rent. Marketing excluded by design. |
| **D-061** | Marketplace: revenue is commission plus advertising earnings plus platform fee. Buyout: revenue is GMV less discount less GST. |
| **D-062** | Never allocated. Always shown unallocated below CM2. |
| **D-063** | Optional, not mandatory. Default consumer segmentation is product and channel. |
| **D-064** | Included. Balance sheet, cash flow and working capital ship in the P0 pack. |
| **D-065** | Auto-accept rupee ceiling: flat ₹1,00,000 per period, not a percent of revenue (revenue is not computable at auto-accept time, before any mapping version exists). |
| **D-066** | Ask admission gate 6 cost cap: ₹5 per query, estimated AI model spend. |
| **D-067** | Ask admission gate 7 row cap: confirmed at 10,000, applied via LIMIT. |
| **D-068** | Tenant data retention: request-triggered deletion only (named requester, named reason). No automatic time-based purge. |
| **D-069** | Forecast engine started 2026-08-24, ahead of its corpus/02 section 5 trigger ("statements tie for three consecutive months"), against a synthetic apparel/retail dataset. See corpus/13. |
| **D-001** | Exclusive. Sales ledgers carry the pre-tax value; GST is a separate output-tax credit. Resolved 2026-08-24 for the apparel pilot, matches how its GL was already built. |
| **D-002** | Invoice date. Revenue recognised when the sale is booked, no separate dispatch/delivery lag. Resolved 2026-08-24 for the apparel pilot. |
| **D-006** | Sell-out. Franchise-operated (COFO/FOCO/FOFO) revenue is the end-consumer retail sale value; franchise commission is a separate cost line, not a netting of revenue. Resolved 2026-08-24. |
| **D-012** | Expensed. Freight inward hits the P&L directly rather than being capitalised into inventory value. Resolved 2026-08-24. |
| **D-015** | Opex, not COGS. `cogs.power_fuel` renamed `opex.power_fuel`; corpus/08 section 4.2's manufacturing row order moved accordingly. Resolved 2026-08-24. |
| **D-016** | Opex, not COGS. `cogs.direct_labour` renamed `opex.direct_labour`; same corpus/08 section 4.2 move as D-015. Resolved 2026-08-24. |
| **D-017** | Standard costing, absorption variance sits in COGS. Matches `cogs.absorption_variance` already existing as a canonical class and the manufacturer company's own established policy. Resolved 2026-08-24. |
| **D-018** | FIFO. Resolved 2026-08-24. Note: the manufacturer synthetic company's own profile.py comment states weighted average as *that* company's book policy -- since no per-tenant override exists yet (see the note above the "Still open" table), FIFO is now the enforced global default for both companies; the manufacturer comment is aspirational until that override mechanism is built. |

### Second pass, 20 August 2026: suggested defaults accepted

Twenty-five further decisions resolved by accepting the suggested option in the body of this file. One was not accepted as suggested; see D-020.

| ID | Resolution |
|---|---|
| **D-005** | Shipping recovered from the customer is a contra to freight cost, not revenue. |
| **D-007** | Quick commerce revenue recognised on despatch to the dark store. Dark-store stock remains our inventory until sold. |
| **D-008** | Export sales booked at the invoice-date rate. Exchange difference sits in other income, not in revenue. |
| **D-009** | Scrap sales credit COGS as a yield recovery, not revenue. Manufacturing only. |
| **D-010** | Job work income received is a revenue line, not netted against conversion cost. |
| **D-013** | Primary and secondary packing material both in COGS. |
| **D-014** | Payment gateway and COD fees in COGS. Variable per order. |
| **D-019** | Inventory write-down and obsolescence provision in COGS, not exceptional. |
| **D-020** | **Resolved against D-060, not against the original suggestion.** Consumer: warehouse, fulfilment and offline manpower sit in operating cost above CM1, NOT in COGS, otherwise the CM1 rung loses its meaning. Manufacturing: warehousing stays in COGS, since there is no ladder. |
| **D-022** | Related-party rent and charges reported as booked. Any normalisation is an itemised adjusted-EBITDA add-back, never a silent restatement. |
| **D-025** | EBITDA struck before other income. Interest income never treated as operating. |
| **D-027** | CSR, donations and directors' sitting fees inside EBITDA. |
| **D-029** | Unbilled revenue and retention money excluded from AR, disclosed separately. Consistent with D-028. |
| **D-032** | Customer advances shown as a liability, never netted against AR. Netting flatters DSO. |
| **D-035** | Debt includes term loans, cash credit and overdraft, current maturities, bill discounting (per D-036) and unsecured related-party loans. Excludes lease liabilities, since AS applies and no lease liability is recognised. |
| **D-037** | Capex measured as additions to gross block plus capital WIP movement, not cash paid. |
| **D-040** | Every change to a locked period is flagged. Notification above 0.25 percent of period revenue, aligned with D-024. |
| **D-043** | Yield measured at output in the declared unit, rejection counted at output. Per-company override where the process demands it. |
| **D-044** | WIP valued and included in inventory metrics where the ERP tracks it. Where it does not, DIO is computed on RM plus FG and the exclusion is stated on the output. |
| **D-045** | Subcontracted and job work volume counted in own output, flagged separately so it can be excluded. |
| **D-047** | Returns booked in the period the return occurs, matching the books. Not restated to the original sale period. |
| **D-049** | AOV computed net of returns, per order. |
| **D-054** | An unreconciled period blocks the monthly pack. It does not ship badged. |
| **D-055** | Management layout, with a Schedule III Division I reconciliation appendix. AS regime per V-001. |
| **D-056** | Crores with one decimal for headline metrics, lakhs with one decimal for statement detail, absolute rupees at business unit level per the reference MIS. Negatives in brackets. |
| **D-057** | Prior month and prior year mandatory on every statement. Budget only where the client has one in usable form. Forecast column present in the layout, empty in P0. |

**D-020 conflicted with D-060 and was resolved against the suggestion.** The original suggestion put warehouse and fulfilment in COGS. D-060, settled from the reference MIS, puts fulfilment in operating cost above CM1. Accepting the suggestion literally would have double-counted fulfilment into COGS and emptied the CM1 rung of meaning. The ladder wins for consumer; COGS wins for manufacturing, which has no ladder.

### Still open: 4

| ID | Why it stays open |
|---|---|
| D-041 | Declared unit of measure per product family. Nothing per-unit computes without it |
| D-042 | Capacity basis: installed, rated or practical |
| D-050 | Franchise inventory: consignment or sold |
| D-052 | Books-to-bank tolerance. Set after observing two months of real residuals. Deliberately not invented |

D-001, D-002, D-006, D-012, D-015, D-016, D-017 and D-018 were resolved 2026-08-24 for the apparel pilot's own books -- see section 2b. They are recorded here as **global** defaults (there is no per-tenant override mechanism built yet, despite section 1 rule 2's framing of an override as always available; `src/config/loader.py`'s `ConfigRegistry` reads one `config/decisions.yml`, not one per tenant), so the manufacturer reference company now reports under the same answers. Three of the remaining four (D-041, D-042, D-050) are properties of a specific company's books that were simply never asked. The fourth, D-052, is a threshold that can only honestly be set from observation. None blocks the build.

### Superseded: original P0-blocking list

D-001, D-002, D-006, D-012, D-015, D-016, D-017, D-018, D-041, D-042, D-050.

Every one of these is a property of a specific company's books rather than a product policy. None can be answered in the abstract and none blocks the build, because the override mechanism is specified. They are the accounting policy interview, run once per pilot.

### VERIFY closed

| ID | Outcome |
|---|---|
| **V-001** | **AS, not Ind AS.** Confirmed by the founder. Resolves D-026 to lease rentals expensed in full, and removes right-of-use assets, expected credit loss and contract assets from the ontology entirely. |
| **V-012** | Zero-retention terms acceptable, US-hosted inference acceptable to target promoters. |
| **V-003** | Still open, and **no longer blocking**. The Tally agent is P1. Pilot one uses whatever export the customer can produce, normalised by hand into the file 01 templates. The Tally tab of the data request stays a placeholder. |

---

## 2c. Section L. Decisions added from the reference MIS

A real consumer MIS was reviewed on 20 August 2026. It corrected three material errors in this corpus and produced five new decisions.

**What it corrected.** The consumer P&L is a contribution margin ladder, not a statutory P&L: GMV, less GST, less discount, less COGS, less operating cost, less marketing, less corporate overhead. GMV was absent from the ontology entirely. And a single contribution margin metric collapses CM1 and CM2 into one number, which destroys the most important distinction in the statement: CM1 answers whether unit economics work before marketing, CM2 answers whether marketing pays back. In the reference file CM1 was positive while CM2 was negative, so collapsing them would have hidden exactly what the reader needed.

| ID | Decision | Resolution |
|---|---|---|
| **D-060** | CM1 operating cost composition | Servicing, fulfilment, offline manpower, offline rent. Marketing excluded |
| **D-061** | Marketplace versus buyout revenue | Both supported as distinct models, not one with a switch |
| **D-062** | Corporate overhead allocation | Never allocated. Unallocated below CM2 |
| **D-063** | Business unit dimension | Optional. Default consumer segmentation is product and channel |
| **D-064** | Balance sheet, cash flow and working capital in the pack | Included, despite the reference MIS having none of them |

**One observation worth carrying forward.** The reference MIS contains no balance sheet, no cash flow and no working capital analysis at all. That is what a CFO in this segment currently receives. D-064 keeps them in the SPEQULA pack, which means the pack is offering something the incumbent MIS does not, and that is a claim to test in pilot one rather than assume.

---

## 3. How to use this as a customer conversation

Sections A through J are, in order, a working script for a ninety-minute conversation with a pilot customer's finance lead or CA. Run it once per company. Record the answers in the resolution column. That conversation is also the most useful qualification call you will have, because a company that cannot answer section B has a bigger problem than a missing FP&A tool.

You have said you are the approver for pilot one. That is workable, but log it explicitly: the audit trail should record that the founder signed off the mappings, not an independent finance professional, because that is a fact a later customer or investor may ask about. It should also come with a hard rule for pilot one: any decision in section A or B that you are not certain about goes to a CA before it is frozen, not after the pack ships.

---

## SECTION A. Revenue and its boundaries

| ID | Decision | Options | Why it matters | Blocks |
|---|---|---|---|---|
| **D-001** | Are sales ledgers booked GST-inclusive or GST-exclusive? | (a) exclusive *(suggested, and the norm)*; (b) inclusive; (c) mixed by ledger | If the mapping assumes exclusive and one ledger is inclusive, revenue for that stream is overstated by the GST rate. This is a silent 12 to 18 percent error that no downstream check catches unless GST reconciliation is running, and it is not in P0. **P0-BLOCKING** | 03, 05, 06 |
| **D-002** | Revenue recognised at invoice date, dispatch date, or delivery/acceptance? | (a) invoice *(suggested)*; (b) dispatch; (c) delivery | Determines the event_date on `fact_invoice_line` and therefore which month a sale lands in. Ex-works versus delivered terms make this material for manufacturers with long freight legs. **P0-BLOCKING** | 04, 05 |
| **D-003** | Which deductions net off to reach net revenue? | Tick each: sales returns; trade discount; cash/early-payment discount; rate difference credit notes; scheme and rebate accruals; freight recovered | Every combination is defensible. Different combinations move gross margin by hundreds of basis points. **P0-BLOCKING** | 03, 05 |
| **D-004** | Marketplace commission: netted from revenue, or booked as a cost line? | (a) net from revenue; (b) cost line above gross profit *(suggested)*; (c) cost line below gross profit | Changes both revenue and gross margin. Consumer only. **P0-BLOCKING** | 03, 05, 06 |
| **D-005** | Shipping charged to the customer: revenue, or contra to freight cost? | (a) revenue; (b) contra-cost *(suggested)* | Consumer only. Inflates revenue and depresses margin percentage if treated as revenue. | 03, 05 |
| **D-006** | Franchise channel: is revenue the sell-in to the franchisee or the sell-out to the consumer? | (a) sell-in *(suggested, and usually the only one you have data for)*; (b) sell-out | Sell-out is the more useful management number and the harder data problem. Confirm what the franchisee actually reports. Consumer only. **P0-BLOCKING** | 04, 05, 06 |
| **D-007** | Quick commerce: revenue on despatch to the dark store, or on sale to the consumer? | (a) despatch *(suggested)*; (b) sale | Determines whether dark-store stock is your inventory or their receivable. Consumer only. | 04, 05 |
| **D-008** | Export sales: booked at the invoice-date rate, at a policy rate, or at the realisation rate? And does exchange difference sit in revenue or in other income? | (a) invoice-date rate, exchange difference in other income *(suggested)*; (b) invoice-date rate, exchange difference in revenue; (c) policy rate | Manufacturing, and any consumer brand exporting. Affects the txn/base amount pair on every fact row. | 04, 05 |
| **D-009** | Scrap sales: revenue line, or credit to COGS? | (a) other income; (b) credit to COGS *(suggested for manufacturing, since it is a yield recovery)*; (c) revenue | Manufacturing only. Can move gross margin by 50 to 150 bps in metal-intensive businesses. | 03, 05 |
| **D-010** | Job work income received: revenue line, or netted against conversion cost? | (a) revenue *(suggested)*; (b) netted | Manufacturing only. | 03, 05 |

---

## SECTION B. COGS and the gross margin boundary

This is the section where two people in the same company most often mean different things, and it is the one your architecture document calls out by name.

| ID | Decision | Options | Why it matters | Blocks |
|---|---|---|---|---|
| **D-011** | Freight outward: COGS or opex? | (a) COGS; (b) opex *(suggested for manufacturing)*; (c) COGS for consumer, opex for manufacturing | The single most common gross-margin argument in Indian mid-market. **P0-BLOCKING** | 03, 05, 08 |
| **D-012** | Freight inward and clearing: capitalised into inventory value, or expensed? | (a) capitalised *(suggested, and usually what the books already do)*; (b) expensed | Changes both inventory value and COGS timing. Check what the books actually do rather than what policy says. **P0-BLOCKING** | 04, 05 |
| **D-013** | Primary and secondary packing material: COGS or opex? | (a) both COGS *(suggested)*; (b) primary COGS, secondary opex; (c) both opex | | 03, 05 |
| **D-014** | Payment gateway and COD fees: COGS or opex? | (a) COGS *(suggested, it is variable per order)*; (b) opex | Consumer only. Affects contribution margin more than gross margin. | 03, 05 |
| **D-015** | Power and fuel: COGS, or opex? | (a) COGS via absorption *(suggested)*; (b) opex | Manufacturing only. In an energy-intensive plant this is 5 to 15 percent of cost and its placement moves gross margin materially. **P0-BLOCKING** | 03, 05 |
| **D-016** | Direct factory labour: inside COGS, or inside the employee cost line? | (a) COGS *(suggested)*; (b) employee cost | Manufacturing. Note the books usually put all payroll in one line, so this requires a cost-centre split that may not exist. If it does not exist, say so rather than estimating. **P0-BLOCKING** | 03, 05 |
| **D-017** | Standard costing or actual costing? If standard, does absorption variance sit in COGS? | (a) actual *(suggested if available)*; (b) standard with variance in COGS; (c) standard with variance below gross profit | Manufacturing. Your architecture document names absorption variance masking a real margin fall as the characteristic manufacturing anomaly. If the client runs standard costing, this decision is the difference between catching that and hiding it. **P0-BLOCKING** | 03, 05, 09 |
| **D-018** | Inventory valuation basis? | (a) weighted average *(most common in Tally)*; (b) FIFO; (c) standard | Do not assume. Read it from the books. **P0-BLOCKING** | 04, 05 |
| **D-019** | Inventory write-down and obsolescence provision: COGS, or exceptional? | (a) COGS *(suggested)*; (b) exceptional, excluded from EBITDA | | 03, 05 |
| **D-020** | Warehouse rent, labour and fulfilment cost: COGS or opex? | (a) COGS *(suggested for consumer)*; (b) opex | Consumer only. | 03, 05 |

---

## SECTION C. Operating expense, EBITDA and add-backs

| ID | Decision | Options | Why it matters | Blocks |
|---|---|---|---|---|
| **D-021** | Owner and promoter remuneration: added back to EBITDA? | (a) no add-back, report as booked *(suggested as the default, with an adjusted-EBITDA line shown separately)*; (b) add back in full; (c) add back the excess over a market salary | Never blend. If you add back, show both numbers. This is the number a buyer will argue about later and it is worth getting the discipline right now. **P0-BLOCKING** | 03, 05, 08 |
| **D-022** | Related-party rent and charges: adjusted to market, or left as booked? | (a) as booked *(suggested)*; (b) adjusted, with the adjustment disclosed | | 03, 05 |
| **D-023** | Performance marketing: variable cost (inside contribution margin) or fixed opex? | (a) variable *(suggested for consumer)*; (b) fixed | Consumer. Determines whether contribution margin means anything. **P0-BLOCKING** | 03, 05 |
| **D-024** | What counts as a one-off, and above what value? | Define: categories, and a rupee or percent-of-revenue threshold | Without a rule, one-offs become whatever makes the quarter look better. **P0-BLOCKING** | 03, 05, 09 |
| **D-025** | Is EBITDA struck before or after other income? Which other income counts as operating? | (a) before other income *(suggested)*; (b) after, with interest income excluded; (c) after, in full | | 03, 05 |
| **D-026** | Lease rentals: expensed in full, or split into depreciation and interest? | (a) expensed *(correct under AS)*; (b) right-of-use split *(correct under Ind AS 116)* | **RESOLVED: (a) expensed in full.** V-001 closed as AS. Reconfirm per company for any business near the net worth threshold, because the transition to Ind AS inflates EBITDA mechanically | 03, 05 |
| **D-027** | CSR, donations, directors' sitting fees: inside EBITDA or below? | (a) inside *(suggested)*; (b) below | | 03, 05 |

---

## SECTION D. Working capital ratios

| ID | Decision | Options | Why it matters | Blocks |
|---|---|---|---|---|
| **D-028** | DSO basis: period-end or average AR? Gross or net revenue? 365 or 360 days? | Three sub-choices. Suggested: period-end AR, net revenue, 365 days | The three combinations produce visibly different numbers, and the promoter has one in his head already. Match his. **P0-BLOCKING** | 05, 10 |
| **D-029** | Does AR include unbilled revenue and retention money? | (a) exclude both, disclose separately *(suggested)*; (b) include | Manufacturing with project or milestone billing. | 04, 05 |
| **D-030** | DPO computed on COGS, on purchases, or on total addressable spend? | (a) purchases *(suggested, it is the actual driver of AP)*; (b) COGS; (c) COGS plus opex | **P0-BLOCKING** | 05, 10 |
| **D-031** | DIO computed on COGS or on production cost? Which inventory buckets? | Suggested: COGS, with RM plus WIP plus FG for manufacturing and FG only for consumer | **P0-BLOCKING** | 05, 10 |
| **D-032** | Customer advances: netted against AR, or shown as a liability? | (a) liability *(suggested, and correct presentation)*; (b) netted | Manufacturing with advance-against-order terms. Netting flatters DSO. | 04, 05 |
| **D-033** | Marketplace settlement receivable: part of AR, or its own line? | (a) own line *(suggested)*; (b) part of AR | Consumer. Behaves nothing like trade AR, ages differently, and mixing them makes DSO meaningless. **P0-BLOCKING** | 04, 05 |

---

## SECTION E. Balance sheet, debt and cash

| ID | Decision | Options | Why it matters | Blocks |
|---|---|---|---|---|
| **D-034** | Does "cash" include fixed deposits, margin money and restricted balances? | (a) free cash only, restricted disclosed separately *(suggested)*; (b) all bank balances | Margin money against LCs and BGs is common in manufacturing and is not available cash. **P0-BLOCKING** | 04, 05 |
| **D-035** | What counts as debt? | Tick: term loans; cash credit / OD; current maturities; unsecured related-party loans; lease liabilities | Related-party loans are the contentious one. | 04, 05 |
| **D-036** | Bill discounting and channel financing: debt, or a reduction of AR? | (a) debt with AR retained *(suggested, and the honest view)*; (b) AR reduction | Very common in manufacturing. Option (b) makes DSO look excellent and hides leverage. Getting this wrong is the kind of thing that costs credibility with a CFO permanently. **P0-BLOCKING** | 04, 05 |
| **D-037** | Capex measured on a cash basis or as additions to gross block? | (a) additions to gross block *(suggested)*; (b) cash paid | Diverge when there are advances to vendors for capital goods. | 04, 05 |

---

## SECTION F. Calendar, periods and restatement

| ID | Decision | Options | Why it matters | Blocks |
|---|---|---|---|---|
| **D-038** | Fiscal year start month. | (a) April *(assumed)*; (b) other | Confirm per company rather than assuming. **P0-BLOCKING** | 04 |
| **D-039** | Who locks a period, and on what day of the following month? | Name the role and the day | Without a lock there is no restatement, only silent edits. **P0-BLOCKING** | 04, 09 |
| **D-040** | Restatement threshold: below what change do we accept a revised figure without flagging it? | Suggested: flag every change to a locked period regardless of size, but only notify above a value threshold | | 09 |

---

## SECTION G. Manufacturing operating layer

| ID | Decision | Options | Blocks |
|---|---|---|---|
| **D-041** | Unit of output: tonnes, pieces, litres, SKU units? Realisation is per what unit? | Company-specific. Must be a single declared unit per product family, otherwise volume and price decomposition is meaningless. **P0-BLOCKING** | 04, 05, 10 |
| **D-042** | Capacity basis: installed, rated, or practical/achievable? | Practical *(suggested)*. Installed capacity flatters utilisation. **P0-BLOCKING** | 04, 05 |
| **D-043** | Yield: measured by weight or by count? Where does rejection sit, at input or output? | Company-specific | 04, 05 |
| **D-044** | Is WIP valued and included in inventory metrics? | (a) yes *(suggested if the ERP tracks it)*; (b) no, FG and RM only | 04, 05 |
| **D-045** | Subcontracted / job work volume: counted in own output? | (a) yes, flagged separately *(suggested)*; (b) no | 04, 05 |

---

## SECTION H. Consumer and retail operating layer

| ID | Decision | Options | Blocks |
|---|---|---|---|
| **D-046** | Exact channel taxonomy. | Proposed: own website; marketplace (per marketplace); quick commerce (per platform); owned retail (per store); franchise retail; distributor/general trade; exports. Confirm and freeze. **P0-BLOCKING** | 04, 05, 06, 10 |
| **D-047** | Returns: netted at the original order line, or booked in the period the return occurs? | (a) period of return *(suggested, it is what the books do)*; (b) restated to the original line *(better analysis, needs bitemporal handling)* | 04, 05 |
| **D-048** | Contribution margin: after which costs exactly? | Suggested: net revenue less COGS, less channel-specific fees, less shipping, less returns cost, less performance marketing. Confirm each. **P0-BLOCKING** | 03, 05 |
| **D-049** | AOV: gross or net of returns? Per order or per customer? | Suggested: net, per order | 05, 10 |
| **D-050** | Franchise inventory: consignment (ours) or sold (theirs)? | Company-specific. Changes the balance sheet, not just the analysis. **P0-BLOCKING** | 04, 05 |

---

## SECTION I. Reconciliation tolerances and data gating

| ID | Decision | Suggested | Blocks |
|---|---|---|---|
| **D-051** | Trial balance tie tolerance | Zero. A trial balance that does not balance is a blocking error, not a tolerance | 09 |
| **D-052** | Books-to-bank residual tolerance, as a percent of period cash movement | To be set per company after two months of observation. Do not invent one now | 09 |
| **D-053** | Unmapped value threshold above which metrics are blocked entirely | Suggested: block above 2 percent of period value, badge between 0.5 and 2 percent, silent below 0.5 percent | 06, 09 |
| **D-054** | What happens when a period is unreconciled: block the pack, or ship it badged? | (a) block *(suggested for the monthly pack)*; (b) badge | 07, 09 |
| **D-065** | Mapping engine auto-accept rupee ceiling (corpus/06 section 4.2) | Resolved 2026-08-24: flat ₹1,00,000 per period. Not a percent of revenue -- revenue is a derived metric that requires a frozen mapping version to compile, which doesn't exist yet at auto-accept time; a revenue-relative ceiling would be circular | 06 |

---

## SECTION J. Reporting, security and data handling

| ID | Decision | Options | Blocks |
|---|---|---|---|
| **D-055** | Pack layout: Schedule III statutory presentation, or a management layout? | (a) management layout with a Schedule III reconciliation appendix *(suggested)*; (b) Schedule III throughout. Depends partly on **V-002** | 07 |
| **D-056** | Units and rounding in all outputs. | Suggested: rupees in lakhs for P&L detail, crores for headline metrics, one decimal, negatives in brackets. Confirm, because promoters have strong habits here | 07 |
| **D-057** | Which comparisons are mandatory on every statement? | Suggested for P0: prior month and prior year. Budget only if the client has one in a usable form, which most will not | 07 |
| **D-059** | Price, volume and mix decomposition convention. | Several standard allocations of the interaction term exist and they give different answers on the same data. Suggested: volume effect at prior-period price, price effect at current-period volume, mix as the residual, with the residual reported rather than absorbed. **P0-BLOCKING** for the variance_explain intent | 05, 07, 08, 10 |
| **D-058** | Pseudonymisation scope: which entities get tokenised before any model call? | Suggested: employee (always, full), customer (name and contact tokenised, group and segment retained), vendor (name tokenised, category retained). Tokens are per tenant, stable, and resolved back to real names only in the render layer. The model-reachable views contain tokens only, so masking is a property of the schema and not a step anyone can forget. **P0-BLOCKING** | 04, 07 |
| **D-066** | Ask admission control gate 6, cost cap (corpus/07 section 7) | Resolved 2026-08-24: ₹5 per query, estimated AI model spend (tokens x pricing) -- not a row count, which is gate 7's separate job. Query rejected outright, before reaching the database, if estimated spend exceeds this | 07 |
| **D-067** | Ask admission control gate 7, row cap (corpus/07 section 7) | Resolved 2026-08-24: confirmed at 10,000 rows, applied via `LIMIT` | 07 |
| **D-068** | Tenant data retention period after a pilot ends (corpus/12 sprint 7) | Resolved 2026-08-24: request-triggered deletion only (named requester, named reason). No background job purges anything based on elapsed time -- confirmed as the deliberate policy, matching `src/admin/tenant_lifecycle.delete_tenant()`'s existing behaviour | 12 |

---

## SECTION K. VERIFY register

These are not opinions. They are facts about the outside world that I could not confirm and must not guess.

| ID | Item | Why it is open | Owner | Blocks |
|---|---|---|---|---|
| ~~**V-001**~~ | **CLOSED 20 Aug 2026: AS, not Ind AS.** The unlisted trigger is net worth based, not revenue based, so a ₹100 Cr revenue company sits under AS with Schedule III Division I. Resolves D-026. Still worth a CA reconfirmation per company at onboarding. | Closed by founder | 03, 05, D-026 |
| **V-002** | Schedule III Division I versus Division II presentation requirements for the pack layout. | Follows from V-001 | CA | 07, D-055 |
| **V-003** | TallyPrime export formats, report names and actual column headers for: chart of accounts, trial balance, day book, ledger, sales register, purchase register, stock summary, outstanding receivables and payables. | I have general knowledge of Tally's XML-over-local-HTTP interface and ODBC availability. I do not have reliable knowledge of current tag names or export headers, and I will not invent them. | Bhavya, one day with any accountant running Tally | 01, 06 |
| **V-004** | Tally licence conditions on programmatic and ODBC access. | Commercial, not technical. Relevant before the on-prem agent is built | Bhavya | P1 scope |
| **V-005** | Zoho Books API: rate limits, org-scoped token behaviour, which reports are exposed. | Changes with releases | Co-founder | P1 scope |
| **V-006** | SAP Business One: whether Service Layer access is realistically available in partner-customised installations at this segment, or whether a read replica or scheduled extract is the practical route. | This is a political question as much as a technical one | Bhavya, on a real prospect | P1 scope |
| **V-007** | Actual corporate statement formats for the banks your pilots use. | Every bank differs and formats change | Bhavya, from the first real statement | 01 |
| **V-008** | Amazon Seller Central settlement report structure and typical settlement lag. | Consumer pilots. Drives the reconciliation gate | Co-founder | P1 scope |
| **V-009** | What data quick commerce platforms actually give a brand, in what format, at what lag. | I do not know this reliably and it varies per platform and per contract | Bhavya, from a consumer prospect | 01, P1 scope |
| **V-010** | GST Suvidha Provider commercial terms, pricing and what a client authorisation requires. | Contract as much as integration | Bhavya | P1 scope |
| **V-011** | DPDP Act 2023 obligations for this product, including the status of notified rules and what the data processing agreement must contain. | I can describe the general shape. I cannot give you your position | Lawyer, before the first paid pilot | Legal, not corpus |
| **V-012** | Model vendor zero-retention terms currently on offer, and whether an India-hosted inference option exists that your promoters would accept. | Vendor terms change | Co-founder | 07, security section |
| **V-013** | MSMED Act payment-period rules and the associated income tax disallowance, and whether they apply to your pilots' vendor base. | Manufacturers care about this a great deal and it affects AP ageing analysis and the vendor master. I know the framework exists; I do not know the current thresholds well enough to specify against | CA | 05, 10 |
| **V-014** | e-invoicing applicability at ₹100 Cr turnover, and therefore whether an IRP feed is available as a near-real-time revenue cross-check. | If it applies, this is a materially better revenue verification source than GSTR-1 and changes the P1 roadmap | CA | P1 scope |

---

## 4. What happens next

1. Resolve the 22 **P0-BLOCKING** decisions. Most are answerable by you in an hour; a handful need a CA.
2. Close **V-001** and **V-003** first. V-001 changes the ontology. V-003 unblocks the Tally tab of the data request pack and, later, the whole agent.
3. Everything else can move in parallel with the corpus being written.

Where a decision is still open when a downstream file needs it, that file carries the marker inline and uses the suggested option, flagged. Nothing is decided by omission.
