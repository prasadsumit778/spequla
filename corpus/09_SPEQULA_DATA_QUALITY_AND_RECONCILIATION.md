# SPEQULA DATA QUALITY AND RECONCILIATION

**File 09 of 12. Status: draft 1. Every tolerance value is deliberately blank.**
Implements: architecture document section 10, narrowed from eight reconciliation classes to two.

---

## 1. The governing rule

**The system never silently continues when critical data is unreliable.**

This is not a quality aspiration, it is a product decision with a cost. It means periods will fail to produce statements, packs will fail to generate, and a client will occasionally be told "we cannot report July yet" when a competitor's tool would have shown them a number. That is the correct trade. Your architecture document names one bad figure reaching a board pack as one of the three failures that kill the company, and a tool that reports confidently through a gap is worse than no tool, because it removes the client's own instinct to check.

---

## 2. Check catalogue

Eight classes. Severity determines what happens, and the distinction is enforced in code, not left to judgement at runtime.

- **BLOCKING** halts the load or prevents statement assembly. The affected output does not exist.
- **WARNING** badges the number with a reason and lets it through.
- **INFORMATIONAL** appears in the exception queue and nowhere else.

### 2.1 Completeness

| Check | Severity | Action |
|---|---|---|
| A month in the requested range has zero GL rows | BLOCKING | Period not reportable |
| A required stream has not been supplied at all | BLOCKING | Named on the data health screen |
| An account carries value but has no mapping | WARNING below the D-053 threshold, BLOCKING above | Unmapped rupee value displayed |
| A fact row has a null dimension key that the metric requires | WARNING | Metric badged, rows quantified |
| Opening balances missing for the earliest period | BLOCKING | Balance sheet cannot be assembled |

### 2.2 Validity

| Check | Severity | Action |
|---|---|---|
| Date outside the plausible range, or in the future | BLOCKING | Row quarantined |
| Negative quantity where the voucher type does not permit it | WARNING | Row quarantined, quantified |
| Both debit and credit populated on one GL line | BLOCKING | Row quarantined |
| Currency present without a rate, or a rate without a source | BLOCKING | Row quarantined |
| Margin outside a plausible band, for example above 100 percent or below negative 100 percent | WARNING | Surfaced as an exception, never as an insight |
| A UOM appears for a product family that already has a different declared UOM | BLOCKING | Per-unit metrics blocked. Never converted, per D-041 |

### 2.3 Uniqueness

| Check | Severity | Action |
|---|---|---|
| Duplicate voucher number and line within a period | BLOCKING | Deduplicated on `row_hash`, difference logged |
| The same file uploaded twice | INFORMATIONAL | Content hash catches it. Idempotent by design, and a weekly event |
| A repeated settlement or reference id in a bank file | WARNING | Flagged for review |

### 2.4 Consistency

| Check | Severity | Action |
|---|---|---|
| **Trial balance does not balance.** Sum of `amount_base` over the period is not exactly zero | BLOCKING | Statement assembly blocked. Tolerance is zero, per D-051 |
| Control account balance does not match the sum of its subledger | BLOCKING | Which of AR, AP or inventory is named |
| **Balance sheet does not balance** | BLOCKING | Not displayed at all |
| **Cash flow closing cash does not equal balance sheet cash** | BLOCKING | Cash flow not displayed |
| A metric's components do not sum to its stated total | BLOCKING | Decomposition reported as incomplete, per file 07 section 5 |

The four bold checks above catch more mapping errors than every other check combined. The cash flow tie in particular fails whenever a balance sheet movement has been misclassified, which is the most common mapping mistake and the hardest to spot by eye.

### 2.5 Reconciliation

Two checks in P0. Detailed in section 3.

| Check | Severity |
|---|---|
| Trial balance internal tie | BLOCKING, zero tolerance |
| Books to bank, cash movement | Period marked unreconciled above tolerance |

Out of P0: books to GST, GST to bank, marketplace payout to order value, order file to books for consumer brands. The last of these is reported as a residual without explanation, per file 02 section 3.

### 2.6 Continuity

| Check | Severity | Action |
|---|---|---|
| Gap in a voucher number sequence | WARNING | Quantified. Common and often benign, but never ignored |
| A stream that reported last month reports nothing this month | BLOCKING | Connector alarmed |
| Schema hash of a source file changes | BLOCKING | Never auto-adopted. A silent column change corrupts metrics quietly |
| Backdated entry found touching a locked period | INFORMATIONAL, escalating to a restatement event | Per section 5 |

### 2.7 Anomaly

| Check | Severity | Action |
|---|---|---|
| Value outside the trailing distribution for that account | INFORMATIONAL | **Surfaced as an exception, never as an insight** |
| A new account appears carrying large value | WARNING | Queued by rupee value |
| Margin sign flip on a product or channel | WARNING | Queued |

**The distinction between an anomaly and an insight matters.** An anomaly is "this number is unusual and may be wrong." An insight is "this number is correct and here is what it means." Presenting the first as the second is how a data quality problem becomes a business recommendation.

### 2.8 Freshness

| Check | Severity | Action |
|---|---|---|
| Hours since last successful load, per source | Displayed always | Timestamp on every screen and on the pack cover |
| Source stale beyond its declared SLA | WARNING | Badge on every metric drawing on that source |

---

## 3. Reconciliation

### 3.1 Trial balance tie

The simplest and most important check in the system. Sum of `amount_base` across all current rows for a complete period equals exactly zero.

Tolerance is zero. There is no defensible non-zero tolerance for a trial balance, and D-051 records this as settled rather than open. A period that fails does not proceed to statement assembly, and the failure names the accounts contributing the largest imbalance.

### 3.2 Books to bank

Three sources, one honest answer.

```
Books (accrual, net of credit notes)         Bank receipts (cash in, incl. advances)
                    \                       /
                     RECONCILIATION ENGINE
                     rule-based, per period
                              |
       EXPECTED DIFFERENCES, MODELLED NOT TREATED AS ERRORS
       - credit period: invoiced this month, collected next
       - advances received against future orders
       - TDS deducted by the customer
       - gateway or marketplace settlement lag
       - unpresented instruments
       - inter-account and inter-company transfers
       - direct bank charges not yet booked
                              |
        residual within tolerance  ->  period marked reconciled
        residual above tolerance   ->  metrics badged, exception queued
```

**The rule that protects the relationship.** If books say one figure and bank says another, the product states both, explains the modelled portion of the gap, and reports the residual. It never picks one and moves on. Choosing a winner silently is how a tool loses a CFO permanently, because the first time he checks and finds you chose, everything else you have shown him becomes suspect.

**Tolerance is per company and is deliberately unset.** D-052 records this. A 0.4 percent residual is normal for one business and an incident for another, and the honest way to set it is to observe two months of actual residuals for that company and then agree a threshold with the finance lead. Inventing one now would be inventing a number.

---

## 4. The exception queue

A product surface, not a log file. If exceptions live in a spreadsheet the founder maintains, the business does not scale past three customers.

**Ordering.** By severity, then by `value_inr` descending. Always by money, never by count. Twelve unmapped ledgers worth ₹4,000 between them matter less than one worth ₹40 lakh, and a queue sorted by count buries the second behind the first.

**Every exception carries:** class, severity, period, the object it concerns, the rupee exposure, a plain description, a suggested action, and its current status.

**Resolution paths.** Fix at source and reload. Map or reclassify. Accept with a written reason, which is logged and appears in the pack's data quality appendix. Defer, with an owner and a date.

**Nothing is dismissed without a reason.** A one-click dismiss button produces a queue everyone empties and nobody reads.

---

## 5. Period state machine

```
OPEN            data arriving, nothing gated
   |  all blocking checks pass
VALIDATED       structurally sound, mapping not yet frozen
   |  mapping version approved, coverage above threshold
MAPPED          metrics computable, statements assemble
   |  trial balance ties, books to bank within tolerance
RECONCILED      pack may be generated
   |  finance signs off
LOCKED          snapshot_at pinned. Reports render against this snapshot forever
   |  a change arrives touching a locked period
RESTATED        new period_lock row, pointer to the prior one, delta explained
```

**A period never moves backwards silently.** If a locked period becomes unreconciled because new data arrived, that is a restatement event with a reason, an owner and a visible delta, not a status flag quietly flipping. The alarm in file 04 for "a period that was reconciled becoming unreconciled" exists for exactly this.

**Backdated entries are the normal case in Indian accounting, not an exception.** Every load re-pulls a trailing ninety-day window. Anything found with `entry_date > event_date` is a backdated entry, and if it touches a locked period it triggers the restatement path.

---

## 6. The data health screen

Four panels, one page.

| Panel | Contents |
|---|---|
| Freshness | Last successful load per source, with age and SLA status |
| Completeness | Mapped value over total value as a percentage, **and the unmapped amount in rupees** |
| Reconciliation | Per period, per check: reconciled, within tolerance, or breached, with the residual in rupees |
| Exceptions | Open count by severity, total rupee exposure, and the top ten by value |

**The unmapped rupee figure is the single most useful number on the screen.** Percentage complete tells a reviewer nothing about whether to keep going. "₹21 lakh unmapped" tells them exactly.

---

## 7. What is deliberately not checked in P0

| Absent | Reason |
|---|---|
| Books to GST | GST is out of P0 |
| Marketplace payout to order value | Deferred to P1, per file 02 section 3 |
| Statistical anomaly detection beyond a trailing distribution check | Two months of history is not a distribution |
| Inter-company elimination consistency | Multi-entity is out of P0 |
| Cross-source customer identity conflicts | Entity resolution is P1 |

---

## 8. Acceptance criteria

| Criterion | Test |
|---|---|
| A period failing the trial balance tie cannot produce a statement | Integration test |
| A non-balancing balance sheet is not displayed | Integration test |
| Cash flow closing cash equals balance sheet cash, or neither displays | Integration test |
| A blocking exception prevents pack generation without a logged override | Integration test |
| The exception queue sorts by rupee value within severity | UI test |
| Unmapped rupee value appears on the data health screen at all times | UI test |
| The same file uploaded twice creates no duplicate facts | Idempotency test |
| A backdated entry touching a locked period creates a restatement, not an edit | Bitemporal test |
| A schema hash change on a source file blocks the load rather than adapting | Integration test |
| Every reconciliation result records the modelled differences and the residual separately | Structural test |

---

## 9. Open dependencies

| Item | Effect |
|---|---|
| D-052 books-to-bank tolerance | The reconciliation gate has no threshold. Set after two months of observation, per company |
| D-053 unmapped value threshold | The boundary between badging and blocking is undefined |
| D-054 unreconciled pack behaviour | Whether an unreconciled period blocks the pack or ships it badged |
| D-039 period lock owner and day | The state machine has no trigger for the lock transition |
| D-040 restatement notification threshold | Every change is flagged; who gets told is undefined |
| The list of modelled differences per company | Comes from the accounting policy conversation, one company at a time |
