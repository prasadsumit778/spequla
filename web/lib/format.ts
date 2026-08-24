// Display formatting for every figure this product shows.
//
// ---------------------------------------------------------------------------
// Two rules govern this file, and neither is a style preference.
//
// 1. The backend sends money as a *string*. src/api/routes/* stringify every
//    Decimal deliberately, per CLAUDE.md section 8 ("Decimal for money, never
//    float"). Parsing that back through JavaScript's Number would undo the
//    decision at the last hop: 2^53 is about 9.007e15, so a rupee figure past
//    roughly 90,071 crore silently loses precision. So every money function
//    below operates on the digits of the string itself and never constructs a
//    Number from it -- including the rounding, which is string arithmetic with
//    an explicit half-up rule.
//
// 2. Units and rounding are not ours to choose. D-056 is RESOLVED (corpus/00
//    "Resolved", and config/decisions.yml): "Crores with one decimal for
//    headline metrics, lakhs with one decimal for statement detail, absolute
//    rupees at business unit level per the reference MIS. Negatives in
//    brackets." corpus/08 section 4.2 says the same, and corpus/08's own
//    conventions table applies it to "every displayed figure".
//
//    So: "crore" for headline tiles, "lakh" for statement detail, "rupee" for
//    anything more granular than a statement line -- an exception row, a
//    mapping queue row, a trial balance total, a reconciliation residual.
//    Those are working figures an analyst has to tie back to a ledger line
//    exactly, which is the same reason the reference MIS drops to absolute
//    rupees below corporate level.
//
//    A rounded figure never stands alone: exactAmount() goes in the title
//    attribute beside it, and the citation trace carries the stored value.
// ---------------------------------------------------------------------------

const EM_DASH = "—";

export type Scale = "rupee" | "lakh" | "crore";

const SCALES: Record<Scale, { exponent: number; digits: number; suffix: string; note: string }> = {
  rupee: { exponent: 0, digits: 2, suffix: "", note: "₹" },
  lakh: { exponent: 5, digits: 1, suffix: " L", note: "₹ in lakh" },
  crore: { exponent: 7, digits: 1, suffix: " Cr", note: "₹ in crore" },
};

/** The header note that tells a reader what a column is denominated in. */
export function scaleNote(scale: Scale): string {
  return SCALES[scale].note;
}

/* -------------------------------------------------- decimal-string plumbing */

type Parsed = { negative: boolean; digits: string; point: number };

/** "-1234.56" -> { negative: true, digits: "123456", point: 4 } */
function parseDecimalString(raw: string): Parsed | null {
  const match = /^\s*([+-]?)(\d*)(?:\.(\d*))?\s*$/.exec(raw);
  if (!match) return null;
  const [, sign, intPart = "", fracPart = ""] = match;
  if (!intPart && !fracPart) return null;
  return { negative: sign === "-", digits: intPart + fracPart, point: intPart.length };
}

/** Add one to a string of digits, propagating the carry. "999" -> "1000". */
function incrementDigits(value: string): string {
  const out = value.split("");
  let i = out.length - 1;
  while (i >= 0) {
    if (out[i] === "9") {
      out[i] = "0";
      i -= 1;
    } else {
      out[i] = String(Number(out[i]) + 1);
      return out.join("");
    }
  }
  return "1" + out.join("");
}

/** Indian digit grouping: last three digits, then pairs. 12,34,56,789. */
function groupIndian(digits: string): string {
  if (digits.length <= 3) return digits;
  const head = digits.slice(0, -3);
  const tail = digits.slice(-3);
  return head.replace(/\B(?=(\d{2})+(?!\d))/g, ",") + "," + tail;
}

/**
 * Divide by 10^exponent and round half-up to `decimals` places, entirely in
 * string space.
 */
function scaleAndRound(
  parsed: Parsed,
  exponent: number,
  decimals: number
): { int: string; frac: string; zero: boolean } {
  const point = parsed.point - exponent;
  const d = parsed.digits;

  let intPart: string;
  let fracPart: string;
  if (point <= 0) {
    intPart = "0";
    fracPart = "0".repeat(-point) + d;
  } else if (point >= d.length) {
    intPart = d + "0".repeat(point - d.length);
    fracPart = "";
  } else {
    intPart = d.slice(0, point);
    fracPart = d.slice(point);
  }

  if (fracPart.length <= decimals) {
    fracPart = fracPart.padEnd(decimals, "0");
  } else {
    const keep = fracPart.slice(0, decimals);
    const nextDigit = fracPart.charCodeAt(decimals) - 48;
    let combined = intPart + keep;
    if (nextDigit >= 5) combined = incrementDigits(combined);
    fracPart = decimals > 0 ? combined.slice(combined.length - decimals) : "";
    intPart = decimals > 0 ? combined.slice(0, combined.length - decimals) : combined;
    if (intPart === "") intPart = "0";
  }

  intPart = intPart.replace(/^0+(?=\d)/, "");
  const zero = /^0*$/.test(intPart) && /^0*$/.test(fracPart);
  return { int: groupIndian(intPart), frac: fracPart, zero };
}

/* -------------------------------------------------------------------- money */

export type MoneyOptions = {
  /** D-056's three tiers. Defaults to absolute rupees. */
  scale?: Scale;
  /** Drop the ₹ symbol *and* the scale suffix, for a column whose header
   *  already carries the unit ("₹ in lakh"). Saying it twice per row is noise. */
  bare?: boolean;
  /** Render an explicit + on positives, for deltas and movements. */
  signed?: boolean;
  fallback?: string;
};

/**
 * Format a rupee amount held as a decimal string, per D-056.
 * Negatives are bracketed, never given a minus sign.
 */
export function formatAmount(
  value: string | number | null | undefined,
  options: MoneyOptions = {}
): string {
  const { scale = "rupee", bare = false, signed = false, fallback = EM_DASH } = options;
  if (value === null || value === undefined || value === "") return fallback;

  const raw = typeof value === "number" ? value.toFixed(2) : value;
  const parsed = parseDecimalString(raw);
  // Never silently drop something we could not read -- show it as it arrived.
  if (!parsed) return String(value);

  const spec = SCALES[scale];
  const { int, frac, zero } = scaleAndRound(parsed, spec.exponent, spec.digits);

  const body = (bare ? "" : "₹") + int + (frac ? "." + frac : "") + (bare ? "" : spec.suffix);
  if (parsed.negative && !zero) return `(${body})`;
  if (signed && !zero) return `+${body}`;
  return body;
}

/** Headline metric tiles: crores, one decimal (D-056). */
export function formatHeadline(value: string | number | null | undefined, fallback = EM_DASH): string {
  return formatAmount(value, { scale: "crore", fallback });
}

/** Statement detail: lakhs, one decimal (D-056). Pass bare for a column whose
 *  header already reads "₹ in lakh". */
export function formatStatement(
  value: string | number | null | undefined,
  options: { bare?: boolean; fallback?: string } = {}
): string {
  return formatAmount(value, { scale: "lakh", bare: options.bare, fallback: options.fallback });
}

/**
 * The stored figure, every digit of it, for the title attribute beside a
 * rounded one and for the citation trace. Nothing is ever only rounded.
 */
export function exactAmount(value: string | number | null | undefined, fallback = EM_DASH): string {
  if (value === null || value === undefined || value === "") return fallback;
  const raw = typeof value === "number" ? value.toFixed(2) : value;
  const parsed = parseDecimalString(raw);
  if (!parsed) return String(value);
  const { int, frac, zero } = scaleAndRound(parsed, 0, 2);
  const body = `₹${int}.${frac}`;
  return parsed.negative && !zero ? `(${body})` : body;
}

/** True when a money string is present and non-zero, without going via Number. */
export function isNonZeroAmount(value: string | number | null | undefined): boolean {
  if (value === null || value === undefined || value === "") return false;
  if (typeof value === "number") return value !== 0;
  return /[1-9]/.test(value);
}

/** True when a money string is negative. */
export function isNegativeAmount(value: string | number | null | undefined): boolean {
  if (value === null || value === undefined || value === "") return false;
  if (typeof value === "number") return value < 0;
  return value.trim().startsWith("-") && /[1-9]/.test(value);
}

/* --------------------------------------------------------- other quantities */

/**
 * Percentages are stored as fractions and rendered at display time
 * (CLAUDE.md section 8). 0.4213 -> "42.1%".
 */
export function formatPercent(
  value: string | number | null | undefined,
  options: { digits?: number; signed?: boolean; fallback?: string } = {}
): string {
  const { digits = 1, signed = false, fallback = EM_DASH } = options;
  if (value === null || value === undefined || value === "") return fallback;
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  const pct = n * 100;
  const sign = signed && pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(digits)}%`;
}

/** A count of days, as DSO/DIO/DPO are expressed. */
export function formatDays(value: string | number | null | undefined, fallback = EM_DASH): string {
  if (value === null || value === undefined || value === "") return fallback;
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return `${n.toFixed(0)} ${Math.abs(n) === 1 ? "day" : "days"}`;
}

/** A plain quantity: production volumes, rejections, order counts. */
export function formatQuantity(value: string | number | null | undefined, fallback = EM_DASH): string {
  if (value === null || value === undefined || value === "") return fallback;
  const raw = typeof value === "number" ? String(value) : value;
  const parsed = parseDecimalString(raw);
  if (!parsed) return String(value);
  const point = parsed.point;
  const intPart = (point <= 0 ? "0" : parsed.digits.slice(0, point) || "0").replace(/^0+(?=\d)/, "");
  const fracPart = (point <= 0 ? "0".repeat(-point) + parsed.digits : parsed.digits.slice(point)).replace(/0+$/, "");
  return (parsed.negative ? "-" : "") + groupIndian(intPart) + (fracPart ? "." + fracPart : "");
}

export function formatCount(value: number | null | undefined, fallback = EM_DASH): string {
  if (value === null || value === undefined) return fallback;
  const n = Math.trunc(value);
  return (n < 0 ? "-" : "") + groupIndian(String(Math.abs(n)));
}

/* ----------------------------------------------------------- dates, periods */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const LONG_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];

/** ISO date or timestamp -> "24 Aug 2026". */
export function formatDate(value: string | null | undefined, fallback = EM_DASH): string {
  if (!value) return fallback;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

/** ISO timestamp -> "24 Aug 2026, 14:32". */
export function formatDateTime(value: string | null | undefined, fallback = EM_DASH): string {
  if (!value) return fallback;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${formatDate(value)}, ${hh}:${mm}`;
}

/** "2026-04" -> "April 2026". Period keys are YYYY-MM throughout the API. */
export function formatPeriodKey(value: string | null | undefined, fallback = EM_DASH): string {
  if (!value) return fallback;
  const match = /^(\d{4})-(\d{2})$/.exec(value.trim());
  if (!match) return value;
  const monthIndex = Number(match[2]) - 1;
  if (monthIndex < 0 || monthIndex > 11) return value;
  return `${LONG_MONTHS[monthIndex]} ${match[1]}`;
}

/** Hours since the last successful load, as the freshness panel reports it. */
export function formatHoursSince(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return "never loaded";
  if (hours < 1) return "under an hour ago";
  if (hours < 24) return `${hours.toFixed(0)}h ago`;
  const days = hours / 24;
  if (days < 2) return "yesterday";
  return `${days.toFixed(0)} days ago`;
}

/* ----------------------------------------------------------------- language */

/** snake_case or a canonical class -> readable label, for API-supplied keys. */
export function humanise(value: string): string {
  const spaced = value.replace(/[._]/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Any thrown value -> a sentence a finance user can act on. */
export function errorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === "string" && err) return err;
  return "The request did not complete. Nothing was changed.";
}

/* --------------------------------------------------------- metric rendering */

/**
 * Render a metric's value in the unit corpus/05's registry declares for it
 * (lib/metricUnits.ts). A metric with no declared unit is rendered as a plain
 * number: an unknown unit is never assumed to be rupees, because a count
 * printed as "₹412" is exactly the plausible wrong number this system exists
 * to prevent.
 */
export function formatMetricValue(
  metricId: string,
  value: string | number | null | undefined,
  unit: string | undefined,
  scale: Scale = "crore"
): string {
  if (value === null || value === undefined || value === "") return EM_DASH;
  switch (unit) {
    case "INR":
      return formatAmount(value, { scale });
    case "INR per unit":
      return formatAmount(value, { scale: "rupee" }) + " per unit";
    case "INR per order":
      return formatAmount(value, { scale: "rupee" }) + " per order";
    case "fraction":
      return formatPercent(value);
    case "days":
      return formatDays(value);
    case "ratio":
      return `${Number(value).toFixed(2)}×`;
    case "count":
    case "declared_unit":
      // declared_unit's actual unit is whatever the company declared for that
      // product; the caller renders it alongside, from the row's own uom.
      return formatQuantity(value);
    default:
      return formatQuantity(value);
  }
}

/** The exact stored figure for a metric, for the title attribute. */
export function exactMetricValue(
  value: string | number | null | undefined,
  unit: string | undefined
): string | undefined {
  if (value === null || value === undefined || value === "") return undefined;
  if (unit === "INR") return `${exactAmount(value)} exactly`;
  return undefined;
}

export { EM_DASH };
