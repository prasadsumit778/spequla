"use client";

import { useState } from "react";
import { useAuth, useAccessToken } from "@workos-inc/authkit-nextjs/components";
import { listExceptions, resolveException, ExceptionRow } from "@/lib/api";

const inr = (v: string | null | undefined) => (v == null ? "—" : Number(v).toLocaleString("en-IN"));
const severityColor: Record<string, string> = { blocking: "#b00020", warning: "#b26a00", informational: "#555" };

export default function ExceptionsPage() {
  const { user, loading: authLoading } = useAuth();
  const { accessToken } = useAccessToken();

  const [rows, setRows] = useState<ExceptionRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [noteById, setNoteById] = useState<Record<number, string>>({});

  if (authLoading) return <p>Loading...</p>;
  if (!user) return <p>Signing in...</p>;

  async function load() {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      const result = await listExceptions(accessToken, "open");
      setRows(result.exceptions);
    } catch (err: any) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  async function resolve(id: number, resolution: "accepted" | "deferred" | "resolved") {
    if (!accessToken) return;
    const note = noteById[id]?.trim();
    if (!note) {
      setError("A reason is required -- nothing is dismissed without one, per corpus/09 section 4.");
      return;
    }
    try {
      await resolveException(accessToken, id, resolution, note);
      await load();
    } catch (err: any) {
      setError(err.message || String(err));
    }
  }

  return (
    <div>
      <h1>Exception queue</h1>
      <p>
        Corpus/09 section 4: sorted by severity, then by rupee value descending -- always by money, never by count.
        Nothing is dismissed without a reason.
      </p>

      <button onClick={load} disabled={busy} style={{ marginBottom: 16 }}>
        Refresh
      </button>

      {error && (
        <p style={{ color: "#b00020" }}>
          <strong>Error:</strong> {error}
        </p>
      )}

      <table cellPadding={6} style={{ borderCollapse: "collapse", width: "100%", maxWidth: 1000 }}>
        <thead>
          <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
            <th>Severity</th>
            <th>Class</th>
            <th>Period</th>
            <th>Description</th>
            <th style={{ textAlign: "right" }}>Value (₹)</th>
            <th>Resolution note</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.exception_id} style={{ borderBottom: "1px solid #f0f0f0" }}>
              <td style={{ color: severityColor[r.severity] || "#000", fontWeight: 600 }}>{r.severity}</td>
              <td>{r.exception_class}</td>
              <td>{r.period_key || "—"}</td>
              <td style={{ maxWidth: 360 }}>
                {r.description}
                {r.suggested_action && <div style={{ fontSize: 12, color: "#888" }}>{r.suggested_action}</div>}
              </td>
              <td style={{ textAlign: "right" }}>{inr(r.value_inr)}</td>
              <td>
                <input
                  placeholder="Reason (required)"
                  value={noteById[r.exception_id] || ""}
                  onChange={(e) => setNoteById({ ...noteById, [r.exception_id]: e.target.value })}
                  style={{ width: 160 }}
                />
              </td>
              <td style={{ whiteSpace: "nowrap" }}>
                <button onClick={() => resolve(r.exception_id, "accepted")}>Accept</button>{" "}
                <button onClick={() => resolve(r.exception_id, "deferred")}>Defer</button>{" "}
                <button onClick={() => resolve(r.exception_id, "resolved")}>Resolve</button>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={7} style={{ color: "#888", padding: 12 }}>
                No open exceptions -- click Refresh to load.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
