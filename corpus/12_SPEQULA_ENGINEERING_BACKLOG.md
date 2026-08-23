# SPEQULA ENGINEERING BACKLOG

**File 12 of 12. Status: draft 1.**
Implements: architecture document sections 31 (MVP architecture) and 36 (recommended stack), narrowed to P0.

Assumes two engineers: you plus the technical co-founder, with you also carrying the analyst role for pilot one. Sprints are two weeks. Fourteen weeks to a pilot producing a signed pack from the product rather than from Excel.

---

## 1. The stack, and why each piece

Boring on purpose. Every choice optimises for two engineers shipping correct financial output, not for architectural elegance. The interesting engineering in this company is the metric registry, the mapping loop and eventually the Tally agent. Everything else should be as ordinary as possible.

| Layer | Choice | Why for the MVP | Rejected | Replaceable later |
|---|---|---|---|---|
| App database | PostgreSQL | Transactions, JSON, row-level security, operational simplicity. One database to secure, back up and reason about | Nothing else is close at this size | No |
| Analytical store | Postgres, schema per tenant | Ten tenants do not need a warehouse. Schema per tenant is one afternoon and gives a hard isolation boundary | ClickHouse, BigQuery, Snowflake: all cost and ops for zero benefit at three customers | Yes, when a standard monthly pack query exceeds a few seconds |
| Raw storage | Object storage, immutable | Full replay forever, for slightly more code now | Storing raw in Postgres | No |
| Transforms | dbt-core on Postgres | Tests, docs and lineage come free | Hand-written SQL scripts | Yes |
| Backend | Python, FastAPI | Same language as the data work. Fast, typed, boring | Node, Go: would split the language surface for no gain | No |
| Frontend | Next.js with a component library | Do not build a design system during a pilot | A bespoke design system | No |
| Orchestration | Cron plus a Postgres job table | Genuinely enough for ten tenants. Cheap to replace | Airflow, Dagster, Temporal: operational weight with no payoff yet | Yes, Dagster past roughly twenty pipeline assets |
| Models | Hosted API, two tiers | Zero ops burden. Zero-retention terms, per VERIFY[V-012] | Self-hosting: a distraction at this stage | Yes |
| Charts | Vega-Lite specs plus a component library for fixed tiles | Store the spec, not the picture, so the same answer renders in app, PDF and email | Plotly, D3 | No |
| Auth | Bought, Clerk or WorkOS | **Never build auth** | Building it | No |
| Vectors | None in P0 | No document layer. This removes a whole subsystem | pgvector, dedicated vector stores | Added in P1 |
| Monitoring | Error tracking plus an LLM trace tool | Cheap, immediate | A full observability stack | Yes |
| Deployment | Containers on a managed platform, one India region | Data residency, minimal ops | Kubernetes | Yes, if the team ever justifies it |

---

## 2. Sprint 0: before any application code

Two to three days. Skipping this is how a corpus becomes shelfware.

- Repository created, with the corpus committed into `/corpus` so the specification versions alongside the code.
- CI running, empty test suite, deploy pipeline to a staging environment.
- Auth provider integrated, three roles stubbed.
- Postgres provisioned with the schema-per-tenant pattern and one test tenant.
- Object storage bucket with tenant-prefixed paths.
- Synthetic reference dataset generated, per file 11 section 2. **This is the first real work item** and everything downstream tests against it.

**Exit criterion:** a developer can clone, run one command, and have a working environment with the synthetic company loaded.

---

## 3. Sprints

### Sprint 1: ingestion and the canonical spine
*Weeks 1 to 2*

> **Story.** As the SPEQULA analyst, I can upload a company's trial balance, chart of accounts and general ledger, and see canonical GL facts in the system with full lineage back to the file.

| Area | Work |
|---|---|
| Database | `dim_date` with the Indian fiscal calendar, `dim_entity`, `dim_account`, `fact_gl_entry` with bitemporal columns, `load_run`, `source_file`, `audit_log`. Schema-per-tenant migration loop |
| Backend | File upload, content hashing, immutable landing, staging transforms, typed parsing, currency handling, deduplication on `row_hash`, canonical write with `valid_from` and `valid_to` |
| Frontend | Upload screen, load run status, basic file list |
| AI | None |
| Tests | Idempotency: same file twice, no duplicate facts. Replay: full re-run produces identical output. Bitemporal: a backdated entry closes the prior row rather than updating it |

**Acceptance:** a trial balance generated from `fact_gl_entry` matches the source trial balance exactly, to the rupee, for all 36 months of the synthetic company.

---

### Sprint 2: mapping and statements
*Weeks 3 to 5*

> **Story.** As the analyst, I can review and approve account mappings sorted by rupee value, freeze them as version 1, and generate a P&L and balance sheet that tie to the client's own trial balance.

| Area | Work |
|---|---|
| Database | `map_account`, `mapping_version`, `map_item`, `map_channel`. Canonical class taxonomy seeded from file 06 |
| Backend | Chart of accounts extraction, exact-rule matcher, rule library, auto-accept gate with the six judgement-class exclusions, mapping freeze and versioning, statement assembly by `statement_line` |
| Frontend | Mapping review queue sorted by `period_value_inr` descending, with running coverage and unmapped rupee value always on screen. P&L and balance sheet screens with three-level drilldown |
| AI | Mapping proposal, strict JSON schema, confidence and stated reason, invalid response retried once then queued unproposed |
| Tests | Auto-accept never fires on a judgement class. Coverage gate blocks statements below threshold. A prior signed statement re-renders identically after a version change |

**Acceptance:** P&L and balance sheet generate from mappings, the balance sheet balances, and both tie exactly to the synthetic reference set. The freeze gate reads PASS only when all three conditions in the mapping workbook hold.

---

### Sprint 3: metrics and reconciliation
*Weeks 5 to 7*

> **Story.** As the analyst, I can see the headline metrics for a period, know whether that period is reconciled, and work an exception queue sorted by rupee exposure.

| Area | Work |
|---|---|
| Database | `metric_definition` with versions and overrides, `reconciliation_run`, `period_lock`, `exception`, `token_map` |
| Backend | Metric contract loader, deterministic compiler from contract to SQL, override resolution chain, trial balance tie, books-to-bank reconciliation with modelled differences itemised, the full check catalogue from file 09, period state machine, tokenisation at ingestion |
| Frontend | Financial overview with the nine metric tiles, data health screen with four panels, exception queue |
| AI | None |
| Tests | `ratio_of_sums` versus average-of-ratios on uneven monthly revenue. All eleven seeded defects detected at the correct severity. Cash flow closing cash equals balance sheet cash or neither displays. Compilation gate: a metric with an unresolved decision does not serve a default |

**Acceptance:** a period is marked reconciled with a visible residual, and every metric on the overview screen carries a citation that resolves to source rows.

---

### Sprint 4: Ask
*Weeks 7 to 9*

> **Story.** As the client finance lead, I can ask a question in natural language, get a correct number with a citation I can click through to the underlying rows, and get a clear refusal when the question is out of scope.

| Area | Work |
|---|---|
| Database | `query_log`, model-reachable read-only role with grants on canonical schemas only |
| Backend | Semantic IR schema and validator, SQL compiler from IR plus metric contract, the seven admission-control gates, result sanity checks, deterministic price-volume-mix and margin bridges, citation object assembly |
| Frontend | Ask screen: question, answer, chart, citation chip, view SQL, drill to rows |
| AI | Intent classification with the closed twelve-intent list, semantic IR generation via constrained decoding, narration receiving computed numbers as data only |
| Tests | The full file 10 suite. IR parsing at 100 percent on metric and period fields. **Refusal at 100 percent.** No SQL string ever produced by a model. A query without a tenant predicate cannot execute |

**Acceptance:** 37 of 37 runnable gating golden questions pass, and 14 of 14 refusals refuse correctly. Five of the 42 gating questions are manufacturing per-unit questions blocked on D-041 and are excluded until the unit of measure is declared for that company. Below either, Ask does not go live for a client.

---

### Sprint 5: the monthly pack
*Weeks 9 to 11*

> **Story.** As the analyst, I can generate a monthly management pack from the product, review and sign it, and re-render it identically six months later.

| Area | Work |
|---|---|
| Database | Report artefact store recording snapshot id, metric versions, mapping version, freshness, reconciliation status, reviewer |
| Backend | Statement assembly into the eight pack sections from file 08, cash flow indirect method, chart spec generation, export renderer, sign-off workflow with the blocking-exception gate and logged override |
| Frontend | Reports screen: generate, review, edit commentary, sign, export |
| AI | None. Commentary is human-written in pilot one |
| Tests | Re-render reproducibility byte-identical. Pack cannot generate with an open blocking exception unless overridden with a logged reason. Data quality appendix present in every pack |

**Acceptance:** the pack is delivered from the product rather than from Excel, and section 1 correctly states the pack's own reconciliation status and data freshness.

---

### Sprint 6: hardening and the second pilot
*Weeks 11 to 13*

> **Story.** As the analyst, I can onboard a second company in materially fewer hours than the first.

| Area | Work |
|---|---|
| Database | Consumer: `fact_channel_order_line` with `revenue_model` and `order_type`, `dim_channel`, `dim_business_unit`. Manufacturing: `fact_production_output` |
| Backend | The consumer CM ladder end to end: GMV, GST, discount, COGS, operating cost, CM1, marketing, CM2, unallocated corporate overhead, EBITDA. Both revenue models. Manufacturing operating metrics. Order-file-to-books residual reported, never resolved. Rule library growth from pilot one |
| Frontend | Profile-specific layouts: the CM ladder for consumer, the cost-structure P&L for manufacturing. Channel, product and business unit breakdowns |
| AI | Mapping proposal now retrieves from approved mappings across companies |
| Tests | Marketplace GMV is never summed into revenue. A 100 percent gross margin line does not raise an anomaly. Corporate overhead is never allocated. Per-tenant golden sets run in isolation. Cross-tenant queries fail at the role level |

**Acceptance:** **the ratio.** Pilot two costs half the analyst hours of pilot one, measured, not estimated. This is the only acceptance criterion in this sprint that matters.

---

### Sprint 7: pilot operations
*Weeks 13 to 14*

> **Story.** As the founder, I can run three pilots concurrently without any client-specific code.

| Area | Work |
|---|---|
| Database | Retention and deletion paths, backup and restore tested |
| Backend | Per-tenant configuration entirely in data, not code. Named, time-bound, logged employee access to client data |
| Frontend | Settings, permissions, audit log viewer |
| AI | Model cost tracking per tenant |
| Tests | Point-in-time restore rehearsal. Employee access logging. Full regression across all tenants |

**Acceptance:** no client-specific code exists anywhere in the repository. Every difference between companies is a row in a configuration table.

---

## 4. What is not in any sprint

Stated explicitly so it does not arrive by accident: the Tally on-prem agent, bank and GST connectors, forecasting, scenarios, LLM commentary, insight detection, alerts, the document and vector layer, industry packs, AI chart selection, multi-entity consolidation, marketplace settlement reconciliation, budget versus actual, and self-serve onboarding.

Each has a defined trigger in file 02 section 5. None of them starts because it would be interesting.

---

## 5. Ordering rules

1. **Nothing is built before the corpus item it implements is resolved.** A metric whose governing decision is open does not get a default; it does not compile. That is the gate, and it is the point.
2. **Bitemporality, schema-per-tenant and the metric registry ship in sprints 1 to 3.** They look like scale features and they are not deferrable. Retrofitting any of the three costs more than building all three now.
3. **Correctness before capability.** Sprint 4 does not start until statements tie exactly in sprint 2 and 3. An Ask surface over numbers that do not tie is worse than no Ask surface.
4. **The eval harness grows with each sprint**, not after sprint 7.
5. **Every sprint ends with a demo against the synthetic dataset,** and from sprint 3 onward, against real pilot data.

---

## 6. Risk register for the build

| Risk | Impact | Mitigation |
|---|---|---|
| Mapping takes far longer than estimated on a real chart of accounts | Onboarding never leverages, and the whole model fails | Value-sorted queue, rule library from day one, and you do the first mapping by hand so the estimate is real |
| The taxonomy in file 06 is materially wrong | Sprint 2 rework | It is labelled version 0 and provisional. Revise against the first real COA before company two |
| Decisions in file 00 stay unresolved | 8 of 61 metrics cannot compile, down from 30 of 51 at first draft | The compilation gate makes the cost visible. All 8 are blocked by per-company items resolved in the accounting policy conversation at onboarding |
| Pilot data arrives later than the build needs it | Untested code | The synthetic dataset removes this dependency for development, though not for validation |
| Scope creep from a pilot customer request | Sprints slip | Section 4 above, plus file 02 section 5's anti-scope list |
| A pilot company turns out to report under Ind AS | Lease treatment and provisioning defaults change | V-001 closed as AS globally. Reconfirm per company at onboarding, particularly for any company near the net worth threshold |
| One engineer becomes the only person who understands the compiler | Bus factor of one on the most important component | Both engineers pair on the compiler in sprint 3 and 4 |

---

## 7. The honest summary

Pilot one is delivered mostly by hand, with the product used as the workbench. The engineering goal is not to automate pilot one. It is to make pilot two cost half the hours of pilot one, and pilot five a quarter.

Every P0 item in this backlog is chosen because it moves that ratio. Anything that does not move that ratio can wait, and most of it should.
