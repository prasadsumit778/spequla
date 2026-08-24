"use client";

import Link from "next/link";
import { useState } from "react";
import { getDataHealth } from "@/lib/api";
import { useApiQuery } from "@/lib/useApi";
import { useWorkspace } from "@/lib/workspace";
import { exactAmount, formatDateTime, formatHoursSince, formatPercent, isNonZeroAmount } from "@/lib/format";
import PageHeader from "@/components/app/PageHeader";
import Badge, { SeverityBadge } from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, Toolbar } from "@/components/ui/Field";
import { Table, TBody, TD, TFrame, TH, THead, TR } from "@/components/ui/TableExports";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";

/**
 * corpus/09 section 6: four panels, one page. "The unmapped rupee figure is
 * the single most useful number on the screen" -- so it is the largest thing
 * on it, in rupees rather than as a percentage.
 */
export default function DataHealthPage() {
  const { entityId, ready } = useWorkspace();
  const [period, setPeriod] = useState("2025-03");

  const health = useApiQuery(
    (token) => getDataHealth(token, period, entityId),
    [period, entityId],
    { enabled: ready }
  );

  const data = health.data;

  return (
    <>
      <PageHeader
        title="Data health"
        description="Whether the numbers on the other screens can be trusted right now: what has arrived, what is mapped, what reconciles, and what is open."
        corpusRef="corpus/09 section 6"
        actions={
          <Button variant="secondary" onClick={health.reload} busy={health.loading} busyLabel="Loading">
            Refresh
          </Button>
        }
      />

      <Toolbar className="mb-4">
        <Field label="Period" htmlFor="health-period">
          <input
            id="health-period"
            type="month"
            value={period}
            onChange={(e) => e.target.value && setPeriod(e.target.value)}
            className="h-9 rounded-control border border-line-strong bg-surface px-2.5 text-sm tabular-nums"
          />
        </Field>
      </Toolbar>

      {health.error && (
        <ErrorState
          title="Data health could not be loaded"
          message={health.error}
          hint="Nothing has been changed. Try again, or check that this entity has any load runs at all."
          onRetry={health.reload}
        />
      )}

      {!health.error && !data && health.loading && (
        <div className="grid gap-4 lg:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-56 rounded-card" />
          ))}
        </div>
      )}

      {!health.error && data && (
        <div className="grid gap-4 lg:grid-cols-2">
          <CompletenessPanel completeness={data.completeness} />
          <FreshnessPanel freshness={data.freshness} />
          <ReconciliationPanel rows={data.reconciliation} period={period} />
          <ExceptionsPanel exceptions={data.exceptions} />
        </div>
      )}
    </>
  );
}

/* ----------------------------------------------------------- completeness */

function CompletenessPanel({
  completeness,
}: {
  completeness: { mapped_pct: number | null; unmapped_value_inr: string | null; total_value_inr?: string; reason?: string };
}) {
  const unmapped = completeness.unmapped_value_inr;
  const present = isNonZeroAmount(unmapped);

  return (
    <Card>
      <CardHeader title="Completeness" description="How much of the ledger has a canonical class" />
      <CardBody>
        {completeness.reason ? (
          <EmptyState
            title="Not computed for this period"
            description={completeness.reason}
            className="py-8"
          />
        ) : (
          <>
            <p className="label-caps">Unmapped value</p>
            <p
              className={`figure mt-1 text-[32px] leading-10 font-semibold ${present ? "text-warn" : "text-pos"}`}
              title="Shown in absolute rupees: this is a working figure that has to tie to a ledger line exactly"
            >
              {exactAmount(unmapped ?? "0")}
            </p>
            <p className="mt-1 text-[13px] text-ink-muted">
              {present
                ? "Sitting in suspense. Every rupee here is excluded from the statements above."
                : "Every rupee in this period's ledger carries a canonical class."}
            </p>

            <dl className="mt-4 grid grid-cols-2 gap-4 border-t border-line pt-3">
              <div>
                <dt className="label-caps">Mapped</dt>
                <dd className="figure mt-0.5 text-[18px] font-semibold">
                  {formatPercent(completeness.mapped_pct, { digits: 2 })}
                </dd>
              </div>
              <div>
                <dt className="label-caps">Total value classified</dt>
                <dd className="figure mt-0.5 text-[18px] font-semibold" title="Absolute rupees">
                  {exactAmount(completeness.total_value_inr ?? null)}
                </dd>
              </div>
            </dl>

            {present && (
              <Link
                href="/mapping"
                className="mt-4 inline-flex h-8 items-center rounded-control border border-line-strong px-3 text-[13px] font-medium hover:bg-surface-sunken"
              >
                Go to mapping review
              </Link>
            )}
          </>
        )}
      </CardBody>
    </Card>
  );
}

/* -------------------------------------------------------------- freshness */

function FreshnessPanel({
  freshness,
}: {
  freshness: { source_system: string; last_successful_load_at: string | null; hours_since: number | null }[];
}) {
  return (
    <Card>
      <CardHeader title="Freshness" description="Last successful load, per source" />
      {freshness.length === 0 ? (
        <CardBody>
          <EmptyState
            title="Nothing has loaded yet"
            description="No source has completed a successful load run for this entity."
            className="py-8"
          />
        </CardBody>
      ) : (
        <TFrame>
          <Table>
            <THead>
              <TR>
                <TH>Source</TH>
                <TH>Last successful load</TH>
                <TH align="right">Age</TH>
              </TR>
            </THead>
            <TBody>
              {freshness.map((f) => (
                <TR key={f.source_system}>
                  <TD className="font-medium text-ink">{f.source_system}</TD>
                  <TD>{f.last_successful_load_at ? formatDateTime(f.last_successful_load_at) : "—"}</TD>
                  <TD align="right">
                    {f.hours_since == null ? (
                      <Badge tone="warning">never loaded</Badge>
                    ) : (
                      <span className="text-ink">{formatHoursSince(f.hours_since)}</span>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </TFrame>
      )}
      <div className="border-t border-line px-5 py-2.5">
        <p className="text-[12px] leading-5 text-ink-faint">
          corpus/09 section 2.8 also badges a source that is stale beyond its declared SLA. No SLA value is declared
          anywhere in the corpus, so ages are reported without a judgement attached rather than against a threshold
          this app invented.
        </p>
      </div>
    </Card>
  );
}

/* --------------------------------------------------------- reconciliation */

function ReconciliationPanel({
  rows,
  period,
}: {
  rows: { check_type: string; status: string; residual_inr: string; tolerance_pct: string | null; run_at: string }[];
  period: string;
}) {
  return (
    <Card>
      <CardHeader title="Reconciliation" description="Per check, for this period, with the residual in rupees" />
      {rows.length === 0 ? (
        <CardBody>
          <EmptyState
            title="No reconciliation has run for this period"
            description="Checks record a result here once they have run. An absent result is not a passing one."
            className="py-8"
          />
        </CardBody>
      ) : (
        <TFrame>
          <Table>
            <THead>
              <TR>
                <TH>Check</TH>
                <TH>Result</TH>
                <TH align="right">Residual</TH>
                <TH align="right">Run</TH>
              </TR>
            </THead>
            <TBody>
              {rows.map((r, i) => (
                <TR key={`${r.check_type}-${i}`}>
                  <TD className="font-medium text-ink">{r.check_type}</TD>
                  <TD>
                    <ReconciliationResult status={r.status} />
                    {r.tolerance_pct && (
                      <span className="ml-1.5 text-[12px] text-ink-faint">tolerance {r.tolerance_pct}</span>
                    )}
                  </TD>
                  <TD numeric title="Absolute rupees">
                    {exactAmount(r.residual_inr)}
                  </TD>
                  <TD align="right" className="whitespace-nowrap text-ink-muted">
                    {formatDateTime(r.run_at)}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </TFrame>
      )}
      <div className="border-t border-line px-5 py-2.5">
        <p className="text-[12px] leading-5 text-ink-faint">
          Trial balance tolerance is zero (D-051). The books-to-bank tolerance is deliberately unset until two
          months of a company&rsquo;s real residuals have been observed (D-052), so a residual here is reported, not
          scored against a threshold.
        </p>
      </div>
    </Card>
  );
}

function ReconciliationResult({ status }: { status: string }) {
  const tone =
    status === "reconciled" || status === "passed" || status === "within_tolerance"
      ? "positive"
      : status === "breached" || status === "failed"
      ? "blocking"
      : "neutral";
  return (
    <Badge tone={tone} dot>
      {status.replace(/_/g, " ")}
    </Badge>
  );
}

/* ------------------------------------------------------------- exceptions */

function ExceptionsPanel({
  exceptions,
}: {
  exceptions: {
    open_by_severity: Record<string, { count: number; value_inr: string }>;
    top_ten_by_value: { exception_class: string; severity: string; description: string; value_inr: string | null }[];
  };
}) {
  const severities = Object.entries(exceptions.open_by_severity);

  return (
    <Card>
      <CardHeader
        title="Exceptions"
        description="Open items, by severity and by money at stake"
        actions={
          <Link
            href="/exceptions"
            className="inline-flex h-8 items-center rounded-control border border-line-strong px-3 text-[13px] font-medium hover:bg-surface-sunken"
          >
            Open the queue
          </Link>
        }
      />
      <CardBody>
        {severities.length === 0 ? (
          <EmptyState icon="check" title="No open exceptions" description="Nothing is currently blocking or flagged." className="py-6" />
        ) : (
          <div className="flex flex-wrap gap-3">
            {severities.map(([severity, summary]) => (
              <div key={severity} className="min-w-[140px] flex-1 rounded-control border border-line px-3 py-2">
                <SeverityBadge severity={severity} />
                <p className="figure mt-1.5 text-[20px] font-semibold">{summary.count}</p>
                <p className="text-[12px] text-ink-muted" title="Absolute rupees">
                  {exactAmount(summary.value_inr)} at stake
                </p>
              </div>
            ))}
          </div>
        )}
      </CardBody>

      {exceptions.top_ten_by_value.length > 0 && (
        <>
          <div className="border-t border-line px-5 pt-3">
            <p className="label-caps">Largest ten by value</p>
          </div>
          <TFrame>
            <Table>
              <TBody>
                {exceptions.top_ten_by_value.map((e, i) => (
                  <TR key={`${e.exception_class}-${i}`}>
                    <TD>
                      <SeverityBadge severity={e.severity} />
                    </TD>
                    <TD>
                      <span className="text-ink">{e.description}</span>
                      <span className="mt-0.5 block font-mono text-[11px] text-ink-faint">{e.exception_class}</span>
                    </TD>
                    <TD numeric title="Absolute rupees">
                      {exactAmount(e.value_inr)}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </TFrame>
        </>
      )}
    </Card>
  );
}
