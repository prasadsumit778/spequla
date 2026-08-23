"use client";

import { useState } from "react";
import { useAuth, useAccessToken } from "@workos-inc/authkit-nextjs/components";
import { getDataHealth, DataHealthResult } from "@/lib/api";

const inr = (v: string | null | undefined) => (v == null ? "—" : Number(v).toLocaleString("en-IN"));

export default function DataHealthPage() {
  const { user, loading: authLoading } = useAuth();
  const { accessToken } = useAccessToken();

  const [period, setPeriod] = useState("2025-03");
  const [entityId, setEntityId] = useState(1);
  const [data, setData] = useState<DataHealthResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (authLoading) return <p>Loading...</p>;
  if (!user) return <p>Signing in...</p>;

  async function load() {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      setData(await getDataHealth(accessToken, period, entityId));
    } catch (err: any) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Data health</h1>
      <p>Corpus/09 section 6: freshness, completeness, reconciliation, exceptions -- one page, four panels.</p>

      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 16 }}>
        <label>
          Period (YYYY-MM)
          <input value={period} onChange={(e) => setPeriod(e.target.value)} style={{ display: "block" }} />
        </label>
        <label>
          Entity ID
          <input type="number" value={entityId} onChange={(e) => setEntityId(Number(e.target.value))} style={{ display: "block" }} />
        </label>
        <button onClick={load} disabled={busy}>Load</button>
      </div>

      {error && (
        <p style={{ color: "#b00020" }}>
          <strong>Error:</strong> {error}
        </p>
      )}

      {data && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, maxWidth: 900 }}>
          <div>
            <h3>Freshness</h3>
            <table cellPadding={4} style={{ borderCollapse: "collapse", width: "100%" }}>
              <tbody>
                {data.freshness.map((f) => (
                  <tr key={f.source_system} style={{ borderBottom: "1px solid #f0f0f0" }}>
                    <td>{f.source_system}</td>
                    <td style={{ textAlign: "right" }}>
                      {f.hours_since != null ? `${f.hours_since.toFixed(1)}h ago` : "never loaded"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <h3>Completeness</h3>
            {data.completeness.reason ? (
              <p style={{ fontSize: 13, color: "#888" }}>{data.completeness.reason}</p>
            ) : (
              <>
                <p style={{ fontSize: 28, fontWeight: 700, margin: "4px 0" }}>
                  {data.completeness.mapped_pct != null ? `${(data.completeness.mapped_pct * 100).toFixed(1)}%` : "—"} mapped
                </p>
                <p style={{ fontSize: 14, color: "#b00020" }}>
                  ₹{inr(data.completeness.unmapped_value_inr)} unmapped
                </p>
              </>
            )}
          </div>

          <div>
            <h3>Reconciliation</h3>
            <table cellPadding={4} style={{ borderCollapse: "collapse", width: "100%" }}>
              <tbody>
                {data.reconciliation.map((r, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid #f0f0f0" }}>
                    <td>{r.check_type}</td>
                    <td>{r.status}</td>
                    <td style={{ textAlign: "right" }}>residual ₹{inr(r.residual_inr)}</td>
                  </tr>
                ))}
                {data.reconciliation.length === 0 && (
                  <tr>
                    <td style={{ color: "#888" }}>No reconciliation runs recorded for this period yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div>
            <h3>Exceptions</h3>
            <p style={{ fontSize: 13 }}>
              {Object.entries(data.exceptions.open_by_severity).map(([sev, s]) => (
                <span key={sev} style={{ marginRight: 12 }}>
                  <strong>{sev}</strong>: {s.count} (₹{inr(s.value_inr)})
                </span>
              ))}
            </p>
            <table cellPadding={4} style={{ borderCollapse: "collapse", width: "100%" }}>
              <tbody>
                {data.exceptions.top_ten_by_value.map((e, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid #f0f0f0" }}>
                    <td style={{ fontSize: 12 }}>
                      <strong>{e.severity}</strong> · {e.description}
                    </td>
                    <td style={{ textAlign: "right" }}>₹{inr(e.value_inr)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
