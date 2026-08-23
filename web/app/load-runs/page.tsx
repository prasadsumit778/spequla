"use client";

import { useEffect, useState } from "react";
import { useAuth, useAccessToken } from "@workos-inc/authkit-nextjs/components";
import { listFiles, listLoadRuns, LoadRun, SourceFile } from "@/lib/api";

export default function LoadRunsPage() {
  const { user, loading: authLoading } = useAuth();
  const { accessToken } = useAccessToken();
  const [runs, setRuns] = useState<LoadRun[] | null>(null);
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    Promise.all([listLoadRuns(accessToken), listFiles(accessToken)])
      .then(([r, f]) => {
        setRuns(r);
        setFiles(f);
      })
      .catch((err) => setError(err.message || String(err)));
  }, [accessToken]);

  if (authLoading) return <p>Loading...</p>;
  if (!user) return <p>Signing in...</p>;

  return (
    <div>
      <h1>Load runs</h1>

      {error && <p style={{ color: "#b00020" }}>{error}</p>}

      {runs && (
        <>
          <h2>Runs</h2>
          <table cellPadding={6} style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
                <th>ID</th>
                <th>Status</th>
                <th>Source</th>
                <th>Triggered by</th>
                <th>Started</th>
                <th>Completed</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.load_run_id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td>{r.load_run_id}</td>
                  <td>{r.status}</td>
                  <td>{r.source_system}</td>
                  <td>{r.triggered_by}</td>
                  <td>{r.started_at}</td>
                  <td>{r.completed_at ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {files && (
        <>
          <h2 style={{ marginTop: 24 }}>Files</h2>
          <table cellPadding={6} style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
                <th>File</th>
                <th>Template</th>
                <th>Rows</th>
                <th>Load run</th>
                <th>Received</th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr key={f.source_file_id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td>{f.file_name}</td>
                  <td>{f.template_type}</td>
                  <td>{f.row_count}</td>
                  <td>{f.load_run_id}</td>
                  <td>{f.received_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
