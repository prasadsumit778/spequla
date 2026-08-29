# RISKS.md

Skeptical audit of the SPEQULA repo. HEAD `d720199`, audited 2026-08-27.
Every claim below is either quoted source or a command I ran against the live local database.

**Bottom line up front.** The engineering discipline here is genuinely high — bitemporal writes,
zero-tolerance trial balance, a real dependency-gated metric compiler, honest docstrings that
disclose their own gaps. But three things would stop me signing off on a pilot:

1. **Row-level security is not in force in either configured environment.** The app connects as a
   Postgres superuser, which bypasses RLS unconditionally. Verified empirically below.
2. **Four of the seven admission gates cannot reject anything meaningful**, and two of them accept
   the SQL text as a parameter and never read it.
3. **Numbers with no source rows are displayed as real numbers with citations.** Demonstrated with
   a runnable repro. This is the exact failure mode `CLAUDE.md` says the system exists to prevent.

---

## 1. The seven admission gates — all present, four toothless

All seven functions exist in [src/semantic/admission.py](src/semantic/admission.py) and
`run_admission_gates` ([:123](src/semantic/admission.py#L123)) calls them in order. So "are all 7
implemented?" — yes, as functions. Whether they *gate* anything is a different question, gate by gate.

### Gate 1 — "parse" ([admission.py:53](src/semantic/admission.py#L53))

```python
def gate_1_parse(sql_text: str) -> None:
    stripped = sql_text.strip()
    if not stripped:
        raise AdmissionRejected("parse", "empty SQL text")
    if not re.match(r"^\s*(SELECT|WITH)\b", stripped, re.IGNORECASE):
        raise AdmissionRejected("parse", "does not start with SELECT or WITH -- not a valid read query")
    if stripped.count("(") != stripped.count(")"):
        raise AdmissionRejected("parse", "unbalanced parentheses")
```

**It does not parse.** It is a prefix regex plus a paren count. `sqlparse` is declared in
[requirements-dev.txt](requirements-dev.txt) — a **dev-only** dependency that the production
Dockerfile never installs — and `grep -rn sqlparse src/` returns **zero hits**. It is never imported.

Two concrete holes: paren counting is defeated by a parenthesis inside a string literal
(`WHERE narration = ':-('`), and **there is no check for `;`** — so `SELECT 1; SELECT pg_sleep(60)`
passes gate 1 intact.

**Verdict: theatre.** Naming it "parse" oversells a three-line string check.

### Gate 2 — read-only ([admission.py:63](src/semantic/admission.py#L63))

```python
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|"
    r"pg_read_file|pg_ls_dir|lo_import|lo_export|dblink)\b", re.IGNORECASE)

def gate_2_read_only(sql_text: str) -> None:
    match = _FORBIDDEN_KEYWORDS.search(sql_text)
    if match:
        raise AdmissionRejected("read_only", f"forbidden keyword {match.group(0)!r} -- read-only queries only")
```

**The only gate that genuinely inspects the SQL.** But it is a **blacklist**, and blacklists lose.
Not covered: `MERGE`, `CALL`, `DO`, `EXECUTE`, `SET`, `RESET`, `VACUUM`, `ANALYZE`, `pg_sleep`,
`pg_stat_file`, `pg_read_binary_file`, `SET ROLE`. It also false-positives on any narration or
account name containing the word "update" or "create".

**Verdict: real but weak.** The correct control is the database role, which is not used (§4).

### Gates 3 and 5 — allowlist and PII exclusion ([:69](src/semantic/admission.py#L69), [:83](src/semantic/admission.py#L83))

```python
def gate_3_table_allowlist(sql_text: str, tables_referenced: list[str]) -> None:
    for table in tables_referenced:                    # <- sql_text never read
        bare = table.split(".")[-1].strip('"')
        if bare not in CANONICAL_TABLE_ALLOWLIST:
            raise AdmissionRejected("table_allowlist", f"{table!r} is not a canonical table or approved view")

def gate_5_pii_exclusion(sql_text: str, tables_referenced: list[str]) -> None:
    for table in tables_referenced:                    # <- sql_text never read
        bare = table.split(".")[-1].strip('"')
        if bare in FORBIDDEN_TABLES:
            raise AdmissionRejected("pii_exclusion", f"{table!r} is not a model-reachable table")
```

**Both accept `sql_text` and never reference it in the body.** They validate `tables_referenced` —
a Python list handed in by the same compiler they exist to check. The module docstring claims the
gates run "on the actual string about to reach Postgres, not on the compiler's own intent." For
gates 3 and 5 that is exactly backwards: they check the compiler's declaration of intent and ignore
the string entirely. A query touching `app.token_map` passes both gates if the caller simply doesn't
list it.

**Verdict: structurally unable to catch what they exist to catch.**

### Gate 4 — tenant predicate ([admission.py:76](src/semantic/admission.py#L76))

```python
def gate_4_tenant_predicate(sql_text: str, tenant_id: str) -> None:
    if "tenant_id" not in sql_text:
        raise AdmissionRejected("tenant_predicate", "no tenant_id predicate present in the compiled SQL")
    if tenant_id not in sql_text and "%s" not in sql_text:
        raise AdmissionRejected("tenant_predicate", "tenant_id predicate present but not bound to this tenant")
```

A **substring search**. `SELECT tenant_id FROM fact_gl_entry` passes — the string appears in the
SELECT list with no `WHERE` clause at all. The second check is dead on arrival: every real query is
parameterised, so `"%s" in sql_text` is always true and the branch never fires.

**Verdict: checks that a 9-character substring exists somewhere. Not a predicate check.**

### Gate 6 — cost estimate ([admission.py:99](src/semantic/admission.py#L99))

```python
def gate_6_cost_estimate(estimated_cost_inr: Decimal | None, cap: Decimal | None = COST_CAP_INR_PER_QUERY) -> None:
    if cap is not None and estimated_cost_inr is not None and estimated_cost_inr > cap:
        raise AdmissionRejected("cost_estimate", ...)
```

The sole caller passes three arguments ([ask.py:151](src/semantic/ask.py#L151)), so
`estimated_cost_inr` defaults to `None` and the guard short-circuits. **This gate cannot reject.**
Honestly disclosed in the docstring and in the caller's comment — but disclosed and functional are
different things.

### Gate 7 — row cap ([admission.py:117](src/semantic/admission.py#L117))

```python
def gate_7_row_cap(sql_text: str) -> str:
    if re.search(r"\bLIMIT\s+\d+", sql_text, re.IGNORECASE):
        return sql_text
    return f"{sql_text.rstrip().rstrip(';')} LIMIT {ROW_CAP}"
```

Returns capped SQL into `AdmissionResult.sql_text`. The caller reads only `.admitted` and `.gate` —
**`sql_text` is discarded** ([ask.py:152](src/semantic/ask.py#L152)). Also, a `LIMIT` inside a
subquery satisfies the regex and suppresses the outer cap.

**Verdict: computes a correct answer nobody uses.**

### The framing problem behind all seven

The gates run **after** the database has been read. Execution is
[ask.py:135](src/semantic/ask.py#L135); gates are [ask.py:151](src/semantic/ask.py#L151). And what
they inspect is not the executed query — it is `_representative_gl_class_sql`
([ask_compiler.py:67](src/semantic/ask_compiler.py#L67)), a **reconstruction** built to "mirror" the
real query. The real SQL is emitted inside `_fetch_leaf_amounts`
([compiler.py:167](src/semantic/compiler.py#L167)) and never shown to a gate.

| Gate | Implemented | Reads the SQL | Can reject | Guards the executed query |
|---|---|---|---|---|
| 1 parse | ✓ (regex, not a parser) | ✓ | ✓ | ✗ runs post-execution |
| 2 read-only | ✓ (blacklist) | ✓ | ✓ | ✗ runs post-execution |
| 3 allowlist | ✓ | **✗** | ✓ | ✗ |
| 4 tenant predicate | ✓ (substring) | ✓ | weakly | ✗ |
| 5 PII exclusion | ✓ | **✗** | ✓ | ✗ |
| 6 cost estimate | ✓ | n/a | **✗ never** | ✗ |
| 7 row cap | ✓ | ✓ | n/a | **✗ output discarded** |

17 unit tests cover these gates ([tests/unit/test_admission.py](tests/unit/test_admission.py)) —
all of them call the gate functions directly with hand-written SQL. None tests the wiring.

---

## 2. Is the "deterministic" engine calling an LLM?

**No. This one is clean, and I tried hard to break it.**

`grep -rn "model_client\|anthropic\|openai\|classify_intent\|generate_ir\|narrate" src/` returns hits
in exactly three files: [model_client.py](src/semantic/model_client.py) (the definition),
[ask.py:102,111](src/semantic/ask.py#L102) (the two model-touching stages, both *before* the
deterministic path), and docstrings/comments elsewhere.

`compile_metric`, `formula.py`, `bridges.py`, `citation.py`, every module in `src/reports/`, and every
module in `src/forecasting/` import no model client and make no network call. `CLAUDE.md` invariant
1 ("no model ever writes SQL") and corpus/07's "nothing that touches a number is a model call" both
hold at the code level.

The caveat is that this is currently trivially true: **nothing calls a model at all.**
[ask.py:27](src/api/routes/ask.py#L27) hardwires `StubModelClient({})` with an empty fixture dict, so
every question refuses at intent classification. The separation is real and well-built, but it has
never been tested against an actual model in the loop. When `AnthropicModelClient` is wired up, the
first thing to re-audit is whether `estimated_cost_inr` actually starts flowing into gate 6 and
whether the `_representative_gl_class_sql` reconstruction still matches what runs.

---

## 3. Numbers without a traceable source

The diagram promises "every number traceable to its source file." `CLAUDE.md` invariant 7:
"A number without one is not displayed. Not badged, not greyed out. Not displayed."

### 3.1 Six of eight endpoints return numbers with no citation at all

```
grep -c citation src/api/routes/{statements,operating,reports,forecast,data_health,exceptions}.py
→ 0, 0, 0, 0, 0, 0
```

Only `/overview/tiles` and `/ask` construct citations. `/statements/pnl` returns every P&L line and
subtotal, `/statements/balance-sheet` returns every group total, `/operating/*` returns the whole CM
ladder, and the monthly pack (`generate_pack`, 434 LOC) assembles eight sections — **none carries a
citation object**. That is the large majority of numbers this product displays.

### 3.2 A zero with no rows behind it is displayed as a real number — runnable repro

`build_citation` ([citation.py:96](src/semantic/citation.py#L96)) guards only on status and null value:

```python
if compiled.status != "ok" or compiled.value is None:
    raise NotCitable(...)
```

There is **no guard on `row_count == 0` or `source_files == []`**. And a metric whose canonical
classes have no GL rows evaluates to a clean `Decimal("0")`:

```
$ .venv/bin/python -c "..."
cash formula: gl_class(asset.cash_bank)
value with ZERO fetched rows: 0
```

Chain: `_fetch_leaf_amounts` returns `({}, 0, set())` → `eval_gl_class_formula` returns `0`
([formula.py:120-127](src/semantic/formula.py#L120)) → `status="ok"`, `row_count=0`,
`load_run_ids=set()` → `fetch_source_files` returns `[]`
([citation.py:65](src/semantic/citation.py#L65)) → a Citation is built. The overview tile renders the
number ([overview.py:52](src/api/routes/overview.py#L52)), and
[Citation.tsx:94](web/components/app/Citation.tsx#L94) handles the empty file list with a ternary —
**it renders, it does not refuse.**

The code cannot distinguish "genuinely zero activity" from "no data loaded." A freshly-onboarded
tenant with an approved mapping and no GL shows **₹0 cash, cited, on the board-facing overview.**
This is a plausible wrong number reaching a screen — precisely what `CLAUDE.md` §1 names as the
failure mode the system exists to prevent.

### 3.3 `reconciliation_status` is a hardcoded literal on the Ask path

[ask.py:184](src/semantic/ask.py#L184): `build_citation(..., "reconciled")`. No read of `period_lock`.
Every Ask citation asserts the period is reconciled regardless of its actual state. (`/overview` does
this correctly, passing a computed value.) Given that the period state machine has **zero production
callers** (§5), no period is ever actually reconciled — so this field is always false.

### 3.4 `basis="accrual"` hardcoded

[citation.py:107](src/semantic/citation.py#L107) ignores `IRRequest.basis`, which the IR schema
declares as `Literal["accrual","cash"]`. A cash-basis question is answered on accrual and cited as
accrual.

### 3.5 The drill-through does not exist

Every citation carries `drill_url=f"/query/{query_hash}/rows"`
([citation.py:111](src/semantic/citation.py#L111)). No such route exists. To the team's credit the UI
says so out loud ([Citation.tsx:114](web/components/app/Citation.tsx#L114)) rather than shipping a
broken link — but "resolves to source rows" is currently a filename list, not a drill-through.

---

## 4. Auth, tenancy, secrets, input validation

### 4.1 🔴 RLS is bypassed in every configured environment — verified

`CLAUDE.md` invariant 5: "row-level security **forced at the connection role**, never in query text."
The migrations do this correctly: `ENABLE` + `FORCE ROW LEVEL SECURITY` and a `tenant_isolation`
policy on all seven `app` tables.

I checked what role the app actually connects as:

```
$ psycopg.connect("postgresql://spequla:spequla@localhost:5432/spequla")
  SELECT current_user, rolsuper, rolbypassrls ...
  → ('spequla', True, False)
```

**`rolsuper = True`.** Postgres superusers bypass row-level security unconditionally — `FORCE RLS`
extends RLS to the table *owner*, not to superusers. So every RLS policy in this repo is inert as
configured. `docker-compose.yml` sets `POSTGRES_USER: spequla`, which the `postgres:16` image creates
as a superuser; the checked-in `.env` points at a Supabase pooler as `postgres.<project>`, also
superuser-class.

Tenant isolation today therefore rests entirely on (a) physical schema separation for analytical
data — which is real and solid — and (b) every `app`-table query remembering to include
`WHERE tenant_id = %s` in its text. Which is the thing the invariant exists to forbid.

**Also:** `app.tenant` has **no RLS at all** — verified `relrowsecurity = False`. It has to be readable
before tenant context exists ([tenant.py:41](src/api/deps/tenant.py#L41)), so this is structurally
necessary, but it means every tenant's name, `schema_name` and `workos_organization_id` is readable
from any connection.

**And:** all nine `/admin/*` routes open a raw connection via `_conn()`
([admin.py:31](src/api/routes/admin.py#L31)) and **never set `app.tenant_id`**. They are cross-tenant
by design and gated on `require_admin_role`, but they operate with zero RLS context — so the role
check in application code is the only thing standing between an admin session and every tenant's
data.

**The test that "proves" invariant 6 explicitly assumes a role production never assumes.**
[test_token_map_role_denied.py:20](tests/integration/test_token_map_role_denied.py#L20) issues
`SET ROLE model_reachable` and asserts the denial. Production never issues that statement —
[ask.py:198](src/semantic/ask.py#L198) documents why it can't. Green test, unenforced guarantee.

### 4.2 🟢 Authentication itself is good

[auth.py:72](src/api/deps/auth.py#L72) verifies the RS256 signature against WorkOS's JWKS before
reading any claim; user, org and role come only from verified claims. Tenant is resolved from the
signed `org_id`, never a header ([tenant.py:41](src/api/deps/tenant.py#L41)). Missing WorkOS env vars
raise `RuntimeError` rather than defaulting. [test_auth.py](tests/unit/test_auth.py) generates its own
RSA keypair and tests forged, expired and valid tokens without network access — that's the right way
to test this. No complaints.

One gap: `verify_aud` is disabled ([auth.py:80](src/api/deps/auth.py#L80)) with a documented WorkOS
rationale. Defensible, worth revisiting.

### 4.3 🟢 No secrets committed

`git ls-files | grep .env` → only `.env.example` and `web/.env.local.example`. No `.env` in history.
`.gitignore` covers `.env`, `.venv/`, `web/.next/`, `data/`.

🟡 But seven of nine backend env vars silently fall back to dev defaults —
`DATABASE_URL` → localhost, `OBJECT_STORE_SECRET_KEY` → `"spequla_dev_only"`
([landing.py:20](src/ingest/landing.py#L20)). `CLAUDE.md` §8 says "no default values that mask a
missing input." A misconfigured production deploy points at a nonexistent local Postgres instead of
refusing to boot. Only the two WorkOS keys fail loudly.

🟡 The working-tree `.env` holds live Supabase and WorkOS credentials and nothing auto-loads it (no
`python-dotenv`, no `env_file:`). An `export $(cat .env)` before `db/migrations/runner.py` runs
forward-only migrations against the shared hosted database.

### 4.4 Input validation — mostly fine, three gaps

🟢 SQL injection: not exploitable. Schema names are interpolated into f-strings, but they always come
from `app.tenant.schema_name` via a DB round-trip and are generated as `tenant_{uuid.hex}`
([create_tenant.py:25](scripts/create_tenant.py#L25)). Every user value is a bound parameter.

🟢 Most query params are validated: `pattern=r"^\d{4}-\d{2}$"` for periods,
`^(manufacturing|consumer)$` for profile, `^(open|resolved|deferred|accepted)$` for status.

🔴 **No upload size limit.** [upload.py:50](src/api/routes/upload.py#L50) is
`raw_bytes = await file.read()` — the entire file into memory, no cap, no streaming, before any
validation. A single large upload is a trivial OOM on the API container. There is no reverse-proxy
config in the repo imposing one either.

🟡 `tenant_id: str` on the destructive `/admin/tenants/{tenant_id}/delete`
([admin.py:178](src/api/routes/admin.py#L178)) is untyped — a malformed value reaches Postgres as a
failed uuid cast, producing a 500 rather than a 422. Cosmetic, but it is the `DROP SCHEMA CASCADE`
route.

🟡 Four broad excepts, one of them silent: [ask.py:244](src/semantic/ask.py#L244)
`except Exception: pass` around the `query_log` write. corpus/07 §7 requires every query and every
rejection to be logged; that requirement fails silently by design.

---

## 5. Test coverage by module

320 tests, all passing (249 unit / 71 integration+eval, verified). Counted by test functions, then
mapped to source:

| Module | Src files | Direct test files | Assessment |
|---|---|---|---|
| `src/semantic` | 11 | 5 (`test_admission` 17, `test_ir` 12, `test_semantic_formula` 17, `test_semantic_compiler` 6, `test_compiler_gate` 4) | 🟢 Best-covered. **But `ask_compiler.py` (322 LOC), `bridges.py`, `refusal.py`, `overrides.py` have no direct tests** — only indirect coverage via `test_golden_questions`. |
| `src/ingest` | 10 | 6 (`test_staging` 11, `test_xlsx` 24, `test_hashing` 5, `test_tokenise` 6, `test_templates` 3, `test_repull` 4) | 🟢 Strong on staging/parsing. 🔴 **`landing.py` has zero tests** — the immutable-storage writer is untested. |
| `src/mapping` | 3 | 3 (18 tests) + 3 integration | 🟢 Well covered including the auto-accept judgement-class invariant. |
| `src/reports` | 13 | 4 (`test_reports` 14, `test_document` 13, `test_consumer_ladder` 5, `test_manufacturing_operating` 5) | 🟡 **`cashflow.py` (266 LOC), `comparatives.py`, `signoff.py`, `edits.py`, `charts.py` have no direct unit tests.** `pack.py` (434 LOC) is covered only by `test_monthly_pack` (5 tests). |
| `src/quality` | 4 | 4 unit + 2 integration | 🟡 Covered — but the tests call `write_exceptions` and the period transitions **directly**, which is the only thing that ever calls them (§6). |
| `src/forecasting` | 4 | 1 unit (6 tests) + 1 integration (5) | 🟡 `engine.py` has 6 tests for 235 LOC of financial projection. `baseline.py` (199 LOC) has none directly. |
| `src/config` | 2 | 1 (`test_config_loader` 8) | 🟡 `schema.py` untested. |
| `src/access`, `src/admin` | 3 | 2 integration (10 tests) | 🟡 Thin for `DROP SCHEMA CASCADE`. |
| **`src/api` (15 files, 1,590 LOC)** | 15 | **0** | 🔴 **Zero API-level tests. No `TestClient`, no `httpx` anywhere in `tests/`.** |

### The single biggest coverage hole

```
grep -rn "TestClient\|httpx\|fastapi.testclient" tests/  → (nothing)
```

**39 HTTP endpoints, 1,590 lines of route code, not one test.** Untested as a consequence: every
`Depends()` wiring, every auth gate on every route, all status codes, every response shape the
frontend consumes, and — materially — `conn.commit()` placement. [upload.py:75](src/api/routes/upload.py#L75)
commits *before* checking `result.status`; nothing tests that. `require_upload_role` vs `require_role`
on 39 routes is verified by reading, not by any test.

The bugs I found in REQUEST_TRACE.md (execute-before-gate, TB-not-a-gate, discarded row cap,
hardcoded `reconciliation_status`) are all **wiring** bugs. They survive precisely because every test
calls functions directly and no test exercises a request end to end.

---

## 6. Top 10 riskiest files

Ranked by *blast radius × likelihood of being wrong × how little would catch it*.

| # | File | LOC | Why it's risky |
|---|---|---|---|
| **1** | [src/api/deps/tenant.py](src/api/deps/tenant.py) | 62 | The entire multi-tenant isolation story funnels through 35 lines. Its central guarantee — RLS forced at the connection role — **does not hold as configured** (superuser bypass, §4.1). Smallest file with the largest blast radius: one wrong `tenant_id` here is cross-tenant financial data leakage, and no test at this layer exists. |
| **2** | [src/semantic/admission.py](src/semantic/admission.py) | 140 | Presented as seven security gates between a model and the database. Two never read the SQL, one can't reject, one's output is discarded, one is a substring check, "parse" isn't parsing, and the whole set runs after execution against a reconstruction. 17 tests all pass because they test the functions, never the wiring. |
| **3** | [src/ingest/canonical.py](src/ingest/canonical.py) | 792 | The **sole writer** of every fact table. Owns bitemporal close-not-update, batching under the 65,535 bind-param ceiling, and account resolution. Largest file in `src/`; one test file. A bug here silently corrupts the ledger for every downstream number, and the `ux_gl_row_hash_current` index is the only backstop. |
| **4** | [src/ingest/load_pipeline.py](src/ingest/load_pipeline.py) | 320 | Seven near-identical loaders, copy-pasted rather than parameterised — which is *why* only 4 of 7 do the schema-drift check. Sets `status="succeeded"` unconditionally at [:131](src/ingest/load_pipeline.py#L131) with the trial-balance result computed but never read, and the caller commits before checking. An out-of-balance month loads clean. |
| **5** | [src/reports/pack.py](src/reports/pack.py) | 434 | Assembles the artefact that reaches a board. Eight sections, computed once, frozen, signed. Five tests. Zero citations on any number in it. Every "plausible wrong number" risk in this codebase terminates here. |
| **6** | [src/semantic/compiler.py](src/semantic/compiler.py) | 363 | The best-engineered file here (transitive dependency gating, override chain, shared memo) — and the one place `CLAUDE.md` invariant 2 is bent: `dso`, `dpo` and `dio` have their formulas **rewritten in Python** at [:337-353](src/semantic/compiler.py#L337) instead of read from the registry. Also the origin of the zero-with-no-rows problem (§3.2). |
| **7** | [src/quality/checks.py](src/quality/checks.py) | 430 | 430 lines of correct, tested, **never-executed** code. `write_exceptions` has zero production callers, so the exception queue, data-health panels, pack DQ appendix and sign-off gate all read a permanently empty table. Dangerous because it *looks* like the safety net is deployed. |
| **8** | [src/semantic/ask.py](src/semantic/ask.py) | 245 | Orchestrates 11 stages and gets the order wrong: executes at 135, gates at 151. Hardcodes `reconciliation_status="reconciled"`. Silences its own audit log with `except Exception: pass`. Currently dark, so the damage is latent — it becomes live the day a model is configured. |
| **9** | [src/admin/tenant_lifecycle.py](src/admin/tenant_lifecycle.py) | 108 | `DROP SCHEMA IF EXISTS "{schema_name}" CASCADE` — the only irreversible operation in the system. Reached from an HTTP POST whose `tenant_id` is an unvalidated `str`. Four integration tests. The safeguards (audit-first ordering, tombstone) are thoughtfully built; the input path to them is not. |
| **10** | [src/reports/cashflow.py](src/reports/cashflow.py) | 266 | 266 lines of indirect-method cash flow with **no direct unit test and no endpoint** — reachable only inside `generate_pack`. `CLAUDE.md` invariant 9 ties it to the balance sheet as a display gate; `cash_flow_ties_to_balance_sheet` exists in `checks.py` and is never called from `src/`. Untested financial arithmetic that reaches a board pack. |

**Honourable mentions:** [src/api/routes/upload.py](src/api/routes/upload.py) (unbounded `file.read()`,
no test) and [src/semantic/citation.py](src/semantic/citation.py) (the traceability guarantee itself,
with no guard on an empty source-file list).

---

## What I'd fix before a paying pilot, in order

1. **Create a non-superuser application role** and connect as it. Everything in §4.1 is one
   `CREATE ROLE ... NOSUPERUSER` plus a connection-string change away from being true. Add a startup
   assertion that refuses to boot if `rolsuper` or `rolbypassrls` is set.
2. **Refuse to cite a number with `row_count == 0` and no source files.** Three lines in
   `build_citation`. This is invariant 7 as written, and it is currently violated on the landing screen.
3. **Move the admission gates before execution, and gate the real SQL** — or delete gates 3 and 5 and
   stop claiming seven. Half-working security controls are worse than absent ones because they're
   budgeted for.
4. **Wire `write_exceptions` and the period-state transitions into the load pipeline.** The safety
   net is built and unplugged.
5. **Make the trial balance a gate**, at load or at statement assembly. Invariant 8 currently has no
   enforcement point anywhere.
6. **Add API-level tests.** One `TestClient` fixture would have caught items 3, 4 and 5 and most of
   what's in REQUEST_TRACE.md.
7. **Cap the upload size.**
