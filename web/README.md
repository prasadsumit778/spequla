# SPEQULA — web

Next.js + TypeScript frontend. See the [repo root README](../README.md) for the full project, corpus, architecture, and local setup instructions (including the WorkOS configuration this frontend needs).

Quick start once `web/.env.local` is filled in:

```
npm install
npm run dev
```

Runs on `http://localhost:3000`, talking to the FastAPI backend at `NEXT_PUBLIC_API_BASE_URL` (defaults to `http://localhost:8000`).

## Screens

Overview, Statements, Operating metrics, Ask, Monthly pack, Upload, Load runs, Mapping review, Data health, Exceptions, Settings. `/` redirects to the overview: corpus/08 section 3 makes it the landing screen, and section 1 makes the numbers the default surface.

Navigation is role-aware per corpus/02 section 2 — a promoter is offered Overview, Ask and the pack, and not the mapping screens or the exception queue. That is presentation only. The backend is the access boundary (`src/api/deps/auth.py`).

## How the frontend is put together

| Path | What lives there |
|---|---|
| `lib/api.ts` | The fetch layer. One function per endpoint. Nothing else calls `fetch` |
| `lib/useApi.ts` | `useApiQuery` / `useApiAction` — the single read and write path, so loading, failure and reload behave identically on every screen |
| `lib/format.ts` | Every figure on screen is formatted here. See below |
| `lib/metricUnits.ts` | `metric_id → unit`, generated from corpus/05's `unit` column |
| `lib/statementLayout.ts` | Statement row order, from corpus/08 sections 4.1, 4.2 and 5 |
| `lib/workspace.tsx` | Entity and profile, chosen once in the top bar instead of on every screen |
| `lib/nav.ts` | The navigation model and its role visibility |
| `components/ui/` | Generic primitives: buttons, cards, badges, tables, fields, loading / empty / error states |
| `components/app/` | SPEQULA-specific pieces: the shell, the state strip, metric tiles, citations, statement tables, chart specs |
| `app/globals.css` | Tailwind v4 and the design tokens. Colour, type and spacing are defined only here |

### Figures

**Nothing formats money inline.** `lib/format.ts` is the only place a rupee figure becomes text, for two reasons:

1. The API sends money as a *string* — every route stringifies its `Decimal` deliberately, per CLAUDE.md section 8. Parsing that back through JavaScript's `Number` loses precision past about ₹90,071 crore, so the formatters do their grouping *and their rounding* as string arithmetic and never construct a `Number` from a money value.
2. **D-056 is resolved and decides the units**: crores to one decimal for headline metrics, lakhs to one decimal for statement detail, absolute rupees below that, and negatives in brackets rather than with a minus sign. `formatHeadline`, `formatStatement` and `formatAmount` are those three tiers. Working figures an analyst has to tie back to a ledger line exactly — exception exposure, mapping queue values, reconciliation residuals, trial balance totals — stay in absolute rupees.

A rounded figure never stands alone: `exactAmount()` goes in the `title` beside it, and the citation trace carries the value as computed.

### The three states every screen owes the reader

- **Loading** — a skeleton in the shape of the thing being loaded, never a blank page. An enabled query counts as loading until it settles, including while the session is still resolving.
- **Empty** — says what would be here and how it gets here, never an empty table.
- **Error** — the backend's `detail` verbatim (it is written for this reader: *"balance sheet does not balance as of …"*), framed by what it means for the numbers on screen and whether anything changed. Never a raw stack trace; `app/error.tsx` is the backstop.

### What the product promises on screen

- Every displayed number carries a `Citation` that opens the metric contract and version, the period and basis, the rows read, the mapping version, the source fact tables and files, the snapshot and the query reference.
- A metric that did not resolve shows **no number at all** — the reason takes the place the figure would have occupied, at the same size and weight, with the open decisions that block it named (`MetricTile`, `NotAvailable`).
- Reconciliation status, mapping version and the unmapped rupee value sit permanently on screen (`StateStrip`), per corpus/08 section 1.
- Where the corpus specifies something the API does not return — the tile sparklines, the manufacturing margin percentages, a freshness SLA badge — the screen says so instead of deriving it. No ratio is computed in the frontend; every metric comes from the registry.

### Charts

The pack stores chart *specifications*, not pictures (corpus/08 section 8). `components/app/ChartSpec.tsx` renders them as inline SVG with no charting dependency: one validated series colour, a 2px line, gaps where a period has no value rather than a line drawn through it, endpoint labels only, the vertical range stated in words, per-point hover, and a values table under every chart.
