"use client";

import { useState } from "react";
import { getBalanceSheet, getPnL, type BalanceSheetResult, type PnLResult } from "@/lib/api";
import { useApiQuery } from "@/lib/useApi";
import { useWorkspace } from "@/lib/workspace";
import {
  BALANCE_SHEET_GROUPS,
  CONSUMER_LADDER_LAYOUT,
  MANUFACTURING_PNL_LAYOUT,
  keysInLayout,
  labelsInLayout,
  type LayoutRow,
} from "@/lib/statementLayout";
import { exactAmount, formatDate, formatPercent, formatStatement, humanise, isNonZeroAmount } from "@/lib/format";
import PageHeader from "@/components/app/PageHeader";
import { StatementRow, StatementSection, StatementTable } from "@/components/app/StatementTable";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, Toolbar } from "@/components/ui/Field";
import { Callout, ErrorState, SkeletonTable } from "@/components/ui/States";

/**
 * corpus/08 sections 4 and 5. The profile decides which P&L renders -- they
 * are not variants of one template -- and the balance sheet has a hard gate:
 * one that does not balance is not displayed at all.
 *
 * The two statements are fetched independently. A balance sheet that fails
 * its gate must not also take the P&L off the screen; the gate is about that
 * statement, and the reason for the failure is more useful next to the space
 * where it would have been.
 */
export default function StatementsPage() {
  const { entityId, profile, ready } = useWorkspace();
  const [periodStart, setPeriodStart] = useState("2023-04-01");
  const [periodEnd, setPeriodEnd] = useState("2023-04-30");
  const [applied, setApplied] = useState({ periodStart: "2023-04-01", periodEnd: "2023-04-30" });

  const pnl = useApiQuery(
    (token) => getPnL(token, profile, applied.periodStart, applied.periodEnd, entityId),
    [applied.periodStart, applied.periodEnd, profile, entityId],
    { enabled: ready }
  );

  const bs = useApiQuery(
    (token) => getBalanceSheet(token, applied.periodEnd, entityId),
    [applied.periodEnd, entityId],
    { enabled: ready }
  );

  const dirty = periodStart !== applied.periodStart || periodEnd !== applied.periodEnd;

  return (
    <>
      <PageHeader
        title="Statements"
        description={
          profile === "manufacturing"
            ? "The cost-structure profit and loss, and the balance sheet as at the period end."
            : "The contribution margin ladder, and the balance sheet as at the period end."
        }
        corpusRef="corpus/08 sections 4 and 5 · figures in ₹ lakh to one decimal (D-056)"
      />

      <Toolbar className="mb-4">
        <Field label="Period start" htmlFor="stmt-start">
          <input
            id="stmt-start"
            type="date"
            value={periodStart}
            onChange={(e) => setPeriodStart(e.target.value)}
            className="h-9 rounded-control border border-line-strong bg-surface px-2.5 text-sm tabular-nums"
          />
        </Field>
        <Field label="Period end / as at" htmlFor="stmt-end">
          <input
            id="stmt-end"
            type="date"
            value={periodEnd}
            onChange={(e) => setPeriodEnd(e.target.value)}
            className="h-9 rounded-control border border-line-strong bg-surface px-2.5 text-sm tabular-nums"
          />
        </Field>
        <Button
          variant={dirty ? "primary" : "secondary"}
          onClick={() => setApplied({ periodStart, periodEnd })}
          busy={pnl.loading || bs.loading}
          busyLabel="Assembling"
        >
          {dirty ? "Apply" : "Refresh"}
        </Button>
        <p className="ml-auto self-center text-[12px] text-ink-faint">
          Profile: {profile === "manufacturing" ? "Manufacturing" : "Consumer"} · change it in the top bar
        </p>
      </Toolbar>

      <div className="grid gap-4 xl:grid-cols-2">
        <ProfitAndLoss query={pnl} profile={profile} periodStart={applied.periodStart} periodEnd={applied.periodEnd} />
        <BalanceSheet query={bs} asOf={applied.periodEnd} />
      </div>
    </>
  );
}

/* ---------------------------------------------------------------------- P&L */

function ProfitAndLoss({
  query,
  profile,
  periodStart,
  periodEnd,
}: {
  query: ReturnType<typeof useApiQuery<PnLResult>>;
  profile: "manufacturing" | "consumer";
  periodStart: string;
  periodEnd: string;
}) {
  const title = profile === "manufacturing" ? "Profit and loss" : "Contribution margin ladder";
  const layout = profile === "manufacturing" ? MANUFACTURING_PNL_LAYOUT : CONSUMER_LADDER_LAYOUT;
  const data = query.data;

  const extraLines = data
    ? Object.entries(data.lines).filter(([label]) => !labelsInLayout(layout).has(label))
    : [];
  const extraSubtotals = data
    ? Object.entries(data.subtotals).filter(([key]) => !keysInLayout(layout).has(key))
    : [];

  return (
    <Card>
      <CardHeader
        title={title}
        description={`${formatDate(periodStart)} to ${formatDate(periodEnd)} · ₹ in lakh`}
        actions={data ? <Badge tone="info">Mapping v{data.mapping_version_id}</Badge> : null}
      />

      {query.error && (
        <CardBody>
          <ErrorState
            title="This statement was not produced"
            message={query.error}
            hint="A period with no approved mapping version cannot produce a statement. Nothing has been changed in your books."
            onRetry={query.reload}
          />
        </CardBody>
      )}

      {!query.error && !data && query.loading && <SkeletonTable rows={10} cols={2} />}

      {!query.error && data && (
        <>
          <CardBody className="pt-2">
            <StatementTable caption={title}>
              {layout.map((row) => (
                <LayoutRowView key={rowKey(row)} row={row} data={data} />
              ))}

              {extraLines.length > 0 && (
                <>
                  <StatementSection label="Also returned for this period" />
                  {extraLines.map(([label, amount]) => (
                    <StatementRow
                      key={label}
                      label={label}
                      value={<Amount value={amount} />}
                    />
                  ))}
                </>
              )}

              {extraSubtotals.length > 0 && (
                <>
                  <StatementSection label="Other subtotals returned" />
                  {extraSubtotals.map(([key, amount]) => (
                    <StatementRow
                      key={key}
                      label={humanise(key)}
                      kind="subtotal"
                      value={
                        key.endsWith("_pct") ? (
                          formatPercent(amount)
                        ) : (
                          <Amount value={amount} />
                        )
                      }
                    />
                  ))}
                </>
              )}
            </StatementTable>
          </CardBody>

          <UnmappedFooter value={data.unmapped_value_inr} />

          {profile === "manufacturing" && (
            <div className="border-t border-line px-5 py-3">
              <p className="text-[12px] leading-5 text-ink-faint">
                corpus/08 section 4.2 also places gross margin % and EBITDA margin % under their subtotals. The P&amp;L
                endpoint does not return them for this profile, and no ratio is computed in this app — every metric
                comes from the registry (CLAUDE.md invariant 2) — so those two rows are absent rather than derived
                here.
              </p>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

function rowKey(row: LayoutRow): string {
  return row.kind === "line" ? `line:${row.label}` : `${row.kind}:${row.key}`;
}

function LayoutRowView({ row, data }: { row: LayoutRow; data: PnLResult }) {
  if (row.kind === "line") {
    const amount = data.lines[row.label];
    // A conditional row the endpoint did not return for this company (an
    // absorption variance where there is no standard costing, say) is absent,
    // not shown as a zero it never reported.
    if (amount === undefined) return null;
    return (
      <StatementRow
        label={row.label}
        prefix={row.prefix}
        indent={row.indent}
        note={row.note}
        value={<Amount value={amount} />}
      />
    );
  }

  if (row.kind === "ratio") {
    const value = data.subtotals[row.key];
    if (value === undefined) return null;
    return <StatementRow label={row.label} kind="ratio" value={formatPercent(value)} />;
  }

  const amount = data.subtotals[row.key];
  if (amount === undefined) return null;
  return (
    <StatementRow
      label={row.label}
      prefix={row.prefix}
      kind={row.total ? "total" : "subtotal"}
      value={<Amount value={amount} />}
    />
  );
}

/** A statement figure: lakhs to one decimal on screen, exact on hover. */
function Amount({ value }: { value: string | null }) {
  return (
    <span title={value === null ? undefined : `${exactAmount(value)} exactly`}>
      {formatStatement(value, { bare: true })}
    </span>
  );
}

function UnmappedFooter({ value }: { value: string }) {
  const present = isNonZeroAmount(value);
  return (
    <div className="border-t border-line bg-surface-muted px-5 py-2.5">
      <p className="text-[12.5px]">
        <span className="label-caps mr-2">Unmapped this period</span>
        <span
          className={present ? "font-semibold text-warn" : "font-semibold text-pos"}
          title={`${exactAmount(value)} exactly`}
        >
          {formatStatement(value)}
        </span>
        {present && (
          <span className="ml-2 text-ink-muted">
            sitting in suspense and not included in any line above
          </span>
        )}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------- balance sheet */

function BalanceSheet({ query, asOf }: { query: ReturnType<typeof useApiQuery<BalanceSheetResult>>; asOf: string }) {
  const data = query.data;

  return (
    <Card>
      <CardHeader
        title="Balance sheet"
        description={`As at ${formatDate(asOf)} · ₹ in lakh`}
        actions={
          data ? (
            data.balances ? (
              <Badge tone="positive" dot>
                Balances
              </Badge>
            ) : (
              <Badge tone="blocking" dot>
                Does not balance
              </Badge>
            )
          ) : null
        }
      />

      {query.error && (
        <CardBody>
          <ErrorState
            title="This balance sheet is not displayed"
            message={query.error}
            hint="corpus/08 section 5 is a hard gate: a balance sheet that does not balance is not shown at all, badged or otherwise. The profit and loss beside it is unaffected."
            onRetry={query.reload}
          />
        </CardBody>
      )}

      {!query.error && !data && query.loading && <SkeletonTable rows={10} cols={2} />}

      {!query.error && data && (
        <>
          <CardBody className="pt-2">
            <StatementTable caption="Balance sheet">
              {BALANCE_SHEET_GROUPS.filter((group) => data.groups[group.key]).map((group) => (
                <GroupRows
                  key={group.key}
                  label={group.label}
                  lines={data.groups[group.key]}
                  total={data.group_totals[group.key]}
                />
              ))}

              {Object.keys(data.groups)
                .filter((key) => !BALANCE_SHEET_GROUPS.some((g) => g.key === key))
                .map((key) => (
                  <GroupRows
                    key={key}
                    label={humanise(key)}
                    lines={data.groups[key]}
                    total={data.group_totals[key]}
                  />
                ))}

              <StatementSection label="Proof" />
              <StatementRow label="Total assets" kind="subtotal" value={<Amount value={data.total_assets} />} />
              <StatementRow
                label="Total liabilities and equity"
                kind="total"
                value={<Amount value={data.total_liabilities_and_equity} />}
              />
            </StatementTable>
          </CardBody>

          {data.balances ? (
            <div className="border-t border-line bg-pos-soft px-5 py-2.5">
              <p className="text-[12.5px] text-pos">
                Assets equal liabilities and equity exactly. Trial balance tolerance is zero.
              </p>
            </div>
          ) : (
            <Callout tone="blocking" className="m-5">
              This balance sheet does not balance and should not be relied on.
            </Callout>
          )}

          <UnmappedFooter value={data.unmapped_value_inr} />
        </>
      )}
    </Card>
  );
}

function GroupRows({
  label,
  lines,
  total,
}: {
  label: string;
  lines: Record<string, string>;
  total: string | undefined;
}) {
  return (
    <>
      <StatementSection label={label} />
      {Object.entries(lines).map(([lineLabel, amount]) => (
        <StatementRow key={lineLabel} label={lineLabel} indent={1} value={<Amount value={amount} />} />
      ))}
      <StatementRow label={`Total ${label.toLowerCase()}`} kind="subtotal" value={<Amount value={total ?? null} />} />
    </>
  );
}
