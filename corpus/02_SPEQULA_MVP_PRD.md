# SPEQULA MVP PRODUCT REQUIREMENTS

**File 02 of 12. Status: draft 1.**
Implements: architecture document sections 30 to 37 (ranked risks, MVP, first connectors, screens, build order), narrowed for pilot one.
Defers: architecture sections 15 to 19 (forecasting, scenarios, visualization, insight engine, industry packs) and section 11 (document retrieval) in full.

Where this file and the architecture document disagree, **this file wins for the MVP** and the disagreement is logged in section 9.

---

## 1. What we are building, stated precisely

A system that takes a real Indian mid-market company's accounting and operating data, converts it into one canonical financial model, produces statements and metrics that tie to the books, answers a bounded set of financial questions with every number traceable to source rows, and generates a monthly management pack.

It does not forecast. It does not run scenarios. It does not write commentary. It does not read documents. Those come after pilot one.

### The honest framing

Pilot one is delivered mostly by hand, with the product as the workbench. This is not a compromise, it is the correct sequence, and the architecture document says so directly. The engineering goal for the MVP is not to automate pilot one. It is to make pilot two cost half the hours of pilot one.

Every P0 item below earns its place by moving that ratio. Anything that does not move it is P1 or later.

### The one sentence a customer hears

Send us your books and your operating data. Within three weeks you get a monthly pack that ties to your own trial balance, and a way to ask questions of your own numbers where every answer shows its working.

---

## 2. Users and roles

Four roles. No more in the MVP.

| Role | Who | What they do | What they see |
|---|---|---|---|
| **Promoter** | Owner, MD, CEO | Reads the pack. Asks questions. Rarely logs in more than weekly | Financial overview, Ask, Reports. No mapping screens, no exception queue |
| **Client finance lead** | CFO, finance controller, or the CA | Answers the accounting policy questions. Reviews mappings. Signs off that statements tie | Everything except SPEQULA internal admin |
| **SPEQULA analyst** | You, for pilot one | Runs onboarding, proposes and approves mappings, reconciles, assembles and reviews the pack | Everything, plus the exception queue and the audit log |
| **Admin** | Engineering | Tenancy, connectors, deploys | System configuration, no default access to client data |

**Two notes on this.**

Employee-level access to client data is time-bound, named and logged. Your architecture document is right that this is the control clients actually ask about, and it costs almost nothing to build correctly at the start.

You are the SPEQULA analyst for pilot one, which means you are both the person selling the pilot and the person signing off the numbers in it. That is workable at this stage but the audit trail must record it accurately. Do not label it as independent finance review, because it is not.

---

## 3. The two customer profiles

Both are in scope. The shared core is the same; the operating layer differs.

| | **Manufacturing** | **Consumer brand** |
|---|---|---|
| Revenue scale | Around ₹100 Cr | Around ₹100 Cr |
| Legal structure | Single entity assumed. Multi-entity is out of P0 | Single entity assumed |
| Accounting system | Tally, SAP Business One, or Zoho | Tally or Zoho |
| Revenue channels | Direct customers, distributors, exports | Own site, marketplaces, quick commerce, owned retail, franchise retail |
| Operating source | Production MIS or ERP, often partly in Excel | Order management system, marketplace reports, often partly in Excel |
| Extra canonical facts | `fact_production_output`, `fact_inventory_position` | `fact_channel_order_line` with `revenue_model` and `order_type`, `dim_business_unit` |
| The question that sells it | Where did margin go, and how much cash is stuck in stock | Which channel makes money after everything, and do the unit economics work before marketing |
| Hardest reconciliation | Absorption variance and inventory valuation | Marketplace settlement, which is **deferred to P1** |

**Marketplace settlement reconciliation is out of P0.** It is the hardest tie-out in the book, it depends on report formats we have not seen (VERIFY[V-008], VERIFY[V-009]), and learning it in week five of a pilot is how a wrong revenue number reaches a promoter. For pilot one, consumer revenue is taken from the books and from the order file, the gap between them is reported as a residual, and no attempt is made to explain it automatically.

---

## 4. Scope: P0

Required before pilot one produces anything. Thirteen items.

| # | Capability | Definition of done |
|---|---|---|
| **1** | Fixed-schema file ingestion | Excel and CSV against the templates in file 01. Files land immutably with a load run id and a content hash. No parsing intelligence, no format guessing. The analyst normalises anything that does not match. |
| **2** | Raw landing and replay | Every file retained byte-for-byte. The full pipeline can be re-run from raw at any time and produce identical output for the same mapping version. |
| **3** | Canonical model, bitemporal | Tables per file 04. Every fact carries an event date and a load run. Both "as reported" and "as it stands now" are queryable. Not deferrable. |
| **4** | Mapping engine and review UI | Every source account and item mapped to a canonical class. Queue sorted by rupee value, not by count. Every mapping versioned, effective-dated, human-approved, reversible. |
| **5** | Metric registry and compiler | 61 metric contracts, of which 53 compile and 8 are blocked on per-company decisions. A manufacturer sees 32 Ask-exposed metrics, a consumer brand 40. Deterministic SQL generated from the contract. No metric formula anywhere in application code. |
| **6** | Statement assembly | P&L, balance sheet, and indirect cash flow, generated from mappings and the registry. |
| **7** | Reconciliation, two checks only | Trial balance ties exactly. Books-to-bank cash movement ties within a per-company tolerance. Nothing else in P0. |
| **8** | Data health and exception queue | Freshness, completeness, unmapped value in rupees, open exceptions. A first-class screen, not a log file. |
| **9** | Ask | Fixed intent set over registry metrics. Natural language to semantic IR to compiled SQL. Every number cited and clickable through to rows. Unsupported questions are refused with a readable reason, never guessed. |
| **10** | Monthly pack generation | Statements, variance table, and bridges, exported as a document. Commentary is written by a human in pilot one. |
| **11** | Audit and lineage store | Every displayed number traces to metric version, query, snapshot, source rows and source file. |
| **12** | Auth, RBAC, tenant isolation | Bought auth. Schema per tenant for analytical data, row-level security on app data. Tokenisation of person and party names at the schema boundary. |
| **13** | Eval harness and 42 gating golden questions | Runs on every change. A regression is a build break. |

### The three that look like scale features and are not deferrable

Stated again because they will be the first things an engineer under time pressure proposes cutting.

1. **Bitemporal facts.** Two columns and a snapshot table now. A rewrite of every query, cached aggregate and saved report later.
2. **Schema per tenant.** One afternoon now. A company-ending incident later.
3. **Metric registry from day one.** Skip it and the second customer costs as much as the first, which invalidates the entire business model.

---

## 5. Scope: P1 and P2

### P1, after pilot one is live and producing packs

| Capability | Trigger to start |
|---|---|
| Tally on-prem agent | VERIFY[V-003] closed, and manual exports have become the bottleneck |
| Driver forecast engine, then scenario DAG | Statements tie for three consecutive months. **Driver forecast engine started 2026-08-24 ahead of this trigger** (D-069, `corpus/00`) -- against a synthetic apparel/retail dataset, not a live pilot's tied statements. See `corpus/13`. The scenario DAG half of this row is not built. |
| LLM commentary drafting | You have hand-written at least three packs to establish the target voice |
| Insight detection rules | Two months of history in the system to detect against |
| Marketplace settlement reconciliation | A real settlement report in hand |
| GST reconciliation via a GSP | VERIFY[V-010] closed |
| Document store, OCR and retrieval | A pilot asks a question that requires a contract or policy note |
| Industry pack file format, plus the first two packs | Pilot three, when hand-configuration stops being cheaper |
| Additional connectors: Zoho Books, Shopify, Razorpay | Pilot demand, not roadmap |
| Budget versus actual | A pilot has a budget in usable form. Most will not |

### P2 and later

Proactive alerts. Multi-entity consolidation and elimination. AI chart selection. Investigation agent. Data request agent. Research agent. Self-serve onboarding. Warehouse migration. Fine-tuned mapping model. SSO and SCIM. Multi-region.

### Anti-scope

The following will be proposed during the build and must be refused unless a pilot customer is blocked without it: real-time sync, a chat-first interface, a mobile app, custom dashboard builders, Slack or WhatsApp delivery, a public API, white labelling, and any feature justified by "an enterprise buyer will eventually want it."

---

## 6. The pilot workflow

Fourteen steps. The column that matters is who does it, because it is the honest cost model.

| # | Step | Automated | AI-assisted | Human approves | Fully manual in MVP |
|---|---|---|---|---|---|
| 1 | Company profile: entity, FY, industry, users | | | | Yes |
| 2 | Accounting policy conversation, file 00 sections A to J | | | | Yes |
| 3 | Data request issued, file 01 | | | | Yes |
| 4 | Files received and normalised to templates | | | | Yes |
| 5 | Upload and raw landing | Yes | | | |
| 6 | Structural validation and completeness checks | Yes | | | |
| 7 | Chart of accounts extraction | Yes | | | |
| 8 | Mapping proposal | | Yes | | |
| 9 | Mapping review and approval | | | Yes | |
| 10 | Statement generation | Yes | | | |
| 11 | Tie-out against the client's own trial balance and audited accounts | | | Yes | |
| 12 | Reconciliation, books to bank | Yes | | Yes, on residual | |
| 13 | Ask goes live for the client | Yes | | | |
| 14 | Monthly pack assembled, commentary written, signed | Yes for numbers | | Yes | Yes for commentary |

Steps 1 to 4 are pure founder work and they are where the pilot is won or lost. No engineering removes them in pilot one.

---

## 7. Non-functional requirements

| Area | Requirement | Why this level |
|---|---|---|
| Correctness | A generated trial balance matches the client's own, exactly, to the rupee | Any tolerance here is a bug in disguise |
| Traceability | Every displayed number resolves to metric version, query hash, row count, snapshot id and source file. A number that cannot be traced is not displayed | This is the trust mechanism and the product differentiator |
| Reproducibility | Re-rendering a signed pack six months later reproduces it exactly, including figures since restated | Without this there is no audit conversation |
| Interactive latency | An Ask answer inside a few seconds for a standard metric query. A slow correct answer beats a fast wrong one, but a slow answer is still a problem | Baseline in pilot one, do not set a target now |
| Batch | A full re-run from raw for one company completes overnight | Ten tenants, one Postgres |
| Availability | Business hours IST, with a documented recovery path. No high-availability engineering | Three customers |
| Data residency | One region in India for storage. Model inference may go to a US-hosted API under zero-retention terms, carrying tokens only | Your answer, plus VERIFY[V-012] |
| Personal data | Employee, customer and vendor names replaced with per-tenant stable tokens at the schema boundary. Model-reachable views contain tokens only. Real names resolved in the render layer for the human user | See section 8 |
| Backups | Point-in-time recovery, restore tested before the first paid pilot | Cheap, and clients ask |

---

## 8. Tokenisation: an architectural decision, not a process

Masking before an API call fails the first time someone forgets. The correct shape:

1. On ingestion, every person and party name is written to `token_map` and replaced in the canonical fact tables with a stable per-tenant token (`VENDOR_0417`, `CUST_0912`, `EMP_0033`).
2. The model-reachable database role can read the fact and dimension tables. It has no grant on `token_map`.
3. The render layer, which is deterministic application code and not a model, resolves tokens to real names for the human user.
4. Employee data is excluded from model-reachable views entirely, not just tokenised.

The model cannot leak what it never received, supplier concentration and customer Pareto analysis continue to work on tokens, and there is no step in the pipeline that a person can forget to run. See DECISION-REQUIRED[D-058] for the exact field scope.

---

## 9. Where this file overrides the architecture document

| Architecture doc says | MVP says | Reason |
|---|---|---|
| Tally agent is connector number two | No agent in P0. Manual Tally exports only | VERIFY[V-003] is open. Building an agent against guessed field names is the largest avoidable risk in the plan |
| Eight reconciliation classes | Two: trial balance, books to bank | GST is out of P0 and marketplace settlement is deferred. Two checks that always run beat eight that half work |
| pgvector for documents from day one | No vector store, no document layer at all | No documents in pilot one. This removes an entire subsystem |
| Insight engine detects deterministically and narrates with AI | Detection is P1. Narration is P1. Human writes commentary in pilot one | You need a target voice before a model can imitate one, and edits per pack needs a hand-written baseline |
| Forecast and scenario engines in the 10 to 14 week build | Both P1 | Nothing to forecast until statements tie |

The user interface follows the architecture document, not the chat-first layout in the original brief: the default surface is the numbers, and Ask is a tool inside that surface. This was your call in the last exchange and it is recorded here as settled.

---

## 10. Pilot success criteria

Targets are only given where a target can be derived from first principles. Anything that depends on data we do not have is marked **baseline**, meaning: measure it in pilot one and set the target for pilot two from what you observe. Inventing a number here would be worse than leaving it open.

### Correctness, hard gates

| Measure | Target |
|---|---|
| Generated trial balance versus the client's | Exact match, to the rupee |
| Generated P&L and balance sheet versus last audited accounts, for the audited year | Exact match at every statement line, or every difference individually explained and logged |
| Balance sheet balances | Always. A non-balancing balance sheet is not displayed |
| Golden question set, numeric answers | 42 of 42 pass. Below 42, Ask does not go live for the client |
| Hallucination set: questions with no answer in the data | 100 percent refused. A single fabricated answer blocks release |
| Citation resolves to real source rows | 100 percent. A number without a resolving citation is not displayed |

### Onboarding, the ratio that matters

| Measure | Target |
|---|---|
| Analyst hours, pilot one, data received to first signed pack | Baseline |
| Analyst hours, pilot two | Half of pilot one |
| Analyst hours, pilot three | A quarter of pilot one |
| Elapsed days, data received to first signed pack | Under 21 days for pilot one |
| Percent of period value mapped before statements unlock | 98 percent, with the unmapped remainder quantified in rupees and visible |

### Product

| Measure | Target |
|---|---|
| Edits per pack, count of commentary and number corrections made by the analyst before signing | Baseline in month one, falling month on month. This is the primary commercial metric |
| Percent of client questions answerable in Ask without analyst intervention | Baseline |
| Questions asked per client per month | Baseline. This is the real read on whether decision latency actually fell |
| Repeat questions, same question asked in a later month | Baseline. A high number means the pack is not answering it |

### Commercial

| Measure | Target |
|---|---|
| Finance hours saved at the client, self-reported | Baseline |
| Pilot converts to a paid engagement | 2 of 3 |
| Client is willing to be a named reference | 1 of 3 |

---

## 11. Assumptions and dependencies

**Assumptions this document rests on.** Each is a risk if wrong.

1. Pilot companies are single legal entities. Multi-entity is out of P0 and its arrival requires an entity dimension and elimination rules that are designed for but not built.
2. Pilots will supply 24 months of history minimum. Below that, seasonality cannot be separated from trend and the product should say so rather than imply otherwise.
3. Pilots can produce a general ledger export. If a company genuinely cannot, it is not a pilot candidate for the MVP.
4. ~~Assumption.~~ **Confirmed 20 August 2026: AS, not Ind AS.** VERIFY[V-001] closed. Reconfirm per company at onboarding, because a company approaching the net worth threshold will transition and the transition changes EBITDA mechanically.
5. Manual file exchange is acceptable to pilot customers for the first three months.

**Hard dependencies before the build starts.**

- ~~29 P0-BLOCKING decisions resolved.~~ **18 resolved on 20 August 2026.** The remaining 11 are per-company and are answered at onboarding, not before the build.
- ~~VERIFY[V-001].~~ **Closed: AS.**
- VERIFY[V-003]. **No longer blocking.** The Tally agent is P1; pilot one uses manual exports. Still needed before the agent is built.
- One real chart of accounts in hand, so the taxonomy in file 06 is built against something real.
- ~~VERIFY[V-012].~~ **Closed: zero-retention terms and US-hosted inference acceptable.**
- Legal review of the DPDP position before the first paid pilot, VERIFY[V-011].
