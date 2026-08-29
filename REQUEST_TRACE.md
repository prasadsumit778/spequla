# REQUEST_TRACE.md

Two complete execution paths through SPEQULA, traced call-by-call against the source.
HEAD `d720199`, traced 2026-08-27. Every line number verified against the file as it stands.

Markers used inline:
**⑂ BRANCH** — control flow forks here · **⚠ FAKED** — hardcoded, stubbed or reconstructed value ·
**✗ GAP** — the step the diagram implies does not happen here

---

# Part A — A management question → a cited answer

`POST /ask` with `{"question": "What was our net revenue in April 2026?", "entity_id": 1, "tenant_profile": "manufacturing"}`

## A.1 — HTTP entry and request scoping

| # | Call | File:line | Transforms | Returns |
|---|---|---|---|---|
| 1 | `ask_endpoint` | [src/api/routes/ask.py:43](src/api/routes/ask.py#L43) | HTTP body → `AskRequest` (Pydantic, `tenant_profile` required, never defaulted) | the response dict, eventually |
| 2 | `current_session` | [src/api/deps/auth.py:72](src/api/deps/auth.py#L72) | `Authorization: Bearer <jwt>` → fetches WorkOS JWKS, verifies RS256 signature | `Session(user_id, org_id, role)` from **verified claims only** |
| 3 | `require_role` | [src/api/deps/auth.py:87](src/api/deps/auth.py#L87) | checks `role ∈ {promoter, client_finance_lead, spequla_analyst, admin}` | `Session`, or **403** |
| 4 | `resolve_tenant` | [src/api/deps/tenant.py:27](src/api/deps/tenant.py#L27) | `session.org_id` → `SELECT tenant_id, schema_name FROM app.tenant WHERE workos_organization_id = %s`, then `set_config('app.tenant_id', ...)` on a fresh connection so RLS applies for the request | generator yielding `(conn, tenant_id, schema)` |
| 5 | `load_registry` | [src/config/loader.py:97](src/config/loader.py#L97) | reads `config/decisions.yml`, `config/taxonomy.yml`, `config/metrics/*.yml` from disk | `ConfigRegistry` (83 decisions, 86 classes, 61 contracts) |

**⑂ BRANCH at 3/4:** a missing `org_id` → 403; an org with no linked tenant → 404 naming `scripts/link_tenant_workos_org.py`.

## A.2 — Stage 1: intent classification (the AI Layer)

| # | Call | File:line | Transforms | Returns |
|---|---|---|---|---|
| 6 | `run_ask` | [src/semantic/ask.py:98](src/semantic/ask.py#L98) | stamps `started = now()`; orchestrates all 11 corpus/07 stages | `AskResponse` |
| 7 | `model_client.classify_intent` | [src/semantic/model_client.py:79](src/semantic/model_client.py#L79) | question string → intent | `IntentClassification` |

**⚠ FAKED — and this is where every real request dies.**
[ask.py:46](src/api/routes/ask.py#L46) injects `get_model_client()`, which returns the module-level
singleton `_NO_MODEL_CONFIGURED = StubModelClient({})` built at
[ask.py:27](src/api/routes/ask.py#L27) — **an empty fixture dict**. So at
[model_client.py:80](src/semantic/model_client.py#L80), `question not in self._fixtures` is always
true, and the method returns `intent="unsupported", confidence=0.0`.

## A.3 — The refusal exit that every production request actually takes

| # | Call | File:line | Transforms | Returns |
|---|---|---|---|---|
| 8 | `build_refusal("out_of_scope", ...)` | [src/semantic/refusal.py:?](src/semantic/refusal.py) via [ask.py:104](src/semantic/ask.py#L104) | reason string → structured refusal | `Refusal(refusal_class, reason, nearest_supported_question, clarifying_options)` |
| 9 | `_log` → `_write_query_log` | [ask.py:237](src/semantic/ask.py#L237) → [ask.py:75](src/semantic/ask.py#L75) | `INSERT INTO app.query_log (...)` with `admitted=false`, `rejection_gate='intent_classification'` | `query_log_id` |
| 10 | return | [ask.py:108](src/semantic/ask.py#L108) | — | `AskResponse(status="refused", intent="unsupported")` |
| 11 | `_jsonable_refusal` | [ask.py:74](src/api/routes/ask.py#L74) | `Refusal` → dict | HTTP 200 with `status: "refused"`, `result: null`, `citation: null` |

**⚠ FAKED at [ask.py:105](src/semantic/ask.py#L105):** `nearest_supported_question="What was our
revenue last month?"` is a hardcoded string literal, returned identically no matter what was asked.
corpus/07 §6 requires every refusal to name the nearest supported question; here it names the same
one every time.

**⚠ At [ask.py:244](src/semantic/ask.py#L244):** `except Exception: pass` around the query-log write.
A bare except, contrary to `CLAUDE.md` §8 ("Fail loudly. No bare `except`"). The Ask audit trail can
fail silently and the caller sees a normal response.

**Everything below (A.4 onward) is reachable only from tests, which construct
`StubModelClient({question: (intent, ir_dict)})` with fixtures.** It is fully implemented and
exercised by [tests/fixtures/golden_ir.py](tests/fixtures/golden_ir.py); it has never run against a
real question.

## A.4 — Stages 4–5: IR generation and validation

| # | Call | File:line | Transforms | Returns |
|---|---|---|---|---|
| 12 | `model_client.generate_ir` | [model_client.py:87](src/semantic/model_client.py#L87) | (question, intent) → IR dict | `dict` — from a fixture, or `ModelNotConfigured` |
| 13 | `IRRequest(**ir_dict)` | [src/semantic/ir.py:61](src/semantic/ir.py#L61) | dict → Pydantic model, `extra="forbid"` | `IRRequest` (10 corpus/07 §3 fields) |
| 14 | `validate_ir` | [src/semantic/ir.py:102](src/semantic/ir.py#L102) | checks intent ∈ 12, metric exists in registry, `p0_ask=true`, grain/period/filter coherence — **no DB access** | `None`, or `IRValidationError(field, reason)` |

**⑂ BRANCH ×3:** IR generation raises → `status="error"` ([ask.py:115](src/semantic/ask.py#L115)).
Schema mismatch → `status="rejected"`, gate `ir_schema` ([ask.py:124](src/semantic/ask.py#L124)).
Validation failure → `status="rejected"`, gate `ir_validation` ([ask.py:132](src/semantic/ask.py#L132)).
All three log to `query_log` first. Validation never repairs an IR by guessing — corpus/07 §3.

## A.5 — Stage 6+8: compile *and execute* (note the order)

| # | Call | File:line | Transforms | Returns |
|---|---|---|---|---|
| 15 | `_execute_as_model_reachable` | [ask.py:198](src/semantic/ask.py#L198) | pass-through wrapper | `AskResult` |
| 16 | `compile_and_execute` | [src/semantic/ask_compiler.py:86](src/semantic/ask_compiler.py#L86) | `ir.intent` → handler lookup in `_INTENT_HANDLERS` | dispatch |
| 17 | `_metric_value` | [ask_compiler.py:102](src/semantic/ask_compiler.py#L102) | IR → period key + contract | `AskResult` |
| 18 | `_representative_gl_class_sql` | [ask_compiler.py:67](src/semantic/ask_compiler.py#L67) | formula + taxonomy → **a SQL string that is never executed** | `(sql_text, tables_referenced)` |
| 19 | `compile_metric` | [src/semantic/compiler.py:194](src/semantic/compiler.py#L194) | (metric, period) → value | `CompiledMetric` |
| 20 | `transitive_blocking_decisions` | [compiler.py:117](src/semantic/compiler.py#L117) | walks `dependencies` recursively against open decisions | list of blocking decision ids |
| 21 | `resolve_parameters` | [src/semantic/overrides.py:46](src/semantic/overrides.py#L46) | `entity_override → company_override → global_default` from `metric_definition` | `ResolvedParameters(source, parameters, definition_version)` |
| 22 | `resolve_mapping_version_for_period` | [src/reports/query.py:24](src/reports/query.py#L24) | period_end → `SELECT ... WHERE status='approved' AND effective_from <= %s AND effective_to > %s` | `mapping_version_id`, or `NoApprovedMappingError` |
| 23 | `find_gl_class_patterns` / `match_gl_classes` | [src/semantic/formula.py](src/semantic/formula.py) | `gl_class(...)` formula → concrete class list | `list[str]` |
| 24 | **`_fetch_leaf_amounts`** | [compiler.py:147](src/semantic/compiler.py#L147) | **the real query fires here** — two `SELECT`s joining `fact_gl_entry → dim_account → map_account`, filtered on `is_current` | `(amounts, row_count, load_run_ids)` |
| 25 | `eval_gl_class_formula` | [formula.py](src/semantic/formula.py) | `{class: Decimal}` + formula → one Decimal | `Decimal` |

**⚠ FAKED at step 18.** `sql_text` is a *reconstruction*. Its own docstring says it "mirrors
`_fetch_leaf_amounts`'s query shape exactly, so what the gates see is what would really run." The
gates in A.6 inspect this reconstruction — **not the statement that step 24 actually sent to
Postgres.** Any divergence between the two is invisible to admission control by construction.

**⑂ BRANCH at 20:** decision-gated → `CompiledMetric.status='blocked'` with `blocking_decisions`
populated, returns at [compiler.py:244](src/semantic/compiler.py#L244). With 16 decisions currently
open, `net_revenue` takes this branch today.
**⑂ BRANCH at 22:** no approved mapping → `status` stays default, `reason` set, returns at
[compiler.py:273](src/semantic/compiler.py#L273).
**⑂ BRANCH at 19 for derived metrics:** [compiler.py:305](src/semantic/compiler.py#L305) recurses
per dependency through a shared `_cache`; any unusable dependency propagates
`blocked`/`undefined` upward ([compiler.py:309-315](src/semantic/compiler.py#L309)).
**⚠ Special-cased at [compiler.py:337-353](src/semantic/compiler.py#L337):** `dso`, `dpo` and `dio`
have their formulas **rewritten in Python** rather than read from the contract, and their
denominators swapped for `_trailing_twelve_months_value`. Three metrics whose arithmetic lives in
the compiler, not the registry — the one place `CLAUDE.md` invariant 2 is bent.

## A.6 — Stages 7+9: admission gates and sanity check (running *after* execution)

| # | Call | File:line | Transforms | Returns |
|---|---|---|---|---|
| 26 | `_sanity_check` | [ask.py:62](src/semantic/ask.py#L62) | checks NaN, bridge components summing to total | `str | None` |
| 27 | `run_admission_gates` | [src/semantic/admission.py:123](src/semantic/admission.py#L123) | seven gates over `sql_text` | `AdmissionResult` |
| 27.1 | `gate_1_parse` | [admission.py:53](src/semantic/admission.py#L53) | `sqlparse` — one statement only | — |
| 27.2 | `gate_2_read_only` | [admission.py:63](src/semantic/admission.py#L63) | regex for DDL/DML keywords | — |
| 27.3 | `gate_3_table_allowlist` | [admission.py:69](src/semantic/admission.py#L69) | `tables_referenced` ⊆ `CANONICAL_TABLE_ALLOWLIST` | — |
| 27.4 | `gate_4_tenant_predicate` | [admission.py:76](src/semantic/admission.py#L76) | asserts `tenant_id` appears in the text | — |
| 27.5 | `gate_5_pii_exclusion` | [admission.py:83](src/semantic/admission.py#L83) | blocks `token_map`, PII columns | — |
| 27.6 | `gate_6_cost_estimate` | [admission.py:99](src/semantic/admission.py#L99) | compares model spend to ₹5 cap | — |
| 27.7 | `gate_7_row_cap` | [admission.py:117](src/semantic/admission.py#L117) | appends `LIMIT 10000` if absent | capped SQL |

**✗ GAP — the gates run after the database has already been read.** Execution is
[ask.py:135](src/semantic/ask.py#L135); gates are [ask.py:151](src/semantic/ask.py#L151). A
rejection at 27.3/27.4/27.5 suppresses the *response*, not the *query*. The diagram places this box
between the AI layer and the engine; the code places it after both.

**⚠ FAKED at 27.6:** `run_admission_gates` is called with `estimated_cost_inr` defaulting to `None`
([ask.py:151](src/semantic/ask.py#L151) passes only three args), and
[admission.py:107](src/semantic/admission.py#L107) reads `... and estimated_cost_inr is not None ...`
— so **gate 6 can never reject**. Disclosed in the comment at
[ask.py:143-150](src/semantic/ask.py#L143).

**✗ GAP at 27.7:** `run_admission_gates` returns `AdmissionResult(admitted=True, sql_text=capped_sql)`
at [admission.py:141](src/semantic/admission.py#L141). The caller at
[ask.py:152](src/semantic/ask.py#L152) reads only `.admitted` and `.gate` — **`sql_text` is
discarded.** The 10,000-row cap is computed and thrown away, and the query it would have capped ran
25 steps ago anyway.

**✗ GAP at 15:** `_execute_as_model_reachable` does **not** `SET ROLE model_reachable`. Its docstring
([ask.py:199-226](src/semantic/ask.py#L199)) explains why honestly — the migrations `REVOKE`
`map_account` from that role, so `SET ROLE` would break every query. Consequence: gates 2 and 5 are
regex over a string, not Postgres grants.

**⑂ BRANCH:** `admitted=false` → log with the gate name, return `status="rejected"`
([ask.py:155](src/semantic/ask.py#L155)).
**⑂ BRANCH ×3 at [ask.py:159/166/173](src/semantic/ask.py#L159):** `blocked` → refusal naming the
decisions; `unavailable` → `requires_data_not_held`; `error` → passthrough. Each logs first.

## A.7 — Stage 11: citation, and the response

| # | Call | File:line | Transforms | Returns |
|---|---|---|---|---|
| 28 | `resolve_mapping_version_for_period` | [query.py:24](src/reports/query.py#L24) | resolved a second time, for the citation | `mapping_version_id` |
| 29 | `build_citation` | [src/semantic/citation.py:93](src/semantic/citation.py#L93) | `CompiledMetric` → citation | `Citation` |
| 30 | `compute_query_hash` | [citation.py:54](src/semantic/citation.py#L54) | sha256 of `tenant\|metric\|entity\|period\|mapping_version\|snapshot` → 6 hex chars | `str` |
| 31 | `fetch_source_files` | [citation.py:64](src/semantic/citation.py#L64) | `load_run_ids` → `SELECT DISTINCT file_name FROM app.source_file` | `list[str]` — **the source-row resolution** |
| 32 | `fetch_unmapped_value_inr` | [citation.py:79](src/semantic/citation.py#L79) | `SUM(period_value_inr) WHERE canonical_class='suspense.unmapped'` | `Decimal` |
| 33 | `_log` | [ask.py:190](src/semantic/ask.py#L190) | final `query_log` row with `query_hash` and `row_count` | — |
| 34 | `_jsonable_result` + return | [ask.py:54](src/api/routes/ask.py#L54), [:81](src/api/routes/ask.py#L81) | Decimals → strings | HTTP 200 with `status`, `ir`, `result`, `citation` |

**⚠ FAKED at [ask.py:184](src/semantic/ask.py#L184):** `build_citation(..., "reconciled")` — the
`reconciliation_status` field is a **hardcoded string literal**. The citation asserts the period is
reconciled without reading `period_lock` at all. Compare
[overview.py:47](src/api/routes/overview.py#L47), which passes a computed value down from its
caller. On the Ask path, a period that has never been reconciled still returns
`reconciliation_status: "reconciled"`.

**⚠ FAKED at [citation.py:107](src/semantic/citation.py#L107):** `basis="accrual"` is hardcoded,
ignoring `IRRequest.basis` — which the IR schema defines as `Literal["accrual","cash"]`
([ir.py:78](src/semantic/ir.py#L78)). A cash-basis question would be answered on accrual and cited
as accrual.

**⚠ Dead link at [citation.py:111](src/semantic/citation.py#L111):** `drill_url=f"/query/{hash}/rows"`
points at a route that does not exist — no `/query/` handler anywhere in `src/api/routes/`. To its
credit the UI discloses this rather than hiding it: [Citation.tsx:114](web/components/app/Citation.tsx#L114)
renders the URL alongside the words "is specified in corpus/07 but is not built."

**✗ GAP — stage 11's narration never runs.** `ModelClient.narrate` has **zero call sites** in `src/`.
The pipeline returns numbers plus a citation; no prose is generated on any path.

---

# Part B — A file lands → canonical facts

`POST /upload` with `template_type=GL`, a CSV/XLSX body.

## B.1 — HTTP entry

| # | Call | File:line | Transforms | Returns |
|---|---|---|---|---|
| 1 | `upload_file` | [src/api/routes/upload.py:36](src/api/routes/upload.py#L36) | multipart form → `template_type`, `entity_id`, `UploadFile` | response dict |
| 2 | `require_upload_role` | [auth.py:97](src/api/deps/auth.py#L97) | role ∈ `{spequla_analyst, client_finance_lead}` | `Session`, or **403** |
| 3 | `resolve_tenant` | [tenant.py:27](src/api/deps/tenant.py#L27) | as A.1 step 4 | `(conn, tenant_id, schema)` |
| 4 | validate template | [upload.py:47](src/api/routes/upload.py#L47) | `template_type ∈ {COA,TB,GL,Bank,ConsumerSales,MFGProduction,StoreMaster}` | **400** if not |
| 5 | `await file.read()` | [upload.py:50](src/api/routes/upload.py#L50) | stream → `bytes` (whole file in memory) | `raw_bytes` |
| 6 | dispatch | [upload.py:58-71](src/api/routes/upload.py#L58) | 7-way `if/elif` on `template_type` | one of seven loaders |

**⑂ BRANCH at 6:** an `if/elif` chain, not a registry — `TEMPLATE_TYPES` and the dispatch are two
lists that must be kept in sync by hand.

## B.2 — The load pipeline (`load_gl_file`)

| # | Call | File:line | Transforms | Returns |
|---|---|---|---|---|
| 7 | `load_gl_file` | [src/ingest/load_pipeline.py:97](src/ingest/load_pipeline.py#L97) | orchestrates the whole load | `LoadResult` |
| 8 | `_create_load_run` | [load_pipeline.py:58](src/ingest/load_pipeline.py#L58) | `INSERT INTO app.load_run (... status='running')` | `load_run_id` — **the "every load logged" half** |
| 9 | `stage_gl` | [src/ingest/staging.py:141](src/ingest/staging.py#L141) | raw bytes → typed rows | `StagingResult(valid_rows, quarantined, schema_hash)` |
| 10 | `_read_tabular` | [staging.py:56](src/ingest/staging.py#L56) | CSV or XLSX → `(header, list[dict])`; XLSX via [xlsx.py](src/ingest/xlsx.py) | strings, verbatim, uncoerced |
| 11 | `schema_hash(header)` | [src/ingest/landing.py:47](src/ingest/landing.py#L47) | header row → sha256 | `bytes` |
| 12 | per-row validation | [staging.py:153-207](src/ingest/staging.py#L153) | 6 quarantine rules, then `amount_base = debit if debit>0 else -credit` (Dr+/Cr−, corpus/03 §1) | appends to `valid_rows` or `quarantined` |
| 13 | `compute_row_hash` | [src/ingest/hashing.py:57](src/ingest/hashing.py#L57) | 12 business columns joined by `\x1f` → sha256; **excludes** all lineage columns | `bytes` |
| 14 | in-file dedup | [staging.py:202](src/ingest/staging.py#L202) | `(voucher_no, line_no, row_hash)` seen-set | duplicates → quarantined |

**✗ GAP at 12/14 — "quarantined" does not persist.** `QuarantinedRow`
([staging.py:35](src/ingest/staging.py#L35)) is built with its index, the original row and a reason,
then at [load_pipeline.py:120](src/ingest/load_pipeline.py#L120) only `len()` is taken. There is no
quarantine table in `db/migrations/` — the rejected rows are garbage-collected when the request
ends. The analyst learns a count and nothing else.

**⚠ FAKED at [staging.py:186-191](src/ingest/staging.py#L186):** four constants are stamped onto
every GL row — `currency_code="INR"`, `fx_rate=Decimal("1")`, `amount_txn = amount_base`,
`is_opening_balance=False` — because corpus/01's GL template carries no currency field. The
`fx_rate_source` column is set to a sentence explaining this, which is at least honest, but
`amount_txn` and `amount_base` are the same number for every row in the system.
**⚠ At [staging.py:161](src/ingest/staging.py#L161):** `entry_date = _parse_date(...) or voucher_date`
— when the source omits entry_date, knowledge-time is silently set equal to event-time, collapsing
one axis of the bitemporal model for those rows.

## B.3 — Validation gate: schema drift

| # | Call | File:line | Transforms | Returns |
|---|---|---|---|---|
| 15 | `_last_schema_hash` | [load_pipeline.py:74](src/ingest/load_pipeline.py#L74) | `SELECT schema_hash FROM app.source_file WHERE template_type='GL' ORDER BY ... LIMIT 1` | `bytes | None` |
| 16 | compare | [load_pipeline.py:106](src/ingest/load_pipeline.py#L106) | mismatch → `status="blocked"` | early return |

**⑂ BRANCH — and it returns before landing.** [load_pipeline.py:112](src/ingest/load_pipeline.py#L112)
calls `_finish_load_run(..., "failed")` and returns at line 113 — **`land_file` is never reached.**
A file rejected for schema drift has its `load_run` logged but **its bytes are never stored**. The
diagram's "files stored immutably" holds for accepted files only; the one file an analyst most needs
to inspect is the one not kept.

**✗ GAP — coverage is 4 of 7 templates.** `_last_schema_hash` is called at
[:105](src/ingest/load_pipeline.py#L105) (GL), [:194](src/ingest/load_pipeline.py#L194) (Bank),
[:231](src/ingest/load_pipeline.py#L231) (ConsumerSales), [:295](src/ingest/load_pipeline.py#L295)
(MFGProduction). **COA, TB and StoreMaster have no drift check** — a changed header is accepted
silently.

## B.4 — Immutable landing

| # | Call | File:line | Transforms | Returns |
|---|---|---|---|---|
| 17 | `compute_content_hash` | [hashing.py](src/ingest/hashing.py) | whole file → sha256 | `bytes` |
| 18 | `land_file` | [src/ingest/landing.py:54](src/ingest/landing.py#L54) | `boto3.put_object` to `{tenant_id}/{load_run_id}/{file_name}` — tenant id as first path segment, corpus/04 §6 | `storage_path` |
| 19 | `_record_source_file` | [load_pipeline.py:85](src/ingest/load_pipeline.py#L85) | `INSERT INTO app.source_file (content_hash, schema_hash, storage_path, row_count, ...)` | — |

## B.5 — Canonical write (close-not-update)

| # | Call | File:line | Transforms | Returns |
|---|---|---|---|---|
| 20 | `write_gl_rows` | [src/ingest/canonical.py:218](src/ingest/canonical.py#L218) | staged rows → bitemporal facts | `CanonicalWriteResult(inserted, closed_and_reinserted, unchanged)` |
| 21 | `get_placeholder_mapping_version` | [canonical.py:198](src/ingest/canonical.py#L198) | `SELECT ... WHERE version_no = 0` | the seeded placeholder id |
| 22 | `resolve_account_keys_batch` | [canonical.py:81](src/ingest/canonical.py#L81) | thousands of `(code, name)` pairs → hundreds of distinct accounts; one `SELECT ... = ANY(...)` + one chunked `INSERT ... RETURNING` | `{source_record_id: account_key}` |
| 23 | `tokenise_batch` | [src/ingest/tokenise.py](src/ingest/tokenise.py) | every `party_name` → row in `app.token_map` | — |
| 24 | existing-fact lookup | [canonical.py:254](src/ingest/canonical.py#L254) | `SELECT source_record_id, fact_id, row_hash ... WHERE is_current AND source_record_id = ANY(%s)` | `{sr: (fact_id, row_hash)}` |
| 25 | three-way diff | [canonical.py:263-273](src/ingest/canonical.py#L263) | hash match → `unchanged`; hash differs → `to_close` + `to_insert`; absent → `to_insert` | the **idempotency guarantee** |
| 26 | close prior rows | [canonical.py:276](src/ingest/canonical.py#L276) | `UPDATE ... SET valid_to = now(), is_current = false WHERE fact_id = ANY(%s)` | — |
| 27 | chunked insert | [canonical.py:282-303](src/ingest/canonical.py#L282) | 22 columns × N rows, chunked under the 65,535 bind-param ceiling ([canonical.py:39](src/ingest/canonical.py#L39)) | new `fact_gl_entry` rows |

Step 26 is the only `UPDATE` on a fact table in the system, and it writes lineage columns only —
never business content. `CLAUDE.md` invariant 4 holds.

**⚠ FAKED at 21/27.** Every fact row is stamped with the **version-0 placeholder**
`mapping_version_id`, not a real mapping. [query.py:9-12](src/reports/query.py#L9) confirms
statement assembly deliberately ignores that column and re-resolves the effective version per
period. So `fact_gl_entry.mapping_version_id` is NOT NULL, populated on every row, and read by
nothing.

**✗ GAP at 23.** `tokenise_batch` writes `token_map` entries but the resulting token is **never
attached to the fact row** — `fact_gl_entry.customer_key`/`vendor_key` stay null because
`dim_customer`/`dim_vendor` do not exist. Disclosed in
[tokenise.py:9-18](src/ingest/tokenise.py#L9). Party names are tokenised into a table nothing joins.

## B.6 — Trial balance: computed after the write, and not a gate

| # | Call | File:line | Transforms | Returns |
|---|---|---|---|---|
| 28 | derive periods | [load_pipeline.py:126](src/ingest/load_pipeline.py#L126) | `{YYYY-MM}` set from `voucher_date` | `list[str]` |
| 29 | `check_trial_balance` | [src/quality/trial_balance.py:56](src/quality/trial_balance.py#L56) | `SUM(amount_base)` per period over current rows | `TrialBalanceCheckResult(balanced, total, top_contributors)` |
| 30 | `_finish_load_run` | [load_pipeline.py:68](src/ingest/load_pipeline.py#L68) | `UPDATE app.load_run SET status='succeeded'` | — |
| 31 | `conn.commit()` | [upload.py:75](src/api/routes/upload.py#L75) | — | transaction durable |
| 32 | return | [upload.py:80](src/api/routes/upload.py#L80) | `LoadResult` → JSON incl. per-period `balanced` flags | HTTP 200 |

**✗ GAP — the trial balance does not block anything.** Step 29 runs at
[load_pipeline.py:129](src/ingest/load_pipeline.py#L129), *after* the facts are written at step 27.
[load_pipeline.py:131](src/ingest/load_pipeline.py#L131) then sets `result.status = "succeeded"`
**unconditionally** — `balanced` is never read. `upload.py` commits at line 75 and only checks
`status == "blocked"` at line 77, which only the schema-hash branch ever sets. **An out-of-balance
month is written, committed and reported as a successful load.**

**✗ GAP — invariant 8 has no enforcement point downstream either.** `check_trial_balance` has
exactly one caller in the entire codebase: this line. `grep trial_balance src/reports/ src/api/routes/`
returns only `upload.py`'s response key. `CLAUDE.md` invariant 8 says "a period that does not balance
does not produce a statement" — nothing at `/statements/pnl`
([statements.py:23](src/api/routes/statements.py#L23)) or in `generate_pack` checks it.
(Invariant 9's sibling gate *is* enforced: [statements.py:66](src/api/routes/statements.py#L66)
raises 422 on a non-balancing balance sheet.)

## B.7 — The three diagram steps that are not in this path at all

**✗ Reconciliation.** The diagram places "Data Quality & Reconciliation" between validation and
mapping. `run_books_to_bank` ([books_to_bank.py:124](src/quality/books_to_bank.py#L124)) has **zero
callers in `src/`** — not in the load pipeline, not behind any route. Nothing reconciles during or
after an ingestion run.

**✗ The check catalogue.** `write_exceptions` ([checks.py:63](src/quality/checks.py#L63)) has **zero
callers in `src/`**. The 11 check functions never fire on a real load; the `exception` table is
never written. The upload response's only quality signal is the TB flag from step 29.

**✗ Mapping is not part of ingestion.** The diagram draws Ledger Mapping inside the ingest chain.
In code it is a separate, manually-triggered request — `POST /mapping/runs`
([mapping.py:36](src/api/routes/mapping.py#L36)) → `create_draft_version`
([review.py:40](src/mapping/review.py#L40)) → `run_mapping_pass`
([review.py:89](src/mapping/review.py#L89)) → `extract_coa` → `propose_mappings` →
`evaluate_auto_accept` ([engine.py:98](src/mapping/engine.py#L98)) → then a second request,
`POST /mapping/runs/{id}/freeze` → `freeze_mapping_version`
([review.py:185](src/mapping/review.py#L185)), which enforces the three-condition gate: no
unassigned ledgers, no unapproved rows, coverage ≥ 98%.

**⚠ FAKED — "client approves" is one parameter.** At
[mapping.py:45](src/api/routes/mapping.py#L45), `run_mapping_pass(..., session.user_id)` passes the
caller as `human_approver`. At [review.py:118-123](src/mapping/review.py#L118), every judgement-class
proposal — the six classes invariant 12 forbids auto-accepting — is written with
`approved_by=human_approver` **in the same request that triggered the run**. No human ever sees the
row. The `human_approved` counter records approvals that happened at machine speed. The module
docstring states this plainly: "There is no live human in this build, so 'review' is simulated."
Invariant 12's letter holds (auto-accept did not fire); its intent does not.

---

## Summary: where each path is load-bearing vs. theatre

| | Ask path | Ingest path |
|---|---|---|
| **Real and exercised in production** | auth → tenant → RLS scoping; refusal; `query_log` | auth → tenant; staging + typing; schema-drift block (4/7); immutable landing; bitemporal close-not-update; batch account resolution |
| **Real but reachable only from tests** | steps 12–34: IR validation, compiler, dependency gating, override chain, admission gates, citation | the check catalogue; books-to-bank; period state transitions |
| **Faked / hardcoded** | empty stub client; fixed `nearest_supported_question`; reconstructed `sql_text`; `reconciliation_status="reconciled"`; `basis="accrual"`; unreachable `drill_url`; gate 6 always passes; gate 7's output discarded | `currency_code`/`fx_rate`/`amount_txn`/`is_opening_balance`; placeholder `mapping_version_id`; `entry_date` fallback; `approved_by` set without review |
| **Absent from the path the diagram draws** | narration; `SET ROLE model_reachable`; gates before execution | reconciliation; exception writing; mapping; quarantine persistence; TB as a gate |

The single most consequential ordering bug in each path is the same shape: **a check that exists,
is correct, and runs after the thing it is supposed to prevent.** Admission gates inspect a
reconstruction of a query that already ran; the trial balance evaluates facts that are already
committed.
