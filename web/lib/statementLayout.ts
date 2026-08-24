/**
 * Statement row order, taken from corpus/08 sections 4.1, 4.2 and 5.
 *
 * The API returns `lines` and `subtotals` as objects, and JSON object order is
 * whatever the assembler's dict happened to build (src/reports/pnl.py fills
 * missing rows at the end, after the ones that had movements). Order is part
 * of the statement, not a rendering detail -- corpus/08 section 4.2 says
 * "assembled ... in this order" -- so the layout is declared here and applied
 * to whatever the endpoint returns.
 *
 * Anything the endpoint returns that this layout does not name is still
 * rendered, at the end, under its own heading. A line is never dropped
 * because the layout did not expect it.
 */

export type LayoutRow =
  | { kind: "line"; label: string; prefix?: string; indent?: number; note?: string }
  | { kind: "subtotal"; key: string; label: string; prefix?: string; total?: boolean }
  | { kind: "ratio"; key: string; label: string };

/** corpus/08 section 4.2, verbatim row order. */
export const MANUFACTURING_PNL_LAYOUT: LayoutRow[] = [
  { kind: "line", label: "Gross revenue" },
  { kind: "line", label: "Returns", prefix: "less", indent: 1 },
  { kind: "line", label: "Discounts and rate differences", prefix: "less", indent: 1 },
  { kind: "subtotal", key: "net_revenue", label: "Net revenue", prefix: "=" },
  { kind: "subtotal", key: "cogs_total", label: "Cost of goods sold", prefix: "less" },
  { kind: "line", label: "Raw material", indent: 2 },
  { kind: "line", label: "Packing material", indent: 2 },
  { kind: "line", label: "Direct labour", indent: 2 },
  { kind: "line", label: "Power and fuel", indent: 2 },
  { kind: "line", label: "Freight", indent: 2 },
  { kind: "line", label: "Other direct cost", indent: 2 },
  { kind: "line", label: "Absorption variance", indent: 2, note: "if standard costing" },
  { kind: "subtotal", key: "gross_profit", label: "Gross profit", prefix: "=" },
  { kind: "subtotal", key: "opex_total", label: "Operating expenses", prefix: "less" },
  { kind: "line", label: "Employee cost", indent: 2 },
  { kind: "line", label: "Marketing and advertising", indent: 2 },
  { kind: "line", label: "Selling and distribution", indent: 2 },
  { kind: "line", label: "Rent", indent: 2 },
  { kind: "line", label: "Repairs and maintenance", indent: 2 },
  { kind: "line", label: "Professional fees", indent: 2 },
  { kind: "line", label: "Travel", indent: 2 },
  { kind: "line", label: "Administration and general", indent: 2 },
  // corpus/08 section 4.2: "always separate lines, even when small."
  { kind: "line", label: "Owner remuneration", indent: 2, note: "always separate" },
  { kind: "line", label: "Related party charges", indent: 2, note: "always separate" },
  { kind: "line", label: "Other", indent: 2 },
  { kind: "subtotal", key: "ebitda", label: "EBITDA", prefix: "=" },
  { kind: "line", label: "Depreciation and amortisation", prefix: "less", indent: 1 },
  { kind: "subtotal", key: "ebit", label: "EBIT", prefix: "=" },
  { kind: "line", label: "Other income", prefix: "add", indent: 1 },
  { kind: "line", label: "Finance cost", prefix: "less", indent: 1 },
  { kind: "subtotal", key: "pbt", label: "Profit before tax", prefix: "=" },
  { kind: "line", label: "Tax", prefix: "less", indent: 1 },
  { kind: "subtotal", key: "pat", label: "Profit after tax", prefix: "=", total: true },
];

/** corpus/08 section 4.1, the consumer contribution margin ladder. */
export const CONSUMER_LADDER_LAYOUT: LayoutRow[] = [
  { kind: "line", label: "GMV" },
  { kind: "line", label: "GST", prefix: "less", indent: 1 },
  { kind: "subtotal", key: "gross_revenue", label: "Gross revenue", prefix: "=" },
  { kind: "line", label: "Discount", prefix: "less", indent: 1 },
  { kind: "subtotal", key: "net_revenue", label: "Net revenue", prefix: "=" },
  // D-020 / D-060: COGS is buyout lines only; fulfilment sits above CM1, not here.
  { kind: "line", label: "Cost of goods sold", prefix: "less", indent: 1, note: "buyout lines only" },
  { kind: "subtotal", key: "gross_margin", label: "Gross margin", prefix: "=" },
  { kind: "ratio", key: "gross_margin_pct", label: "Gross margin %" },
  { kind: "line", label: "Operating cost", prefix: "less", indent: 1 },
  { kind: "subtotal", key: "cm1", label: "CM1", prefix: "=" },
  { kind: "ratio", key: "cm1_pct", label: "CM1 %" },
  // CLAUDE.md invariant 14: marketing is the CM1 to CM2 step, never inside CM1.
  { kind: "line", label: "Marketing", prefix: "less", indent: 1 },
  { kind: "subtotal", key: "cm2", label: "CM2", prefix: "=" },
  { kind: "ratio", key: "cm2_pct", label: "CM2 %" },
  { kind: "line", label: "Corporate overhead", prefix: "less", indent: 1, note: "never allocated" },
  { kind: "subtotal", key: "ebitda", label: "EBITDA", prefix: "=", total: true },
];

/** corpus/08 section 5's grouped presentation order. */
export const BALANCE_SHEET_GROUPS = [
  { key: "current_assets", label: "Current assets" },
  { key: "non_current_assets", label: "Non-current assets" },
  { key: "current_liabilities", label: "Current liabilities" },
  { key: "non_current_liabilities", label: "Non-current liabilities" },
  { key: "equity", label: "Equity" },
];

/** Line labels a layout already places, so the leftovers can be found. */
export function labelsInLayout(layout: LayoutRow[]): Set<string> {
  const labels = new Set<string>();
  for (const row of layout) if (row.kind === "line") labels.add(row.label);
  return labels;
}

/** Subtotal keys a layout already places. */
export function keysInLayout(layout: LayoutRow[]): Set<string> {
  const keys = new Set<string>();
  for (const row of layout) if (row.kind !== "line") keys.add(row.key);
  return keys;
}
