# SPEQULA EVALUATION FRAMEWORK

**File 11 of 12. Status: draft 1.**
Implements: architecture document section 29, plus the synthetic reference dataset you approved.
Companion: `10_SPEQULA_GOLDEN_QUESTIONS.csv`.

---

## 1. Why this is built during pilot one, not after pilot five

Without an eval harness you will not know when a prompt change, a model version change or a mapping edit broke something. In a product where the failure mode is a plausible wrong number rather than an error message, "we would have noticed" is not true. Nobody notices a revenue figure that is 4 percent low.

The harness is cheap to build alongside the first pilot and expensive to retrofit, because retrofitting means reconstructing the expected answers for every question after the data has already moved.

---

## 2. The synthetic reference dataset

You have no real data and will not have it for several weeks. Building against nothing produces untested code and an eval suite with an empty expected-answer column. The fix is a synthetic company built to be realistic in exactly the ways that matter.

**Everything in it is invented. It is labelled synthetic in every file, every table and every screen it appears on, and it is never mixed with real tenant data.**

### 2.1 What it contains

| Component | Specification |
|---|---|
| Company | A single-entity Indian manufacturer, fictional, roughly ₹100 Cr revenue |
| Period | 36 months, fiscal April to March |
| Chart of accounts | Around 400 ledgers, with the name conventions that actually occur: free text, inconsistent casing, embedded channel and geography in brackets, abbreviations, a handful of ledgers named things like "Misc 3" |
| Value distribution | Around 40 ledgers carrying the great majority of value, a long tail carrying almost none. This is what makes the value-sorted review queue testable |
| GL | Journal lines that balance exactly, every period |
| Sales | Invoice lines with quantity, rate, discount, tax, credit notes classified as returns and as rate differences |
| Purchases | Bill lines including MSME and non-MSME vendors |
| Bank | Statement lines that reconcile to books with a residual explained by credit period, advances, TDS and unpresented instruments |
| Inventory | Monthly closing positions by item and stock type, including WIP |
| Production | Monthly output, rejection and input consumption, in one consistent unit per family |
| AR and AP | Open item ageing at each month end |

### 2.2 The defects it contains deliberately

A clean synthetic dataset tests nothing. These are seeded on purpose, each mapped to a check in file 09:

| Seeded defect | Tests |
|---|---|
| A backdated journal batch posted into a prior, already-locked month | Bitemporality, restatement path |
| A duplicate voucher run, same content, different ids | Deduplication on `row_hash` |
| One month where the bank file is missing entirely | Completeness blocking, period gating |
| A trial balance that fails to balance in exactly one month | The zero-tolerance blocking check |
| A ledger that appears mid-year carrying large value | Continuity check, value-sorted queue |
| A source file whose column headers change between two months | Schema hash blocking |
| A product family with two units of measure | The D-041 constraint, which must block rather than convert |
| A credit note with no reason code | The returns versus discounts classification exception |
| A margin sign flip on one product in one month | Anomaly surfaced as exception, not as insight |
| Twelve ledgers that fit no canonical class cleanly | Suspense handling |
| A `#DIV/0!` cell in an uploaded spreadsheet | Real MIS files carry live errors. Validity check must quarantine rather than coerce to zero |
| A consumer line with revenue and zero COGS | 100 percent gross margin is correct for a data or insights product and must not raise an anomaly |
| A month where absorption variance masks a real margin fall | The D-017 manufacturing trap |

### 2.3 A second, smaller consumer dataset

Twelve months, multi-channel, with marketplace commission, returns arriving in a later period than the sale, and an order file that does not tie exactly to the books. Purpose: to test that the residual between order file and books is reported rather than resolved, per file 02 section 3.

### 2.4 What the synthetic dataset cannot do

It is generated from my model of what messy Indian accounts look like. It contains the messes I know about. Real data will contain messes I did not think of, and those are the ones that will cost time. The synthetic set is a development and regression tool, not evidence that the product works. **The moment real pilot data arrives, it becomes the primary eval set and the synthetic set drops to regression duty.**

---

## 3. Eval suites

Nine suites. Each states its input, expected output, tolerance and failure condition.

### 3.1 Financial accuracy, GATING

| | |
|---|---|
| Input | The synthetic dataset, and later each pilot's real data |
| Expected | Generated trial balance, P&L, balance sheet and cash flow match the reference set line by line |
| Tolerance | **Exact, to the rupee.** No tolerance |
| Failure | Any line differs. A build with a failing financial accuracy test does not deploy |

For real pilot data, the reference set is the client's own trial balance and the last audited accounts. Every difference is either eliminated or individually explained and logged.

### 3.2 Golden questions, numeric, GATING

| | |
|---|---|
| Input | The 42 gating questions in file 10 |
| Expected | The numeric answer matches the independently computed value |
| Tolerance | Exact for currency and counts. Within one basis point for ratios, to allow for float representation only |
| Failure | Below 42 of 42, Ask does not go live for the client |

**The expected-answer column in file 10 is empty and must stay empty until a human computes it.** Answers generated by the system and then recorded as expected are not a test, they are a snapshot of current behaviour including its bugs.

### 3.3 Refusal and hallucination, GATING

| | |
|---|---|
| Input | The 14 refusal questions in file 10, plus adversarial paraphrases |
| Expected | Refusal, naming the reason, offering the nearest supported question |
| Tolerance | **100 percent** |
| Failure | A single fabricated answer blocks release |

This is the strictest gate in the framework and it should be. A product that refuses too often is annoying. A product that answers a question it cannot answer is not recoverable, because the client stops being able to tell which answers to trust.

### 3.4 Citation, GATING

| | |
|---|---|
| Input | A sample of answers across all intents |
| Expected | Every citation resolves to real source rows, the row count matches, the metric version is correct |
| Tolerance | 100 percent resolution. A number with a non-resolving citation must not have been displayed at all |
| Failure | Any non-resolving citation |

### 3.5 IR parsing

| | |
|---|---|
| Input | Every question in file 10, plus three paraphrases each |
| Expected | Field-level match against the hand-written correct IR |
| Tolerance | Above 95 percent field-level match. Metric and period fields must be 100 percent |
| Failure | Below threshold, or any metric or period error |

Metric and period are held at 100 percent because an error in either produces a correct-looking number for the wrong thing, which is the failure the whole architecture exists to prevent.

### 3.6 SQL compilation

| | |
|---|---|
| Input | Hand-written IR objects with known correct result sets |
| Expected | Result equality |
| Tolerance | **100 percent. It is deterministic** |
| Failure | Any mismatch is a compiler defect, not a tuning problem |

### 3.7 Mapping accuracy

| | |
|---|---|
| Input | Held-out reviewed mappings, initially from the synthetic chart of accounts |
| Expected | The proposal matches the approved class |
| Tolerance | Measured, not targeted, until real mappings exist. **Auto-accept precision must be 100 percent**, because auto-accept fires only on exact rule matches |
| Failure | Any auto-accepted mapping that a human later reverses. That is a rule defect |

Proposal accuracy is a productivity measure, not a correctness gate, because every proposal is reviewed by a person. A model that is right 70 percent of the time still saves most of the review effort. A model that auto-accepts wrongly once has broken the trust model.

### 3.8 Data quality checks

| | |
|---|---|
| Input | The synthetic dataset with its eleven seeded defects |
| Expected | Each defect raises the specific check named in section 2.2, at the correct severity |
| Tolerance | 11 of 11 |
| Failure | Any seeded defect passing undetected |

### 3.9 Reproducibility and determinism

| | |
|---|---|
| Input | A signed pack, re-rendered after a mapping version change and a restatement |
| Expected | Byte-identical output to the original |
| Tolerance | Exact |
| Failure | Any difference |

Plus: the same question asked twice returns identical numbers, and a full pipeline replay from raw produces identical canonical output.

---

## 4. Metrics tracked but not gated

These are read, not enforced. Setting a target on any of them before pilot one would be inventing a number.

| Measure | Why it is tracked |
|---|---|
| **Edits per pack** | The primary commercial metric. If the analyst rewrites half the commentary every month, the leverage story does not hold. Track from pilot one, expect it to fall |
| Insight acceptance rate | P1, when insights exist |
| Chart selection agreement | Rules-based in P0, so this is a rules-coverage measure |
| Answer latency, p50 and p95 | Baseline in pilot one |
| Model cost per answer | Baseline |
| Questions per client per month | The only honest read on whether decision latency actually fell |
| Repeat questions | A question asked again in a later month means the pack is not answering it |
| Forecast MAPE by horizon | P1. Tracked, never targeted |

---

## 5. When each suite runs

| Trigger | Suites |
|---|---|
| Every commit | SQL compilation, IR parsing, unit tests |
| Every pull request | All of the above plus financial accuracy and data quality against the synthetic set |
| Every deploy | Full suite including refusal, citation and reproducibility |
| Every prompt or model version change | Full suite. **A prompt change is a code change** and goes through the same gate |
| Nightly | Full suite plus per-pilot golden questions against real data |
| Every mapping version approval | Financial accuracy plus reproducibility for that tenant |

**Any regression is a build break, not a ticket.** The suite either passes or the change does not ship.

---

## 6. Building the eval set for a new pilot

Six steps, run once per company. Budget roughly a day.

1. Take the 42 gating questions and adapt the wording to the company's own vocabulary. If they say "realisation" and the question says "average price", change the question.
2. Add 10 to 20 questions the promoter actually asked during the sales conversation. These are the highest-value tests you will have, because they are the questions the product exists to answer.
3. **Compute every expected answer by hand, in a spreadsheet, from the source files.** Not from the product. This is the step people skip and it is the step that makes the suite meaningful.
4. Have the client's finance lead check the hand-computed answers. Disagreement here is not a problem to resolve quickly; it is the accounting policy conversation surfacing again, and it belongs in file 00.
5. Load into the harness as that tenant's golden set.
6. Run nightly. A tenant whose pass rate falls has had something break in their configuration, and you should know before they do.

---

## 7. What cannot be evaluated yet, and why

Honesty about the limits of this framework.

| Not evaluable | Reason |
|---|---|
| Whether the commentary is good | Commentary is human-written in P0. Once a model writes it, "edits per pack" is the proxy, and it is a proxy, not a measure of quality |
| Whether an insight is useful | Requires a human judgement per insight. P1, measured as acceptance rate |
| Whether the mapping taxonomy is right | Only real charts of accounts reveal this. Expect revision after company one |
| Forecast accuracy | No forecast, and no data to backtest against |
| Whether the product actually reduced decision latency | The real question, and it is answered by questions asked per month and by whether the pilot converts, not by any test in this file |
| Whether tolerances are correctly set | D-052 and D-053 are unset by design. They come from observing two months of real residuals |

---

## 8. Acceptance criteria for the harness itself

| Criterion | Test |
|---|---|
| The full suite runs in a single command | Manual |
| A failing gating suite blocks deploy automatically | CI configuration test |
| Expected answers are stored separately from system output and cannot be overwritten by a run | Structural |
| Every suite reports which specific case failed, with the IR and the SQL | Manual |
| The synthetic dataset regenerates deterministically from a seed | Structural |
| A prompt change triggers the full suite | CI configuration test |
| Per-tenant golden sets run without cross-tenant data access | Security test |
