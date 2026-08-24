"use client";

import { useState } from "react";
import { askQuestion, type AskResponse } from "@/lib/api";
import { useApiAction } from "@/lib/useApi";
import { useWorkspace } from "@/lib/workspace";
import { METRIC_UNITS } from "@/lib/metricUnits";
import {
  exactAmount,
  exactMetricValue,
  formatAmount,
  formatMetricValue,
  formatPeriodKey,
} from "@/lib/format";
import PageHeader from "@/components/app/PageHeader";
import Citation from "@/components/app/Citation";
import Badge, { type Tone } from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import Disclosure, { CodeBlock } from "@/components/ui/Disclosure";
import { Table, TBody, TD, TFrame, TH, THead, TR } from "@/components/ui/TableExports";
import { Callout, EmptyState, ErrorState, Skeleton } from "@/components/ui/States";

/**
 * corpus/07 and corpus/08 section 2: question, answer, citation, view SQL.
 *
 * Four outcomes, and three of them are not an answer. corpus/07's whole point
 * is that refusing well is a feature: a question outside the supported set,
 * one blocked on an open decision, and one whose data has not been ingested
 * are different situations, and each is said differently here rather than all
 * three collapsing into "no result".
 */
export default function AskPage() {
  const { entityId, profile } = useWorkspace();
  const [question, setQuestion] = useState("How much cash do we have?");
  const [asked, setAsked] = useState<string | null>(null);
  const [response, setResponse] = useState<AskResponse | null>(null);

  const ask = useApiAction(askQuestion);

  async function submit(text?: string) {
    const q = (text ?? question).trim();
    if (!q) return;
    setQuestion(q);
    setAsked(q);
    setResponse(null);
    const result = await ask.run(q, entityId, profile);
    if (result) setResponse(result);
  }

  return (
    <>
      <PageHeader
        title="Ask"
        description="Ask about the numbers in your own words. Every answer arrives with the metric definition, the period, the rows it read and the query that produced it — or with a straight explanation of why there is no answer."
        corpusRef="corpus/07"
      />

      <Card className="mb-4">
        <CardBody>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
            className="flex flex-col gap-2 sm:flex-row"
          >
            <label htmlFor="ask-question" className="sr-only">
              Your question
            </label>
            <input
              id="ask-question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="What was net revenue last month?"
              className="h-11 flex-1 rounded-control border border-line-strong bg-surface px-3.5 text-[15px]"
            />
            <Button type="submit" variant="primary" className="h-11 px-6" busy={ask.busy} busyLabel="Working">
              Ask
            </Button>
          </form>
          <p className="mt-2 text-[12px] text-ink-muted">
            Entity {entityId} · {profile === "manufacturing" ? "Manufacturing" : "Consumer"} — both come from the top
            bar, so the question does not have to carry them.
          </p>
        </CardBody>
      </Card>

      {ask.error && (
        <ErrorState
          title="The question could not be sent"
          message={ask.error}
          hint="Nothing was queried. Try again."
          onRetry={() => submit(asked ?? undefined)}
        />
      )}

      {ask.busy && (
        <Card>
          <CardBody className="space-y-3">
            <Skeleton className="h-3 w-40" />
            <Skeleton className="h-9 w-64" />
            <Skeleton className="h-3 w-full" />
          </CardBody>
        </Card>
      )}

      {!ask.busy && !response && !ask.error && (
        <Card>
          <EmptyState
            icon="search"
            title="Nothing asked yet"
            description="Type a question above. If it is outside what the system can answer exactly, it will say so and point you at the nearest question it can."
          />
        </Card>
      )}

      {!ask.busy && response && <Answer response={response} asked={asked} onAsk={submit} />}
    </>
  );
}

/* ------------------------------------------------------------------ answer */

const STATUS: Record<string, { tone: Tone; label: string }> = {
  ok: { tone: "positive", label: "Answered" },
  blocked: { tone: "warning", label: "Blocked by an open decision" },
  unavailable: { tone: "warning", label: "Data not available yet" },
  refused: { tone: "neutral", label: "Not a supported question" },
  rejected: { tone: "blocking", label: "Rejected" },
  error: { tone: "blocking", label: "Failed" },
};

function Answer({
  response,
  asked,
  onAsk,
}: {
  response: AskResponse;
  asked: string | null;
  onAsk: (text: string) => void;
}) {
  const status = STATUS[response.status] ?? { tone: "neutral" as Tone, label: response.status };

  return (
    <Card>
      <CardHeader
        title={asked || response.question}
        description={response.intent ? `Read as: ${response.intent.replace(/_/g, " ")}` : undefined}
        actions={
          <Badge tone={status.tone} dot>
            {status.label}
          </Badge>
        }
      />

      <CardBody>
        {response.status === "ok" && <OkAnswer response={response} />}
        {(response.status === "refused" || response.status === "rejected") && (
          <RefusedAnswer response={response} onAsk={onAsk} />
        )}
        {(response.status === "blocked" || response.status === "unavailable") && (
          <BlockedAnswer response={response} />
        )}
        {!["ok", "refused", "rejected", "blocked", "unavailable"].includes(response.status) && (
          <Callout tone="blocking" title="Something went wrong">
            {response.result?.reason || "No reason was returned."}
          </Callout>
        )}
      </CardBody>

      {response.result?.sql_text && (
        <div className="border-t border-line px-5 py-3">
          <Disclosure label="View the SQL that produced this" openLabel="Hide the SQL">
            <CodeBlock>{response.result.sql_text}</CodeBlock>
            <p className="mt-2 text-[12px] leading-5 text-ink-faint">
              No model wrote this. The question was turned into a validated semantic form, and a deterministic
              compiler emitted the SQL from it — there is no path in this system by which a model produces SQL.
            </p>
          </Disclosure>
        </div>
      )}
    </Card>
  );
}

function OkAnswer({ response }: { response: AskResponse }) {
  const result = response.result;
  const citation = response.citation;
  const unit = citation ? METRIC_UNITS[citation.metric] : undefined;

  const scalar =
    result?.value != null && typeof result.value !== "object"
      ? String(result.value)
      : null;

  return (
    <>
      {scalar !== null && (
        <p
          className="figure text-[34px] leading-11 font-semibold tracking-[-0.02em]"
          title={citation ? exactMetricValue(scalar, unit) : undefined}
        >
          {citation ? formatMetricValue(citation.metric, scalar, unit, "crore") : scalar}
        </p>
      )}

      {result?.series && result.series.length > 0 && (
        <TFrame className="mt-4 rounded-card border border-line">
          <Table>
            <THead>
              <TR>
                <TH>Period</TH>
                <TH align="right">Value</TH>
              </TR>
            </THead>
            <TBody>
              {result.series.map((point) => (
                <TR key={point.period}>
                  <TD>{formatPeriodKey(point.period)}</TD>
                  <TD numeric={point.status === "ok"} align="right">
                    {point.status === "ok" ? (
                      <span title={citation ? exactMetricValue(point.value, unit) : undefined}>
                        {citation
                          ? formatMetricValue(citation.metric, point.value, unit, "crore")
                          : point.value}
                      </span>
                    ) : (
                      <span className="text-[12.5px] text-warn">
                        Not available — {point.reason || point.status}
                      </span>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </TFrame>
      )}

      {result?.bridge && <Bridge bridge={result.bridge} />}

      {citation ? (
        <div className="mt-4 border-t border-line pt-3">
          <Citation citation={citation} />
        </div>
      ) : (
        <Callout tone="blocking" className="mt-4" title="No citation was returned">
          A figure without a citation is not a figure this product shows.
        </Callout>
      )}
    </>
  );
}

function Bridge({ bridge }: { bridge: NonNullable<NonNullable<AskResponse["result"]>["bridge"]> }) {
  if (!bridge.configured) {
    return (
      <Callout tone="warning" className="mt-4" title="No decomposition is available">
        {bridge.reason || "This movement has no decomposition convention defined."}
      </Callout>
    );
  }

  return (
    <div className="mt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="label-caps">What moved</p>
        <p className="text-[13px]">
          Total movement{" "}
          <span className="figure font-semibold" title={exactAmount(bridge.total_delta)}>
            {formatAmount(bridge.total_delta, { scale: "lakh" })}
          </span>
        </p>
      </div>

      <ul className="mt-2 divide-y divide-line rounded-card border border-line">
        {bridge.components.map((component) => (
          <li key={component.label} className="flex items-center justify-between gap-4 px-3 py-2 text-[13px]">
            <span className="text-ink-soft">
              {component.label}
              {component.is_residual && (
                <Badge tone="warning" className="ml-2">
                  residual
                </Badge>
              )}
            </span>
            <span className="figure font-medium whitespace-nowrap" title={exactAmount(component.value)}>
              {formatAmount(component.value, { scale: "lakh" })}
            </span>
          </li>
        ))}
      </ul>

      {bridge.components_sum_to_total ? (
        <p className="mt-2 text-[12.5px] text-pos">These components sum to the total movement exactly.</p>
      ) : (
        <Callout tone="blocking" className="mt-2" title="This decomposition is incomplete">
          The components above do not sum to the total movement. The gap is reported rather than swept into an
          &ldquo;other&rdquo; line, because a decomposition presented as complete when it is not is worse than none.
        </Callout>
      )}
    </div>
  );
}

function RefusedAnswer({ response, onAsk }: { response: AskResponse; onAsk: (text: string) => void }) {
  const refusal = response.refusal;
  return (
    <>
      <p className="text-[14px] leading-6 text-ink-soft">
        {refusal?.reason || "This question is outside the set the system can answer exactly."}
      </p>

      {refusal?.refusal_class && (
        <p className="mt-1.5 text-[12px] text-ink-faint">
          Refusal class: <span className="font-mono">{refusal.refusal_class}</span>
        </p>
      )}

      {refusal?.nearest_supported_question && (
        <div className="mt-4">
          <p className="label-caps mb-1.5">A question it can answer</p>
          <Button size="sm" variant="secondary" onClick={() => onAsk(refusal.nearest_supported_question!)}>
            {refusal.nearest_supported_question}
          </Button>
        </div>
      )}

      {refusal?.clarifying_options && refusal.clarifying_options.length > 0 && (
        <div className="mt-4">
          <p className="label-caps mb-1.5">Did you mean</p>
          <div className="flex flex-wrap gap-2">
            {refusal.clarifying_options.map((option) => (
              <Button key={option} size="sm" variant="secondary" onClick={() => onAsk(option)}>
                {option}
              </Button>
            ))}
          </div>
        </div>
      )}

      <Callout tone="neutral" className="mt-4">
        Refusing is deliberate. A question the system cannot answer exactly gets a refusal rather than an
        approximation, because an approximation in a board pack is the failure this product exists to prevent.
      </Callout>
    </>
  );
}

function BlockedAnswer({ response }: { response: AskResponse }) {
  const decisions = response.result?.blocking_decisions ?? [];
  return (
    <>
      <p className="text-[14px] leading-6 text-ink-soft">
        {response.refusal?.reason ||
          response.result?.reason ||
          "This figure depends on something that has not been settled yet."}
      </p>

      {decisions.length > 0 && (
        <div className="mt-3">
          <p className="label-caps mb-1.5">Waiting on</p>
          <div className="flex flex-wrap gap-1.5">
            {decisions.map((decision) => (
              <Badge key={decision} tone="warning">
                {decision}
              </Badge>
            ))}
          </div>
          <p className="mt-2 text-[12.5px] text-ink-muted">
            Each of these is an accounting judgement recorded as open. Until one is settled, any number here would be
            a guess dressed as a figure, so none is shown.
          </p>
        </div>
      )}
    </>
  );
}
