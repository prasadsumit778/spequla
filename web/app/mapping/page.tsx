"use client";

import { useState } from "react";
import {
  createMappingRun,
  freezeMappingRun,
  getReviewQueue,
  type FreezeResult,
  type MappingRunResult,
  type QueueRow,
} from "@/lib/api";
import { useApiAction } from "@/lib/useApi";
import { useWorkspace } from "@/lib/workspace";
import { exactAmount, formatDate, formatPercent } from "@/lib/format";
import PageHeader from "@/components/app/PageHeader";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, Input, Toolbar } from "@/components/ui/Field";
import { Table, TBody, TD, TFrame, TH, THead, TR } from "@/components/ui/TableExports";
import { Callout, EmptyState, ErrorState } from "@/components/ui/States";

const SUSPENSE = "suspense.unmapped";

/**
 * corpus/06 section 4: extract, apply exact rules, auto-accept what is safe,
 * queue the rest by rupee value. Section 4.3 requires the running coverage
 * and the unmapped rupee value to be on screen at all times while reviewing,
 * which is what the bar above the queue is for -- and it is a rupee figure,
 * never a percentage on its own.
 */
export default function MappingPage() {
  const { entityId, ready } = useWorkspace();
  const [effectiveFrom, setEffectiveFrom] = useState("2023-04-01");
  const [versionNo, setVersionNo] = useState(1);
  const [changeReason, setChangeReason] = useState("");

  const [run, setRun] = useState<MappingRunResult | null>(null);
  const [queue, setQueue] = useState<QueueRow[] | null>(null);
  const [freeze, setFreeze] = useState<FreezeResult | null>(null);

  const runAction = useApiAction(async (token: string) => {
    const created = await createMappingRun(token, entityId, versionNo, effectiveFrom, changeReason || undefined);
    const rows = await getReviewQueue(token, created.mapping_version_id);
    return { created, rows };
  });

  const freezeAction = useApiAction(async (token: string, mappingVersionId: number) =>
    freezeMappingRun(token, mappingVersionId, entityId)
  );

  async function handleRun() {
    setFreeze(null);
    const result = await runAction.run();
    if (!result) return;
    setRun(result.created);
    setQueue(result.rows);
  }

  async function handleFreeze() {
    if (!run) return;
    const result = await freezeAction.run(run.mapping_version_id);
    if (result) setFreeze(result);
  }

  // corpus/06 section 4.3: the queue is ordered by rupee value descending and
  // each row carries the running state after it, so the last row is where
  // coverage stands once the whole queue has been worked through. Read back
  // from the API, never recomputed here.
  const finalRow = queue && queue.length > 0 ? queue[queue.length - 1] : null;

  return (
    <>
      <PageHeader
        title="Mapping review"
        description="Every ledger account gets a canonical class. What the rules can decide safely is auto-accepted; everything else is queued here, largest rupee value first, so the biggest unknowns are answered before the small ones."
        corpusRef="corpus/06 section 4"
      />

      <Toolbar className="mb-4">
        <Field label="Effective from" htmlFor="map-effective">
          <input
            id="map-effective"
            type="date"
            value={effectiveFrom}
            onChange={(e) => setEffectiveFrom(e.target.value)}
            className="h-9 rounded-control border border-line-strong bg-surface px-2.5 text-sm tabular-nums"
          />
        </Field>
        <Input
          label="Version number"
          type="number"
          min={1}
          value={versionNo}
          onChange={(e) => setVersionNo(Number(e.target.value))}
          fieldClassName="w-32"
        />
        <Input
          label="Change reason"
          placeholder="Why this version exists (optional)"
          value={changeReason}
          onChange={(e) => setChangeReason(e.target.value)}
          fieldClassName="min-w-[240px] flex-1"
        />
        <Button variant="primary" onClick={handleRun} busy={runAction.busy} busyLabel="Running" disabled={!ready}>
          Run mapping pass
        </Button>
      </Toolbar>

      {runAction.error && (
        <ErrorState
          title="The mapping pass did not run"
          message={runAction.error}
          hint="No mapping version was created. Nothing about the existing mapping has changed."
          className="mb-4"
        />
      )}

      {!run && !runAction.busy && !runAction.error && (
        <Card>
          <EmptyState
            title="No mapping pass has been run in this session"
            description="Running a pass creates a draft mapping version, applies the rule library to every ledger account, and queues everything the rules could not decide on their own. Nothing is frozen until you freeze it."
          />
        </Card>
      )}

      {run && (
        <div className="mb-4 grid gap-4 lg:grid-cols-3">
          <RunSummary run={run} />
          <FreezeCard
            run={run}
            freeze={freeze}
            busy={freezeAction.busy}
            error={freezeAction.error}
            onFreeze={handleFreeze}
            effectiveFrom={effectiveFrom}
          />
        </div>
      )}

      {queue && (
        <Card>
          <CardHeader
            title="Review queue"
            description={`${queue.length} account${queue.length === 1 ? "" : "s"} · ordered by rupee value, descending`}
          />

          {finalRow && (
            <div className="sticky top-[52px] z-10 flex flex-wrap items-center gap-x-8 gap-y-2 border-b border-line bg-surface-muted px-5 py-3">
              <div>
                <p className="label-caps">Unmapped value, right now</p>
                <p
                  className={`figure text-[22px] leading-7 font-semibold ${
                    finalRow.unmapped_value_inr > 0 ? "text-warn" : "text-pos"
                  }`}
                  title="Absolute rupees, as corpus/06 section 4.3 requires: a rupee figure, not a percentage"
                >
                  {exactAmount(String(finalRow.unmapped_value_inr))}
                </p>
              </div>
              <div>
                <p className="label-caps">Coverage after the whole queue</p>
                <p className="figure text-[22px] leading-7 font-semibold">
                  {formatPercent(finalRow.running_pct_mapped, { digits: 2 })}
                </p>
              </div>
              <p className="max-w-sm text-[12px] leading-5 text-ink-faint">
                The rupee figure is the one that decides whether to keep going. A percentage alone does not tell a
                reviewer what is still at stake.
              </p>
            </div>
          )}

          {queue.length === 0 ? (
            <EmptyState
              icon="check"
              title="Nothing was queued"
              description="Every account was decided by the rule library. There is nothing left for a human to review in this version."
            />
          ) : (
            <TFrame>
              <Table>
                <THead>
                  <TR>
                    <TH>Ledger account</TH>
                    <TH>Canonical class</TH>
                    <TH>Proposed by</TH>
                    <TH>Approved by</TH>
                    <TH align="right">Value</TH>
                    <TH align="right">Running coverage</TH>
                  </TR>
                </THead>
                <TBody>
                  {queue.map((row) => (
                    <TR key={row.source_record_id}>
                      <TD className="font-medium text-ink">{row.source_account_name}</TD>
                      <TD>
                        {row.canonical_class === SUSPENSE ? (
                          <Badge tone="warning" dot>
                            unmapped — in suspense
                          </Badge>
                        ) : (
                          <span className="font-mono text-[11.5px] text-ink">{row.canonical_class}</span>
                        )}
                      </TD>
                      <TD>{row.proposal_source}</TD>
                      <TD>{row.approved_by || "—"}</TD>
                      <TD numeric title="Absolute rupees">
                        {exactAmount(row.period_value_inr)}
                      </TD>
                      <TD numeric>{formatPercent(row.running_pct_mapped, { digits: 2 })}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </TFrame>
          )}
        </Card>
      )}
    </>
  );
}

function RunSummary({ run }: { run: MappingRunResult }) {
  return (
    <Card className="lg:col-span-2">
      <CardHeader
        title={`Mapping version ${run.mapping_version_id}`}
        description="What the pass decided"
        actions={<Badge tone="info">draft</Badge>}
      />
      <CardBody>
        <div className="grid gap-4 sm:grid-cols-3">
          <Stat
            label="Auto-accepted"
            value={run.auto_accepted}
            note="Decided by an exact rule. Never a judgement class."
          />
          <Stat
            label="Needs a human"
            value={run.human_approved}
            note="Judgement classes and rule conflicts."
          />
          <Stat
            label="Deferred to suspense"
            value={run.deferred_to_suspense}
            note="No confident proposal. Excluded from every statement."
            tone={run.deferred_to_suspense > 0 ? "warn" : undefined}
          />
        </div>
        <dl className="mt-4 grid gap-4 border-t border-line pt-3 sm:grid-cols-2">
          <div>
            <dt className="label-caps">Total value classified</dt>
            <dd className="figure mt-0.5 text-[16px] font-semibold" title="Absolute rupees">
              {exactAmount(run.total_value_inr)}
            </dd>
          </div>
          <div>
            <dt className="label-caps">Mapped value</dt>
            <dd className="figure mt-0.5 text-[16px] font-semibold" title="Absolute rupees">
              {exactAmount(run.mapped_value_inr)}
            </dd>
          </div>
        </dl>
        <p className="mt-3 text-[12px] leading-5 text-ink-faint">
          Auto-accept never fires on a judgement class — one-off exceptionals, owner remuneration, related party
          charges, absorption variance, bill discounting and related-party debt always go to a person.
        </p>
      </CardBody>
    </Card>
  );
}

function Stat({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: number;
  note: string;
  tone?: "warn";
}) {
  return (
    <div>
      <p className="label-caps">{label}</p>
      <p className={`figure mt-0.5 text-[24px] leading-8 font-semibold ${tone === "warn" ? "text-warn" : ""}`}>
        {value}
      </p>
      <p className="mt-0.5 text-[12px] leading-4 text-ink-muted">{note}</p>
    </div>
  );
}

function FreezeCard({
  run,
  freeze,
  busy,
  error,
  onFreeze,
  effectiveFrom,
}: {
  run: MappingRunResult;
  freeze: FreezeResult | null;
  busy: boolean;
  error: string | null;
  onFreeze: () => void;
  effectiveFrom: string;
}) {
  return (
    <Card>
      <CardHeader title="Freeze" description={`Effective from ${formatDate(effectiveFrom)}`} />
      <CardBody>
        <p className="text-[13px] leading-5 text-ink-muted">
          Freezing approves version {run.mapping_version_id} and lets statements and metrics be assembled against it.
          It is versioned forward, never overwritten — an earlier version keeps producing the numbers it produced.
        </p>

        <Button variant="primary" className="mt-3 w-full" onClick={onFreeze} busy={busy} busyLabel="Freezing">
          Freeze this version
        </Button>

        {error && (
          <Callout tone="blocking" title="Freeze blocked" className="mt-3">
            {error}
          </Callout>
        )}

        {freeze && (
          <Callout
            tone={freeze.passed ? "positive" : "blocking"}
            title={freeze.passed ? "Frozen" : "Not frozen"}
            className="mt-3"
          >
            <p>{freeze.reason}</p>
            {freeze.coverage_pct !== null && (
              <p className="mt-1">Coverage {formatPercent(freeze.coverage_pct, { digits: 2 })}</p>
            )}
            {freeze.unmapped_value_inr !== null && (
              <p className="mt-1">Unmapped {exactAmount(freeze.unmapped_value_inr)}</p>
            )}
          </Callout>
        )}
      </CardBody>
    </Card>
  );
}
