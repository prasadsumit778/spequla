// Thin fetch wrapper against the FastAPI backend. Every call forwards the
// WorkOS AuthKit access token as a standard bearer token -- the backend
// verifies it and derives the tenant and role from its signed claims, per
// src/api/deps/auth.py and src/api/deps/tenant.py. There is nothing left
// for the frontend to assert about who it is or which tenant it belongs to.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type LoadRun = {
  load_run_id: number;
  entity_id: number;
  source_system: string;
  status: string;
  triggered_by: string;
  started_at: string | null;
  completed_at: string | null;
};

export type SourceFile = {
  source_file_id: number;
  load_run_id: number;
  file_name: string;
  template_type: string;
  row_count: number | null;
  received_at: string | null;
};

export type UploadResult = {
  load_run_id: number;
  status: string;
  quarantined_count: number;
  inserted: number;
  closed_and_reinserted: number;
  unchanged: number;
  periods_touched: string[];
  trial_balance: { period_key: string; balanced: boolean; total: string }[];
};

export type QueueRow = {
  source_account_name: string;
  source_record_id: string;
  canonical_class: string;
  proposal_source: string;
  approved_by: string;
  period_value_inr: string;
  running_pct_mapped: number;
  unmapped_value_inr: number;
};

export type MappingRunResult = {
  mapping_version_id: number;
  auto_accepted: number;
  human_approved: number;
  deferred_to_suspense: number;
  total_value_inr: string;
  mapped_value_inr: string;
};

export type FreezeResult = {
  passed: boolean;
  reason: string;
  coverage_pct: number | null;
  unmapped_value_inr: string | null;
};

export type PnLResult = {
  profile: string;
  period_start: string;
  period_end: string;
  mapping_version_id: number;
  lines: Record<string, string>;
  subtotals: Record<string, string | null>;
  unmapped_value_inr: string;
};

export type BalanceSheetResult = {
  as_of_date: string;
  mapping_version_id: number;
  groups: Record<string, Record<string, string>>;
  group_totals: Record<string, string>;
  total_assets: string;
  total_liabilities_and_equity: string;
  balances: boolean;
  unmapped_value_inr: string;
};

export type Citation = {
  value: string;
  metric: string;
  metric_version: number;
  period: string;
  basis: string;
  snapshot_at: string;
  reconciliation_status: string;
  query_hash: string;
  row_count: number;
  source_facts: string[];
  source_files: string[];
  mapping_version: number | null;
  unmapped_value_inr: string | null;
  drill_url: string;
};

export type MetricTile = {
  metric: string;
  label: string;
  status: "ok" | "blocked" | "undefined";
  value: string | null;
  reason?: string | null;
  blocking_decisions?: string[];
  citation?: Citation;
};

export type OverviewResult = {
  period: string;
  entity_id: number;
  reconciliation_status: string;
  mapping_version_id: number | null;
  rows: { row: string; tiles: MetricTile[] }[];
};

export type DataHealthResult = {
  period: string;
  freshness: { source_system: string; last_successful_load_at: string | null; hours_since: number | null }[];
  completeness: { mapped_pct: number | null; unmapped_value_inr: string | null; total_value_inr?: string; reason?: string };
  reconciliation: { check_type: string; status: string; residual_inr: string; tolerance_pct: string | null; run_at: string }[];
  exceptions: {
    open_by_severity: Record<string, { count: number; value_inr: string }>;
    top_ten_by_value: { exception_class: string; severity: string; description: string; value_inr: string | null }[];
  };
};

export type ExceptionRow = {
  exception_id: number;
  exception_class: string;
  severity: string;
  period_key: string | null;
  object_type: string | null;
  object_ref: string | null;
  value_inr: string | null;
  description: string;
  suggested_action: string | null;
  status: string;
  raised_at: string;
};

function authHeaders(accessToken: string): HeadersInit {
  return { Authorization: `Bearer ${accessToken}` };
}

async function asJson(res: Response) {
  const body = await res.json();
  if (!res.ok) throw new Error(body.detail || `request failed: ${res.status}`);
  return body;
}

export async function createMappingRun(
  accessToken: string,
  entityId: number,
  versionNo: number,
  effectiveFrom: string,
  changeReason?: string
): Promise<MappingRunResult> {
  const res = await fetch(`${API_BASE}/mapping/runs`, {
    method: "POST",
    headers: { ...authHeaders(accessToken), "Content-Type": "application/json" },
    body: JSON.stringify({ entity_id: entityId, version_no: versionNo, effective_from: effectiveFrom, change_reason: changeReason }),
  });
  return asJson(res);
}

export async function getReviewQueue(accessToken: string, mappingVersionId: number): Promise<QueueRow[]> {
  const res = await fetch(`${API_BASE}/mapping/runs/${mappingVersionId}/queue`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function freezeMappingRun(accessToken: string, mappingVersionId: number, entityId: number): Promise<FreezeResult> {
  const res = await fetch(`${API_BASE}/mapping/runs/${mappingVersionId}/freeze?entity_id=${entityId}`, {
    method: "POST",
    headers: authHeaders(accessToken),
  });
  return asJson(res);
}

export async function getPnL(
  accessToken: string,
  profile: "manufacturing" | "consumer",
  periodStart: string,
  periodEnd: string,
  entityId: number
): Promise<PnLResult> {
  const params = new URLSearchParams({ profile, period_start: periodStart, period_end: periodEnd, entity_id: String(entityId) });
  const res = await fetch(`${API_BASE}/statements/pnl?${params}`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function getBalanceSheet(accessToken: string, asOf: string, entityId: number): Promise<BalanceSheetResult> {
  const params = new URLSearchParams({ as_of: asOf, entity_id: String(entityId) });
  const res = await fetch(`${API_BASE}/statements/balance-sheet?${params}`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function listLoadRuns(accessToken: string): Promise<LoadRun[]> {
  const res = await fetch(`${API_BASE}/load-runs`, { headers: authHeaders(accessToken) });
  if (!res.ok) throw new Error(`load-runs fetch failed: ${res.status}`);
  return res.json();
}

export async function listFiles(accessToken: string): Promise<SourceFile[]> {
  const res = await fetch(`${API_BASE}/files`, { headers: authHeaders(accessToken) });
  if (!res.ok) throw new Error(`files fetch failed: ${res.status}`);
  return res.json();
}

export async function getOverviewTiles(accessToken: string, period: string, entityId: number): Promise<OverviewResult> {
  const params = new URLSearchParams({ period, entity_id: String(entityId) });
  const res = await fetch(`${API_BASE}/overview/tiles?${params}`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function getDataHealth(accessToken: string, period: string, entityId: number): Promise<DataHealthResult> {
  const params = new URLSearchParams({ period, entity_id: String(entityId) });
  const res = await fetch(`${API_BASE}/data-health?${params}`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function listExceptions(accessToken: string, status: string = "open"): Promise<{ exceptions: ExceptionRow[] }> {
  const params = new URLSearchParams({ status });
  const res = await fetch(`${API_BASE}/exceptions?${params}`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function resolveException(
  accessToken: string,
  exceptionId: number,
  resolution: "accepted" | "deferred" | "resolved",
  resolutionNote: string
): Promise<{ exception_id: number; status: string }> {
  const res = await fetch(`${API_BASE}/exceptions/${exceptionId}/resolve`, {
    method: "POST",
    headers: { ...authHeaders(accessToken), "Content-Type": "application/json" },
    body: JSON.stringify({ resolution, resolution_note: resolutionNote }),
  });
  return asJson(res);
}

export type AskCitation = {
  value: string;
  metric: string;
  metric_version: number;
  period: string;
  basis: string;
  snapshot_at: string;
  reconciliation_status: string;
  query_hash: string;
  row_count: number;
  source_facts: string[];
  source_files: string[];
  mapping_version: number | null;
  unmapped_value_inr: string | null;
  drill_url: string;
};

export type AskBridgeComponent = { label: string; value: string; is_residual: boolean };

export type AskResult = {
  status: string;
  intent: string;
  sql_text: string | null;
  value: unknown;
  series: { period: string; status: string; value: string | null; reason: string | null }[];
  reason: string | null;
  blocking_decisions: string[];
  row_count: number;
  bridge: {
    total_delta: string;
    components_sum_to_total: boolean;
    configured: boolean;
    reason: string | null;
    components: AskBridgeComponent[];
  } | null;
};

export type AskRefusal = {
  refusal_class: string;
  reason: string;
  nearest_supported_question: string | null;
  clarifying_options: string[] | null;
};

export type AskResponse = {
  status: string;
  question: string;
  intent: string | null;
  ir: Record<string, unknown> | null;
  result: AskResult | null;
  citation: AskCitation | null;
  refusal: AskRefusal | null;
};

export async function askQuestion(
  accessToken: string,
  question: string,
  entityId: number,
  tenantProfile: "manufacturing" | "consumer"
): Promise<AskResponse> {
  const res = await fetch(`${API_BASE}/ask`, {
    method: "POST",
    headers: { ...authHeaders(accessToken), "Content-Type": "application/json" },
    body: JSON.stringify({ question, entity_id: entityId, tenant_profile: tenantProfile }),
  });
  return asJson(res);
}

export type ReportSummary = {
  report_artefact_id: number;
  period_key: string;
  entity_id: number;
  profile: string;
  generated_at: string | null;
  generated_by: string;
  status: string;
  reviewer: string | null;
  signed_at: string | null;
  content_hash: string;
};

export type ChartSpec = Record<string, unknown> & { chart_type: string; title: string };

export type ReportArtefact = {
  report_artefact_id: number;
  tenant_id: string;
  entity_id: number;
  period_key: string;
  profile: string;
  generated_at: string | null;
  generated_by: string;
  mapping_version_id: number;
  metric_versions: Record<string, number>;
  freshness_snapshot: unknown[];
  reconciliation_snapshot: unknown[];
  sections: Record<string, any>;
  chart_specs: ChartSpec[];
  commentary: string | null;
  unmapped_value_inr: string | null;
  content_hash: string;
  status: string;
  reviewer: string | null;
  signed_at: string | null;
  blocking_exception_override_reason: string | null;
  blocking_exception_override_by: string | null;
  blocking_exception_override_at: string | null;
};

export type BlockingException = { exception_id: number; exception_class: string; description: string; value_inr: string | null };

export async function listReports(accessToken: string, period: string, entityId: number): Promise<ReportSummary[]> {
  const params = new URLSearchParams({ period, entity_id: String(entityId) });
  const res = await fetch(`${API_BASE}/reports?${params}`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function generateReport(accessToken: string, period: string, entityId: number,
                                          profile: "manufacturing" | "consumer"): Promise<ReportSummary> {
  const res = await fetch(`${API_BASE}/reports/generate`, {
    method: "POST",
    headers: { ...authHeaders(accessToken), "Content-Type": "application/json" },
    body: JSON.stringify({ period, entity_id: entityId, profile }),
  });
  return asJson(res);
}

export async function getReport(accessToken: string, reportArtefactId: number): Promise<ReportArtefact> {
  const res = await fetch(`${API_BASE}/reports/${reportArtefactId}`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function updateCommentary(accessToken: string, reportArtefactId: number,
                                            commentary: string): Promise<ReportSummary> {
  const res = await fetch(`${API_BASE}/reports/${reportArtefactId}/commentary`, {
    method: "PATCH",
    headers: { ...authHeaders(accessToken), "Content-Type": "application/json" },
    body: JSON.stringify({ commentary }),
  });
  return asJson(res);
}

export async function getBlockingExceptions(accessToken: string, reportArtefactId: number): Promise<{ blocking_exceptions: BlockingException[] }> {
  const res = await fetch(`${API_BASE}/reports/${reportArtefactId}/blocking-exceptions`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function signReport(accessToken: string, reportArtefactId: number,
                                      overrideReason?: string): Promise<ReportSummary> {
  const res = await fetch(`${API_BASE}/reports/${reportArtefactId}/sign`, {
    method: "POST",
    headers: { ...authHeaders(accessToken), "Content-Type": "application/json" },
    body: JSON.stringify({ override_reason: overrideReason || null }),
  });
  return asJson(res);
}

export function exportReportUrl(reportArtefactId: number): string {
  return `${API_BASE}/reports/${reportArtefactId}/export`;
}

export type ConsumerLadder = {
  profile: string;
  period_start: string;
  period_end: string;
  mapping_version_id: number;
  gmv_total: string;
  gmv_by_model: Record<string, string>;
  discount: string;
  net_revenue: string;
  net_revenue_by_model: Record<string, string>;
  cogs: string;
  gross_margin: string;
  gross_margin_pct: string | null;
  operating_cost_cm1: string;
  cm1: string;
  cm1_pct: string | null;
  marketing: string;
  cm2: string;
  cm2_pct: string | null;
  corporate_overhead: string;
  ebitda: string;
  unmapped_value_inr: string;
  order_file_to_books_residual: { order_file_buyout_revenue: string; books_revenue: string; residual: string };
};

export async function getConsumerLadder(accessToken: string, periodStart: string, periodEnd: string,
                                             entityId: number): Promise<ConsumerLadder> {
  const params = new URLSearchParams({ period_start: periodStart, period_end: periodEnd, entity_id: String(entityId) });
  const res = await fetch(`${API_BASE}/operating/consumer-ladder?${params}`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export type ManufacturingProductOperating = {
  product_key: number;
  product_name: string;
  status: string;
  reason: string | null;
  uom: string | null;
  volume_produced: string | null;
  qty_rejected: string | null;
  yield_pct: string | null;
  rejection_pct: string | null;
  realisation_per_unit_unavailable_reason: string;
  capacity_utilisation_unavailable_reason: string;
};

export type ManufacturingOperating = {
  profile: string;
  period: string;
  mapping_version_id: number;
  products: ManufacturingProductOperating[];
  entity: {
    status: string; reason: string | null; common_uom: string | null;
    total_volume_produced: string | null; rm_cost_per_unit: string | null;
    conversion_cost_per_unit: string | null; conversion_cost_components: string[];
  };
};

export async function getManufacturingOperating(accessToken: string, period: string,
                                                     entityId: number): Promise<ManufacturingOperating> {
  const params = new URLSearchParams({ period, entity_id: String(entityId) });
  const res = await fetch(`${API_BASE}/operating/manufacturing?${params}`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

/* --------------------------------------------------------------- forecast */
// corpus/13. Field names mirror src/forecasting/drivers.py's Pydantic
// models exactly -- the backend validates, the frontend just carries the
// shape through, same "no codegen, hand-typed to match" convention as every
// other type in this file.

export type StoreFormatDrivers = {
  store_format: "COCO" | "COFO" | "FOCO" | "FOFO";
  stores_added_per_year: number[];
  year1_avg_annual_sales_inr: string;
  existing_store_price_growth_yoy: string;
  existing_store_customer_growth_yoy: string;
};

export type OnlineChannelDrivers = {
  channel_name: string;
  orders_growth_yoy: string;
  price_growth_yoy: string;
};

export type CostDrivers = {
  store_personnel_growth_yoy: string;
  store_rent_growth_yoy: string;
  franchise_commission_rate: string;
  ho_cost_growth_yoy: string;
  online_commission_rate: string;
  online_ad_spend_pct_of_sales: string;
  gp_margin_path: string[];
};

export type ProductMixDrivers = {
  target_mix: Record<string, string>;
  convergence_years: number;
};

export type ForecastDrivers = {
  forecast_years: number;
  store_formats: StoreFormatDrivers[];
  online_channels: OnlineChannelDrivers[];
  costs: CostDrivers;
  product_mix: ProductMixDrivers | null;
};

export type ForecastScenarioSummary = {
  scenario_id: number;
  name: string;
  created_by: string;
  created_at: string | null;
};

export type ForecastYearResult = {
  year_index: number;
  existing_store_revenue: string;
  new_store_revenue: string;
  store_revenue_by_format: Record<string, string>;
  online_revenue_by_channel: Record<string, string>;
  total_revenue: string;
  category_mix: Record<string, string>;
  gross_margin_pct: string | null;
  cogs: string | null;
  gross_profit: string | null;
  store_rent: string | null;
  store_personnel: string | null;
  franchise_commission: string | null;
  online_commission: string;
  online_ad_spend: string;
  company_overhead: string | null;
  ebitda: string | null;
};

export type ForecastRunResult = {
  run_id: number;
  scenario_id: number;
  baseline_as_of: string;
  configured: boolean;
  gaps: string[];
  years: ForecastYearResult[];
};

export async function createForecastScenario(
  accessToken: string, entityId: number, name: string, drivers: ForecastDrivers
): Promise<{ scenario_id: number; name: string }> {
  const res = await fetch(`${API_BASE}/forecast/scenarios`, {
    method: "POST",
    headers: { ...authHeaders(accessToken), "Content-Type": "application/json" },
    body: JSON.stringify({ entity_id: entityId, name, drivers }),
  });
  return asJson(res);
}

export async function listForecastScenarios(accessToken: string, entityId: number): Promise<ForecastScenarioSummary[]> {
  const params = new URLSearchParams({ entity_id: String(entityId) });
  const res = await fetch(`${API_BASE}/forecast/scenarios?${params}`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function getForecastScenario(
  accessToken: string, scenarioId: number, entityId: number
): Promise<{ scenario_id: number; name: string; drivers: ForecastDrivers }> {
  const params = new URLSearchParams({ entity_id: String(entityId) });
  const res = await fetch(`${API_BASE}/forecast/scenarios/${scenarioId}?${params}`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function runForecastScenario(
  accessToken: string, scenarioId: number, entityId: number, asOf?: string
): Promise<ForecastRunResult> {
  const res = await fetch(`${API_BASE}/forecast/scenarios/${scenarioId}/run`, {
    method: "POST",
    headers: { ...authHeaders(accessToken), "Content-Type": "application/json" },
    body: JSON.stringify({ entity_id: entityId, as_of: asOf ?? null }),
  });
  return asJson(res);
}

export async function getForecastRun(accessToken: string, runId: number, entityId: number): Promise<ForecastRunResult> {
  const params = new URLSearchParams({ entity_id: String(entityId) });
  const res = await fetch(`${API_BASE}/forecast/runs/${runId}?${params}`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export type TenantSummary = {
  tenant_id: string; name: string; schema_name: string; is_synthetic: boolean;
  created_at: string; deleted_at: string | null;
};

export type AccessGrant = {
  grant_id: number; employee_user_id: string; employee_name: string; granted_by: string;
  reason: string; granted_at: string; expires_at: string; revoked_at: string | null;
  revoked_by: string | null; is_active: boolean;
};

export type AuditLogRow = {
  audit_id: number; actor: string; role_key: string | null; action: string;
  object_type: string | null; object_ref: string | null; detail: Record<string, unknown> | null;
  occurred_at: string;
};

export type ModelCost = {
  tenant_id: string; total_queries: number; total_input_tokens: number; total_output_tokens: number;
  total_cost_inr: string; priced_queries: number;
};

export type RestoreRehearsalResult = {
  source_schema: string; passed: boolean;
  tables: { table_name: string; source_row_count: number; restored_row_count: number; matches: boolean }[];
};

export async function listTenants(accessToken: string): Promise<TenantSummary[]> {
  const res = await fetch(`${API_BASE}/admin/tenants`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function createAccessGrant(accessToken: string, tenantId: string, employeeUserId: string,
                                             employeeName: string, reason: string, expiresAt: string): Promise<AccessGrant> {
  const res = await fetch(`${API_BASE}/admin/tenants/${tenantId}/access-grants`, {
    method: "POST",
    headers: { ...authHeaders(accessToken), "Content-Type": "application/json" },
    body: JSON.stringify({ employee_user_id: employeeUserId, employee_name: employeeName, reason, expires_at: expiresAt }),
  });
  return asJson(res);
}

export async function getAccessGrants(accessToken: string, tenantId: string): Promise<AccessGrant[]> {
  const res = await fetch(`${API_BASE}/admin/tenants/${tenantId}/access-grants`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function revokeAccessGrant(accessToken: string, grantId: number): Promise<{ grant_id: number; revoked_at: string }> {
  const res = await fetch(`${API_BASE}/admin/access-grants/${grantId}/revoke`, {
    method: "POST", headers: authHeaders(accessToken),
  });
  return asJson(res);
}

export async function getAuditLog(accessToken: string, tenantId: string): Promise<AuditLogRow[]> {
  const res = await fetch(`${API_BASE}/admin/tenants/${tenantId}/audit-log`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function getSupportDataHealth(accessToken: string, tenantId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/admin/tenants/${tenantId}/support-data-health`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function getModelCost(accessToken: string, tenantId: string): Promise<ModelCost> {
  const res = await fetch(`${API_BASE}/admin/tenants/${tenantId}/model-cost`, { headers: authHeaders(accessToken) });
  return asJson(res);
}

export async function runRestoreRehearsal(accessToken: string, tenantId: string): Promise<RestoreRehearsalResult> {
  const res = await fetch(`${API_BASE}/admin/tenants/${tenantId}/restore-rehearsal`, {
    method: "POST", headers: authHeaders(accessToken),
  });
  return asJson(res);
}

export async function deleteTenant(accessToken: string, tenantId: string, reason: string): Promise<{ tenant_id: string; deleted_at: string }> {
  const res = await fetch(`${API_BASE}/admin/tenants/${tenantId}/delete`, {
    method: "POST",
    headers: { ...authHeaders(accessToken), "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  return asJson(res);
}

export async function uploadFile(
  accessToken: string,
  templateType: "COA" | "TB" | "GL" | "ConsumerSales" | "MFGProduction",
  entityId: number,
  file: File
): Promise<UploadResult> {
  const form = new FormData();
  form.append("template_type", templateType);
  form.append("entity_id", String(entityId));
  form.append("file", file);
  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    headers: authHeaders(accessToken),
    body: form,
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body.detail || `upload failed: ${res.status}`);
  return body;
}
