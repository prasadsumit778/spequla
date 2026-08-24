"use client";

import { useState } from "react";
import type { Citation as CitationShape } from "@/lib/api";
import Badge, { ReconciliationBadge } from "@/components/ui/Badge";
import { cn } from "@/components/ui/cn";
import { exactAmount, formatAmount, formatCount, formatDateTime, formatPeriodKey, isNonZeroAmount } from "@/lib/format";
import { METRIC_UNITS } from "@/lib/metricUnits";

/**
 * CLAUDE.md invariant #7: "Every displayed number carries a citation that
 * resolves to source rows. A number without one is not displayed."
 *
 * The compact line sits under every figure. Trace opens the whole citation
 * as corpus/07 section 8 defines it: which metric contract and version
 * produced the number, over what period and on what basis, from which fact
 * tables and which uploaded files, under which mapping version, at what
 * snapshot, and how much value was unmapped when it was computed.
 */
export default function Citation({
  citation,
  className,
}: {
  citation: CitationShape;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const unmapped = isNonZeroAmount(citation.unmapped_value_inr);

  return (
    <div className={cn("text-[11.5px] text-ink-faint", className)}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span title={`Metric contract ${citation.metric}, version ${citation.metric_version}`}>
          {citation.metric} v{citation.metric_version}
        </span>
        <Dot />
        <span>{formatCount(citation.row_count)} source rows</span>
        {citation.mapping_version != null && (
          <>
            <Dot />
            <span>mapping v{citation.mapping_version}</span>
          </>
        )}
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="ml-auto font-medium text-brand-600 hover:text-brand-800"
        >
          {open ? "Hide trace" : "Trace"}
        </button>
      </div>

      {unmapped && (
        <p className="mt-0.5 font-medium text-warn">{formatAmount(citation.unmapped_value_inr)} unmapped</p>
      )}

      {open && (
        <dl className="mt-2.5 grid gap-x-4 gap-y-2 rounded-control border border-line bg-surface-muted px-3 py-2.5 sm:grid-cols-2">
          <Row label="Metric">
            {citation.metric} <span className="text-ink-faint">contract v{citation.metric_version}</span>
          </Row>
          <Row label="Stored value">
            {METRIC_UNITS[citation.metric] === "INR" ? exactAmount(citation.value) : citation.value}
            <span className="ml-1 text-ink-faint">as computed, before display rounding</span>
          </Row>
          <Row label="Period">
            {formatPeriodKey(citation.period)} <span className="text-ink-faint">· {citation.basis} basis</span>
          </Row>
          <Row label="Reconciliation">
            <ReconciliationBadge status={citation.reconciliation_status} />
          </Row>
          <Row label="Rows read">{formatCount(citation.row_count)}</Row>
          <Row label="Mapping version">
            {citation.mapping_version == null ? (
              <Badge tone="warning">none</Badge>
            ) : (
              `v${citation.mapping_version}`
            )}
          </Row>
          <Row label="Unmapped in this figure">
            <span className={unmapped ? "font-semibold text-warn" : "text-pos"}>
              {formatAmount(citation.unmapped_value_inr ?? "0")}
            </span>
          </Row>
          <Row label="Source facts" full>
            {citation.source_facts.length ? (
              <span className="font-mono text-[11px]">{citation.source_facts.join(", ")}</span>
            ) : (
              "—"
            )}
          </Row>
          <Row label="Source files" full>
            {citation.source_files.length ? (
              <ul className="space-y-0.5">
                {citation.source_files.map((f) => (
                  <li key={f} className="font-mono text-[11px] break-all">
                    {f}
                  </li>
                ))}
              </ul>
            ) : (
              "—"
            )}
          </Row>
          <Row label="Snapshot">{formatDateTime(citation.snapshot_at)}</Row>
          <Row label="Query reference">
            <span className="font-mono text-[11px]">{citation.query_hash}</span>
          </Row>
          <div className="sm:col-span-2">
            <p className="text-[11px] text-ink-faint">
              Re-running this metric at the same snapshot reproduces reference{" "}
              <span className="font-mono">{citation.query_hash}</span>. The row-by-row drill-through view (
              <span className="font-mono">{citation.drill_url}</span>) is specified in corpus/07 but is not built in
              this app yet, so it is shown as a reference rather than a link that would go nowhere.
            </p>
          </div>
        </dl>
      )}
    </div>
  );
}

function Row({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return (
    <div className={cn("min-w-0", full && "sm:col-span-2")}>
      <dt className="label-caps">{label}</dt>
      <dd className="mt-0.5 text-[12px] text-ink-soft">{children}</dd>
    </div>
  );
}

function Dot() {
  return <span aria-hidden="true">·</span>;
}
