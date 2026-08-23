"use client";

import { useState } from "react";
import { useAuth, useAccessToken } from "@workos-inc/authkit-nextjs/components";
import { uploadFile, UploadResult } from "@/lib/api";

const TEMPLATE_TYPES = ["COA", "TB", "GL", "Bank", "ConsumerSales", "MFGProduction"] as const;
// Per corpus/02 section 2: only these two roles touch ingestion in P0.
const UPLOAD_ALLOWED_ROLES = new Set(["spequla_analyst", "client_finance_lead"]);

export default function UploadPage() {
  const { user, role, organizationId, loading: authLoading } = useAuth();
  const { accessToken } = useAccessToken();

  const [entityId, setEntityId] = useState(1);
  const [templateType, setTemplateType] = useState<(typeof TEMPLATE_TYPES)[number]>("GL");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (authLoading) return <p>Loading...</p>;
  if (!user) return <p>Signing in...</p>;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !accessToken) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await uploadFile(accessToken, templateType, entityId, file);
      setResult(r);
    } catch (err: any) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  if (!role || !UPLOAD_ALLOWED_ROLES.has(role)) {
    return (
      <div>
        <h1>Upload</h1>
        <p>
          Your role ({role ?? "none assigned"}) cannot upload files. Only the SPEQULA analyst and client finance
          lead roles can, per corpus/02 section 2.
        </p>
      </div>
    );
  }

  return (
    <div>
      <h1>Upload</h1>
      <p>
        Chart of accounts, trial balance, or general ledger, against the corpus/01 templates. Signed in as{" "}
        {user.email} ({role}), organization {organizationId}.
      </p>
      <form onSubmit={handleSubmit} style={{ display: "grid", gap: 12, maxWidth: 480 }}>
        <label>
          Entity ID
          <input
            type="number"
            value={entityId}
            onChange={(e) => setEntityId(Number(e.target.value))}
            style={inputStyle}
          />
        </label>
        <label>
          Template
          <select value={templateType} onChange={(e) => setTemplateType(e.target.value as any)} style={inputStyle}>
            {TEMPLATE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label>
          File
          <input
            type="file"
            accept=".csv,.xlsx"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            required
          />
        </label>
        <button type="submit" disabled={busy || !accessToken} style={{ padding: "8px 16px", width: 160 }}>
          {busy ? "Uploading..." : "Upload"}
        </button>
      </form>

      {error && (
        <p style={{ color: "#b00020", marginTop: 16 }}>
          <strong>Blocked:</strong> {error}
        </p>
      )}

      {result && (
        <div style={{ marginTop: 24, padding: 16, border: "1px solid #ddd", borderRadius: 4 }}>
          <p>
            Load run <strong>#{result.load_run_id}</strong> -- {result.status}
          </p>
          <p>
            {result.inserted} inserted, {result.closed_and_reinserted} closed and re-inserted, {result.unchanged}{" "}
            unchanged, {result.quarantined_count} quarantined.
          </p>
          {result.trial_balance.length > 0 && (
            <>
              <p>Trial balance, by period touched:</p>
              <ul>
                {result.trial_balance.map((tb) => (
                  <li key={tb.period_key} style={{ color: tb.balanced ? "#1a7f37" : "#b00020" }}>
                    {tb.period_key}: {tb.balanced ? "balanced" : `does not balance (${tb.total})`}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}

const inputStyle: React.CSSProperties = { display: "block", width: "100%", padding: 6, marginTop: 4 };
