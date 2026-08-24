"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@workos-inc/authkit-nextjs/components";
import {
  exportReportUrl,
  generateReport,
  getBlockingExceptions,
  getReport,
  listReports,
  signReport,
  updateCommentary,
  type BlockingException,
  type ReportArtefact,
  type ReportSummary,
} from "@/lib/api";
import { useApiAction, useApiQuery } from "@/lib/useApi";
import { useWorkspace } from "@/lib/workspace";
import { exactAmount, formatDateTime, formatHoursSince, formatPeriodKey, isNonZeroAmount } from "@/lib/format";
import PageHeader from "@/components/app/PageHeader";
import ChartSpec from "@/components/app/ChartSpec";
import { StatementRow, StatementTable } from "@/components/app/StatementTable";
import Badge, { ReconciliationBadge, SeverityBadge, StatusBadge } from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { cn } from "@/components/ui/cn";
import Disclosure, { CodeBlock } from "@/components/ui/Disclosure";
import { Field, Textarea, Toolbar } from "@/components/ui/Field";
import { Callout, EmptyState, ErrorState, Skeleton } from "@/components/ui/States";

/**
 * corpus/08 sections 7 and 10: generate, review, sign, export.
 *
 * The commentary is written by a human -- this screen is an editor, not a
 * generator. Signing is gated on open blocking exceptions for the period, and
 * an override is a written reason that ends up printed in the pack's own data
 * quality appendix, not a checkbox that makes the gate go away.
 */
export default function ReportsPage() {
  const { user } = useAuth();
  const { entityId, profile, ready } = useWorkspace();

  const [period, setPeriod] = useState("2026-04");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const list = useApiQuery(
    (token) => listReports(token, period, entityId),
    [period, entityId],
    { enabled: ready }
  );

  const detail = useApiQuery(
    (token) => getReport(token, selectedId as number),
    [selectedId],
    { enabled: selectedId !== null }
  );

  const blocking = useApiQuery(
    (token) => getBlockingExceptions(token, selectedId as number),
    [selectedId, detail.data?.status],
    { enabled: selectedId !== null && detail.data?.status === "draft" }
  );

  const generate = useApiAction(generateReport);

  // Selecting the newest generation for the period keeps the screen from
  // opening on nothing when the period changes.
  useEffect(() => {
    if (!list.data) return;
    if (list.data.length === 0) {
      setSelectedId(null);
      return;
    }
    if (!list.data.some((r) => r.report_artefact_id === selectedId)) {
      setSelectedId(list.data[0].report_artefact_id);
    }
  }, [list.data, selectedId]);

  async function handleGenerate() {
    const summary = await generate.run(period, entityId, profile);
    if (!summary) return;
    list.reload();
    setSelectedId(summary.report_artefact_id);
  }

  return (
    <>
      <PageHeader
        title="Monthly pack"
        description="The eight-section management pack for a period. Generate it, write the commentary yourself, then sign it — after which it is fixed and renders against the same snapshot forever."
        corpusRef="corpus/08 section 7"
      />

      <Toolbar className="mb-4">
        <Field label="Period" htmlFor="pack-period">
          <input
            id="pack-period"
            type="month"
            value={period}
            onChange={(e) => e.target.value && setPeriod(e.target.value)}
            className="h-9 rounded-control border border-line-strong bg-surface px-2.5 text-sm tabular-nums"
          />
        </Field>
        <Button variant="primary" onClick={handleGenerate} busy={generate.busy} busyLabel="Generating" disabled={!ready}>
          Generate a pack
        </Button>
        <p className="ml-auto self-center text-[12px] text-ink-faint">
          Entity {entityId} · {profile === "manufacturing" ? "Manufacturing" : "Consumer"} · both from the top bar
        </p>
      </Toolbar>

      {generate.error && (
        <ErrorState
          title="No pack was generated"
          message={generate.error}
          hint="A period with no approved mapping version cannot produce a pack. Nothing was written."
          className="mb-4"
        />
      )}

      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <GenerationList
          list={list}
          period={period}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />

        <div className="min-w-0">
          {detail.error && (
            <ErrorState title="This pack could not be opened" message={detail.error} onRetry={detail.reload} />
          )}

          {!detail.error && selectedId === null && (
            <Card>
              <EmptyState
                title={`No pack has been generated for ${formatPeriodKey(period)}`}
                description="Generating one assembles every section from the frozen mapping and the metric registry. It starts as a draft — nothing is final until someone signs it."
              />
            </Card>
          )}

          {!detail.error && selectedId !== null && !detail.data && detail.loading && (
            <Card>
              <CardBody className="space-y-3">
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-24 w-full" />
                <Skeleton className="h-24 w-full" />
              </CardBody>
            </Card>
          )}

          {!detail.error && detail.data && (
            <PackDetail
              pack={detail.data}
              blockingExceptions={blocking.data?.blocking_exceptions ?? []}
              blockingLoading={blocking.loading}
              signerEmail={user?.email ?? ""}
              onChanged={() => {
                detail.reload();
                list.reload();
                blocking.reload();
              }}
            />
          )}
        </div>
      </div>
    </>
  );
}

/* -------------------------------------------------------- generation list */

function GenerationList({
  list,
  period,
  selectedId,
  onSelect,
}: {
  list: ReturnType<typeof useApiQuery<ReportSummary[]>>;
  period: string;
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <Card className="self-start">
      <CardHeader title="Generations" description={formatPeriodKey(period)} />

      {list.error && (
        <CardBody>
          <ErrorState title="Could not list packs" message={list.error} onRetry={list.reload} />
        </CardBody>
      )}

      {!list.error && !list.data && list.loading && (
        <CardBody className="space-y-2">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </CardBody>
      )}

      {!list.error && list.data?.length === 0 && (
        <CardBody>
          <p className="text-[13px] text-ink-muted">None yet for this period.</p>
        </CardBody>
      )}

      {!list.error && list.data && list.data.length > 0 && (
        <ul className="p-2">
          {list.data.map((report) => (
            <li key={report.report_artefact_id}>
              <button
                type="button"
                onClick={() => onSelect(report.report_artefact_id)}
                aria-current={selectedId === report.report_artefact_id ? "true" : undefined}
                className={cn(
                  "mb-1 w-full rounded-control border px-3 py-2 text-left transition-colors",
                  selectedId === report.report_artefact_id
                    ? "border-brand-300 bg-brand-50"
                    : "border-transparent hover:bg-surface-muted"
                )}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="text-[13px] font-medium">#{report.report_artefact_id}</span>
                  <StatusBadge status={report.status} />
                </span>
                <span className="mt-0.5 block text-[11.5px] text-ink-muted">
                  {formatDateTime(report.generated_at)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/* --------------------------------------------------------------- the pack */

function PackDetail({
  pack,
  blockingExceptions,
  blockingLoading,
  signerEmail,
  onChanged,
}: {
  pack: ReportArtefact;
  blockingExceptions: BlockingException[];
  blockingLoading: boolean;
  signerEmail: string;
  onChanged: () => void;
}) {
  const cover = pack.sections?.["1_cover"];
  const dataQuality = pack.sections?.["9_data_quality_appendix"];
  const revenue = pack.sections?.["4_revenue_analysis"];
  const workingCapital = pack.sections?.["6_working_capital"];
  const cash = pack.sections?.["7_cash"];
  const margin = pack.sections?.["5_margin_analysis"];

  const isDraft = pack.status === "draft";
  const kpiTiles = pack.chart_specs.filter((c) => c.chart_type === "kpi_tile");
  const lineCharts = pack.chart_specs.filter((c) => c.chart_type === "line");
  const tables = pack.chart_specs.filter((c) => c.chart_type === "table");
  const others = pack.chart_specs.filter(
    (c) => !["kpi_tile", "line", "table"].includes(c.chart_type)
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title={`Pack #${pack.report_artefact_id}`}
          description={`${formatPeriodKey(pack.period_key)} · ${pack.profile} · generated by ${pack.generated_by}`}
          actions={
            <>
              <StatusBadge status={pack.status} />
              {pack.status === "signed" && (
                <a
                  href={exportReportUrl(pack.report_artefact_id)}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex h-8 items-center rounded-control border border-line-strong px-3 text-[13px] font-medium hover:bg-surface-sunken"
                >
                  Export
                </a>
              )}
            </>
          }
        />

        {/* Section 1. The cover is the state of the numbers, so it stays at the
            top rather than being a page nobody reads. */}
        {cover && (
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-line bg-surface-muted px-5 py-3">
            <Meta label="Basis">{cover.basis}</Meta>
            <Meta label="Reconciliation">
              <ReconciliationBadge status={cover.reconciliation_status} />
            </Meta>
            <Meta label="Mapping">v{cover.mapping_version_no}</Meta>
            <Meta label="Unmapped">
              <span
                className={isNonZeroAmount(cover.unmapped_value_inr) ? "font-semibold text-warn" : "font-semibold text-pos"}
              >
                {exactAmount(cover.unmapped_value_inr)}
              </span>
            </Meta>
            {pack.status === "signed" && (
              <Meta label="Signed">
                {pack.reviewer} · {formatDateTime(pack.signed_at)}
              </Meta>
            )}
          </div>
        )}

        {Array.isArray(cover?.freshness) && cover.freshness.length > 0 && (
          <CardBody className="py-3">
            <p className="label-caps mb-1.5">Data freshness at generation</p>
            <ul className="flex flex-wrap gap-x-5 gap-y-1 text-[12.5px] text-ink-muted">
              {cover.freshness.map((f: any) => (
                <li key={f.source_system}>
                  <span className="text-ink">{f.source_system}</span> · {formatHoursSince(f.hours_since)}
                </li>
              ))}
            </ul>
          </CardBody>
        )}
      </Card>

      {/* Section 2 */}
      <CommentarySection pack={pack} isDraft={isDraft} onChanged={onChanged} />

      {/* Section 3 */}
      <Section number={3} title="Financial summary" description="Headline metrics against the prior month and prior year">
        {kpiTiles.length === 0 ? (
          <Callout tone="warning">
            No headline metric resolved for this period, so no tile is shown. A tile is never shown without a value.
          </Callout>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {kpiTiles.map((spec, i) => (
              <ChartSpec key={i} spec={spec} />
            ))}
          </div>
        )}
      </Section>

      {/* Section 4 */}
      {revenue && (
        <Section number={4} title="Revenue analysis" description="Entity level, with what is not broken down stated plainly">
          <UnavailableList reasons={revenue.unavailable_reasons} />
        </Section>
      )}

      {/* Section 5 */}
      {(tables.length > 0 || margin) && (
        <Section number={5} title="Margin analysis" description="Cost line movements against the prior period">
          {tables.map((spec, i) => (
            <ChartSpec key={i} spec={spec} />
          ))}
          {margin?.gross_margin_bridge === null && margin?.gross_margin_bridge_reason && (
            <Callout tone="warning" className="mt-3" title="No gross margin bridge">
              {margin.gross_margin_bridge_reason}
            </Callout>
          )}
        </Section>
      )}

      {/* Sections 6 and 7 */}
      {lineCharts.length > 0 && (
        <Section number={6} title="Working capital and cash" description="Trailing months, per metric">
          <div className="grid gap-3 xl:grid-cols-2">
            {lineCharts.map((spec, i) => (
              <ChartSpec key={i} spec={spec} />
            ))}
          </div>
          <UnavailableList reasons={workingCapital?.unavailable_reasons} className="mt-3" />
          <UnavailableList reasons={cash?.unavailable_reasons} />
        </Section>
      )}

      {others.length > 0 && (
        <Section number={8} title="Other specifications" description="Stored chart specs this app has no renderer for">
          <div className="space-y-3">
            {others.map((spec, i) => (
              <ChartSpec key={i} spec={spec} />
            ))}
          </div>
        </Section>
      )}

      {/* Section 9 */}
      {dataQuality && <DataQualityAppendix appendix={dataQuality} />}

      {/* Sign-off */}
      {isDraft && (
        <SignOff
          pack={pack}
          blockingExceptions={blockingExceptions}
          blockingLoading={blockingLoading}
          signerEmail={signerEmail}
          onChanged={onChanged}
        />
      )}

      <Card>
        <CardBody>
          <Disclosure label="View the stored artefact" openLabel="Hide the stored artefact">
            <p className="mb-2 text-[12px] text-ink-muted">
              Content hash <span className="font-mono">{pack.content_hash}</span>. This is what was persisted; the
              screen above is a rendering of it.
            </p>
            <CodeBlock>{JSON.stringify(pack.sections, null, 2)}</CodeBlock>
          </Disclosure>
        </CardBody>
      </Card>
    </div>
  );
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="label-caps">{label}</span>
      <span className="text-[13px] text-ink">{children}</span>
    </div>
  );
}

function Section({
  number,
  title,
  description,
  children,
}: {
  number: number;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-baseline gap-2">
            <span className="text-[12px] font-semibold text-ink-faint">{number}</span>
            {title}
          </span>
        }
        description={description}
      />
      <CardBody>{children}</CardBody>
    </Card>
  );
}

function UnavailableList({ reasons, className }: { reasons?: string[]; className?: string }) {
  if (!reasons || reasons.length === 0) return null;
  return (
    <div className={cn("rounded-control border border-warn-line bg-warn-soft px-3 py-2.5", className)}>
      <p className="text-[12.5px] font-semibold text-warn">Not broken down, and why</p>
      <ul className="mt-1 space-y-1">
        {reasons.map((reason) => (
          <li key={reason} className="text-[12.5px] leading-5 text-ink-soft">
            {reason}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------- commentary */

function CommentarySection({
  pack,
  isDraft,
  onChanged,
}: {
  pack: ReportArtefact;
  isDraft: boolean;
  onChanged: () => void;
}) {
  const [commentary, setCommentary] = useState(pack.commentary || "");
  const [saved, setSaved] = useState(false);
  const save = useApiAction(updateCommentary);

  useEffect(() => {
    setCommentary(pack.commentary || "");
    setSaved(false);
  }, [pack.report_artefact_id, pack.commentary]);

  async function handleSave() {
    const result = await save.run(pack.report_artefact_id, commentary);
    if (result) {
      setSaved(true);
      onChanged();
    }
  }

  return (
    <Section number={2} title="Executive summary" description="Written by a person. Nothing here is generated.">
      {isDraft ? (
        <>
          <Textarea
            value={commentary}
            onChange={(e) => {
              setCommentary(e.target.value);
              setSaved(false);
            }}
            rows={6}
            placeholder="Six to eight points a board would want in front of the numbers."
          />
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <Button variant="primary" size="sm" onClick={handleSave} busy={save.busy} busyLabel="Saving">
              Save commentary
            </Button>
            {saved && !save.busy && <span className="text-[12.5px] text-pos">Saved.</span>}
            <span className="text-[12px] text-ink-faint">Editable until the pack is signed.</span>
          </div>
          {save.error && (
            <ErrorState title="The commentary was not saved" message={save.error} className="mt-3" />
          )}
        </>
      ) : pack.commentary ? (
        <p className="text-[14px] leading-6 whitespace-pre-wrap text-ink-soft">{pack.commentary}</p>
      ) : (
        <p className="text-[13px] text-ink-faint">No commentary was written before this pack was signed.</p>
      )}
    </Section>
  );
}

/* ------------------------------------------------------- data quality (9) */

function DataQualityAppendix({ appendix }: { appendix: any }) {
  const openExceptions: any[] = appendix.open_exceptions ?? [];
  const limitations: string[] = appendix.known_limitations ?? [];
  const residuals: any[] = appendix.reconciliation_residuals ?? [];

  return (
    <Section
      number={9}
      title="Data quality appendix"
      description="Everything a reader should know before trusting a figure above"
    >
      <div className="flex flex-wrap gap-6">
        <div>
          <p className="label-caps">Unmapped value</p>
          <p
            className={cn(
              "figure mt-0.5 text-[20px] font-semibold",
              isNonZeroAmount(appendix.unmapped_value_inr) ? "text-warn" : "text-pos"
            )}
          >
            {exactAmount(appendix.unmapped_value_inr)}
          </p>
        </div>
        <div>
          <p className="label-caps">Open exceptions</p>
          <p className="figure mt-0.5 text-[20px] font-semibold">{openExceptions.length}</p>
        </div>
      </div>

      {openExceptions.length > 0 && (
        <ul className="mt-4 divide-y divide-line rounded-control border border-line">
          {openExceptions.map((e, i) => (
            <li key={i} className="flex flex-wrap items-start justify-between gap-3 px-3 py-2">
              <span className="flex min-w-0 items-start gap-2">
                <SeverityBadge severity={e.severity} />
                <span className="text-[12.5px] text-ink-soft">{e.description}</span>
              </span>
              <span className="figure text-[12.5px] font-medium whitespace-nowrap">
                {exactAmount(e.value_inr)}
              </span>
            </li>
          ))}
        </ul>
      )}

      {residuals.length > 0 && (
        <div className="mt-4">
          <p className="label-caps mb-1.5">Reconciliation residuals</p>
          <ul className="space-y-1 text-[12.5px] text-ink-muted">
            {residuals.map((r, i) => (
              <li key={i}>
                {r.check_type}: {r.status} · residual {exactAmount(r.residual_inr)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {limitations.length > 0 && (
        <div className="mt-4">
          <p className="label-caps mb-1.5">Known limitations</p>
          <ul className="space-y-1">
            {limitations.map((l, i) => (
              <li key={i} className="text-[12.5px] leading-5 text-ink-soft">
                {l}
              </li>
            ))}
          </ul>
        </div>
      )}

      {appendix.signoff_override && (
        <Callout tone="warning" className="mt-4" title="Signed with an override">
          {appendix.signoff_override.reason} — {appendix.signoff_override.by}
        </Callout>
      )}
    </Section>
  );
}

/* --------------------------------------------------------------- sign-off */

function SignOff({
  pack,
  blockingExceptions,
  blockingLoading,
  signerEmail,
  onChanged,
}: {
  pack: ReportArtefact;
  blockingExceptions: BlockingException[];
  blockingLoading: boolean;
  signerEmail: string;
  onChanged: () => void;
}) {
  const [overrideReason, setOverrideReason] = useState("");
  const sign = useApiAction(signReport);

  const blocked = blockingExceptions.length > 0;
  const canSign = !blocked || overrideReason.trim().length > 0;

  async function handleSign() {
    const result = await sign.run(pack.report_artefact_id, overrideReason.trim() || undefined);
    if (result) onChanged();
  }

  return (
    <Card className={blocked ? "border-warn-line" : undefined}>
      <CardHeader
        title="Sign off"
        description="Signing fixes this pack. It renders against this snapshot from then on."
      />
      <CardBody>
        {blockingLoading && <Skeleton className="h-4 w-56" />}

        {!blockingLoading && !blocked && (
          <Callout tone="positive">
            No blocking exception is open for {formatPeriodKey(pack.period_key)}. This pack can be signed as it
            stands.
          </Callout>
        )}

        {!blockingLoading && blocked && (
          <>
            <Callout
              tone="blocking"
              title={`${blockingExceptions.length} blocking exception${
                blockingExceptions.length === 1 ? "" : "s"
              } open for ${formatPeriodKey(pack.period_key)}`}
            >
              A blocking exception blocks output. Signing anyway requires a written reason, which is logged and
              printed in section 9 of this pack.
            </Callout>

            <StatementTable className="mt-3">
              {blockingExceptions.map((exception) => (
                <StatementRow
                  key={exception.exception_id}
                  label={exception.description}
                  note={exception.exception_class}
                  value={exactAmount(exception.value_inr)}
                />
              ))}
            </StatementTable>

            <div className="mt-3">
              <label htmlFor="override-reason" className="label-caps mb-1 block">
                Override reason — required to sign
              </label>
              <input
                id="override-reason"
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="Why this pack is being signed with these exceptions still open"
                className="h-9 w-full rounded-control border border-line-strong bg-surface px-3 text-sm"
              />
            </div>
          </>
        )}

        {sign.error && <ErrorState title="This pack was not signed" message={sign.error} className="mt-3" />}

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button variant="primary" onClick={handleSign} disabled={!canSign} busy={sign.busy} busyLabel="Signing">
            Sign as {signerEmail || "the signed-in user"}
          </Button>
          <span className="text-[12px] text-ink-faint">
            The signature records you by name. It is not an independent review, and the audit trail says so.
          </span>
        </div>
      </CardBody>
    </Card>
  );
}
