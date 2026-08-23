"use client";

import { useState } from "react";
import { useAuth, useAccessToken } from "@workos-inc/authkit-nextjs/components";
import { createMappingRun, freezeMappingRun, getReviewQueue, FreezeResult, MappingRunResult, QueueRow } from "@/lib/api";

export default function MappingPage() {
  const { user, loading: authLoading } = useAuth();
  const { accessToken } = useAccessToken();

  const [entityId, setEntityId] = useState(1);
  const [effectiveFrom, setEffectiveFrom] = useState("2023-04-01");
  const [run, setRun] = useState<MappingRunResult | null>(null);
  const [queue, setQueue] = useState<QueueRow[] | null>(null);
  const [freeze, setFreeze] = useState<FreezeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (authLoading) return <p>Loading...</p>;
  if (!user) return <p>Signing in...</p>;

  async function handleCreateRun() {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      const r = await createMappingRun(accessToken, entityId, 1, effectiveFrom);
      setRun(r);
      const q = await getReviewQueue(accessToken, r.mapping_version_id);
      setQueue(q);
    } catch (err: any) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleFreeze() {
    if (!accessToken || !run) return;
    setBusy(true);
    setError(null);
    try {
      const f = await freezeMappingRun(accessToken, run.mapping_version_id, entityId);
      setFreeze(f);
    } catch (err: any) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  const unmappedNow = queue && queue.length > 0 ? queue[queue.length - 1].unmapped_value_inr : null;

  return (
    <div>
      <h1>Mapping</h1>
      <p>Extract, apply exact rules, auto-accept, queue the rest -- corpus/06 section 4.</p>

      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 16 }}>
        <label>
          Entity ID
          <input type="number" value={entityId} onChange={(e) => setEntityId(Number(e.target.value))} style={{ display: "block" }} />
        </label>
        <label>
          Effective from
          <input type="date" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} style={{ display: "block" }} />
        </label>
        <button onClick={handleCreateRun} disabled={busy}>Run mapping (version 1)</button>
        {run && <button onClick={handleFreeze} disabled={busy}>Freeze</button>}
      </div>

      {error && <p style={{ color: "#b00020" }}>{error}</p>}

      {run && (
        <p>
          Version <strong>#{run.mapping_version_id}</strong>: {run.auto_accepted} auto-accepted,{" "}
          {run.human_approved} human-approved (judgement classes / conflicts), {run.deferred_to_suspense} deferred
          to suspense.
        </p>
      )}

      {freeze && (
        <p style={{ color: freeze.passed ? "#1a7f37" : "#b00020" }}>
          Freeze gate: <strong>{freeze.passed ? "PASS" : "BLOCKED"}</strong> -- {freeze.reason}
          {freeze.coverage_pct !== null && ` (coverage ${(freeze.coverage_pct * 100).toFixed(2)}%)`}
        </p>
      )}

      {queue && (
        <>
          <h2>Review queue -- sorted by rupee value, descending</h2>
          {unmappedNow !== null && (
            <p>
              <strong>Unmapped value right now: ₹{unmappedNow.toLocaleString("en-IN")}</strong> -- the number that
              must stay on screen, per corpus/06 section 4.3, not a percentage.
            </p>
          )}
          <table cellPadding={6} style={{ borderCollapse: "collapse", width: "100%", fontSize: 14 }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
                <th>Ledger</th>
                <th>Class</th>
                <th>Source</th>
                <th>Approved by</th>
                <th>Value (₹)</th>
                <th>Running % mapped</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((row) => (
                <tr key={row.source_record_id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td>{row.source_account_name}</td>
                  <td style={{ color: row.canonical_class === "suspense.unmapped" ? "#b00020" : undefined }}>
                    {row.canonical_class}
                  </td>
                  <td>{row.proposal_source}</td>
                  <td>{row.approved_by}</td>
                  <td>{Number(row.period_value_inr).toLocaleString("en-IN")}</td>
                  <td>{(row.running_pct_mapped * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
