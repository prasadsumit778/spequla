# ARCHITECTURE_MAP.md

Generated 2026-08-27 by reading the code, migrations, tests and git history — not the README.
Repo: `fpa-engine-main` (product name **SPEQULA**), branch `main`, HEAD `d720199`.

---

## 1. Directory tree (depth 3)

Excludes `node_modules/`, `.venv/`, `dist/`, `.git/`, `__pycache__/`, `web/.next/`, `.pytest_cache/`.

```
.dockerignore
.env                          # present on disk, gitignored, holds live Supabase + WorkOS creds
.env.example
.github/
  workflows/
    ci.yml
    deploy.yml
.gitignore
CLAUDE.md                     # the governing project instructions
Dockerfile
OPEN_QUESTIONS.md             # 8 live escalations (OQ-001..OQ-008)
README.md
config/                       # GENERATED from corpus/ — do not hand-edit
  decisions.yml               # 83 decisions, 16 still status: open
  metrics/                    # 61 metric contract files, one per metric_id
    accounts_payable.yml  accounts_receivable.yml  adjusted_ebitda.yml  aov.yml
    capacity_utilisation_pct.yml  capex.yml  cash.yml  ccc.yml  channel_commission.yml
    closing_cash.yml  cm1.yml  cm1_pct.yml  cm2.yml  cm2_pct.yml  cogs.yml
    corporate_overhead.yml  da.yml  debt.yml  dio.yml  discounts.yml  dpo.yml  dso.yml
    ebit.yml  ebitda.yml  ebitda_margin_pct.yml  equity.yml  financing_cash_flow.yml
    fixed_assets_net.yml  free_cash_flow.yml  gmv.yml  gross_margin_pct.yml
    gross_profit.yml  gross_revenue.yml  gst_on_gmv.yml  interest_expense.yml
    inventory.yml  investing_cash_flow.yml  marketing_cost_per_order.yml
    marketing_spend.yml  net_debt.yml  net_revenue.yml  operating_cash_flow.yml
    operating_cost_cm1.yml  opex.yml  orders.yml  other_current_assets.yml
    other_current_liabilities.yml  other_income.yml  pat.yml  pbt.yml
    realisation_per_unit.yml  restricted_cash.yml  return_rate_pct.yml  returns.yml
    roas.yml  tax_expense.yml  volume_produced.yml  volume_sold.yml
    working_capital.yml  working_capital_change.yml  yield_pct.yml
  taxonomy.yml                # 86 canonical classes
corpus/                       # read-only specification, 16 files (00..13 + 06a)
  00_SPEQULA_OPEN_DECISIONS.md      01_SPEQULA_DATA_REQUEST_PACK.xlsx
  02_SPEQULA_MVP_PRD.md             03_SPEQULA_FINANCE_ONTOLOGY.md
  04_SPEQULA_CANONICAL_DATA_MODEL.md 05_SPEQULA_METRIC_REGISTRY.csv
  05a_SPEQULA_METRIC_CONTRACTS.yml  06_SPEQULA_MAPPING_SPEC.md
  06a_SPEQULA_COA_MAPPING_TEMPLATE.xlsx 07_SPEQULA_QUERY_ARCHITECTURE.md
  08_SPEQULA_REPORT_SPEC.md         09_SPEQULA_DATA_QUALITY_AND_RECONCILIATION.md
  10_SPEQULA_GOLDEN_QUESTIONS.csv   11_SPEQULA_EVALUATION_FRAMEWORK.md
  12_SPEQULA_ENGINEERING_BACKLOG.md 13_SPEQULA_FORECASTING_SPEC.md
data/                         # GITIGNORED, 3.7 MB of generated CSVs on this machine only
  synthetic/
    consumer/                 # generated output
    manufacturer/             # generated output
                              # NOTE: no apparel/ — see §4
db/
  migrations/
    runner.py                 # forward-only runner: shared once, tenant/ once per app.tenant row
    shared/                   # 0000..0010 — app schema, RLS, roles, token_map, audit_log
    tenant/                   # 0001..0023 — dims, bitemporal facts, mapping, packs, forecast
docker-compose.yml            # postgres:16 + minio, local only
docs/
  BUILD_LOG.md  deployment.md  workos_setup.md
fly.api.toml  fly.web.toml    # Fly.io deploy targets
pytest.ini                    # declares only the `eval` marker
requirements.txt  requirements-dev.txt
scripts/
  bootstrap.sh                       # clone → install → migrate → seed
  create_tenant.py                   # register a tenant row (must precede migrations)
  gen_decisions_yml.py               # corpus/00  → config/decisions.yml
  gen_metric_contracts.py            # corpus/05 + 05a → config/metrics/*.yml
  gen_taxonomy_yml.py                # corpus/06a → config/taxonomy.yml
  link_tenant_workos_org.py
  seed_dim_channel.py  seed_dim_date.py  seed_entity.py
  seed_mapping_version_placeholder.py
src/
  access/      grants.py
  admin/       backup_rehearsal.py  tenant_lifecycle.py
  api/         main.py  deps/  routes/
  config/      loader.py  schema.py
  forecasting/ baseline.py  drivers.py  engine.py  scenario.py
  ingest/      calendar.py canonical.py hashing.py landing.py load_pipeline.py
               repull.py staging.py templates.py tokenise.py xlsx.py
  mapping/     engine.py  review.py  rules.py
  quality/     books_to_bank.py  checks.py  period_state.py  trial_balance.py
  reports/     balance_sheet.py cashflow.py charts.py comparatives.py consumer_ladder.py
               document.py edits.py manufacturing_operating.py pack.py pnl.py query.py
               signoff.py statement_lines.py
  semantic/    admission.py ask.py ask_compiler.py bridges.py citation.py compiler.py
               formula.py ir.py model_client.py overrides.py refusal.py
synthetic/
  apparel/     engine.py profile.py stores.py write.py
  consumer/    engine.py profile.py write.py
  manufacturer/ coa.py engine.py parties.py profile.py write.py
  common.py  defects.py  generate.py
tests/
  conftest.py  helpers.py  xlsx_fixture.py
  eval/        7 files     # statements tie, TB 36 months, golden questions, sprint acceptance
  fixtures/    golden_ir.py
  integration/ 18 files    # need a live Postgres; skip cleanly without one
  unit/        31 files    # no DB
web/
  app/         12 route folders (ask, data-health, exceptions, forecast, load-runs, mapping,
               operating, overview, reports, settings, statements, upload) + callback route
  components/  app/ (8 domain components)  ui/ (9 primitives)
  lib/         api.ts format.ts metricUnits.ts nav.ts statementLayout.ts useApi.ts workspace.tsx
  middleware.ts  next.config.js  postcss.config.mjs  tsconfig.json  package.json
```

---

## 2. Languages, frameworks, tooling

| Aspect | Backend | Frontend |
|---|---|---|
| Language | Python 3.12 (166 `.py` files) | TypeScript 5.5 (45 `.ts`/`.tsx`) |
| Framework | FastAPI + `psycopg` 3 (raw SQL, **no ORM**) | Next.js 15 App Router, React 18 |
| Validation | Pydantic v2 at every boundary; `Decimal` for money | — |
| Styling | — | Tailwind CSS 4 (`@tailwindcss/postcss`) |
| Auth | WorkOS AuthKit, JWT verified against JWKS | `@workos-inc/authkit-nextjs` middleware |
| Package manager | `pip` + `requirements.txt` (no lock file, no `pyproject.toml`) | `npm` (`package-lock.json` present) |
| Datastore | PostgreSQL 16, **schema-per-tenant** for analytical data; shared `app` schema with RLS | — |
| Object storage | S3-compatible via `boto3`; MinIO locally | — |

**Notable absences vs. the stated stack in `CLAUDE.md` §6:** there is **no `/dbt` directory** and no `dbt-core` dependency, despite dbt being named as the transform layer. There is no SQLAlchemy either — all analytical SQL is hand-written f-strings over `psycopg` cursors. Neither gap is escalated in `OPEN_QUESTIONS.md`.

### Entrypoints

| Entrypoint | Command |
|---|---|
| API server | `PYTHONPATH=. python3 -m uvicorn src.api.main:app --reload` (`:8000`) |
| Web app | `cd web && npm install && npm run dev` (`:3000`; `/` redirects to `/overview`) |
| Migrations | `PYTHONPATH=. python3 db/migrations/runner.py` (`--schema X` limits the tenant loop) |
| Tenant creation | `python3 scripts/create_tenant.py "<name>" [--synthetic]` — **must run before** migrations |
| Synthetic data | `python3 synthetic/generate.py --company {manufacturer\|consumer\|apparel} --seed 42 [--land]` |
| Full local setup | `scripts/bootstrap.sh` |
| Config regeneration | `scripts/gen_decisions_yml.py`, `gen_metric_contracts.py`, `gen_taxonomy_yml.py` |
| Container | `Dockerfile` → `uvicorn src.api.main:app --port ${PORT:-8000}`; ships `src/ config/ db/migrations/` and 4 scripts only |

### Test setup

`pytest` with a single declared marker (`eval`). Three tiers:

```
pytest tests/unit          # 249 tests, no DB          — VERIFIED PASSING (15s)
pytest tests/integration   # needs live Postgres, skips cleanly otherwise
pytest tests/eval          # gating: statements tie, TB across 36 months, golden questions
```

I ran the full suite against the local Postgres on `:5432`: **320 passed, 0 failed** (unit 15s, integration+eval 118s). `tests/conftest.py` probes `DATABASE_URL` (default `postgresql://spequla:spequla@localhost:5432/spequla`) and calls `pytest.skip` with a remediation message if unreachable.

CI (`.github/workflows/ci.yml`) runs on every push/PR: postgres:16 service + a manually-started MinIO container, then unit → migration dry-run → integration → eval, all gating.

---

## 3. Module map

LOC counts are raw `wc -l` over source files (`.py`/`.ts`/`.tsx`/`.sql`/`.yml`/`.sh`), excluding `node_modules`, `__pycache__` and build output. Responsibilities are inferred from code, not docstring claims.

| Module | Path | Responsibility | LOC | Last commit |
|---|---|---|---|---|
| **API** | [src/api/](src/api/) | FastAPI app with 38 endpoints across 12 route modules; every route resolves the tenant from the WorkOS-signed `org_id` claim and opens an RLS-scoped connection before touching data. | 1,590 | 2026-08-25 |
| **Ingest** | [src/ingest/](src/ingest/) | Takes an uploaded CSV/XLSX through land-immutably → stage-typed → hash → tokenise party names → write bitemporal canonical facts (close-prior-row, never update), with blocking quality checks wired at two points. | 2,467 | 2026-08-24 |
| **Semantic** | [src/semantic/](src/semantic/) | The Ask pipeline: validates a model-produced IR against the registry, deterministically compiles metric contracts to values through a dependency-gate + override chain, runs seven admission gates over the emitted SQL text, and attaches a resolving citation or a typed refusal. | 1,914 | 2026-08-24 |
| **Reports** | [src/reports/](src/reports/) | Assembles P&L, balance sheet, cash flow, CM ladder and the eight-section monthly pack from `fact_gl_entry` read through the mapping version effective for the period, then persists each generation as an immutable artefact with a sign-off workflow. | 2,509 | 2026-08-24 |
| **Quality** | [src/quality/](src/quality/) | The eight-class check catalogue with severity enforced in code, the zero-tolerance trial-balance gate, books-to-bank reconciliation, and the six-state period lifecycle machine (every transition is an INSERT, never an UPDATE). | 840 | 2026-08-23 |
| **Mapping** | [src/mapping/](src/mapping/) | Extracts a chart of accounts, matches it against an exact-match rule library, auto-accepts non-judgement classes, queues the rest by rupee value descending, and freezes an approved, effective-dated mapping version. | 655 | 2026-08-24 |
| **Forecasting** | [src/forecasting/](src/forecasting/) | Reads an observed baseline off mapped facts, applies user-supplied store-cohort and margin drivers as a pure function, and persists named scenarios and their runs append-only; any component without a baseline or a driver is reported as a gap, never defaulted. | 714 | 2026-08-25 |
| **Config** | [src/config/](src/config/) | Loads the generated `config/` surface into typed Pydantic models and refuses to serve any individual metric whose governing decision is still open — naming the decision instead of returning a default. | 212 | 2026-08-23 |
| **Access** | [src/access/](src/access/) | Time-bound, named employee access grants to a tenant's data, logging the granting and the using as two separate event kinds. | 144 | 2026-08-23 |
| **Admin** | [src/admin/](src/admin/) | Tenant deletion (`DROP SCHEMA CASCADE` + PII purge, tombstone retained) and a restore rehearsal that clones and row-count-verifies every table in a tenant schema. | 202 | 2026-08-24 |
| **Migrations** | [db/migrations/](db/migrations/) | Forward-only SQL: 11 shared migrations (roles, RLS, `token_map`, `audit_log`, query cost log) and 23 tenant migrations applied once per registered tenant with `__SCHEMA__` substituted. | 1,205 | 2026-08-25 |
| **Config artefacts** | [config/](config/) | Machine-readable transcription of the corpus: 83 decisions (16 open), 61 metric contracts, 86 canonical classes — generated, never hand-authored. | 4,263 | 2026-08-24 |
| **Synthetic** | [synthetic/](synthetic/) | Deterministic seeded generators for three reference companies (manufacturer, consumer, apparel retail) including a defect log that injects known data-quality faults for the check catalogue to catch. | 2,535 | 2026-08-24 |
| **Scripts** | [scripts/](scripts/) | Corpus→config generators, tenant registration and WorkOS linking, dimension seeders, and the one-command local bootstrap. | 719 | 2026-08-24 |
| **Tests** | [tests/](tests/) | 320 tests in three tiers — pure-arithmetic unit tests, Postgres-backed integration tests (one invariant per file), and gating eval tests asserting statements tie to the rupee. | 5,538 | 2026-08-25 |
| **Web** | [web/](web/) | Next.js App Router UI: 12 screens over the API, with a shared fetch wrapper that forwards the AuthKit bearer token and renders a block reason wherever a number failed to resolve. | 8,324 | 2026-08-25 |
| **Corpus** | [corpus/](corpus/) | Read-only specification; the declared authority over every financial definition, threshold and field name. Never edited by code. | n/a (spec) | 2026-08-24 |
| **Docs** | [docs/](docs/) | Build log, deployment runbook, WorkOS dashboard setup walkthrough. | n/a (prose) | 2026-08-23 |

### `src/api/routes` breakdown

| Route module | Endpoints | Responsibility |
|---|---|---|
| `upload.py` | 1 | Accepts 7 template types (GL, TB, COA, bank, channel orders, production output, store master) and dispatches to the matching loader. |
| `mapping.py` | 3 | Runs a mapping pass, serves the review queue sorted by rupee value, freezes a version under a named approver. |
| `statements.py` | 2 | P&L and balance sheet; `profile` is a request parameter, not persisted tenant config. |
| `operating.py` | 2 | Consumer CM ladder and manufacturing operating metrics, read from operational fact tables rather than the GL. |
| `overview.py` | 1 | The nine headline metric tiles, each with a full citation or an explicit block reason. |
| `data_health.py` | 1 | Four panels: freshness, completeness, reconciliation, exceptions — including the unmapped-rupee figure. |
| `exceptions.py` | 2 | The exception queue, sorted by severity then money; resolution requires a written note. |
| `reports.py` | 7 | Generate, read, edit commentary, sign, export the monthly pack; edits-per-pack counter. |
| `forecast.py` | 5 | Scenario CRUD (delete is an archive) and scenario runs. |
| `ask.py` | 1 | The natural-language pipeline end to end. |
| `load_runs.py` | 2 | Load run status and source file listing. |
| `admin.py` | 7 | Cross-tenant operations, all `require_admin_role`: tenant list, access grants, audit log, model cost, deletion, restore rehearsal. |

---

## 4. Flags

### Dead / missing directories

| Item | Finding |
|---|---|
| `/dbt` | **Does not exist.** `CLAUDE.md` §6 and §7 name dbt-core as the transform layer and `/dbt` as a repo directory. No dbt project, no dependency, no reference anywhere in the code. Every transform is Python-side. |
| `data/synthetic/apparel/` | **Missing on disk** while `consumer/` and `manufacturer/` are populated. `synthetic/generate.py` accepts `--company apparel` and `synthetic/apparel/` is fully implemented and unit-tested, but the apparel dataset — the one the forecast engine was purpose-built against (corpus/13, D-069) — has never been generated here. `data/` is gitignored, so no environment carries it. |
| `data/` | 3.7 MB of generated CSV, gitignored, machine-local. Not dead, but nothing in CI or Docker produces it; a fresh clone has no data until `synthetic/generate.py` runs. |
| `.venv/`, `web/.next/`, `.pytest_cache/`, `web/tsconfig.tsbuildinfo` | Build/tool artefacts, correctly gitignored, present on disk. |
| `src/quality/books_to_bank.py` | **161 LOC with zero importers in `src/`.** Reachable only from three test files. Nothing in `src/api/` exposes books-to-bank reconciliation, yet `src/quality/period_state.py:135` refuses the `MAPPED → RECONCILED` transition with the message "run `src/quality/books_to_bank.run_books_to_bank` first" — a transition no API surface can satisfy. This is the closest thing to an orphaned subsystem in the repo. |
| `src/reports/cashflow.py` | 266 LOC, reachable **only** through `pack.py`. There is no `/statements/cash-flow` endpoint and no cash flow tab in `web/app/statements/page.tsx`, despite `CLAUDE.md` invariant 9 tying cash flow closing cash to balance sheet cash as a display gate. |
| `src/reports/charts.py::waterfall_chart` | Defined and unit-tested; never called from any assembler. Its intended consumers (the margin bridge, the price/volume/mix bridge) are the pack sections `pack.py` reports as not-computable. |
| `src/semantic/model_client.py::AnthropicModelClient` | A stub whose three methods all raise `ModelNotConfigured`. `src/api/routes/ask.py:28` hard-wires `StubModelClient({})`, so **every `/ask` request currently refuses**. This is a deliberate, documented hold on VERIFY[V-012], not rot — but the entire Ask surface is dark. |

### Duplicated logic

| Duplication | Detail |
|---|---|
| **Two consumer CM ladders** | `src/reports/pnl.py::compute_consumer_cm_ladder` (GL-only) and `src/reports/consumer_ladder.py::assemble_consumer_ladder` (order-file + GL) both compute a contribution-margin ladder, from different sources, and both are live. `/statements/pnl`, `pack.py` and `ask_compiler.py` use the GL version; `/operating/consumer-ladder` uses the order-file version; `forecasting/baseline.py` uses the GL version. Two answers to "what is CM1 for April" are reachable from the same deployment. The split is deliberate and documented (corpus/04: books vs. operational truth, gap reported as residual) — but nothing in the API tells a caller which one they got. |
| **Two SQL-emitting compilers** | `src/semantic/compiler.py` (metric-contract → value, invoked by id) and `src/semantic/ask_compiler.py` (IR → SQL text + result). The second wraps the first rather than reimplementing it, but both construct SQL strings, so the admission gates in `admission.py` only see what `ask_compiler` produced. |
| **`_jsonable`** | Byte-for-byte the same private Decimal/date serialiser in `src/reports/pack.py` and `src/forecasting/scenario.py`; the latter's docstring acknowledges the copy. |
| **Statement row order in two languages** | `src/reports/statement_lines.py` (Python) and `web/lib/statementLayout.ts` (TypeScript) both encode corpus/08's verbatim P&L row order. Changing a statement layout means editing both. |
| **Metric units in the frontend** | `web/lib/metricUnits.ts` is a hand-copied transcription of `corpus/05`'s `unit` column. Its own comment says "Regenerate it if the registry changes" — **there is no generator**; `scripts/` has no script that writes it. A registry change silently drifts the rendering (a fraction rendered with a rupee sign). |

### Looks abandoned / at risk

- **`pytest -m eval` does not run the eval suite.** `CLAUDE.md` §9 states "`pytest -m eval` runs the golden set. A regression is a build break." Only 3 of the 7 files in `tests/eval/` carry `@pytest.mark.eval`; `-m eval` collects **4 of 320** tests, silently excluding the golden-question suite, the monthly pack, and both sprint acceptance suites. CI is unaffected (it runs `pytest tests/eval` by path), but anyone following the documented command gets a false green.
- **Stale path reference:** `src/semantic/citation.py:8` points at `src/api/routes/metrics.py`, which does not exist. The behaviour it describes now lives in `overview.py`.
- **8 open escalations** in `OPEN_QUESTIONS.md` (OQ-001…OQ-008), several of which gate shipped code paths — notably OQ-004 (eight cash flow leaf metrics have no formula anywhere in the corpus) and OQ-007 (a balance sheet cannot balance while anything sits in suspense, which contradicts D-053).
- **16 of 83 decisions still `status: open`** in `config/decisions.yml`, which by design blocks individual metrics at resolution time.
- Repo history is only 13 commits over 5 days (2026-08-23 → 2026-08-25), squashed from an "Initial import: sprints 0-7". Git blame is close to useless for understanding why any given line exists — the docstrings and `docs/BUILD_LOG.md` are the real history.

---

## 10 things I'd want a new engineer to know before touching this code

1. **The corpus outranks you, and it outranks your training data.** `/corpus` is 16 read-only spec files that are the sole authority on every financial definition, threshold and source-system field name. If a formula isn't there, you don't know it — you stop and append an `OQ-nnn` to `OPEN_QUESTIONS.md`. A commit that quietly invents a definition is treated as a defect even when the tests pass. Read `CLAUDE.md` §3 before your first change; it is not boilerplate.

2. **`config/` is generated output — never hand-edit it.** `config/decisions.yml`, `config/metrics/*.yml` and `config/taxonomy.yml` come from `scripts/gen_*.py` reading the corpus. Editing them directly is how a corpus change silently fails to propagate. Change the corpus, re-run the generator, commit both.

3. **A metric refusing to produce a number is correct behaviour, not a bug.** 16 decisions are still open; `src/config/loader.py` refuses any metric whose governing decision (or, via `compiler.py`, any transitive dependency's decision) is unresolved, and returns the decision id instead of a value. `net_revenue` is blocked today. Do not "fix" this by adding a fallback — that's exactly the failure mode the system exists to prevent.

4. **Nothing is ever UPDATEd or DELETEd.** Every fact table is bitemporal (`valid_from`/`valid_to`/`is_current`/`load_run_id`); a changed fact closes the prior row and inserts a new one. Period-lock transitions insert. Mapping versions, report artefacts and forecast scenarios version forward — scenario "delete" is an archive (migration `0023`). The only genuinely destructive path in the codebase is `src/admin/tenant_lifecycle.delete_tenant`, and it is deliberately never time-triggered.

5. **Tenancy is enforced at two different layers and you must not mix them up.** Analytical data is schema-per-tenant (`__SCHEMA__` substituted by `db/migrations/runner.py`); app data is shared tables with row-level security forced by the connection role via the `app.tenant_id` session variable — never by a `WHERE` clause you write. The tenant comes from a WorkOS-signed `org_id` claim, never from a header. Separately, the model-reachable DB role has no grant on `token_map` or `audit_log`; that's a schema property, not something a pipeline step can forget.

6. **No model writes SQL, and no arithmetic lives outside the registry.** Models emit semantic IR validated against a schema (`src/semantic/ir.py`); a deterministic compiler emits SQL; seven admission gates run over the emitted SQL *text* before it reaches Postgres. If you find yourself summing canonical columns in a route handler or a React component, you've broken invariant 2.

7. **Ask is dark and statements are live — know which surface you're in.** `/ask` hard-wires `StubModelClient({})` (`src/api/routes/ask.py:28`), so every question refuses until a vendor decision (V-012) lands. Everything downstream of a valid IR is real. Meanwhile statement assembly deliberately bypasses the metric registry entirely — `pnl.py`/`balance_sheet.py` read `fact_gl_entry` through the effective mapping version, which is why statements tie to the books even while metrics are decision-blocked.

8. **Order of operations for a working local environment is non-obvious.** `scripts/create_tenant.py` must run *before* `db/migrations/runner.py`, because the tenant loop iterates `app.tenant` rows. Then seed `dim_date`, `dim_entity`, `dim_channel` and the version-0 mapping placeholder. Then generate synthetic data. Then — critically — run and **freeze a mapping version** from the Mapping screen, or every gated number correctly reports "not available." `scripts/bootstrap.sh` does the whole chain; use it.

9. **Nothing loads `.env` for you.** There is no `python-dotenv` and `docker-compose.yml` has no `env_file`. The `.env` on disk holds live Supabase and WorkOS credentials and points at a shared remote database — but only takes effect if you export it yourself. Every module falls back to `postgresql://spequla:spequla@localhost:5432/spequla`. Know which database you're about to migrate before you run the runner: an accidental `export $(cat .env)` runs forward-only migrations against the shared project.

10. **Verify the test command before you trust it.** `pytest tests/unit` (249 tests, ~15s, no DB) and the full suite (320 tests, ~2min with local Postgres) both pass today. But `pytest -m eval` — the command `CLAUDE.md` §9 names as the gating golden-set run — collects only 4 of 320 tests, because four of the seven files in `tests/eval/` never got the marker. Run eval tests **by path** (`pytest tests/eval`), the way CI does. And per §9, never record system output as an expected value: an eval assertion is computed independently from the corpus, or it's a snapshot pretending to be a test.
