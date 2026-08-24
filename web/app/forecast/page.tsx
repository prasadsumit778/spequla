"use client";

import { useState } from "react";
import {
  createForecastScenario,
  listForecastScenarios,
  runForecastScenario,
  type CostDrivers,
  type ForecastDrivers,
  type ForecastRunResult,
  type ForecastScenarioSummary,
  type OnlineChannelDrivers,
  type StoreFormatDrivers,
} from "@/lib/api";
import { useApiAction, useApiQuery } from "@/lib/useApi";
import { useWorkspace } from "@/lib/workspace";
import { exactAmount, formatDate, formatPercent, formatStatement } from "@/lib/format";
import PageHeader from "@/components/app/PageHeader";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, Input, Toolbar } from "@/components/ui/Field";
import { Table, TBody, TD, TFrame, TH, THead, TR } from "@/components/ui/TableExports";
import { Callout, EmptyState, ErrorState, SkeletonTable } from "@/components/ui/States";

const STORE_FORMATS = ["COCO", "COFO", "FOCO", "FOFO"] as const;

type FormatFormState = {
  enabled: boolean;
  storesAddedPerYear: string; // comma-separated, one entry per forecast year
  year1AvgAnnualSalesInr: string;
  priceGrowthPct: string;
  customerGrowthPct: string;
};

type OnlineRowState = { channelName: string; ordersGrowthPct: string; priceGrowthPct: string };

const DEFAULT_FORMAT_STATE: FormatFormState = {
  enabled: false, storesAddedPerYear: "", year1AvgAnnualSalesInr: "", priceGrowthPct: "4", customerGrowthPct: "2.5",
};

/**
 * corpus/13. A scenario is a saved, named driver-assumption set
 * (src/forecasting/drivers.py's ForecastDrivers, verbatim); a run projects
 * it forward from the current canonical model's observed baseline
 * (src/forecasting/baseline.py). Nothing here is a model call -- every
 * projected number traces to either an observed figure or a driver typed in
 * below, and a component with neither is reported as a gap, not silently
 * zeroed.
 */
export default function ForecastPage() {
  const { entityId, ready } = useWorkspace();

  const scenarios = useApiQuery(
    (token) => listForecastScenarios(token, entityId),
    [entityId],
    { enabled: ready }
  );

  const [lastRun, setLastRun] = useState<ForecastRunResult | null>(null);
  const [runningScenarioId, setRunningScenarioId] = useState<number | null>(null);

  const runAction = useApiAction((token: string, scenarioId: number) => runForecastScenario(token, scenarioId, entityId));

  async function handleRun(scenarioId: number) {
    setRunningScenarioId(scenarioId);
    const result = await runAction.run(scenarioId);
    if (result) setLastRun(result);
  }

  return (
    <>
      <PageHeader
        title="Forecasting"
        description="Driver-based revenue and cost projection for the apparel/retail profile: store-cohort economics plus online channel growth, projected forward from the current canonical model."
        corpusRef="corpus/13"
      />

      <div className="grid gap-4 xl:grid-cols-2">
        <ScenarioBuilder entityId={entityId} onSaved={scenarios.reload} />

        <Card>
          <CardHeader title="Saved scenarios" description="Run any of these against the current baseline." />
          <CardBody>
            {scenarios.error && (
              <ErrorState title="Scenarios did not load" message={scenarios.error} onRetry={scenarios.reload} />
            )}
            {!scenarios.error && !scenarios.data && scenarios.loading && <SkeletonTable rows={4} cols={3} />}
            {!scenarios.error && scenarios.data && scenarios.data.length === 0 && (
              <EmptyState title="No scenarios yet" description="Build one on the left and save it to run a forecast." />
            )}
            {!scenarios.error && scenarios.data && scenarios.data.length > 0 && (
              <ScenarioList
                scenarios={scenarios.data}
                onRun={handleRun}
                busyScenarioId={runAction.busy ? runningScenarioId : null}
                error={runAction.error}
              />
            )}
          </CardBody>
        </Card>
      </div>

      {lastRun && <RunResult result={lastRun} />}
    </>
  );
}

function ScenarioList({
  scenarios,
  onRun,
  busyScenarioId,
  error,
}: {
  scenarios: ForecastScenarioSummary[];
  onRun: (scenarioId: number) => void;
  busyScenarioId: number | null;
  error: string | null;
}) {
  return (
    <>
      <TFrame>
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>Created by</TH>
              <TH>Created</TH>
              <TH align="right">Action</TH>
            </TR>
          </THead>
          <TBody>
            {scenarios.map((s) => (
              <TR key={s.scenario_id}>
                <TD className="font-medium text-ink">{s.name}</TD>
                <TD>{s.created_by}</TD>
                <TD>{s.created_at ? formatDate(s.created_at) : "—"}</TD>
                <TD align="right">
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => onRun(s.scenario_id)}
                    busy={busyScenarioId === s.scenario_id}
                    busyLabel="Running"
                  >
                    Run
                  </Button>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </TFrame>
      {error && <p className="mt-2 text-[12.5px] text-neg">{error}</p>}
    </>
  );
}

function ScenarioBuilder({ entityId, onSaved }: { entityId: number; onSaved: () => void }) {
  const [name, setName] = useState("");
  const [forecastYears, setForecastYears] = useState(3);
  const [formats, setFormats] = useState<Record<(typeof STORE_FORMATS)[number], FormatFormState>>(
    Object.fromEntries(STORE_FORMATS.map((f) => [f, DEFAULT_FORMAT_STATE])) as Record<
      (typeof STORE_FORMATS)[number],
      FormatFormState
    >
  );
  const [onlineRows, setOnlineRows] = useState<OnlineRowState[]>([
    { channelName: "", ordersGrowthPct: "25", priceGrowthPct: "2.5" },
  ]);
  const [costs, setCosts] = useState({
    storePersonnelGrowthPct: "7", storeRentGrowthPct: "6", franchiseCommissionRatePct: "10",
    hoCostGrowthPct: "7.5", onlineCommissionRatePct: "16", onlineAdSpendPctOfSalesPct: "7.5",
    gpMarginPath: "0.55, 0.57, 0.58",
  });

  const saveAction = useApiAction((token: string, drivers: ForecastDrivers) =>
    createForecastScenario(token, entityId, name, drivers)
  );

  function updateFormat(fmt: (typeof STORE_FORMATS)[number], patch: Partial<FormatFormState>) {
    setFormats((prev) => ({ ...prev, [fmt]: { ...prev[fmt], ...patch } }));
  }

  function buildDrivers(): ForecastDrivers | null {
    const pct = (s: string) => (Number(s) / 100).toString();
    const storeFormatDrivers: StoreFormatDrivers[] = STORE_FORMATS.filter((f) => formats[f].enabled).map((f) => {
      const state = formats[f];
      return {
        store_format: f,
        stores_added_per_year: state.storesAddedPerYear
          .split(",")
          .map((s) => parseInt(s.trim(), 10))
          .filter((n) => !Number.isNaN(n)),
        year1_avg_annual_sales_inr: state.year1AvgAnnualSalesInr || "0",
        existing_store_price_growth_yoy: pct(state.priceGrowthPct || "0"),
        existing_store_customer_growth_yoy: pct(state.customerGrowthPct || "0"),
      };
    });

    const onlineChannelDrivers: OnlineChannelDrivers[] = onlineRows
      .filter((r) => r.channelName.trim())
      .map((r) => ({
        channel_name: r.channelName.trim(),
        orders_growth_yoy: pct(r.ordersGrowthPct || "0"),
        price_growth_yoy: pct(r.priceGrowthPct || "0"),
      }));

    const costDrivers: CostDrivers = {
      store_personnel_growth_yoy: pct(costs.storePersonnelGrowthPct),
      store_rent_growth_yoy: pct(costs.storeRentGrowthPct),
      franchise_commission_rate: pct(costs.franchiseCommissionRatePct),
      ho_cost_growth_yoy: pct(costs.hoCostGrowthPct),
      online_commission_rate: pct(costs.onlineCommissionRatePct),
      online_ad_spend_pct_of_sales: pct(costs.onlineAdSpendPctOfSalesPct),
      gp_margin_path: costs.gpMarginPath.split(",").map((s) => s.trim()).filter(Boolean),
    };

    if (!name.trim()) return null;
    return {
      forecast_years: forecastYears,
      store_formats: storeFormatDrivers,
      online_channels: onlineChannelDrivers,
      costs: costDrivers,
      product_mix: null, // held flat at the observed baseline mix, per corpus/13 section 3
    };
  }

  async function handleSave() {
    const drivers = buildDrivers();
    if (!drivers) return;
    const result = await saveAction.run(drivers);
    if (result) {
      setName("");
      onSaved();
    }
  }

  return (
    <Card>
      <CardHeader title="Build a scenario" description="Every number below is an assumption you supply — nothing is defaulted." />
      <CardBody className="space-y-5">
        <Toolbar>
          <Input label="Scenario name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Base case FY27-29" />
          <Field label="Forecast years" htmlFor="forecast-years">
            <input
              id="forecast-years" type="number" min={1} max={10} value={forecastYears}
              onChange={(e) => setForecastYears(Math.max(1, Math.min(10, Number(e.target.value) || 1)))}
              className="h-9 w-24 rounded-control border border-line-strong bg-surface px-2.5 text-sm tabular-nums"
            />
          </Field>
        </Toolbar>

        <div>
          <p className="label-caps mb-2">Store formats</p>
          <div className="space-y-3">
            {STORE_FORMATS.map((fmt) => {
              const state = formats[fmt];
              return (
                <div key={fmt} className="rounded-control border border-line p-3">
                  <label className="flex items-center gap-2 text-sm font-medium text-ink">
                    <input type="checkbox" checked={state.enabled} onChange={(e) => updateFormat(fmt, { enabled: e.target.checked })} />
                    {fmt}
                  </label>
                  {state.enabled && (
                    <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                      <Input
                        label="Stores added / year"
                        hint="comma-separated, one per year"
                        value={state.storesAddedPerYear}
                        onChange={(e) => updateFormat(fmt, { storesAddedPerYear: e.target.value })}
                        placeholder="4, 5, 6"
                      />
                      <Input
                        label="Year-1 avg. sales (₹)"
                        value={state.year1AvgAnnualSalesInr}
                        onChange={(e) => updateFormat(fmt, { year1AvgAnnualSalesInr: e.target.value })}
                        placeholder="20000000"
                      />
                      <Input
                        label="Price growth % / yr"
                        value={state.priceGrowthPct}
                        onChange={(e) => updateFormat(fmt, { priceGrowthPct: e.target.value })}
                      />
                      <Input
                        label="Customer growth % / yr"
                        value={state.customerGrowthPct}
                        onChange={(e) => updateFormat(fmt, { customerGrowthPct: e.target.value })}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <p className="label-caps">Online channels</p>
            <Button
              size="sm" variant="ghost"
              onClick={() => setOnlineRows((rows) => [...rows, { channelName: "", ordersGrowthPct: "25", priceGrowthPct: "2.5" }])}
            >
              + Add channel
            </Button>
          </div>
          <div className="space-y-2">
            {onlineRows.map((row, i) => (
              <div key={i} className="grid grid-cols-3 gap-2">
                <Input
                  placeholder="Channel name, matching your data"
                  value={row.channelName}
                  onChange={(e) => setOnlineRows((rows) => rows.map((r, j) => (j === i ? { ...r, channelName: e.target.value } : r)))}
                />
                <Input
                  placeholder="Orders growth % / yr"
                  value={row.ordersGrowthPct}
                  onChange={(e) => setOnlineRows((rows) => rows.map((r, j) => (j === i ? { ...r, ordersGrowthPct: e.target.value } : r)))}
                />
                <Input
                  placeholder="Price growth % / yr"
                  value={row.priceGrowthPct}
                  onChange={(e) => setOnlineRows((rows) => rows.map((r, j) => (j === i ? { ...r, priceGrowthPct: e.target.value } : r)))}
                />
              </div>
            ))}
          </div>
        </div>

        <div>
          <p className="label-caps mb-2">Costs</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <Input label="Store personnel growth % / yr" value={costs.storePersonnelGrowthPct}
              onChange={(e) => setCosts((c) => ({ ...c, storePersonnelGrowthPct: e.target.value }))} />
            <Input label="Store rent growth % / yr" value={costs.storeRentGrowthPct}
              onChange={(e) => setCosts((c) => ({ ...c, storeRentGrowthPct: e.target.value }))} />
            <Input label="Franchise commission %" value={costs.franchiseCommissionRatePct}
              onChange={(e) => setCosts((c) => ({ ...c, franchiseCommissionRatePct: e.target.value }))} />
            <Input label="HO/company cost growth % / yr" value={costs.hoCostGrowthPct}
              onChange={(e) => setCosts((c) => ({ ...c, hoCostGrowthPct: e.target.value }))} />
            <Input label="Online commission %" value={costs.onlineCommissionRatePct}
              onChange={(e) => setCosts((c) => ({ ...c, onlineCommissionRatePct: e.target.value }))} />
            <Input label="Online ad spend % of sales" value={costs.onlineAdSpendPctOfSalesPct}
              onChange={(e) => setCosts((c) => ({ ...c, onlineAdSpendPctOfSalesPct: e.target.value }))} />
          </div>
          <Input
            className="mt-2" label="Gross margin path" hint="comma-separated fraction per forecast year, e.g. 0.55, 0.57, 0.58"
            value={costs.gpMarginPath} onChange={(e) => setCosts((c) => ({ ...c, gpMarginPath: e.target.value }))}
          />
        </div>

        <Callout tone="neutral">
          Product mix is held flat at whatever the current canonical model shows — this build doesn't yet expose a
          mix-target editor. Nothing about which categories grow faster is assumed on your behalf.
        </Callout>

        {saveAction.error && <p className="text-[12.5px] text-neg">{saveAction.error}</p>}
        <Button variant="primary" onClick={handleSave} busy={saveAction.busy} busyLabel="Saving" disabled={!name.trim()}>
          Save scenario
        </Button>
      </CardBody>
    </Card>
  );
}

function RunResult({ result }: { result: ForecastRunResult }) {
  return (
    <Card className="mt-4">
      <CardHeader
        title="Projection"
        description={`Baseline as of ${formatDate(result.baseline_as_of)}`}
        actions={<Badge tone={result.configured ? "positive" : "warning"}>{result.configured ? "Fully configured" : "Gaps disclosed below"}</Badge>}
      />
      <CardBody>
        {result.gaps.length > 0 && (
          <Callout tone="warning" className="mb-4">
            <p className="mb-1 font-medium">Not computed for every year — reported, not hidden:</p>
            <ul className="list-inside list-disc space-y-0.5">
              {result.gaps.map((g, i) => (
                <li key={i}>{g}</li>
              ))}
            </ul>
          </Callout>
        )}
        <TFrame>
          <Table>
            <THead>
              <TR>
                <TH>Metric</TH>
                {result.years.map((y) => (
                  <TH key={y.year_index} align="right">
                    Year {y.year_index}
                  </TH>
                ))}
              </TR>
            </THead>
            <TBody>
              <MetricRow label="Existing store revenue" years={result.years} pick={(y) => y.existing_store_revenue} />
              <MetricRow label="New store revenue" years={result.years} pick={(y) => y.new_store_revenue} />
              <MetricRow label="Online revenue" years={result.years} pick={(y) => sumRecord(y.online_revenue_by_channel)} />
              <MetricRow label="Total revenue" years={result.years} pick={(y) => y.total_revenue} bold />
              <MetricRow label="Gross margin %" years={result.years} pick={(y) => y.gross_margin_pct} percent />
              <MetricRow label="Gross profit" years={result.years} pick={(y) => y.gross_profit} />
              <MetricRow label="Store rent" years={result.years} pick={(y) => y.store_rent} />
              <MetricRow label="Store personnel" years={result.years} pick={(y) => y.store_personnel} />
              <MetricRow label="Franchise commission" years={result.years} pick={(y) => y.franchise_commission} />
              <MetricRow label="Online commission" years={result.years} pick={(y) => y.online_commission} />
              <MetricRow label="Online ad spend" years={result.years} pick={(y) => y.online_ad_spend} />
              <MetricRow label="Company overhead" years={result.years} pick={(y) => y.company_overhead} />
              <MetricRow label="EBITDA" years={result.years} pick={(y) => y.ebitda} bold />
            </TBody>
          </Table>
        </TFrame>
      </CardBody>
    </Card>
  );
}

function sumRecord(rec: Record<string, string>): string {
  return Object.values(rec)
    .reduce((acc, v) => acc + Number(v || 0), 0)
    .toString();
}

function MetricRow({
  label,
  years,
  pick,
  bold,
  percent,
}: {
  label: string;
  years: ForecastRunResult["years"];
  pick: (y: ForecastRunResult["years"][number]) => string | null;
  bold?: boolean;
  percent?: boolean;
}) {
  return (
    <TR>
      <TD className={bold ? "font-semibold text-ink" : ""}>{label}</TD>
      {years.map((y) => {
        const value = pick(y);
        return (
          <TD key={y.year_index} align="right" numeric className={bold ? "font-semibold" : ""}>
            {value === null ? (
              <span className="text-ink-faint">—</span>
            ) : percent ? (
              formatPercent(value)
            ) : (
              <span title={`${exactAmount(value)} exactly`}>{formatStatement(value, { bare: true })}</span>
            )}
          </TD>
        );
      })}
    </TR>
  );
}
