"use client";

import { useEffect, useState } from "react";
import { useAuth, useAccessToken } from "@workos-inc/authkit-nextjs/components";
import {
  AccessGrant,
  AuditLogRow,
  ModelCost,
  RestoreRehearsalResult,
  TenantSummary,
  createAccessGrant,
  deleteTenant,
  getAccessGrants,
  getAuditLog,
  getModelCost,
  listTenants,
  revokeAccessGrant,
  runRestoreRehearsal,
} from "@/lib/api";

const ROLES = [
  { role: "promoter", who: "Owner, MD or CEO", sees: "Financial overview, Ask, Reports. No mapping screens, no exception queue." },
  { role: "client_finance_lead", who: "CFO, controller or CA", sees: "Everything except SPEQULA internal admin." },
  { role: "spequla_analyst", who: "SPEQULA, for pilot one", sees: "Everything, plus the exception queue and the audit log." },
  { role: "admin", who: "Engineering", sees: "System configuration. No default access to client data." },
];

function GrantsPanel({ accessToken, tenantId }: { accessToken: string; tenantId: string }) {
  const [grants, setGrants] = useState<AccessGrant[]>([]);
  const [employeeUserId, setEmployeeUserId] = useState("");
  const [employeeName, setEmployeeName] = useState("");
  const [reason, setReason] = useState("");
  const [hours, setHours] = useState(24);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setGrants(await getAccessGrants(accessToken, tenantId));
  }
  useEffect(() => { refresh(); }, [tenantId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function submitGrant() {
    setBusy(true);
    setError(null);
    try {
      const expiresAt = new Date(Date.now() + hours * 3600 * 1000).toISOString();
      await createAccessGrant(accessToken, tenantId, employeeUserId, employeeName, reason, expiresAt);
      setEmployeeUserId(""); setEmployeeName(""); setReason("");
      await refresh();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doRevoke(grantId: number) {
    setBusy(true);
    try {
      await revokeAccessGrant(accessToken, grantId);
      await refresh();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h3>Employee access grants</h3>
      <p style={{ fontSize: 12, color: "#666" }}>
        Corpus/02 section 7: "Employee-level access to client data is time-bound, named and logged." Every grant expires;
        there is no standing access.
      </p>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 12, flexWrap: "wrap" }}>
        <label>User id<input value={employeeUserId} onChange={(e) => setEmployeeUserId(e.target.value)} style={{ display: "block", width: 140 }} /></label>
        <label>Name<input value={employeeName} onChange={(e) => setEmployeeName(e.target.value)} style={{ display: "block", width: 140 }} /></label>
        <label>Reason<input value={reason} onChange={(e) => setReason(e.target.value)} style={{ display: "block", width: 200 }} /></label>
        <label>Hours<input type="number" value={hours} onChange={(e) => setHours(Number(e.target.value))} style={{ display: "block", width: 70 }} /></label>
        <button onClick={submitGrant} disabled={busy || !employeeUserId || !employeeName || !reason}>Grant access</button>
      </div>
      {error && <p style={{ color: "#b00020", fontSize: 12 }}>{error}</p>}
      <table cellPadding={6} style={{ borderCollapse: "collapse", fontSize: 13, width: "100%" }}>
        <thead><tr style={{ borderBottom: "1px solid #ddd", textAlign: "left" }}>
          <th>Employee</th><th>Reason</th><th>Granted</th><th>Expires</th><th>Status</th><th></th>
        </tr></thead>
        <tbody>
          {grants.map((g) => (
            <tr key={g.grant_id} style={{ borderBottom: "1px solid #f0f0f0" }}>
              <td>{g.employee_name} ({g.employee_user_id})</td>
              <td>{g.reason}</td>
              <td>{g.granted_at.slice(0, 16)}</td>
              <td>{g.expires_at.slice(0, 16)}</td>
              <td style={{ color: g.is_active ? "#1a7f37" : "#888" }}>{g.is_active ? "active" : (g.revoked_at ? "revoked" : "expired")}</td>
              <td>{g.is_active && <button onClick={() => doRevoke(g.grant_id)} disabled={busy}>Revoke</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AuditLogPanel({ accessToken, tenantId }: { accessToken: string; tenantId: string }) {
  const [rows, setRows] = useState<AuditLogRow[]>([]);
  useEffect(() => { getAuditLog(accessToken, tenantId).then(setRows); }, [accessToken, tenantId]);
  return (
    <div>
      <h3>Audit log</h3>
      {rows.length === 0 && <p style={{ fontSize: 12, color: "#888" }}>No audited actions for this tenant yet.</p>}
      <table cellPadding={6} style={{ borderCollapse: "collapse", fontSize: 12, width: "100%" }}>
        <thead><tr style={{ borderBottom: "1px solid #ddd", textAlign: "left" }}>
          <th>When</th><th>Actor</th><th>Action</th><th>Object</th><th>Detail</th>
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.audit_id} style={{ borderBottom: "1px solid #f5f5f5" }}>
              <td>{r.occurred_at.slice(0, 19)}</td>
              <td>{r.actor}</td>
              <td>{r.action}</td>
              <td>{r.object_type}{r.object_ref ? ` #${r.object_ref}` : ""}</td>
              <td style={{ maxWidth: 300, overflowX: "auto" }}>{r.detail ? JSON.stringify(r.detail) : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OperationsPanel({ accessToken, tenant }: { accessToken: string; tenant: TenantSummary }) {
  const [cost, setCost] = useState<ModelCost | null>(null);
  const [rehearsal, setRehearsal] = useState<RestoreRehearsalResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmName, setConfirmName] = useState("");
  const [deleteReason, setDeleteReason] = useState("");
  const [deleted, setDeleted] = useState(false);

  useEffect(() => { getModelCost(accessToken, tenant.tenant_id).then(setCost); }, [accessToken, tenant.tenant_id]);

  async function doRehearsal() {
    setBusy(true);
    setError(null);
    try {
      setRehearsal(await runRestoreRehearsal(accessToken, tenant.tenant_id));
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doDelete() {
    setBusy(true);
    setError(null);
    try {
      await deleteTenant(accessToken, tenant.tenant_id, deleteReason);
      setDeleted(true);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h3>Model cost</h3>
      {cost && (
        <p style={{ fontSize: 13 }}>
          {cost.total_queries} quer{cost.total_queries === 1 ? "y" : "ies"} logged, {cost.priced_queries} with recorded cost.
          Total: ₹{Number(cost.total_cost_inr).toLocaleString("en-IN")}
          {cost.priced_queries === 0 && (
            <span style={{ color: "#888" }}> -- no model is configured yet (src/semantic/model_client.py), so nothing has a real cost.</span>
          )}
        </p>
      )}

      <h3>Restore rehearsal</h3>
      <p style={{ fontSize: 12, color: "#666" }}>
        Clones every table in this tenant's schema into a throwaway schema, verifies row counts, then drops the clone.
        Point-in-time recovery itself is a Supabase platform feature; this proves the data is fully reconstructible.
      </p>
      <button onClick={doRehearsal} disabled={busy}>Run rehearsal</button>
      {rehearsal && (
        <div style={{ marginTop: 8, fontSize: 12 }}>
          <strong style={{ color: rehearsal.passed ? "#1a7f37" : "#b00020" }}>{rehearsal.passed ? "Passed" : "Failed"}</strong>
          {" "}-- {rehearsal.tables.length} tables checked.
        </div>
      )}

      {!tenant.is_synthetic && (
        <div style={{ marginTop: 24, border: "1px solid #b00020", borderRadius: 6, padding: 12 }}>
          <h3 style={{ marginTop: 0, color: "#b00020" }}>Delete tenant</h3>
          <p style={{ fontSize: 12 }}>
            Irreversible. Drops the tenant's entire schema and purges PII-bearing records. No retention period is
            enforced automatically -- this is the only path, and it only runs on an explicit named request.
          </p>
          {deleted ? (
            <p style={{ color: "#1a7f37" }}>Deleted.</p>
          ) : (
            <>
              <input placeholder="Reason" value={deleteReason} onChange={(e) => setDeleteReason(e.target.value)} style={{ display: "block", width: "100%", marginBottom: 8 }} />
              <input placeholder={`Type "${tenant.name}" to confirm`} value={confirmName} onChange={(e) => setConfirmName(e.target.value)} style={{ display: "block", width: "100%", marginBottom: 8 }} />
              <button onClick={doDelete} disabled={busy || !deleteReason || confirmName !== tenant.name} style={{ color: "#b00020" }}>
                Delete {tenant.name}
              </button>
            </>
          )}
        </div>
      )}
      {error && <p style={{ color: "#b00020", fontSize: 12 }}>{error}</p>}
    </div>
  );
}

export default function SettingsPage() {
  const { user, loading: authLoading } = useAuth();
  const { accessToken } = useAccessToken();
  const [tenants, setTenants] = useState<TenantSummary[] | null>(null);
  const [selected, setSelected] = useState<TenantSummary | null>(null);
  const [forbidden, setForbidden] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    listTenants(accessToken)
      .then((t) => { setTenants(t); if (t.length > 0) setSelected(t[0]); })
      .catch((e) => { if (String(e.message || e).includes("403")) setForbidden(true); });
  }, [accessToken]);

  if (authLoading) return <p>Loading...</p>;
  if (!user || !accessToken) return <p>Signing in...</p>;

  return (
    <div>
      <h1>Settings</h1>

      <h2 style={{ fontSize: 16 }}>Roles and permissions</h2>
      <table cellPadding={6} style={{ borderCollapse: "collapse", fontSize: 13, marginBottom: 24 }}>
        <thead><tr style={{ borderBottom: "1px solid #ddd", textAlign: "left" }}><th>Role</th><th>Who</th><th>Sees</th></tr></thead>
        <tbody>
          {ROLES.map((r) => (
            <tr key={r.role} style={{ borderBottom: "1px solid #f0f0f0" }}>
              <td>{r.role}</td><td>{r.who}</td><td>{r.sees}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {forbidden && <p style={{ color: "#888" }}>Tenancy administration (grants, audit log, deletion) is admin-only.</p>}

      {!forbidden && tenants && (
        <div>
          <h2 style={{ fontSize: 16 }}>Tenants</h2>
          <select value={selected?.tenant_id || ""} onChange={(e) => setSelected(tenants.find((t) => t.tenant_id === e.target.value) || null)}
                    style={{ marginBottom: 16 }}>
            {tenants.map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>
                {t.name}{t.deleted_at ? " (deleted)" : ""}
              </option>
            ))}
          </select>

          {selected && !selected.deleted_at && (
            <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
              <GrantsPanel accessToken={accessToken} tenantId={selected.tenant_id} />
              <AuditLogPanel accessToken={accessToken} tenantId={selected.tenant_id} />
              <OperationsPanel accessToken={accessToken} tenant={selected} />
            </div>
          )}
          {selected?.deleted_at && <p style={{ color: "#888" }}>This tenant was deleted on {selected.deleted_at.slice(0, 10)}.</p>}
        </div>
      )}
    </div>
  );
}
