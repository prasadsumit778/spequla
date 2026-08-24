"use client";

import { useState } from "react";
import {
  getConsumerLadder,
  getManufacturingOperating,
  type ConsumerLadder,
  type ManufacturingOperating,
} from "@/lib/api";
import { useApiQuery } from "@/lib/useApi";
import { useWorkspace } from "@/lib/workspace";
import {
  exactAmount,
  formatDate,
  formatPercent,
  formatQuantity,
  formatStatement,
  humanise,
  isNonZeroAmount,
} from "@/lib/format";
import PageHeader from "@/components/app/PageHeader";
import NotAvailable from "@/components/app/NotAvailable";
import { StatementRow, StatementTable } from "@/components/app/StatementTable";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, Toolbar } from "@/components/ui/Field";
import { Table, TBody, TD, TFrame, TH, THead, TR } from "@/components/ui/TableExports";
import { Callout, ErrorState, SkeletonTable } from "@/components/ui/States";

/**
 * corpus/03 section 6 (manufacturing) and section 7 (consumer). These read the
 * operating facts directly -- production output, channel order lines -- rather
 * than the general ledger, which is why they are a separate screen from the
 * statements.
 */
export default function OperatingPage() {
  const { profile } = useWorkspace();

  return (
    <>
      <PageHeader
        title="Operating metrics"
        description={
          profile === "consumer"
            ? "The contribution margin ladder as the operating data reports it, and where it disagrees with the books."
            : "Volume, yield and cost per unit from production output — the layer under the profit and loss."
        }
        corpusRef={
          profile === "consumer"
            ? "corpus/03 section 7 · corpus/08 section 4.1 · figures in ₹ lakh (D-056)"
            : "corpus/03 section 6"
        }
      />

      {profile === "consumer" ? <ConsumerView /> : <ManufacturingView />}
    </>
  );
}

/* ------------------------------------------------------------------ consumer */

function ConsumerView() {
  const { entityId, ready } = useWorkspace();
  const [start, setStart] = useState("2025-04-01");
  const [end, setEnd] = useState("2025-04-30");
  const [applied, setApplied] = useState({ start: "2025-04-01", end: "2025-04-30" });

  const ladder = useApiQuery(
    (token) => getConsumerLadder(token, applied.start, applied.end, entityId),
    [applied.start, applied.end, entityId],
    { enabled: ready }
  );

  const dirty = start !== applied.start || end !== applied.end;

  return (
    <>
      <Toolbar className="mb-4">
        <Field label="From" htmlFor="ladder-start">
          <input
            id="ladder-start"
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="h-9 rounded-control border border-line-strong bg-surface px-2.5 text-sm tabular-nums"
          />
        </Field>
        <Field label="To" htmlFor="ladder-end">
          <input
            id="ladder-end"
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="h-9 rounded-control border border-line-strong bg-surface px-2.5 text-sm tabular-nums"
          />
        </Field>
        <Button
          variant={dirty ? "primary" : "secondary"}
          onClick={() => setApplied({ start, end })}
          busy={ladder.loading}
          busyLabel="Assembling"
        >
          {dirty ? "Apply" : "Refresh"}
        </Button>
      </Toolbar>

      {ladder.error && (
        <ErrorState
          title="The ladder was not assembled"
          message={ladder.error}
          hint="A period with no approved mapping version cannot produce one. Nothing has changed in your data."
          onRetry={ladder.reload}
        />
      )}

      {!ladder.error && !ladder.data && ladder.loading && (
        <Card>
          <SkeletonTable rows={12} cols={2} />
        </Card>
      )}

      {!ladder.error && ladder.data && <Ladder data={ladder.data} start={applied.start} end={applied.end} />}
    </>
  );
}

function Ladder({ data, start, end }: { data: ConsumerLadder; start: string; end: string }) {
  const unmapped = isNonZeroAmount(data.unmapped_value_inr);
  const residual = data.order_file_to_books_residual;

  return (
    <div className="grid gap-4 xl:grid-cols-3">
      <Card className="xl:col-span-2">
        <CardHeader
          title="Contribution margin ladder"
          description={`${formatDate(start)} to ${formatDate(end)} · ₹ in lakh`}
          actions={<Badge tone="info">Mapping v{data.mapping_version_id}</Badge>}
        />
        <CardBody className="pt-2">
          <StatementTable caption="Contribution margin ladder">
            <StatementRow label="GMV" kind="subtotal" value={<Figure value={data.gmv_total} />} />
            {Object.entries(data.gmv_by_model).map(([model, value]) => (
              <StatementRow
                key={`gmv-${model}`}
                kind="memo"
                indent={1}
                label={`of which ${humanise(model).toLowerCase()}`}
                // CLAUDE.md invariant 13: marketplace GMV is volume flowing
                // through someone else's inventory. It is a memo, and it is
                // never summed into revenue.
                note={model === "marketplace" ? "volume, not revenue" : undefined}
                value={<Figure value={value} />}
              />
            ))}

            <StatementRow
              label="Discount"
              prefix="less"
              indent={1}
              note="disclosed; already reflected in net revenue"
              value={<Figure value={data.discount} />}
            />
            <StatementRow label="Net revenue" prefix="=" kind="subtotal" value={<Figure value={data.net_revenue} />} />
            {Object.entries(data.net_revenue_by_model).map(([model, value]) => (
              <StatementRow
                key={`nr-${model}`}
                kind="memo"
                indent={1}
                label={`of which ${humanise(model).toLowerCase()}`}
                value={<Figure value={value} />}
              />
            ))}

            <StatementRow
              label="Cost of goods sold"
              prefix="less"
              indent={1}
              note="buyout lines only"
              value={<Figure value={data.cogs} />}
            />
            <StatementRow label="Gross margin" prefix="=" kind="subtotal" value={<Figure value={data.gross_margin} />} />
            <StatementRow label="Gross margin %" kind="ratio" value={formatPercent(data.gross_margin_pct)} />

            <StatementRow
              label="Operating cost"
              prefix="less"
              indent={1}
              note="servicing, fulfilment, offline manpower and rent"
              value={<Figure value={data.operating_cost_cm1} />}
            />
            <StatementRow label="CM1" prefix="=" kind="subtotal" value={<Figure value={data.cm1} />} />
            <StatementRow label="CM1 %" kind="ratio" value={formatPercent(data.cm1_pct)} />

            <StatementRow
              label="Marketing"
              prefix="less"
              indent={1}
              note="the CM1 to CM2 step, never inside CM1"
              value={<Figure value={data.marketing} />}
            />
            <StatementRow label="CM2" prefix="=" kind="subtotal" value={<Figure value={data.cm2} />} />
            <StatementRow label="CM2 %" kind="ratio" value={formatPercent(data.cm2_pct)} />

            <StatementRow
              label="Corporate overhead"
              prefix="less"
              indent={1}
              note="never allocated"
              value={<Figure value={data.corporate_overhead} />}
            />
            <StatementRow label="EBITDA" prefix="=" kind="total" value={<Figure value={data.ebitda} />} />
          </StatementTable>
        </CardBody>

        <div className="border-t border-line bg-surface-muted px-5 py-2.5">
          <p className="text-[12.5px]">
            <span className="label-caps mr-2">Unmapped this period</span>
            <span
              className={unmapped ? "font-semibold text-warn" : "font-semibold text-pos"}
              title={`${exactAmount(data.unmapped_value_inr)} exactly`}
            >
              {formatStatement(data.unmapped_value_inr)}
            </span>
          </p>
        </div>
      </Card>

      <Card className="self-start">
        <CardHeader title="Order file against the books" description="Reported, never resolved" />
        <CardBody>
          <StatementTable>
            <StatementRow
              label="Order file, buyout revenue"
              value={<Figure value={residual.order_file_buyout_revenue} />}
            />
            <StatementRow label="Books, product sales" value={<Figure value={residual.books_revenue} />} />
            <StatementRow
              label="Residual"
              kind="total"
              tone={isNonZeroAmount(residual.residual) ? "warning" : "positive"}
              value={<Figure value={residual.residual} />}
            />
          </StatementTable>
          <Callout tone="neutral" className="mt-3">
            Where the order file and the books disagree, both figures are stated and the gap is reported. Neither is
            picked as the winner — the first time a CFO finds that one was chosen silently, every other number
            becomes suspect.
          </Callout>
        </CardBody>
      </Card>
    </div>
  );
}

function Figure({ value }: { value: string | null }) {
  return (
    <span title={value === null ? undefined : `${exactAmount(value)} exactly`}>
      {formatStatement(value, { bare: true })}
    </span>
  );
}

/* ------------------------------------------------------------- manufacturing */

function ManufacturingView() {
  const { entityId, ready } = useWorkspace();
  const [period, setPeriod] = useState("2022-04");

  const operating = useApiQuery(
    (token) => getManufacturingOperating(token, period, entityId),
    [period, entityId],
    { enabled: ready }
  );

  return (
    <>
      <Toolbar className="mb-4">
        <Field label="Period" htmlFor="mfg-period">
          <input
            id="mfg-period"
            type="month"
            value={period}
            onChange={(e) => e.target.value && setPeriod(e.target.value)}
            className="h-9 rounded-control border border-line-strong bg-surface px-2.5 text-sm tabular-nums"
          />
        </Field>
        <Button variant="secondary" onClick={operating.reload} busy={operating.loading} busyLabel="Loading">
          Refresh
        </Button>
      </Toolbar>

      {operating.error && (
        <ErrorState
          title="Operating metrics were not produced"
          message={operating.error}
          hint="Nothing has changed in your data."
          onRetry={operating.reload}
        />
      )}

      {!operating.error && !operating.data && operating.loading && (
        <Card>
          <SkeletonTable rows={6} cols={6} />
        </Card>
      )}

      {!operating.error && operating.data && <ManufacturingBody data={operating.data} />}
    </>
  );
}

function ManufacturingBody({ data }: { data: ManufacturingOperating }) {
  const entity = data.entity;

  // Every product carries its own reason for the two metrics that cannot be
  // computed. They are usually the same reason; showing the distinct set in
  // full beats a tooltip nobody on a phone can reach.
  const unavailableReasons = Array.from(
    new Set(
      data.products.flatMap((p) => [
        p.realisation_per_unit_unavailable_reason,
        p.capacity_utilisation_unavailable_reason,
      ])
    )
  ).filter(Boolean);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Entity level"
          description="Raw material and conversion cost per unit"
          actions={<Badge tone="info">Mapping v{data.mapping_version_id}</Badge>}
        />
        <CardBody>
          {entity.status === "ok" ? (
            <>
              <dl className="grid gap-4 sm:grid-cols-3">
                <div>
                  <dt className="label-caps">Total volume produced</dt>
                  <dd className="figure mt-0.5 text-[22px] font-semibold">
                    {formatQuantity(entity.total_volume_produced)}
                    {entity.common_uom && (
                      <span className="ml-1.5 text-[13px] font-normal text-ink-muted">{entity.common_uom}</span>
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="label-caps">Raw material cost per unit</dt>
                  <dd className="figure mt-0.5 text-[22px] font-semibold">
                    {exactAmount(entity.rm_cost_per_unit)}
                  </dd>
                </div>
                <div>
                  <dt className="label-caps">Conversion cost per unit</dt>
                  <dd className="figure mt-0.5 text-[22px] font-semibold">
                    {exactAmount(entity.conversion_cost_per_unit)}
                  </dd>
                </div>
              </dl>
              {entity.conversion_cost_components.length > 0 && (
                <p className="mt-3 text-[12px] leading-5 text-ink-faint">
                  Conversion cost is built from {entity.conversion_cost_components.join(", ")}. Factory overhead is
                  not among them — it has no declared canonical class, so it is left out rather than approximated
                  into the figure.
                </p>
              )}
            </>
          ) : (
            <NotAvailable reason={entity.reason} />
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="By product" description={`${data.products.length} product${data.products.length === 1 ? "" : "s"}`} />
        <TFrame>
          <Table>
            <THead>
              <TR>
                <TH>Product</TH>
                <TH>Unit</TH>
                <TH align="right">Produced</TH>
                <TH align="right">Rejected</TH>
                <TH align="right">Yield</TH>
                <TH align="right">Rejection</TH>
                <TH align="right">Realisation / unit</TH>
                <TH align="right">Capacity used</TH>
              </TR>
            </THead>
            <TBody>
              {data.products.map((product) => (
                <TR key={product.product_key}>
                  <TD className="font-medium text-ink">{product.product_name}</TD>
                  <TD>{product.uom ?? "—"}</TD>
                  {product.status === "ok" ? (
                    <>
                      <TD numeric>{formatQuantity(product.volume_produced)}</TD>
                      <TD numeric>{formatQuantity(product.qty_rejected)}</TD>
                      <TD numeric>{formatPercent(product.yield_pct)}</TD>
                      <TD numeric>{formatPercent(product.rejection_pct)}</TD>
                    </>
                  ) : (
                    <TD colSpan={4}>
                      <NotAvailable reason={product.reason} compact />
                      <span className="ml-2 text-[12px] text-ink-muted">{product.reason}</span>
                    </TD>
                  )}
                  <TD align="right">
                    <NotAvailable reason={product.realisation_per_unit_unavailable_reason} compact />
                  </TD>
                  <TD align="right">
                    <NotAvailable reason={product.capacity_utilisation_unavailable_reason} compact />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </TFrame>

        {unavailableReasons.length > 0 && (
          <div className="border-t border-line px-5 py-3">
            <p className="label-caps mb-1.5">Why realisation per unit and capacity used are blank</p>
            <ul className="space-y-1">
              {unavailableReasons.map((reason) => (
                <li key={reason} className="text-[12.5px] leading-5 text-ink-muted">
                  {reason}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>
    </div>
  );
}
