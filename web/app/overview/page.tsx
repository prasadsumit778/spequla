"use client";

import { useState } from "react";
import { useAuth, useAccessToken } from "@workos-inc/authkit-nextjs/components";
import { getOverviewTiles, MetricTile, OverviewResult } from "@/lib/api";

const inr = (v: string | null | undefined) => (v == null ? "—" : Number(v).toLocaleString("en-IN"));
const isPct = (metric: string) => metric.endsWith("_pct");
const isDays = (metric: string) => ["dso", "dio", "dpo"].includes(metric);

function Tile({ tile }: { tile: MetricTile }) {
  if (tile.status !== "ok") {
    // corpus/08 section 3: "not hidden and not blank" -- and per
    // CLAUDE.md invariant #7, no number is shown here at all, only why.
    return (
      <div style={{ border: "1px solid #e2b400", borderRadius: 6, padding: 12, background: "#fffbea" }}>
        <div style={{ fontSize: 12, color: "#555" }}>{tile.label}</div>
        <div style={{ fontSize: 14, fontWeight: 600, color: "#7a5b00", marginTop: 4 }}>Not available</div>
        <div style={{ fontSize: 12, color: "#7a5b00", marginTop: 4 }}>{tile.reason}</div>
      </div>
    );
  }

  const displayValue = isPct(tile.metric)
    ? `${(Number(tile.value) * 100).toFixed(1)}%`
    : isDays(tile.metric)
    ? `${Number(tile.value).toFixed(0)} days`
    : `₹${inr(tile.value)}`;

  return (
    <div style={{ border: "1px solid #ddd", borderRadius: 6, padding: 12 }}>
      <div style={{ fontSize: 12, color: "#555" }}>{tile.label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, marginTop: 4 }}>{displayValue}</div>
      {tile.citation && (
        <div style={{ fontSize: 11, color: "#888", marginTop: 6 }}>
          v{tile.citation.metric_version} · {tile.citation.row_count} rows · mapping v{tile.citation.mapping_version} ·{" "}
          <a href={tile.citation.drill_url} style={{ color: "#888" }}>
            {tile.citation.query_hash}
          </a>
          {tile.citation.unmapped_value_inr && Number(tile.citation.unmapped_value_inr) > 0 && (
            <span> · ₹{inr(tile.citation.unmapped_value_inr)} unmapped</span>
          )}
        </div>
      )}
    </div>
  );
}

export default function OverviewPage() {
  const { user, loading: authLoading } = useAuth();
  const { accessToken } = useAccessToken();

  const [period, setPeriod] = useState("2025-03");
  const [entityId, setEntityId] = useState(1);
  const [data, setData] = useState<OverviewResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (authLoading) return <p>Loading...</p>;
  if (!user) return <p>Signing in...</p>;

  async function load() {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      setData(await getOverviewTiles(accessToken, period, entityId));
    } catch (err: any) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Financial overview</h1>
      <p>Corpus/08 section 3: nine headline tiles. Every resolved tile carries a citation that drills to source rows.</p>

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
        <>
          <p style={{ fontSize: 13, color: "#555" }}>
            Reconciliation status: <strong>{data.reconciliation_status}</strong>
            {data.mapping_version_id != null && <> · Mapping version #{data.mapping_version_id}</>}
          </p>
          {data.rows.map((row) => (
            <div key={row.row} style={{ marginBottom: 20 }}>
              <h3 style={{ marginBottom: 8 }}>{row.row}</h3>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(180px, 1fr))", gap: 12, maxWidth: 720 }}>
                {row.tiles.map((tile) => (
                  <Tile key={tile.metric} tile={tile} />
                ))}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
