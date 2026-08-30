# CLAUDE.md

Project instructions for SPEQULA. Read this before every task. It overrides your defaults.

---

## 1. What this is

SPEQULA is an always-on FP&A system for Indian mid-market companies. It ingests a company's accounting and operating data, converts it into one canonical financial model, produces statements and metrics that tie exactly to the client's own books, answers a bounded set of financial questions with every number traceable to source rows, and generates a monthly management pack.

**The failure mode this system exists to prevent is a plausible wrong number.** Not a crash, not a slow query, not an ugly screen. A number that looks right, reaches a board pack, and is wrong. Everything below follows from that.

---

## 2. The corpus is the only source of finance truth

`/corpus` contains thirteen specification files. They are the authority on every financial definition, threshold, field name and business rule in this system.

| File | Authority over |
|---|---|
| `00_SPEQULA_OPEN_DECISIONS.md` | Every finance judgement call and its resolution |
| `01_SPEQULA_DATA_REQUEST_PACK.xlsx` | What a customer is asked to supply, and in what shape |
| `02_SPEQULA_MVP_PRD.md` | Scope. P0 versus P1 versus P2. Success criteria |
| `03_SPEQULA_FINANCE_ONTOLOGY.md` | What every financial concept means |
| `04_SPEQULA_CANONICAL_DATA_MODEL.md` | Tables, columns, keys, grains, lineage |
| `05_SPEQULA_METRIC_REGISTRY.csv` | The metric inventory |
| `05a_SPEQULA_METRIC_CONTRACTS.yml` | The executable metric contracts |
| `06_SPEQULA_MAPPING_SPEC.md` | Canonical class taxonomy and the mapping loop |
| `07_SPEQULA_QUERY_ARCHITECTURE.md` | Semantic IR, intents, safety gates, refusal |
| `08_SPEQULA_REPORT_SPEC.md` | Statement layouts and the monthly pack |
| `09_SPEQULA_DATA_QUALITY_AND_RECONCILIATION.md` | Checks, severities, reconciliation, period gating |
| `10_SPEQULA_GOLDEN_QUESTIONS.csv` | The evaluation set |
| `11_SPEQULA_EVALUATION_FRAMEWORK.md` | Test suites, tolerances, gates |
| `12_SPEQULA_ENGINEERING_BACKLOG.md` | Sprint scope and acceptance criteria |

If the corpus and your training data disagree, **the corpus wins.** If two corpus files disagree, stop and ask. Do not reconcile them yourself.

---

## 3. The four prohibitions

These are absolute. Violating any of them is worse than not completing the task.

### 3.1 Never invent a financial definition

If a metric formula, an accounting treatment, or a statement classification is not in the corpus, you do not know it. Do not supply a textbook definition. Do not infer one from a similar metric. Stop and ask.

### 3.2 Never invent a threshold, tolerance or limit

No default row caps, timeout values, materiality thresholds, confidence cut-offs or reconciliation tolerances beyond what the corpus states. Where the corpus deliberately leaves one blank, such as D-052, that blank is a decision. Leave it blank and make the code fail loudly rather than proceed.

### 3.3 Never invent a source system field name

You do not know Tally's XML tags, TallyPrime export headers, Indian bank statement column names, GST return schemas, or marketplace settlement report structures. VERIFY[V-003] and VERIFY[V-007] are open for exactly this reason. If a task requires one of these, stop. Do not produce a plausible-looking field name.

### 3.4 Never fabricate a number

No example figures presented as real, no placeholder metrics, no invented benchmarks, no made-up accuracy targets. Synthetic test data is permitted and required, and every row of it is labelled synthetic in the data itself.

### 3.5 Never read or output a secret

`.env`, `.env.*`, and any file containing credentials are never read, printed,
`cat`-ed, echoed, grepped, tailed, copied, piped, committed or logged — not
partially, not masked, not truncated. The same applies to `printenv`, `env`,
`set`, and anything that dumps process environment.

If a task needs a variable's *name*, refer to `.env.example`. To check
configuration, test for existence (`[ -n "$VAR" ] && echo set`), never value.
If a task appears to require a secret's value, that is an escalation per
section 4, not a judgement call.


---

## 4. When you must stop

Stop, do not guess, and escalate when:

- A required definition, threshold or field name is absent from the corpus.
- A task depends on one of the 12 open decisions in `00`, section "Still open".
- Two corpus files conflict.
- Implementing something as specified would violate an invariant in section 5.
- A task requires touching real client data.

**Escalation format.** Append to `/OPEN_QUESTIONS.md` and stop that task, continuing with unblocked work:

```markdown
## OQ-nnn  <short title>
Raised: <date>   Task: <what you were doing>
Blocked by: DECISION-REQUIRED[D-0nn] | VERIFY[V-0nn] | corpus gap | conflict
What I need: <the specific question, answerable in one sentence>
Options I can see: <a> ... <b> ...
What I will NOT do: pick one and proceed.
Downstream blocked: <files, tests, features>
```

A commit that silently resolves an open decision is a defect, even if the code works.

---

## 5. Architectural invariants

Never violated. If a task appears to require violating one, that is an escalation, not a judgement call.

1. **No model ever writes SQL.** Models emit semantic IR validated against a JSON schema. A deterministic compiler emits SQL. There is no code path, flag, debug mode or internal tool that lets a model produce SQL.
2. **No metric formula exists outside the registry.** No arithmetic on canonical columns in a service, a component, a prompt or a notebook. If you need a number, resolve a metric contract and compile it.
3. **Every fact table is bitemporal.** `event_date`, `entry_date`, `valid_from`, `valid_to`, `is_current`, `load_run_id`. No exceptions, including for tables that "will not need history".
4. **Nothing is ever overwritten or deleted.** A changed fact closes the prior row and inserts a new one. Mappings, metric definitions and forecasts version forward. There are no destructive updates in this system.
5. **Analytical data is schema-per-tenant.** App data is shared tables with row-level security forced at the connection role, never in query text.
6. **The model-reachable database role has no grant on `token_map`, `audit_log`, or any app table.** Tokenisation is a schema property, not a pipeline step someone can forget.
7. **Every displayed number carries a citation that resolves to source rows.** A number without one is not displayed. Not badged, not greyed out. Not displayed.
8. **Trial balance tolerance is zero.** A period that does not balance does not produce a statement.
9. **A balance sheet that does not balance is not displayed.** Cash flow closing cash must equal balance sheet cash exactly, or neither displays.
10. **A blocking exception blocks output.** No silent continuation past unreliable data, ever.
11. **Every ratio uses `ratio_of_sums`.** Never the average of period ratios. Quarterly gross margin is quarterly gross profit over quarterly net revenue.
12. **Auto-accept never fires on a judgement class**: `exceptional.one_off`, `opex.owner_remuneration`, `opex.related_party_charges`, `cogs.absorption_variance`, `liability.bill_discounting`, `liability.debt_related_party`.
13. **Marketplace GMV is never summed into revenue.** Under the marketplace model, revenue is commission plus advertising earnings plus platform fee. See D-061.
14. **Marketing never enters CM1.** It is the CM1 to CM2 step. Fulfilment sits above CM1 for consumer and in COGS for manufacturing. See D-060 and D-020.
15. **A decomposition whose components do not sum to the total reports the gap.** It never presents a partial decomposition as complete and never sweeps a residual into "other".

---

## 6. Stack

Boring on purpose. The interesting engineering is the metric registry, the mapping loop and the compiler. Everything else is as ordinary as possible.

- Python 3.12, FastAPI, SQLAlchemy Core (not the ORM for analytical paths), Pydantic v2
- PostgreSQL 16. Schema per tenant for analytical data
- dbt-core for transforms
- Object storage for immutable raw landing
- Next.js with TypeScript and a component library. Do not build a design system
- Cron plus a Postgres job table for orchestration. No workflow engine
- pytest. Hosted model API, no self-hosting
- Bought auth (Clerk or WorkOS). **Never build auth**

Not in this project: vector stores, warehouses, Kafka, Airflow, Temporal, LangChain, agent frameworks, ORMs for analytical queries, GraphQL, microservices.

---

## 7. Repo layout

```
/corpus              specification, read-only, never edited by you
/config
  decisions.yml      resolved decisions as machine-readable config
  metrics/           metric contracts, generated from corpus 05 and 05a
  taxonomy.yml       canonical classes from corpus 06
/db/migrations       forward-only, one schema-per-tenant loop
/dbt                 transforms
/src/ingest          connectors, staging, canonical loaders
/src/mapping         proposer, rule library, review API
/src/semantic        registry loader, IR schema, validator, SQL compiler
/src/quality         check catalogue, reconciliation, exception queue
/src/reports         statement assembly, pack generation
/src/forecasting     driver-based projection, apparel/retail profile (corpus 13)
/src/api             FastAPI
/web                 Next.js
/synthetic           generator for the reference dataset
/tests
  /unit /integration /eval
/OPEN_QUESTIONS.md   escalations
```

---

## 8. Conventions

- **Config, never code.** Every difference between two companies is a row in a table or a line of YAML. If you find yourself writing `if company == ...`, stop.
- **Type everything.** Pydantic models at every boundary. `Decimal` for money, never `float`.
- **Money is `numeric(18,2)`.** Fractions for percentages, stored not rendered. Basis points computed at display time, never stored.
- Fail loudly. No bare `except`. No default values that mask a missing input.
- Every function that touches a financial concept names the corpus section it implements in its docstring.
- Commit messages state which corpus file and section the change implements.

---

## 9. Testing

- **Test-first wherever the expected output is derivable from the corpus.** Most of it is.
- Every invariant in section 5 has a test that fails if it is violated.
- The eval harness grows with each sprint. It is not built at the end.
- `pytest -m eval` runs the golden set. A regression is a build break, not a ticket.
- A prompt change is a code change and triggers the full suite.
- **Never record system output as an expected value.** Expected answers are computed independently. A test that asserts current behaviour is a snapshot, not a test.

---

## 10. Out of scope

Do not build, and do not scaffold "for later": Tally on-prem agent, bank or GST connectors, Account Aggregator, LLM-written commentary, insight detection, alerts, document store, OCR, RAG, vector search, industry packs, AI chart selection, multi-entity consolidation, marketplace settlement reconciliation, budget versus actual, self-serve onboarding, mobile app, public API, Slack or WhatsApp delivery.

Each has a defined trigger in corpus `02` section 5. None starts because it would be interesting.

**Forecasting and the scenario engine were started 2026-08-24, ahead of their stated trigger** ("statements tie for three consecutive months," corpus `02` section 5) -- a deliberate founder decision (D-069, corpus `00`) to build the driver-based forecast engine against a synthetic apparel/retail dataset rather than wait for a live pilot. See corpus `13` for what was built and why. The scenario DAG corpus `02` section 5 also names under the same trigger row is not built -- only single-scenario projection (corpus `13` section 6).

---

## 11. Definition of done

A task is done when: it implements a named corpus section, tests pass including the invariant tests, no new fabricated value was introduced, any blocker was escalated to `/OPEN_QUESTIONS.md` rather than resolved by guessing, and the acceptance criterion in corpus `12` for that sprint item is demonstrably met.

Working code that quietly invented a definition is not done. It is a defect that will surface as an unexplainable number six weeks later.
