"use client";

import { useState } from "react";
import { useAuth, useAccessToken } from "@workos-inc/authkit-nextjs/components";
import { askQuestion, AskResponse } from "@/lib/api";

const inr = (v: string | null | undefined) => (v == null ? "—" : Number(v).toLocaleString("en-IN"));

const statusColor: Record<string, string> = {
  ok: "#1a7f37",
  blocked: "#b26a00",
  unavailable: "#b26a00",
  refused: "#555",
  rejected: "#b00020",
  error: "#b00020",
};

function AnswerBody({ response }: { response: AskResponse }) {
  if (response.status === "refused" || response.status === "rejected") {
    return (
      <div>
        <p>
          <strong style={{ color: statusColor[response.status] }}>Not answered.</strong> {response.refusal?.reason}
        </p>
        {response.refusal?.nearest_supported_question && (
          <p style={{ fontSize: 13, color: "#555" }}>
            Try instead: <em>{response.refusal.nearest_supported_question}</em>
          </p>
        )}
      </div>
    );
  }

  if (response.status === "blocked" || response.status === "unavailable") {
    return (
      <div>
        <p>
          <strong style={{ color: statusColor[response.status] }}>
            {response.status === "blocked" ? "Blocked by an open decision." : "Not available yet."}
          </strong>{" "}
          {response.refusal?.reason}
        </p>
        {response.result?.blocking_decisions && response.result.blocking_decisions.length > 0 && (
          <p style={{ fontSize: 13, color: "#555" }}>Decisions: {response.result.blocking_decisions.join(", ")}</p>
        )}
      </div>
    );
  }

  if (response.status === "ok") {
    const result = response.result;
    return (
      <div>
        {result?.value != null && (
          <p style={{ fontSize: 28, fontWeight: 700 }}>
            {typeof result.value === "object" ? JSON.stringify(result.value) : `₹${inr(String(result.value))}`}
          </p>
        )}
        {result?.series && result.series.length > 0 && (
          <table cellPadding={4} style={{ borderCollapse: "collapse" }}>
            <tbody>
              {result.series.map((s) => (
                <tr key={s.period}>
                  <td>{s.period}</td>
                  <td style={{ textAlign: "right" }}>{s.status === "ok" ? `₹${inr(s.value)}` : `— (${s.status})`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {result?.bridge && (
          <div style={{ marginTop: 8 }}>
            <p style={{ fontSize: 13, color: result.bridge.components_sum_to_total ? "#1a7f37" : "#b00020" }}>
              {result.bridge.configured
                ? result.bridge.components_sum_to_total
                  ? "Components sum to the total movement."
                  : "Components do NOT sum to the total -- decomposition incomplete."
                : result.bridge.reason}
            </p>
            {result.bridge.components.map((c) => (
              <div key={c.label} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, maxWidth: 320 }}>
                <span>
                  {c.label} {c.is_residual ? "(residual)" : ""}
                </span>
                <span>₹{inr(c.value)}</span>
              </div>
            ))}
          </div>
        )}
        {response.citation && (
          <div style={{ fontSize: 11, color: "#888", marginTop: 10 }}>
            {response.citation.metric} v{response.citation.metric_version} · {response.citation.row_count} rows ·{" "}
            mapping v{response.citation.mapping_version} · <a href={response.citation.drill_url}>{response.citation.query_hash}</a>
            {response.citation.unmapped_value_inr && Number(response.citation.unmapped_value_inr) > 0 && (
              <span> · ₹{inr(response.citation.unmapped_value_inr)} unmapped</span>
            )}
          </div>
        )}
        {result?.value == null && !result?.series?.length && (
          <pre style={{ fontSize: 12, background: "#f7f7f7", padding: 8, overflowX: "auto" }}>
            {JSON.stringify(result?.value ?? {}, null, 2)}
          </pre>
        )}
      </div>
    );
  }

  return <p style={{ color: "#b00020" }}>Something went wrong: {result_reason(response)}</p>;
}

function result_reason(response: AskResponse): string {
  return response.result?.reason || "unknown error";
}

export default function AskPage() {
  const { user, loading: authLoading } = useAuth();
  const { accessToken } = useAccessToken();

  const [question, setQuestion] = useState("How much cash do we have?");
  const [entityId, setEntityId] = useState(1);
  const [profile, setProfile] = useState<"manufacturing" | "consumer">("manufacturing");
  const [response, setResponse] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showSql, setShowSql] = useState(false);

  if (authLoading) return <p>Loading...</p>;
  if (!user) return <p>Signing in...</p>;

  async function submit() {
    if (!accessToken || !question.trim()) return;
    setBusy(true);
    setError(null);
    setShowSql(false);
    try {
      setResponse(await askQuestion(accessToken, question, entityId, profile));
    } catch (err: any) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Ask</h1>
      <p>
        Corpus/07: question, answer, citation, view SQL. Intent classification and IR generation are the only model
        calls (currently unconfigured -- see src/semantic/model_client.py) -- everything from a valid query onward
        runs against your real data.
      </p>

      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 16 }}>
        <label style={{ flex: 1 }}>
          Question
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            style={{ display: "block", width: "100%" }}
          />
        </label>
        <label>
          Entity ID
          <input type="number" value={entityId} onChange={(e) => setEntityId(Number(e.target.value))} style={{ display: "block", width: 80 }} />
        </label>
        <label>
          Profile
          <select value={profile} onChange={(e) => setProfile(e.target.value as any)} style={{ display: "block" }}>
            <option value="manufacturing">Manufacturing</option>
            <option value="consumer">Consumer</option>
          </select>
        </label>
        <button onClick={submit} disabled={busy}>Ask</button>
      </div>

      {error && (
        <p style={{ color: "#b00020" }}>
          <strong>Error:</strong> {error}
        </p>
      )}

      {response && (
        <div style={{ border: "1px solid #ddd", borderRadius: 6, padding: 16, maxWidth: 640 }}>
          <div style={{ fontSize: 12, color: "#888", marginBottom: 8 }}>
            intent: {response.intent ?? "—"} · status:{" "}
            <span style={{ color: statusColor[response.status] || "#000" }}>{response.status}</span>
          </div>
          <AnswerBody response={response} />
          {response.result?.sql_text && (
            <div style={{ marginTop: 12 }}>
              <button onClick={() => setShowSql(!showSql)} style={{ fontSize: 12 }}>
                {showSql ? "Hide" : "View"} SQL
              </button>
              {showSql && (
                <pre style={{ fontSize: 11, background: "#f7f7f7", padding: 8, overflowX: "auto", marginTop: 6 }}>
                  {response.result.sql_text}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
