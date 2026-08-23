"use client";

import { useState } from "react";
import { useAuth, useAccessToken } from "@workos-inc/authkit-nextjs/components";
import {
  ConsumerLadder,
  ManufacturingOperating,
  getConsumerLadder,
  getManufacturingOperating,
} from "@/lib/api";

const inr = (v: string | null | undefined) => (v == null ? "—" : Number(v).toLocaleString("en-IN"));
const pct = (v: string | null | undefined) => (v == null ? "—" : `${(Number(v) * 100).toFixed(1)}%`);

function LadderRow({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid #f0f0f0" }}>
      <span>{label}{sub && <span style={{ color: "#888", fontSize: 12 }}> {sub}</span>}</span>
      <span style={{ fontVariantNumeric: "tabular-nums" }}>{value}</span>
    </div>
  );
}

function ConsumerView({ accessToken, entityId }: { accessToken: string; entityId: number }) {
  const [periodStart, setPeriodStart] = useState("2025-04-01");
  const [periodEnd, setPeriodEnd] = useState("2025-04-30");
  const [ladder, setLadder] = useState<ConsumerLadder | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true);
    setError(null);
    try {
      setLadder(await getConsumerLadder(accessToken, periodStart, periodEnd, entityId));
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 16 }}>
        <label>From<input value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} style={{ display: "block" }} /></label>
        <label>To<input value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} style={{ display: "block" }} /></label>
        <button onClick={load} disabled={busy}>Load ladder</button>
      </div>
      {error && <p style={{ color: "#b00020" }}>{error}</p>}
      {ladder && (
        <div style={{ maxWidth: 480 }}>
          <LadderRow label="GMV" value={`₹${inr(ladder.gmv_total)}`} />
          {Object.entries(ladder.gmv_by_model).map(([model, v]) => (
            <div key={model} style={{ fontSize: 12, color: "#888", paddingLeft: 12 }}>
              memo -- of which {model}: ₹{inr(v)} {model === "marketplace" && "(volume, not revenue)"}
            </div>
          ))}
          <LadderRow label="Discount" value={`₹${inr(ladder.discount)}`} sub="(disclosed, already reflected in net revenue)" />
          <LadderRow label="= Net revenue" value={`₹${inr(ladder.net_revenue)}`} />
          <LadderRow label="less COGS" value={`₹${inr(ladder.cogs)}`} />
          <LadderRow label="= Gross margin" value={`₹${inr(ladder.gross_margin)}`} sub={pct(ladder.gross_margin_pct)} />
          <LadderRow label="less Operating cost" value={`₹${inr(ladder.operating_cost_cm1)}`} />
          <LadderRow label="= CM1" value={`₹${inr(ladder.cm1)}`} sub={pct(ladder.cm1_pct)} />
          <LadderRow label="less Marketing" value={`₹${inr(ladder.marketing)}`} />
          <LadderRow label="= CM2" value={`₹${inr(ladder.cm2)}`} sub={pct(ladder.cm2_pct)} />
          <LadderRow label="less Corporate overhead (unallocated)" value={`₹${inr(ladder.corporate_overhead)}`} />
          <LadderRow label="= EBITDA" value={`₹${inr(ladder.ebitda)}`} />

          <div style={{ marginTop: 16, fontSize: 12, color: "#666" }}>
            <strong>Order file vs books residual</strong> (reported, never resolved):
            <div>Order file (buyout revenue): ₹{inr(ladder.order_file_to_books_residual.order_file_buyout_revenue)}</div>
            <div>Books (revenue.product_sales): ₹{inr(ladder.order_file_to_books_residual.books_revenue)}</div>
            <div>Residual: ₹{inr(ladder.order_file_to_books_residual.residual)}</div>
          </div>
        </div>
      )}
    </div>
  );
}

function ManufacturingView({ accessToken, entityId }: { accessToken: string; entityId: number }) {
  const [period, setPeriod] = useState("2022-04");
  const [data, setData] = useState<ManufacturingOperating | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true);
    setError(null);
    try {
      setData(await getManufacturingOperating(accessToken, period, entityId));
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 16 }}>
        <label>Period<input value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="YYYY-MM" style={{ display: "block" }} /></label>
        <button onClick={load} disabled={busy}>Load metrics</button>
      </div>
      {error && <p style={{ color: "#b00020" }}>{error}</p>}
      {data && (
        <div>
          <div style={{ fontSize: 13, marginBottom: 12 }}>
            <strong>Entity-level (rm/conversion cost per unit)</strong>{" "}
            {data.entity.status === "ok" ? (
              <>
                common unit: {data.entity.common_uom}, volume {inr(data.entity.total_volume_produced)} --
                RM cost/unit ₹{inr(data.entity.rm_cost_per_unit)}, conversion cost/unit ₹{inr(data.entity.conversion_cost_per_unit)}
                <div style={{ fontSize: 11, color: "#888" }}>
                  conversion cost components: {data.entity.conversion_cost_components.join(", ")} (factory overhead has no declared canonical class)
                </div>
              </>
            ) : (
              <span style={{ color: "#b26a00" }}>blocked -- {data.entity.reason}</span>
            )}
          </div>
          <table cellPadding={6} style={{ borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #ddd", textAlign: "left" }}>
                <th>Product</th><th>Status</th><th>UOM</th><th>Volume produced</th><th>Yield %</th><th>Rejection %</th>
              </tr>
            </thead>
            <tbody>
              {data.products.map((p) => (
                <tr key={p.product_key} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td>{p.product_name}</td>
                  <td style={{ color: p.status === "blocked" ? "#b00020" : "#1a7f37" }}>{p.status}</td>
                  <td>{p.uom ?? "—"}</td>
                  <td>{inr(p.volume_produced)}</td>
                  <td>{pct(p.yield_pct)}</td>
                  <td>{pct(p.rejection_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: 11, color: "#888", marginTop: 8 }}>
            realisation_per_unit and capacity_utilisation_pct are not available -- see per-product reasons in the API response
            (fact_invoice_line not ingested; D-042 capacity basis open).
          </p>
        </div>
      )}
    </div>
  );
}

export default function OperatingPage() {
  const { user, loading: authLoading } = useAuth();
  const { accessToken } = useAccessToken();
  const [profile, setProfile] = useState<"consumer" | "manufacturing">("manufacturing");
  const [entityId, setEntityId] = useState(1);

  if (authLoading) return <p>Loading...</p>;
  if (!user || !accessToken) return <p>Signing in...</p>;

  return (
    <div>
      <h1>Operating metrics</h1>
      <p style={{ fontSize: 13, color: "#666" }}>
        Corpus/03 section 6 (manufacturing) and section 7 (consumer CM ladder), sprint 6 -- profile-specific layouts,
        channel and product breakdowns from fact_channel_order_line / fact_production_output.
      </p>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <label>Profile
          <select value={profile} onChange={(e) => setProfile(e.target.value as any)} style={{ display: "block" }}>
            <option value="manufacturing">Manufacturing</option>
            <option value="consumer">Consumer</option>
          </select>
        </label>
        <label>Entity ID<input type="number" value={entityId} onChange={(e) => setEntityId(Number(e.target.value))} style={{ display: "block", width: 80 }} /></label>
      </div>
      {profile === "consumer" ? (
        <ConsumerView accessToken={accessToken} entityId={entityId} />
      ) : (
        <ManufacturingView accessToken={accessToken} entityId={entityId} />
      )}
    </div>
  );
}
