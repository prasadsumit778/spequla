# SPEQULA

An always-on FP&A system for Indian mid-market companies. It ingests a company's accounting and operating data, converts it into one canonical financial model, produces statements and metrics that tie exactly to the client's own books, answers a bounded set of financial questions with every number traceable to source rows, and generates a monthly management pack.

**The failure mode this system exists to prevent is a plausible wrong number.** Not a crash, not a slow query, not an ugly screen. A number that looks right, reaches a board pack, and is wrong. Everything in this codebase follows from that.

## The corpus is the only source of finance truth

`/corpus` contains fourteen specification files — the authority on every financial definition, threshold, field name and business rule in this system. `CLAUDE.md` governs how this repository is built: no invented definitions, no invented thresholds, no invented source-system field names, no fabricated numbers. Where the corpus is genuinely silent or in conflict, the blocker is logged in [`OPEN_QUESTIONS.md`](./OPEN_QUESTIONS.md) rather than guessed — six of the seven raised so far (OQ-001 through OQ-007) are resolved, one partially; each was a real gap or conflict in the spec, not a placeholder.

| File | Authority over |
|---|---|
| `00_SPEQULA_OPEN_DECISIONS.md` | Every finance judgement call and its resolution |
| `01_SPEQULA_DATA_REQUEST_PACK.xlsx` | What a customer is asked to supply, and in what shape |
| `02_SPEQULA_MVP_PRD.md` | Scope, roles, non-functional requirements |
| `03_SPEQULA_FINANCE_ONTOLOGY.md` | What every financial concept means |
| `04_SPEQULA_CANONICAL_DATA_MODEL.md` | Tables, columns, keys, grains, lineage |
| `05_SPEQULA_METRIC_REGISTRY.csv` / `05a_..._CONTRACTS.yml` | The metric inventory and executable contracts |
| `06_SPEQULA_MAPPING_SPEC.md` | Canonical class taxonomy and the mapping loop |
| `07_SPEQULA_QUERY_ARCHITECTURE.md` | Semantic IR, intents, safety gates, refusal |
| `08_SPEQULA_REPORT_SPEC.md` | Statement layouts and the monthly pack |
| `09_SPEQULA_DATA_QUALITY_AND_RECONCILIATION.md` | Checks, severities, reconciliation, period gating |
| `10_SPEQULA_GOLDEN_QUESTIONS.csv` | The evaluation set |
| `11_SPEQULA_EVALUATION_FRAMEWORK.md` | Test suites, tolerances, gates |
| `12_SPEQULA_ENGINEERING_BACKLOG.md` | Sprint scope and acceptance criteria |
| `13_SPEQULA_FORECASTING_SPEC.md` | Driver taxonomy and formulas for the apparel/retail forecast engine |

## Architectural invariants

A handful of rules are never violated anywhere in this codebase:

- No model ever writes SQL — models emit semantic IR, a deterministic compiler emits SQL.
- No metric formula exists outside the registry.
- Every fact table is bitemporal; nothing is ever overwritten or deleted.
- Analytical data is schema-per-tenant; app data is shared tables with row-level security.
- The model-reachable database role has no grant on `token_map`, `audit_log`, or any app table.
- Every displayed number carries a citation that resolves to source rows, or it is not displayed at all.
- Trial balance tolerance is zero. A balance sheet that does not balance is not displayed.
- A decomposition whose components do not sum to the total reports the gap — never sweeps a residual into "other."

See `CLAUDE.md` section 5 for the full list.

## What's built

All eight sprints in `corpus/12`'s backlog are complete:

| Sprint | Scope |
|---|---|
| 0 | Config generation, the refusing loader, synthetic reference dataset (manufacturer + consumer, 13 seeded defects) |
| 1 | Ingestion pipeline (COA/TB/GL/Bank), canonical bitemporal writes, tokenisation |
| 2 | The mapping loop, P&L and balance sheet assembly |
| 3 | Financial overview, data health, exception queue, the full check catalogue |
| 4 | Ask — semantic IR, the deterministic compiler, seven admission gates, deterministic bridges |
| 5 | The monthly management pack — eight sections, indirect cash flow, chart specs as JSON, sign-off workflow |
| 6 | The second profile — `fact_channel_order_line`, the consumer CM ladder, both revenue models, manufacturing operating metrics |
| 7 | Pilot operations — tenant deletion, restore rehearsal, named time-bound employee access, per-tenant model cost tracking |

Since then, three P0 capabilities that were specified but not built have been closed:

| Capability | corpus reference | What was missing |
|---|---|---|
| Excel ingestion | 02 §3 P0 #1 | Only CSV parsed. `.xlsx` now loads on every stream, including the corpus/01 workbook itself |
| Bank file upload | 02 §3 P0 #7 | `load_bank_file` existed but had no upload route, so books-to-bank could not be exercised |
| Pack exported as a document | 02 §3 P0 #10 | Export returned JSON. It now returns a self-contained HTML document (`?format=json` for the data) |
| Edits per pack | 02 §8, 11 §4 | The primary commercial metric was not tracked at all |

Two things are deliberately left as connection points, not gaps: a real `AnthropicModelClient` (the vendor decision is the account owner's to make and set up), and a DB-level masking view enforcing Ask's admission gates at the role level (disclosed, not silently worked around, in `src/semantic/ask.py`).

**Forecasting build (2026-08-24, corpus/13).** A driver-based operating forecast for the apparel/retail profile, started ahead of its P1 trigger by deliberate founder decision (D-069) rather than a live pilot's tied statements — see corpus/00 D-069 and corpus/02 §5. Added: `dim_location`/`dim_product` retail attributes and the Store Master ingestion template (corpus/04 §3.10); three store-level canonical classes (`opex.store_rent`, `opex.store_personnel`, `opex.franchise_commission`); a third synthetic company (`synthetic/apparel/`, five years of actuals, store-cohort and channel-tier mechanics derived from a real apparel financial model's structure, never its figures); the forecast engine itself (`src/forecasting/`) and its Forecasting screen.

## Stack

Python 3.12, FastAPI, psycopg3, Pydantic v2, PostgreSQL 16 (schema-per-tenant), Next.js + TypeScript, WorkOS (AuthKit) for auth, pytest.

## Repo layout

```
/corpus              specification, read-only, authoritative
/config              decisions.yml, taxonomy.yml, metrics/ -- generated from the corpus
/db/migrations        forward-only, shared + per-tenant schema loop
/src/ingest            connectors, staging, canonical loaders
/src/mapping            proposer, rule library, review API
/src/semantic            registry loader, IR schema, validator, SQL compiler, Ask
/src/quality              check catalogue, reconciliation, exception queue
/src/reports               statement assembly, the monthly pack, the consumer ladder
/src/forecasting            driver-based projection, apparel/retail profile (corpus/13)
/src/admin                  tenant lifecycle, restore rehearsal
/src/access                  employee access grants
/src/api                      FastAPI app and routes
/web                           Next.js frontend
/synthetic                      deterministic reference-data generator
/tests                           unit / integration / eval
/OPEN_QUESTIONS.md                 escalations, per CLAUDE.md section 4
```

## Running it locally

You need a Postgres instance (either `docker compose up -d` for local Postgres + MinIO, or a hosted instance such as Supabase — this project has been run against both) and a WorkOS application with AuthKit enabled.

1. **Environment.** Nothing loads `.env` automatically — export it (`set -a; source .env; set +a`) or set the variables in your shell. Copy `.env.example` to `.env` and fill in `DATABASE_URL`, object storage credentials, and `WORKOS_API_KEY` / `WORKOS_CLIENT_ID`. Copy `web/.env.local.example` to `web/.env.local` similarly, plus a generated `WORKOS_COOKIE_PASSWORD` (`openssl rand -base64 24`) and `NEXT_PUBLIC_WORKOS_REDIRECT_URI=http://localhost:3000/callback`.
2. **WorkOS setup.** In the WorkOS dashboard: create the four custom Roles (`promoter`, `client_finance_lead`, `spequla_analyst`, `admin`), add `http://localhost:3000/callback` under Redirects, create an Organization, and add yourself as a member with a role. Link that Organization to a tenant with `scripts/link_tenant_workos_org.py --tenant-id <uuid> --workos-org-id org_...`.
3. **Database.** `python3 db/migrations/runner.py` applies every migration. `python3 scripts/create_tenant.py "Your Company" --synthetic` registers a tenant; `scripts/bootstrap.sh` does the full local-Postgres path end to end, including seeding both synthetic reference companies.
4. **Backend.** `PYTHONPATH=. python3 -m uvicorn src.api.main:app --reload` — runs on `:8000`.
5. **Frontend.** `cd web && npm install && npm run dev` — runs on `:3000`.
6. **See real numbers.** A fresh tenant has no approved mapping, so every gated metric correctly reports "not available" until you run and freeze a mapping version from the **Mapping** screen (or `POST /mapping/runs` then `POST /mapping/runs/{id}/freeze`).

## Testing

```
pytest tests/unit                 # fast, no DB needed
pytest tests/integration          # needs a live Postgres, skips cleanly otherwise
pytest tests/eval                 # the golden question set + sprint acceptance criteria, slow
```

`pytest -m eval` runs the golden set specifically. A regression there is a build break, per `CLAUDE.md` section 9 — not a ticket.
