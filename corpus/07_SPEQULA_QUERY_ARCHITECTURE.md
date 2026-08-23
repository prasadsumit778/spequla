# SPEQULA QUERY ARCHITECTURE

**File 07 of 12. Status: draft 1.**
Implements: architecture document sections 12 (natural language to answer) and 13 (query safety), narrowed to a fixed intent set.

---

## 1. The one architectural decision that matters

**The model does not write SQL. The model writes a semantic intermediate representation and a deterministic compiler writes the SQL.**

Text-to-SQL against a real warehouse fails invisibly. It picks the wrong join, silently drops rows with a bad filter, or uses a column that looks like revenue and is not. The output is a plausible number, which is the worst possible failure mode in finance, because nothing downstream catches it and the person reading it has no reason to doubt it.

With semantic IR the same failure becomes a rejected parse. The user sees "I could not resolve that to a metric I know" instead of a wrong figure on a board pack.

| | Model writes SQL | Model writes semantic IR |
|---|---|---|
| Failure mode | Wrong number, looks correct | Parse rejected, clear error |
| Join correctness | Inferred every time | Fixed once in the compiler |
| Metric formula | Restated in a prompt, drifts | One versioned definition |
| Testability | Compare SQL strings, brittle | Compare JSON objects, unit testable |
| Company overrides | Prompt engineering | Applied at compile time |
| Debuggability | Read generated SQL | Read a small object |

Free-form SQL exists for internal analysts on a separate, audited path. It is never available to the model, under any circumstance, including for "just this one investigation".

---

## 2. The path from question to answer

Eleven stages in the MVP. Three involve a model.

| # | Stage | Type | Failure handling |
|---|---|---|---|
| 1 | Intent classification | AI, small model | Unknown intent asks a clarifying question |
| 2 | Metric resolution | Deterministic, registry lookup | Ambiguous name offers a choice, never guesses |
| 3 | Time resolution | Deterministic, rules over `dim_date` | "Last quarter" resolves against the Indian FY and says which |
| 4 | Semantic IR generation | AI, constrained decoding into the schema | Invalid IR retried once, then surfaced as unsupported |
| 5 | IR validation | Deterministic, JSON schema plus registry plus permissions | Hard rejection with a readable reason |
| 6 | SQL compilation | Deterministic, template codegen from IR plus metric contract | A compiler bug is a code defect, caught by tests |
| 7 | Admission control | Deterministic, seven gates | Rejected before execution, always logged |
| 8 | Execution | Deterministic, read-only role | Timeout returns a narrower suggestion |
| 9 | Result sanity | Deterministic | Suspicious results shown with a warning, never hidden |
| 10 | Decomposition, where the intent asks why | Deterministic bridges | If components do not sum, stop and say so |
| 11 | Narration and citation | AI for wording, deterministic for citation | Missing citation blocks display |

Stages 1, 4 and 11 are the only ones a model touches. **Nothing that touches a number is a model call.** Stage 11 receives computed numbers as data and is permitted to order words around them, nothing more.

---

## 3. The semantic IR schema

```json
{
  "$schema": "spequla.ir.v1",
  "intent": "metric_breakdown",
  "metric": "gross_margin_pct",
  "metric_version": 1,
  "grain": "month",
  "period": {
    "type": "fiscal_quarter",
    "value": "FY27Q2",
    "resolved_from": "last quarter",
    "resolved_range": ["2026-07-01", "2026-09-30"]
  },
  "compare_to": {
    "type": "prior_period",
    "value": "FY27Q1"
  },
  "breakdown": ["channel", "product_category"],
  "filters": [
    { "dimension": "entity", "op": "eq", "value": "IN-01" },
    { "dimension": "channel", "op": "in", "value": ["retail", "distributor"] }
  ],
  "sort": { "by": "metric", "direction": "desc" },
  "limit": 20,
  "basis": "accrual",
  "as_of": "current"
}
```

Ten fields. Every one is validated against the registry before anything executes.

| Field | Validation |
|---|---|
| `intent` | Member of the closed intent list in section 4 |
| `metric` | Exists in the registry, is Ask-exposed, is approved for this company, and its governing decisions are resolved |
| `grain` | Permitted by the metric's `time_grain` |
| `period` | Resolves against `dim_date`. Fiscal periods only, never calendar quarters unless asked for explicitly |
| `compare_to` | In the metric's `comparisons` list |
| `breakdown` | Every dimension is in the metric's `dimensions` list. A dimension not listed is rejected, not silently dropped |
| `filters` | Dimension exists, operator is in the allowlist, value type matches |
| `basis` | `accrual` or `cash`. Never blended. Stated on every output |
| `as_of` | `current`, or a knowledge-time timestamp for "as reported on" questions |

**Rejection is a first-class outcome.** An IR that fails validation produces a message naming the field and the reason. It is never repaired by guessing, and a failed parse is logged so that repeated failures on the same phrasing surface a registry gap rather than a user problem.

---

## 4. Intents in P0

Twelve. Closed set. A thirteenth requires a code change, a test and a golden question, which is the point.

| Intent | Example | Mechanism |
|---|---|---|
| `metric_value` | "What is our DSO?" | Single metric, single period |
| `metric_trend` | "Show revenue over the last twelve months" | Single metric, series over grain |
| `metric_comparison` | "Revenue this month versus last year" | Metric plus `compare_to` |
| `metric_breakdown` | "Revenue by channel" | Metric plus `breakdown` |
| `metric_ranking` | "Top ten customers by revenue" | Breakdown plus sort plus limit |
| `variance_explain` | "Why did gross margin fall?" | Deterministic decomposition, then narration. See section 5 |
| `statement_view` | "Show me the P&L for Q2" | Statement assembly, not a metric query |
| `concentration` | "How dependent are we on our largest customer?" | Top-N share of total |
| `ageing` | "How much receivable is over ninety days?" | Bucketed open items |
| `definition_lookup` | "How do you calculate DSO for us?" | Registry lookup, returns the resolved contract. No SQL runs |
| `data_health` | "Is June reconciled?" | Reads `period_lock` and `reconciliation_run` |
| `unsupported` | Anything else | Explicit refusal. See section 6 |

---

## 5. variance_explain, and the causal discipline

This is the intent that sells the product and the one most likely to produce a confidently wrong sentence. It is therefore the most constrained.

```
1. Compute the metric for both periods.            DET
2. Compute the delta.                              DET
3. Run the applicable bridge:                      DET
     revenue -> price, volume, mix
     margin  -> input cost, price, mix, other
     ebitda  -> gross profit change, opex lines
4. Check the components sum to the total delta.    DET
5. Rank components by absolute contribution.       DET
6. Narrate, receiving the computed numbers.        AI
```

**Step 4 is the gate.** If the components do not sum to the total movement within a rounding tolerance, the system reports the total movement, reports the components it could compute, and states that the decomposition is incomplete. It does not present a partial decomposition as if it explained the whole change, and it does not put the residual into an "other" bucket and move on.

**Language rules bind the narration**, per file 03 section 9. "Driven by" requires that a decomposition attributes the majority of the movement to that driver. "Coincided with" is the wording when two things moved together and nothing links them. "Will continue" is blocked entirely, because that is a forecast and forecasts are P1 and live in a different object with an error band.

**Price, volume and mix have more than one valid allocation of the interaction term.** The convention is declared once, globally, in file 05. Until it is declared, `variance_explain` on a revenue metric returns the total movement and states that the decomposition is not yet configured.

---

## 6. Refusal

The refusal path is a feature, not an error state, and it carries a hard gate in file 11: 100 percent of unanswerable questions must be refused. A single fabricated answer blocks release.

| Class | Example | Response |
|---|---|---|
| Out of scope in P0 | "What will revenue be next quarter?" | Names forecasting as not yet available, and offers the trend |
| Requires documents | "What does our supply contract say about price escalation?" | States that document analysis is not available |
| Requires data not held | "What is our CAC?" | Names the missing input, which is customer identity across channels |
| Requires a decision not made | "What is our contribution margin?" before D-048 | Names the decision and who must make it |
| Period not reportable | Any metric for an unreconciled or unmapped period | States the reconciliation status and the unmapped rupee value |
| Genuinely unanswerable | "Which of our competitors is growing fastest?" | States that the system only sees this company's data |
| Ambiguous | "How are we doing?" | Asks one clarifying question, offering two or three concrete alternatives |

**Every refusal names the nearest supported question.** A refusal that leaves the user with nothing trains them to stop asking, and question volume is one of the few honest reads on whether decision latency actually fell.

---

## 7. Admission control

Seven deterministic gates between a compiled query and the database. Every rejection is logged with the user, the IR and the reason.

| Gate | Check |
|---|---|
| 1. Parse | Compiles to a valid AST |
| 2. Read-only | No DDL, no DML, no functions that touch the filesystem |
| 3. Table allowlist | Only canonical tables and approved views visible to this role |
| 4. Tenant predicate | Present and correct. Enforced by row-level security at the connection role, not by the query text |
| 5. PII exclusion | No column outside the model-reachable views. `token_map`, `audit_log` and all app tables are not granted |
| 6. Cost estimate | Under the configured cap |
| 7. Row cap | Applied |

Execution runs on a read-only role with a statement timeout and a result cap. Every query is logged to `query_log` with the user, role, IR, SQL text, row count, duration and model version, per file 04.

**The model-reachable role is a database object, not a code path.** It has grants on the canonical schema only. This is why a prompt injection through a ledger name cannot reach customer contact data: the data is not in any table the role can read.

---

## 8. Citation

Every number carries a citation object, and a number without a resolving citation is not displayed. This is the trust mechanism and the reason a promoter believes the second number after checking the first.

```json
{
  "value": 421000000,
  "metric": "net_revenue",
  "metric_version": 1,
  "period": "FY27Q2",
  "basis": "accrual",
  "snapshot_at": "2026-07-08T18:30:00+05:30",
  "reconciliation_status": "reconciled",
  "query_hash": "4a91c2",
  "row_count": 12406,
  "source_facts": ["fact_gl_entry", "fact_invoice_line"],
  "source_files": ["tally_export_2026-07-05.xlsx"],
  "mapping_version": 1,
  "unmapped_value_inr": 2100000,
  "drill_url": "/query/4a91c2/rows"
}
```

Four properties follow from this. Every number is clickable through to the rows that produced it. Every number states which metric version produced it, so a definition change is visible rather than silent. Every number states its reconciliation status, so an unreconciled figure is never mistaken for a settled one. And `snapshot_at` means re-rendering a signed answer six months later reproduces it exactly, including figures that have since been restated.

---

## 9. Model routing

| Task | Model class | Why |
|---|---|---|
| Intent classification, metric name matching | Small | High volume, easy to evaluate, latency matters |
| Semantic IR generation | Strong, constrained decoding | Ambiguity resolution is the hard part of the product |
| Narration | Strong, numbers supplied as data | Tone and precision both matter |
| Anything numeric | None. Deterministic code | A board-pack number does not deserve a bigger model, it deserves no model |

**Escalate on ambiguity, never on importance.** The instinct to route the CFO's question to the strongest model is exactly backwards: importance calls for less model involvement, not more.

The model never sees a real customer, vendor or employee name. Tokens only, per file 02 section 8. Ledger names are the deliberate exception, because they are the entire mapping signal.

---

## 10. What is deliberately not here

| Absent | Reason |
|---|---|
| Free-form SQL for the model | Never, at any maturity |
| Multi-hop investigation loops | The investigation agent is P2. In P0, a follow-up question is a new query |
| Document retrieval in an answer | No document layer in the MVP |
| Forecast and scenario intents | P1. They route to `unsupported` with a clear reason |
| AI chart selection | Fixed rules cover every golden question. A chart the rules cannot handle falls back to a table |
| Conversational memory across sessions | A session-scoped filter only. Financial questions are not conversational in the way chat products assume |
| Free-text "explain the business to me" | No bounded correct answer, therefore no evaluable behaviour, therefore not shipped |

---

## 11. Acceptance criteria

| Criterion | Test |
|---|---|
| No SQL string is ever produced by a model | Code review plus a test asserting the model output schema contains no SQL field |
| Every metric formula lives in the registry, not in code | Grep test: no arithmetic on canonical columns outside the compiler |
| An IR referencing an unknown metric is rejected before execution | Unit test |
| An IR breaking down by a dimension not in the metric contract is rejected | Unit test |
| A query without a tenant predicate cannot execute | Integration test against the read-only role |
| Every displayed number has a citation that resolves to real rows | Sampled test in file 11 |
| 100 percent of the refusal set is refused | Gating eval in file 11 |
| A decomposition whose components do not sum reports the gap | Unit test |
| The same question asked twice returns identical numbers | Determinism test |
