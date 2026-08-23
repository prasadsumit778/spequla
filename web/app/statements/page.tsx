"use client";

import { useState } from "react";
import { useAuth, useAccessToken } from "@workos-inc/authkit-nextjs/components";
import { getBalanceSheet, getPnL, BalanceSheetResult, PnLResult } from "@/lib/api";

const inr = (v: string | null | undefined) => (v == null ? "—" : Number(v).toLocaleString("en-IN"));

export default function StatementsPage() {
  const { user, loading: authLoading } = useAuth();
  const { accessToken } = useAccessToken();

  const [profile, setProfile] = useState<"manufacturing" | "consumer">("manufacturing");
  const [entityId, setEntityId] = useState(1);
  const [periodStart, setPeriodStart] = useState("2023-04-01");
  const [periodEnd, setPeriodEnd] = useState("2023-04-30");
  const [pnl, setPnl] = useState<PnLResult | null>(null);
  const [bs, setBs] = useState<BalanceSheetResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (authLoading) return <p>Loading...</p>;
  if (!user) return <p>Signing in...</p>;

  async function load() {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    setPnl(null);
    setBs(null);
    try {
      const [p, b] = await Promise.all([
        getPnL(accessToken, profile, periodStart, periodEnd, entityId),
        getBalanceSheet(accessToken, periodEnd, entityId),
      ]);
      setPnl(p);
      setBs(b);
    } catch (err: any) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Statements</h1>
      <p>Corpus/08: the manufacturing cost-structure P&amp;L (4.2) or the consumer CM ladder (4.1), plus the balance sheet (5).</p>

      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 16, flexWrap: "wrap" }}>
        <label>
          Profile
          <select value={profile} onChange={(e) => setProfile(e.target.value as any)} style={{ display: "block" }}>
            <option value="manufacturing">Manufacturing</option>
            <option value="consumer">Consumer (CM ladder)</option>
          </select>
        </label>
        <label>
          Entity ID
          <input type="number" value={entityId} onChange={(e) => setEntityId(Number(e.target.value))} style={{ display: "block" }} />
        </label>
        <label>
          Period start
          <input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} style={{ display: "block" }} />
        </label>
        <label>
          Period end / as-of
          <input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} style={{ display: "block" }} />
        </label>
        <button onClick={load} disabled={busy}>Generate</button>
      </div>

      {error && (
        <p style={{ color: "#b00020" }}>
          <strong>Not displayed:</strong> {error}
        </p>
      )}

      {pnl && (
        <div style={{ marginBottom: 24 }}>
          <h2>{profile === "manufacturing" ? "Profit and loss" : "CM ladder"}</h2>
          <p>Mapping version #{pnl.mapping_version_id}. Unmapped value this period: ₹{inr(pnl.unmapped_value_inr)}.</p>
          <table cellPadding={6} style={{ borderCollapse: "collapse", width: "100%", maxWidth: 480 }}>
            <tbody>
              {Object.entries(pnl.lines).map(([label, amt]) => (
                <tr key={label} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td>{label}</td>
                  <td style={{ textAlign: "right" }}>{inr(amt)}</td>
                </tr>
              ))}
              {Object.entries(pnl.subtotals).map(([label, amt]) => (
                <tr key={label} style={{ borderBottom: "1px solid #ddd", fontWeight: "bold" }}>
                  <td>{label}</td>
                  <td style={{ textAlign: "right" }}>
                    {label.endsWith("_pct") ? (amt ? `${(Number(amt) * 100).toFixed(1)}%` : "—") : inr(amt)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {bs && (
        <div>
          <h2>Balance sheet</h2>
          <p style={{ color: bs.balances ? "#1a7f37" : "#b00020" }}>
            {bs.balances ? "Balances." : "Does not balance -- would not be displayed."} Unmapped value: ₹{inr(bs.unmapped_value_inr)}.
          </p>
          {Object.entries(bs.groups).map(([group, lines]) => (
            <div key={group} style={{ marginBottom: 12 }}>
              <h3 style={{ marginBottom: 4 }}>{group.replace(/_/g, " ")}</h3>
              <table cellPadding={4} style={{ borderCollapse: "collapse", width: "100%", maxWidth: 480 }}>
                <tbody>
                  {Object.entries(lines).map(([label, amt]) => (
                    <tr key={label}>
                      <td>{label}</td>
                      <td style={{ textAlign: "right" }}>{inr(amt)}</td>
                    </tr>
                  ))}
                  <tr style={{ fontWeight: "bold", borderTop: "1px solid #ddd" }}>
                    <td>Total</td>
                    <td style={{ textAlign: "right" }}>{inr(bs.group_totals[group])}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          ))}
          <p>
            Total assets: ₹{inr(bs.total_assets)} · Total liabilities and equity: ₹{inr(bs.total_liabilities_and_equity)}
          </p>
        </div>
      )}
    </div>
  );
}
