"use client";

import { useEffect, useState } from "react";
import { useAuth, useAccessToken } from "@workos-inc/authkit-nextjs/components";
import {
  BlockingException,
  ReportArtefact,
  ReportSummary,
  exportReportUrl,
  generateReport,
  getBlockingExceptions,
  getReport,
  listReports,
  signReport,
  updateCommentary,
} from "@/lib/api";

const inr = (v: string | number | null | undefined) => (v == null ? "—" : Number(v).toLocaleString("en-IN"));

const statusColor: Record<string, string> = { draft: "#b26a00", signed: "#1a7f37" };

function ChartSpecView({ spec }: { spec: any }) {
  if (spec.chart_type === "kpi_tile") {
    return (
      <div style={{ border: "1px solid #eee", borderRadius: 6, padding: 10, minWidth: 140 }}>
        <div style={{ fontSize: 11, color: "#888" }}>{spec.title}</div>
        <div style={{ fontSize: 20, fontWeight: 700 }}>{spec.unit === "INR" ? `₹${inr(spec.value)}` : spec.value ?? "—"}</div>
        <div style={{ fontSize: 11, color: "#666" }}>
          MoM {spec.delta_vs_prior_month == null ? "—" : inr(spec.delta_vs_prior_month)} · YoY{" "}
          {spec.delta_vs_prior_year == null ? "—" : inr(spec.delta_vs_prior_year)}
        </div>
      </div>
    );
  }
  if (spec.chart_type === "line") {
    const points = spec.series?.[0]?.points || [];
    return (
      <div style={{ border: "1px solid #eee", borderRadius: 6, padding: 10, fontSize: 11 }}>
        <div style={{ color: "#888", marginBottom: 4 }}>{spec.title}</div>
        <div style={{ display: "flex", gap: 6, overflowX: "auto" }}>
          {points.map((p: any) => (
            <span key={p.period}>{p.period.slice(2)}: {p.value == null ? "—" : inr(p.value)}</span>
          ))}
        </div>
      </div>
    );
  }
  if (spec.chart_type === "table") {
    return (
      <div style={{ border: "1px solid #eee", borderRadius: 6, padding: 10, fontSize: 11, overflowX: "auto" }}>
        <div style={{ color: "#888", marginBottom: 4 }}>{spec.title}</div>
        <table cellPadding={3}>
          <thead><tr>{spec.columns.map((c: string) => <th key={c} style={{ textAlign: "left" }}>{c}</th>)}</tr></thead>
          <tbody>
            {spec.rows.map((row: any[], i: number) => (
              <tr key={i}>{row.map((c, j) => <td key={j}>{typeof c === "number" ? inr(c) : c ?? "—"}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return <pre style={{ fontSize: 10 }}>{JSON.stringify(spec)}</pre>;
}

export default function ReportsPage() {
  const { user, loading: authLoading } = useAuth();
  const { accessToken } = useAccessToken();

  const [period, setPeriod] = useState("2026-04");
  const [entityId, setEntityId] = useState(1);
  const [profile, setProfile] = useState<"manufacturing" | "consumer">("manufacturing");
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [selected, setSelected] = useState<ReportArtefact | null>(null);
  const [blocking, setBlocking] = useState<BlockingException[]>([]);
  const [commentary, setCommentary] = useState("");
  const [overrideReason, setOverrideReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  async function refreshList() {
    if (!accessToken) return;
    try {
      setReports(await listReports(accessToken, period, entityId));
    } catch (e: any) {
      setError(e.message || String(e));
    }
  }

  useEffect(() => { refreshList(); }, [accessToken, period, entityId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function openReport(id: number) {
    if (!accessToken) return;
    setError(null);
    try {
      const r = await getReport(accessToken, id);
      setSelected(r);
      setCommentary(r.commentary || "");
      setOverrideReason("");
      if (r.status === "draft") {
        setBlocking((await getBlockingExceptions(accessToken, id)).blocking_exceptions);
      } else {
        setBlocking([]);
      }
    } catch (e: any) {
      setError(e.message || String(e));
    }
  }

  async function generate() {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      const summary = await generateReport(accessToken, period, entityId, profile);
      await refreshList();
      await openReport(summary.report_artefact_id);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveCommentary() {
    if (!accessToken || !selected) return;
    setBusy(true);
    setError(null);
    try {
      await updateCommentary(accessToken, selected.report_artefact_id, commentary);
      await openReport(selected.report_artefact_id);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function sign() {
    if (!accessToken || !selected) return;
    setBusy(true);
    setError(null);
    try {
      await signReport(accessToken, selected.report_artefact_id, overrideReason || undefined);
      await refreshList();
      await openReport(selected.report_artefact_id);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  if (authLoading) return <p>Loading...</p>;
  if (!user) return <p>Signing in...</p>;

  const cover = selected?.sections?.["1_cover"];
  const financialSummary = selected?.sections?.["3_financial_summary"];
  const dataQuality = selected?.sections?.["9_data_quality_appendix"];

  return (
    <div>
      <h1>Reports</h1>
      <p style={{ fontSize: 13, color: "#666" }}>
        Corpus/08 section 7: the eight-section monthly management pack. Commentary (section 2) is human-written --
        this screen is an editor, not a generator. Signing is gated on open blocking exceptions for the period
        (corpus/08 section 10).
      </p>

      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 16 }}>
        <label>Period<input value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="YYYY-MM" style={{ display: "block", width: 100 }} /></label>
        <label>Entity ID<input type="number" value={entityId} onChange={(e) => setEntityId(Number(e.target.value))} style={{ display: "block", width: 80 }} /></label>
        <label>Profile
          <select value={profile} onChange={(e) => setProfile(e.target.value as any)} style={{ display: "block" }}>
            <option value="manufacturing">Manufacturing</option>
            <option value="consumer">Consumer</option>
          </select>
        </label>
        <button onClick={generate} disabled={busy}>Generate pack</button>
      </div>

      {error && <p style={{ color: "#b00020" }}><strong>Error:</strong> {error}</p>}

      <div style={{ display: "flex", gap: 24 }}>
        <div style={{ minWidth: 220 }}>
          <h3 style={{ fontSize: 13 }}>Generations for {period}</h3>
          {reports.length === 0 && <p style={{ fontSize: 12, color: "#888" }}>None yet.</p>}
          <ul style={{ listStyle: "none", padding: 0, fontSize: 12 }}>
            {reports.map((r) => (
              <li key={r.report_artefact_id} style={{ marginBottom: 6 }}>
                <button onClick={() => openReport(r.report_artefact_id)}
                          style={{ textAlign: "left", width: "100%", background: selected?.report_artefact_id === r.report_artefact_id ? "#f0f0f0" : "transparent" }}>
                  #{r.report_artefact_id} · <span style={{ color: statusColor[r.status] }}>{r.status}</span>
                  <br />{r.generated_at?.slice(0, 16)}
                </button>
              </li>
            ))}
          </ul>
        </div>

        {selected && (
          <div style={{ flex: 1, maxWidth: 720 }}>
            <div style={{ fontSize: 12, color: "#888", marginBottom: 8 }}>
              #{selected.report_artefact_id} · <span style={{ color: statusColor[selected.status] }}>{selected.status}</span>
              {selected.status === "signed" && <> · reviewer: {selected.reviewer} · signed {selected.signed_at?.slice(0, 16)}</>}
              {" · "}<a href={exportReportUrl(selected.report_artefact_id)} target="_blank" rel="noreferrer">export</a>
            </div>

            <h3>1. Cover</h3>
            {cover && (
              <div style={{ fontSize: 12 }}>
                <p>Period {cover.period_key} · basis {cover.basis} · reconciliation: {cover.reconciliation_status}</p>
                <p>Unmapped: ₹{inr(cover.unmapped_value_inr)} · mapping v{cover.mapping_version_no}</p>
              </div>
            )}

            <h3>2. Executive summary</h3>
            {selected.status === "draft" ? (
              <div>
                <textarea value={commentary} onChange={(e) => setCommentary(e.target.value)}
                            placeholder="Six to eight bullet points, written by a human."
                            style={{ width: "100%", minHeight: 100, fontFamily: "inherit" }} />
                <div><button onClick={saveCommentary} disabled={busy}>Save commentary</button></div>
              </div>
            ) : (
              <pre style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{selected.commentary || "(none written)"}</pre>
            )}

            <h3>3. Financial summary</h3>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {selected.chart_specs.filter((c) => c.chart_type === "kpi_tile").map((c, i) => (
                <ChartSpecView key={i} spec={c} />
              ))}
            </div>

            <h3>6. Working capital trends / 7. Cash</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {selected.chart_specs.filter((c) => c.chart_type === "line").map((c, i) => (
                <ChartSpecView key={i} spec={c} />
              ))}
            </div>

            <h3>5. Margin analysis</h3>
            {selected.chart_specs.filter((c) => c.chart_type === "table").map((c, i) => (
              <ChartSpecView key={i} spec={c} />
            ))}

            <h3>9. Data quality appendix</h3>
            {dataQuality && (
              <div style={{ fontSize: 12 }}>
                <p>{dataQuality.open_exceptions?.length ?? 0} open exception(s) · unmapped ₹{inr(dataQuality.unmapped_value_inr)}</p>
                {dataQuality.known_limitations?.length > 0 && (
                  <ul>{dataQuality.known_limitations.map((l: string, i: number) => <li key={i}>{l}</li>)}</ul>
                )}
                {dataQuality.signoff_override && (
                  <p style={{ color: "#b26a00" }}>
                    Signed with override: {dataQuality.signoff_override.reason} (by {dataQuality.signoff_override.by})
                  </p>
                )}
              </div>
            )}

            {selected.status === "draft" && (
              <div style={{ marginTop: 16, border: "1px solid #ddd", borderRadius: 6, padding: 12 }}>
                <h3 style={{ marginTop: 0 }}>Sign off</h3>
                {blocking.length > 0 && (
                  <div style={{ fontSize: 12, color: "#b00020", marginBottom: 8 }}>
                    <p><strong>{blocking.length} open blocking exception(s) for {selected.period_key}</strong> -- signing requires a written override reason.</p>
                    <ul>{blocking.map((b) => <li key={b.exception_id}>{b.description}</li>)}</ul>
                    <input value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)}
                             placeholder="Override reason (logged, appears in section 9)" style={{ width: "100%" }} />
                  </div>
                )}
                <button onClick={sign} disabled={busy || (blocking.length > 0 && !overrideReason.trim())}>
                  Sign as {user.email}
                </button>
              </div>
            )}

            <div style={{ marginTop: 16 }}>
              <button onClick={() => setShowRaw(!showRaw)} style={{ fontSize: 12 }}>{showRaw ? "Hide" : "View"} full pack JSON</button>
              {showRaw && <pre style={{ fontSize: 10, background: "#f7f7f7", padding: 8, overflowX: "auto", maxHeight: 400 }}>{JSON.stringify(selected.sections, null, 2)}</pre>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
