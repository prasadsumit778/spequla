# DIAGRAM_SPEC.md

Verbatim transcription of the source diagram **"SPEQULA System Architecture"**.
Transcription only — no assessment of whether any element is implemented.
Stable IDs are assigned in this document so later phases can reference elements unambiguously.

**Canvas title:** `SPEQULA System Architecture` (top left)

---

## 1. Boxes

### Column 1 — Source

**`B1` COMPANY SYSTEMS**
- Accounting / ERP
- Bank statements
- Marketplace & POS
- Payroll & production
- *exports & file drops* — italic, grey

### Column 2 — Intake chain (top to bottom)

**`B2` Secure Data Ingestion**
- Files stored immutably; every load logged

**`B3` Validation gates**
- Duplicates blocked
- Broken cells quarantined
- Format changes caught

**`B4` Data Quality & Reconciliation** — lavender fill, lavender border
- Deterministic checks
- AI-assisted investigation

**`B5` Ledger mapping**
- Client accounts mapped to a standard structure · versioned
- 👤 **client approves** — person icon, bold blue text

### Column 3 — Model

**`B6` ONE GOVERNED COMPANY MODEL** — large pale-blue container, blue border

Contains four white sub-boxes, stacked top to bottom:

| ID | Label |
|---|---|
| `B6.1` | Financial facts |
| `B6.2` | Operating facts |
| `B6.3` | Metric definitions |
| `B6.4` | Full history & audit trail |

Footer caption inside `B6`, italic blue, two lines:
> *Every number traceable*
> *to its source file*

**`B7` SEMANTIC / METRIC LAYER** — pale-blue container, blue border

Bulleted list, laid out in two columns:

| Left column | Right column |
|---|---|
| • Definitions | • Company overrides |
| • Dimensions | • Versioning |
| • Business rules | |

### Column 4 — Question path (top to bottom)

**`B8` Management asks a question** — dark navy rounded pill, white bold text

**`B9` AI LAYER** — lavender fill, lavender border
- *reads the question* — italic
- Query plans · drafts commentary

**`B10` ADMISSION GATES: 7 CHECKS** — pale-yellow fill, amber border, dark-amber bold heading
- out-of-scope refused, never guessed

**`B11` DETERMINISTIC ENGINE** — white fill, heavy black border
- Statements · variance bridges · citations

Contains two grey sub-boxes:

**`B11.1` Metric registry**
> Expert-defined KPIs and industry benchmarks. The company measured against what works in its industry. Connected to Tracxn for competitor benchmarking.

**`B11.2` Forecast & scenario engine**
> Deterministic model templates; AI explains margin & performance shifts vs expert inputs, each quarter

Contains one badge:

**`B11.3` DOMAIN INTELLIGENCE LAYER** — solid blue pill, white bold uppercase text, inside `B11.2`

### Column 5 — Outputs

Six boxes, each white with a solid blue vertical bar on the left edge, stacked top to bottom:

| ID | Label | Sub-label |
|---|---|---|
| `B12` | Live dashboards & statements | — |
| `B13` | Answers with citations | — |
| `B14` | Forecasts & scenarios | — |
| `B15` | Board pack | signed by a named person · 👤 person icon (blue, lower-right of box) |
| `B16` | Alerts as they happen | — |
| `B17` | Potential actions | ranked by impact, never prescriptive |

### Full-width footer

**`B18` ALWAYS-ON CONTROLS** — grey dashed border, very pale grey fill, spans the lower width of the canvas
- Books must balance · Bank reconciliation · Exception queue ranked by ₹ at stake · Role-based access · Immutable audit log

---

## 2. Free-standing annotations (not boxes)

| ID | Text | Placement | Style |
|---|---|---|---|
| `A1` | Bad files quarantined & re-pulled automatically | Left margin, below `B1`, two lines | Italic grey |
| `A2` | blocking issues halt sign-off | Right edge, rotated 90° (reads bottom-to-top) | Italic grey |

---

## 3. Arrows

### 3.1 Solid arrows

| # | Arrow | Notes |
|---|---|---|
| 1 | `B1` COMPANY SYSTEMS → `B2` Secure Data Ingestion | Short horizontal, left to right |
| 2 | `B2` Secure Data Ingestion → `B3` Validation gates | Vertical, downward |
| 3 | `B3` Validation gates → `B4` Data Quality & Reconciliation | Vertical, downward |
| 4 | `B4` Data Quality & Reconciliation → `B5` Ledger mapping | Vertical, downward |
| 5 | `B5` Ledger mapping → `B6` ONE GOVERNED COMPANY MODEL | Elbow: right from `B5`'s right edge, up, then right into `B6`'s left edge |
| 6 | `B6` ONE GOVERNED COMPANY MODEL → `B9` AI LAYER | Elbow: right from `B6`'s upper-right edge, then right into `B9`'s left edge |
| 7 | `B6` ONE GOVERNED COMPANY MODEL → `B7` SEMANTIC / METRIC LAYER | Vertical, downward |
| 8 | `B7` SEMANTIC / METRIC LAYER → `B11` DETERMINISTIC ENGINE | Elbow: right from `B7`'s right edge, up, then right into `B11`'s left edge |
| 9 | `B8` Management asks a question → `B9` AI LAYER | Vertical, downward. **Blue stroke** (the only coloured arrow on the canvas) |
| 10 | `B9` AI LAYER → `B10` ADMISSION GATES: 7 CHECKS | Vertical, downward |
| 11 | `B10` ADMISSION GATES: 7 CHECKS → `B11` DETERMINISTIC ENGINE | Vertical, downward |
| 12 | `B11` DETERMINISTIC ENGINE → `B12` Live dashboards & statements | Fan arrow |
| 13 | `B11` DETERMINISTIC ENGINE → `B13` Answers with citations | Fan arrow |
| 14 | `B11` DETERMINISTIC ENGINE → `B14` Forecasts & scenarios | Fan arrow |
| 15 | `B11` DETERMINISTIC ENGINE → `B15` Board pack | Fan arrow |
| 16 | `B11` DETERMINISTIC ENGINE → `B16` Alerts as they happen | Fan arrow |
| 17 | `B11` DETERMINISTIC ENGINE → `B17` Potential actions | Fan arrow |

Arrows 12–17 originate from a single convergence point on the right edge of `B11` and fan outward to
the six output boxes.

### 3.2 Dashed arrows

| # | Arrow | Notes |
|---|---|---|
| 18 | `B2` Secure Data Ingestion → `B1` COMPANY SYSTEMS | Dashed. Runs down the left margin between `B1` and the intake chain; arrowhead at the top, pointing toward `B2`/`B1`. Annotated by `A1` "Bad files quarantined & re-pulled automatically" |
| 19 | `B5` Ledger mapping → `B18` ALWAYS-ON CONTROLS | Dashed vertical, downward from below `B5` to the top edge of `B18`. No arrowhead rendered |
| 20 | `B15` Board pack → `B18` ALWAYS-ON CONTROLS | Dashed. Elbow: right from `B15`, down the right margin, then left into `B18`'s right edge. **Arrowhead at the `B18` end, pointing left.** Annotated by `A2` "blocking issues halt sign-off" |

---

## 4. Linear reading of the flow as drawn

```
B1 → B2 → B3 → B4 → B5 → B6 → B9 → B10 → B11 → {B12, B13, B14, B15, B16, B17}
                          B6 → B7 → B11
                          B8 → B9
             (dashed)  B2 → B1
             (dashed)  B5 → B18
             (dashed)  B15 → B18
```

---

## 5. Visual encoding used in the source

| Style | Applied to |
|---|---|
| Dark navy pill, white text | `B8` |
| Lavender fill + lavender border | `B4`, `B9` |
| Pale-yellow fill + amber border | `B10` |
| Heavy black border, white fill | `B11` |
| Pale-blue fill + blue border | `B6`, `B7` |
| White fill + light grey border | `B1`, `B2`, `B3`, `B5`, `B6.1`–`B6.4` |
| Grey fill, no border | `B11.1`, `B11.2` |
| Solid blue pill, white uppercase text | `B11.3` |
| White fill + blue left bar | `B12`–`B17` |
| Grey dashed border, pale grey fill | `B18` |
| Italic grey text | `A1`, `A2`, "exports & file drops" |
| Italic blue text | `B6` footer caption, "reads the question" in `B9` |
| Blue bold text + person icon | "client approves" in `B5` |
| Blue person icon | `B15` |

---

## 6. Element index

| ID | Element |
|---|---|
| `B1` | COMPANY SYSTEMS |
| `B2` | Secure Data Ingestion |
| `B3` | Validation gates |
| `B4` | Data Quality & Reconciliation |
| `B5` | Ledger mapping |
| `B6` | ONE GOVERNED COMPANY MODEL |
| `B6.1` | Financial facts |
| `B6.2` | Operating facts |
| `B6.3` | Metric definitions |
| `B6.4` | Full history & audit trail |
| `B7` | SEMANTIC / METRIC LAYER |
| `B8` | Management asks a question |
| `B9` | AI LAYER |
| `B10` | ADMISSION GATES: 7 CHECKS |
| `B11` | DETERMINISTIC ENGINE |
| `B11.1` | Metric registry |
| `B11.2` | Forecast & scenario engine |
| `B11.3` | DOMAIN INTELLIGENCE LAYER |
| `B12` | Live dashboards & statements |
| `B13` | Answers with citations |
| `B14` | Forecasts & scenarios |
| `B15` | Board pack |
| `B16` | Alerts as they happen |
| `B17` | Potential actions |
| `B18` | ALWAYS-ON CONTROLS |
| `A1` | "Bad files quarantined & re-pulled automatically" |
| `A2` | "blocking issues halt sign-off" |

**Totals:** 18 top-level boxes · 7 nested sub-elements · 2 free-standing annotations ·
20 arrows (17 solid, 3 dashed).
