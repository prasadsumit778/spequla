"use client";

import { exactAmount, formatAmount, formatPeriodKey, formatQuantity } from "@/lib/format";
import Badge from "@/components/ui/Badge";
import Disclosure from "@/components/ui/Disclosure";
import { Table, TBody, TD, TFrame, TH, THead, TR } from "@/components/ui/TableExports";
import { cn } from "@/components/ui/cn";

/**
 * corpus/08 section 8: "A model never selects a chart in P0 ... store the
 * specification, not the picture." The pack persists chart *specs*; this
 * renders them, so the same spec draws the same way here, in the exported
 * document and at any prior snapshot.
 *
 * Four spec types exist (src/reports/charts.py). Anything else falls back to a
 * readable dump rather than a blank space, because "anything the rules cannot
 * handle falls back to a table, which is always a correct answer."
 */

type Spec = Record<string, any> & { chart_type: string; title: string };

export default function ChartSpec({ spec }: { spec: Spec }) {
  switch (spec.chart_type) {
    case "kpi_tile":
      return <KpiTile spec={spec} />;
    case "line":
      return <LineChart spec={spec} />;
    case "table":
      return <TableChart spec={spec} />;
    case "waterfall":
      return <Waterfall spec={spec} />;
    default:
      return <Fallback spec={spec} />;
  }
}

/* ---------------------------------------------------------------- kpi tile */

function KpiTile({ spec }: { spec: Spec }) {
  const isMoney = spec.unit === "INR";
  const value = isMoney ? formatAmount(spec.value, { scale: "crore" }) : formatQuantity(spec.value);

  return (
    <div className="rounded-card border border-line bg-surface px-4 py-3">
      <p className="label-caps">{spec.title}</p>
      <p
        className="figure mt-1 text-[24px] leading-8 font-semibold tracking-[-0.02em]"
        title={isMoney ? `${exactAmount(spec.value)} exactly` : undefined}
      >
        {value}
      </p>
      <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 text-[12px]">
        <Delta label="vs prior month" value={spec.delta_vs_prior_month} isMoney={isMoney} />
        <Delta label="vs prior year" value={spec.delta_vs_prior_year} isMoney={isMoney} />
      </div>
    </div>
  );
}

function Delta({ label, value, isMoney }: { label: string; value: unknown; isMoney: boolean }) {
  if (value === null || value === undefined) {
    return (
      <span className="text-ink-faint">
        {label} <span className="text-ink-faint">not available</span>
      </span>
    );
  }
  const numeric = Number(value);
  const rendered = isMoney
    ? formatAmount(value as number, { scale: "crore", signed: true })
    : formatQuantity(value as number);
  return (
    <span className="text-ink-muted">
      {label}{" "}
      <span
        className={cn("figure font-medium", numeric > 0 ? "text-pos" : numeric < 0 ? "text-neg" : "text-ink-soft")}
        title={isMoney ? `${exactAmount(value as number)} exactly` : undefined}
      >
        {rendered}
      </span>
    </span>
  );
}

/* -------------------------------------------------------------- line chart */

type Point = { period: string; value: number | null };

function LineChart({ spec }: { spec: Spec }) {
  const series = spec.series?.[0];
  const points: Point[] = series?.points ?? [];
  const isMoney = spec.unit !== "days";

  const present = points.filter((p) => p.value !== null) as { period: string; value: number }[];

  if (present.length === 0) {
    return (
      <div className="rounded-card border border-line bg-surface px-4 py-3">
        <p className="label-caps">{spec.title}</p>
        <p className="mt-2 text-[12.5px] text-warn">
          No period in this window produced a value, so there is nothing to plot.
        </p>
        <ValuesTable points={points} isMoney={isMoney} />
      </div>
    );
  }

  const values = present.map((p) => p.value);
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const pad = rawMax === rawMin ? Math.abs(rawMax) * 0.1 || 1 : (rawMax - rawMin) * 0.12;
  const min = rawMin - pad;
  const max = rawMax + pad;

  const W = 640;
  const H = 150;
  const PAD_X = 8;
  const PAD_Y = 14;

  const x = (i: number) =>
    points.length === 1 ? W / 2 : PAD_X + (i * (W - PAD_X * 2)) / (points.length - 1);
  const y = (v: number) => H - PAD_Y - ((v - min) / (max - min)) * (H - PAD_Y * 2);

  // Nulls break the line rather than being bridged: a straight segment across a
  // month with no value would draw data that does not exist.
  const segments: { i: number; x: number; y: number }[][] = [];
  let current: { i: number; x: number; y: number }[] = [];
  points.forEach((p, i) => {
    if (p.value === null) {
      if (current.length) segments.push(current);
      current = [];
    } else {
      current.push({ i, x: x(i), y: y(p.value) });
    }
  });
  if (current.length) segments.push(current);

  const firstIndex = points.findIndex((p) => p.value !== null);
  const lastIndex = points.length - 1 - [...points].reverse().findIndex((p) => p.value !== null);

  const label = (v: number | null) =>
    v === null ? "not available" : isMoney ? formatAmount(v, { scale: "crore" }) : formatQuantity(v);

  return (
    <div className="rounded-card border border-line bg-surface px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="label-caps">{spec.title}</p>
        <p className="text-[11px] text-ink-faint">
          {isMoney ? "₹ in crore" : "days"} · {formatPeriodKey(points[0]?.period)} to{" "}
          {formatPeriodKey(points[points.length - 1]?.period)}
        </p>
      </div>

      {/* The vertical range is stated in words. The baseline is not zero -- on a
          trend that would flatten every movement worth seeing -- so the range
          is said out loud instead, where it cannot be misread. */}
      <p className="mt-0.5 text-[11px] text-ink-faint tabular-nums">
        Range {label(rawMin)} to {label(rawMax)}
      </p>

      <div className="mt-2">
        {/* Uniform scaling: with preserveAspectRatio="none" the end-dots would
            render as ellipses at every width but the authored one. */}
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-auto w-full"
          role="img"
          aria-label={`${spec.title}: ${present.length} of ${points.length} periods have a value`}
        >
          <line x1="0" y1={H - PAD_Y} x2={W} y2={H - PAD_Y} stroke="var(--color-viz-grid)" strokeWidth="1" />

          {segments.map((segment, index) => (
            <polyline
              key={index}
              points={segment.map((p) => `${p.x},${p.y}`).join(" ")}
              fill="none"
              stroke="var(--color-viz-series)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          ))}

          {points.map((p, i) =>
            p.value === null ? null : (
              <g key={p.period}>
                {/* A surface ring keeps the dot legible where it meets the line,
                    and widens the hover target. */}
                <circle cx={x(i)} cy={y(p.value)} r="6.5" fill="var(--color-surface)" />
                <circle cx={x(i)} cy={y(p.value)} r="4.5" fill="var(--color-viz-series)" />
                <rect
                  x={x(i) - 14}
                  y={0}
                  width={28}
                  height={H}
                  fill="transparent"
                  className="cursor-crosshair"
                >
                  <title>{`${formatPeriodKey(p.period)}: ${label(p.value)}`}</title>
                </rect>
              </g>
            )
          )}

          {points.map((p, i) =>
            p.value !== null ? null : (
              <rect key={`gap-${p.period}`} x={x(i) - 14} y={0} width={28} height={H} fill="transparent">
                <title>{`${formatPeriodKey(p.period)}: not available`}</title>
              </rect>
            )
          )}
        </svg>
      </div>

      {/* Direct labels, only on the two ends -- never a number on every point. */}
      <div className="mt-1 flex justify-between text-[11px] text-ink-muted tabular-nums">
        <span>
          {formatPeriodKey(points[firstIndex]?.period)} · {label(points[firstIndex]?.value ?? null)}
        </span>
        <span>
          {formatPeriodKey(points[lastIndex]?.period)} · {label(points[lastIndex]?.value ?? null)}
        </span>
      </div>

      <ValuesTable points={points} isMoney={isMoney} />
    </div>
  );
}

function ValuesTable({ points, isMoney }: { points: Point[]; isMoney: boolean }) {
  return (
    <Disclosure label="Show every value" openLabel="Hide the values" className="mt-2">
      <TFrame className="rounded-control border border-line">
        <Table>
          <THead>
            <TR>
              <TH>Period</TH>
              <TH align="right">Value</TH>
            </TR>
          </THead>
          <TBody>
            {points.map((p) => (
              <TR key={p.period}>
                <TD>{formatPeriodKey(p.period)}</TD>
                <TD numeric={p.value !== null} align="right">
                  {p.value === null ? (
                    <span className="text-[12px] text-warn">Not available</span>
                  ) : isMoney ? (
                    <span title={`${exactAmount(p.value)} exactly`}>{formatAmount(p.value, { scale: "crore" })}</span>
                  ) : (
                    formatQuantity(p.value)
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </TFrame>
    </Disclosure>
  );
}

/* ------------------------------------------------------------- table chart */

function TableChart({ spec }: { spec: Spec }) {
  const columns: string[] = spec.columns ?? [];
  const rows: unknown[][] = spec.rows ?? [];

  return (
    <div className="rounded-card border border-line bg-surface">
      <div className="border-b border-line px-4 py-2.5">
        <p className="label-caps">{spec.title}</p>
        <p className="mt-0.5 text-[11px] text-ink-faint">₹ in lakh</p>
      </div>
      <TFrame>
        <Table>
          <THead>
            <TR>
              {columns.map((c, i) => (
                <TH key={c} align={i === 0 ? "left" : "right"}>
                  {c}
                </TH>
              ))}
            </TR>
          </THead>
          <TBody>
            {rows.map((row, i) => (
              <TR key={i}>
                {row.map((cell, j) => (
                  <TD key={j} numeric={j > 0 && typeof cell === "number"} align={j === 0 ? "left" : "right"}>
                    {typeof cell === "number" ? (
                      <span title={`${exactAmount(cell)} exactly`}>{formatAmount(cell, { scale: "lakh", bare: true })}</span>
                    ) : (
                      (cell as string) ?? "—"
                    )}
                  </TD>
                ))}
              </TR>
            ))}
          </TBody>
        </Table>
      </TFrame>
    </div>
  );
}

/* ---------------------------------------------------------------- waterfall */

function Waterfall({ spec }: { spec: Spec }) {
  const components: { label: string; value: number; is_residual: boolean }[] = spec.components ?? [];
  return (
    <div className="rounded-card border border-line bg-surface px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="label-caps">{spec.title}</p>
        <p className="figure text-[13px] font-semibold" title={`${exactAmount(spec.total_delta)} exactly`}>
          {formatAmount(spec.total_delta, { scale: "lakh" })}
        </p>
      </div>
      <ul className="mt-2 divide-y divide-line">
        {components.map((component) => (
          <li key={component.label} className="flex items-center justify-between gap-3 py-1.5 text-[13px]">
            <span className="text-ink-soft">
              {component.label}
              {component.is_residual && (
                <Badge tone="warning" className="ml-2">
                  residual
                </Badge>
              )}
            </span>
            <span className="figure font-medium" title={`${exactAmount(component.value)} exactly`}>
              {formatAmount(component.value, { scale: "lakh" })}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ----------------------------------------------------------------- fallback */

function Fallback({ spec }: { spec: Spec }) {
  return (
    <div className="rounded-card border border-line bg-surface px-4 py-3">
      <p className="label-caps">{spec.title || spec.chart_type}</p>
      <p className="mt-1 text-[12.5px] text-ink-muted">
        This app has no renderer for a “{spec.chart_type}” spec yet. The stored specification is shown as it is,
        rather than as an approximation of it.
      </p>
      <pre className="scroll-x mt-2 rounded-control bg-surface-sunken px-2.5 py-2 font-mono text-[11px]">
        {JSON.stringify(spec, null, 2)}
      </pre>
    </div>
  );
}
