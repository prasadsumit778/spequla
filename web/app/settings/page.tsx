"use client";

import { useState } from "react";
import { useAuth } from "@workos-inc/authkit-nextjs/components";
import {
  createAccessGrant,
  deleteTenant,
  getAccessGrants,
  getAuditLog,
  getModelCost,
  listTenants,
  revokeAccessGrant,
  runRestoreRehearsal,
  type RestoreRehearsalResult,
  type TenantSummary,
} from "@/lib/api";
import { useApiAction, useApiQuery } from "@/lib/useApi";
import { exactAmount, formatCount, formatDate, formatDateTime } from "@/lib/format";
import { roleLabel } from "@/components/app/AppShell";
import PageHeader from "@/components/app/PageHeader";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import Disclosure, { CodeBlock } from "@/components/ui/Disclosure";
import { Input, Select } from "@/components/ui/Field";
import { Table, TBody, TD, TFrame, TH, THead, TR } from "@/components/ui/TableExports";
import { Callout, EmptyState, ErrorState, Skeleton, SkeletonTable } from "@/components/ui/States";

/** corpus/02 section 2: four roles, no more in the MVP. */
const ROLES = [
  {
    role: "promoter",
    who: "Owner, MD or CEO",
    sees: "Financial overview, Ask and the pack. No mapping screens and no exception queue.",
  },
  {
    role: "client_finance_lead",
    who: "CFO, financial controller, or the CA",
    sees: "Everything except SPEQULA's own internal administration.",
  },
  {
    role: "spequla_analyst",
    who: "SPEQULA, for pilot one",
    sees: "Everything, plus the exception queue and the audit log.",
  },
  {
    role: "admin",
    who: "Engineering",
    sees: "System configuration. No default access to client data.",
  },
];

export default function SettingsPage() {
  const { role } = useAuth();
  const tenants = useApiQuery((token) => listTenants(token), []);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selected =
    tenants.data?.find((t) => t.tenant_id === selectedId) ?? tenants.data?.[0] ?? null;

  return (
    <>
      <PageHeader
        title="Settings"
        description="Who can see what, who has been given temporary access to this company's data, and every action that has been taken on it."
        corpusRef="corpus/02 sections 2 and 7"
      />

      <Card className="mb-4">
        <CardHeader
          title="Roles"
          description="Four roles, no more in the MVP"
          actions={role ? <Badge tone="info">You are {roleLabel(role)}</Badge> : null}
        />
        <TFrame>
          <Table>
            <THead>
              <TR>
                <TH>Role</TH>
                <TH>Who</TH>
                <TH>What they see</TH>
              </TR>
            </THead>
            <TBody>
              {ROLES.map((r) => (
                <TR key={r.role} selected={r.role === role}>
                  <TD className="font-medium whitespace-nowrap text-ink">{roleLabel(r.role)}</TD>
                  <TD className="whitespace-nowrap">{r.who}</TD>
                  <TD>{r.sees}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </TFrame>
        <CardBody className="border-t border-line">
          <p className="text-[12.5px] leading-5 text-ink-muted">
            Employee access to client data is time-bound, named and logged. There is no standing access — every grant
            below expires.
          </p>
        </CardBody>
      </Card>

      {tenants.error && (
        <Card>
          <CardBody>
            <ErrorState
              title="Tenant administration is not available"
              message={tenants.error}
              hint="Grants, the audit log and tenant deletion are administrator-only. If you are not an administrator, this is expected and everything else on this screen still applies to you."
              onRetry={tenants.reload}
            />
          </CardBody>
        </Card>
      )}

      {!tenants.error && !tenants.data && tenants.loading && (
        <Card>
          <CardBody className="space-y-3">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-28 w-full" />
          </CardBody>
        </Card>
      )}

      {!tenants.error && tenants.data?.length === 0 && (
        <Card>
          <EmptyState title="No tenants" description="No tenant is visible to your account." />
        </Card>
      )}

      {!tenants.error && tenants.data && tenants.data.length > 0 && selected && (
        <div className="space-y-4">
          <Card>
            <CardHeader title="Tenant" description="Everything below applies to the tenant selected here" />
            <CardBody>
              <div className="flex flex-wrap items-end gap-3">
                <Select
                  label="Tenant"
                  value={selected.tenant_id}
                  onChange={(e) => setSelectedId(e.target.value)}
                  fieldClassName="min-w-[240px]"
                >
                  {tenants.data.map((t) => (
                    <option key={t.tenant_id} value={t.tenant_id}>
                      {t.name}
                      {t.deleted_at ? " (deleted)" : ""}
                    </option>
                  ))}
                </Select>
                <div className="flex flex-wrap gap-2 pb-1">
                  {selected.is_synthetic && <Badge tone="info">synthetic data</Badge>}
                  {selected.deleted_at && <Badge tone="blocking">deleted {formatDate(selected.deleted_at)}</Badge>}
                  <Badge tone="neutral">schema {selected.schema_name}</Badge>
                </div>
              </div>
            </CardBody>
          </Card>

          {selected.deleted_at ? (
            <Card>
              <EmptyState
                title="This tenant was deleted"
                description={`Deleted on ${formatDate(selected.deleted_at)}. Its schema and PII-bearing records were purged.`}
              />
            </Card>
          ) : (
            <>
              <GrantsPanel tenant={selected} />
              <AuditLogPanel tenant={selected} />
              <OperationsPanel tenant={selected} />
            </>
          )}
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ grants */

function GrantsPanel({ tenant }: { tenant: TenantSummary }) {
  const grants = useApiQuery((token) => getAccessGrants(token, tenant.tenant_id), [tenant.tenant_id]);
  const create = useApiAction(createAccessGrant);
  const revoke = useApiAction(revokeAccessGrant);

  const [employeeUserId, setEmployeeUserId] = useState("");
  const [employeeName, setEmployeeName] = useState("");
  const [reason, setReason] = useState("");
  const [hours, setHours] = useState(24);

  const complete = employeeUserId.trim() && employeeName.trim() && reason.trim();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!complete) return;
    const expiresAt = new Date(Date.now() + hours * 3600 * 1000).toISOString();
    const result = await create.run(tenant.tenant_id, employeeUserId.trim(), employeeName.trim(), reason.trim(), expiresAt);
    if (result) {
      setEmployeeUserId("");
      setEmployeeName("");
      setReason("");
      grants.reload();
    }
  }

  async function handleRevoke(grantId: number) {
    const result = await revoke.run(grantId);
    if (result) grants.reload();
  }

  return (
    <Card>
      <CardHeader
        title="Employee access grants"
        description="Named, time-bound and logged. There is no standing access to a client's data."
      />

      <CardBody className="border-b border-line">
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <Input
            label="User id"
            value={employeeUserId}
            onChange={(e) => setEmployeeUserId(e.target.value)}
            fieldClassName="w-44"
          />
          <Input
            label="Name"
            value={employeeName}
            onChange={(e) => setEmployeeName(e.target.value)}
            fieldClassName="w-44"
          />
          <Input
            label="Reason"
            placeholder="Why this person needs access"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            fieldClassName="min-w-[220px] flex-1"
          />
          <Input
            label="Expires in (hours)"
            type="number"
            min={1}
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            fieldClassName="w-36"
          />
          <Button type="submit" variant="primary" disabled={!complete} busy={create.busy} busyLabel="Granting">
            Grant access
          </Button>
        </form>
        {create.error && <ErrorState title="No grant was created" message={create.error} className="mt-3" />}
        {revoke.error && <ErrorState title="The grant was not revoked" message={revoke.error} className="mt-3" />}
      </CardBody>

      {grants.error && (
        <CardBody>
          <ErrorState title="Grants could not be listed" message={grants.error} onRetry={grants.reload} />
        </CardBody>
      )}

      {!grants.error && !grants.data && grants.loading && <SkeletonTable rows={3} cols={5} />}

      {!grants.error && grants.data?.length === 0 && (
        <EmptyState
          icon="check"
          title="Nobody has access"
          description="No SPEQULA employee currently holds a grant on this tenant's data."
        />
      )}

      {!grants.error && grants.data && grants.data.length > 0 && (
        <TFrame>
          <Table>
            <THead>
              <TR>
                <TH>Employee</TH>
                <TH>Reason</TH>
                <TH>Granted</TH>
                <TH>Expires</TH>
                <TH>State</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {grants.data.map((grant) => (
                <TR key={grant.grant_id}>
                  <TD>
                    <span className="font-medium text-ink">{grant.employee_name}</span>
                    <span className="mt-0.5 block font-mono text-[11px] text-ink-faint">{grant.employee_user_id}</span>
                  </TD>
                  <TD className="max-w-xs">{grant.reason}</TD>
                  <TD className="whitespace-nowrap">{formatDateTime(grant.granted_at)}</TD>
                  <TD className="whitespace-nowrap">{formatDateTime(grant.expires_at)}</TD>
                  <TD>
                    {grant.is_active ? (
                      <Badge tone="warning" dot>
                        active
                      </Badge>
                    ) : grant.revoked_at ? (
                      <Badge tone="neutral">revoked</Badge>
                    ) : (
                      <Badge tone="neutral">expired</Badge>
                    )}
                  </TD>
                  <TD align="right">
                    {grant.is_active && (
                      <Button size="sm" variant="secondary" onClick={() => handleRevoke(grant.grant_id)} busy={revoke.busy}>
                        Revoke
                      </Button>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </TFrame>
      )}
    </Card>
  );
}

/* --------------------------------------------------------------- audit log */

function AuditLogPanel({ tenant }: { tenant: TenantSummary }) {
  const log = useApiQuery((token) => getAuditLog(token, tenant.tenant_id), [tenant.tenant_id]);

  return (
    <Card>
      <CardHeader
        title="Audit log"
        description="Every audited action on this tenant, newest first"
        actions={
          <Button variant="secondary" size="sm" onClick={log.reload} busy={log.loading} busyLabel="Loading">
            Refresh
          </Button>
        }
      />

      {log.error && (
        <CardBody>
          <ErrorState title="The audit log could not be read" message={log.error} onRetry={log.reload} />
        </CardBody>
      )}

      {!log.error && !log.data && log.loading && <SkeletonTable rows={4} cols={5} />}

      {!log.error && log.data?.length === 0 && (
        <EmptyState title="Nothing audited yet" description="Audited actions on this tenant appear here as they happen." />
      )}

      {!log.error && log.data && log.data.length > 0 && (
        <TFrame>
          <Table>
            <THead>
              <TR>
                <TH>When</TH>
                <TH>Actor</TH>
                <TH>Action</TH>
                <TH>Object</TH>
                <TH>Detail</TH>
              </TR>
            </THead>
            <TBody>
              {log.data.map((row) => (
                <TR key={row.audit_id}>
                  <TD className="whitespace-nowrap">{formatDateTime(row.occurred_at)}</TD>
                  <TD className="max-w-[200px] truncate" title={row.actor}>
                    {row.actor}
                    {row.role_key && <span className="mt-0.5 block text-[11px] text-ink-faint">{row.role_key}</span>}
                  </TD>
                  <TD className="font-medium text-ink">{row.action}</TD>
                  <TD>
                    {row.object_type}
                    {row.object_ref ? ` #${row.object_ref}` : ""}
                  </TD>
                  <TD className="max-w-sm">
                    {row.detail ? (
                      <Disclosure label="Show">
                        <CodeBlock>{JSON.stringify(row.detail, null, 2)}</CodeBlock>
                      </Disclosure>
                    ) : (
                      "—"
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </TFrame>
      )}
    </Card>
  );
}

/* -------------------------------------------------------------- operations */

function OperationsPanel({ tenant }: { tenant: TenantSummary }) {
  const cost = useApiQuery((token) => getModelCost(token, tenant.tenant_id), [tenant.tenant_id]);
  const rehearse = useApiAction(runRestoreRehearsal);
  const remove = useApiAction(deleteTenant);

  const [rehearsal, setRehearsal] = useState<RestoreRehearsalResult | null>(null);
  const [confirmName, setConfirmName] = useState("");
  const [deleteReason, setDeleteReason] = useState("");
  const [deleted, setDeleted] = useState(false);

  async function handleRehearsal() {
    const result = await rehearse.run(tenant.tenant_id);
    if (result) setRehearsal(result);
  }

  async function handleDelete() {
    const result = await remove.run(tenant.tenant_id, deleteReason.trim());
    if (result) setDeleted(true);
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader title="Model cost" description="What the question-answering has cost on this tenant" />
        <CardBody>
          {cost.error && <ErrorState title="Cost could not be read" message={cost.error} onRetry={cost.reload} />}
          {!cost.error && !cost.data && cost.loading && <Skeleton className="h-16 w-full" />}
          {!cost.error && cost.data && (
            <>
              <p className="figure text-[24px] font-semibold">{exactAmount(cost.data.total_cost_inr)}</p>
              <p className="mt-1 text-[13px] text-ink-muted">
                {formatCount(cost.data.total_queries)} quer{cost.data.total_queries === 1 ? "y" : "ies"} logged,{" "}
                {formatCount(cost.data.priced_queries)} with a recorded cost.
              </p>
              {cost.data.priced_queries === 0 && (
                <Callout tone="neutral" className="mt-3">
                  No model is configured yet, so nothing has a real cost attached. Questions are refused rather than
                  answered until one is.
                </Callout>
              )}
            </>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Restore rehearsal" description="Proof the data is fully reconstructible" />
        <CardBody>
          <p className="text-[13px] leading-5 text-ink-muted">
            Clones every table in this tenant&rsquo;s schema into a throwaway schema, verifies the row counts match,
            then drops the clone. Nothing in the live schema is touched.
          </p>
          <Button variant="secondary" className="mt-3" onClick={handleRehearsal} busy={rehearse.busy} busyLabel="Running">
            Run a rehearsal
          </Button>

          {rehearse.error && <ErrorState title="The rehearsal did not run" message={rehearse.error} className="mt-3" />}

          {rehearsal && (
            <>
              <Callout
                tone={rehearsal.passed ? "positive" : "blocking"}
                title={rehearsal.passed ? "Passed" : "Failed"}
                className="mt-3"
              >
                {rehearsal.tables.length} table{rehearsal.tables.length === 1 ? "" : "s"} checked from{" "}
                {rehearsal.source_schema}.
              </Callout>
              <Disclosure label="Show every table" className="mt-2">
                <TFrame className="rounded-control border border-line">
                  <Table>
                    <THead>
                      <TR>
                        <TH>Table</TH>
                        <TH align="right">Source rows</TH>
                        <TH align="right">Restored rows</TH>
                        <TH align="right">Match</TH>
                      </TR>
                    </THead>
                    <TBody>
                      {rehearsal.tables.map((t) => (
                        <TR key={t.table_name}>
                          <TD className="font-mono text-[11.5px]">{t.table_name}</TD>
                          <TD numeric>{formatCount(t.source_row_count)}</TD>
                          <TD numeric>{formatCount(t.restored_row_count)}</TD>
                          <TD align="right">
                            {t.matches ? <Badge tone="positive">yes</Badge> : <Badge tone="blocking">no</Badge>}
                          </TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </TFrame>
              </Disclosure>
            </>
          )}
        </CardBody>
      </Card>

      {!tenant.is_synthetic && (
        <Card className="border-neg-line lg:col-span-2">
          <CardHeader
            title={<span className="text-neg">Delete this tenant</span>}
            description="Irreversible. Drops the entire schema and purges PII-bearing records."
          />
          <CardBody>
            {deleted ? (
              <Callout tone="positive" title="Deleted">
                {tenant.name} has been deleted.
              </Callout>
            ) : (
              <>
                <p className="max-w-2xl text-[13px] leading-5 text-ink-muted">
                  There is no undo and no retention window. This runs only on an explicit, named request from the
                  client — type the tenant&rsquo;s name to confirm you mean this one.
                </p>
                <div className="mt-3 flex max-w-2xl flex-wrap items-end gap-3">
                  <Input
                    label="Reason"
                    placeholder="Who asked, and when"
                    value={deleteReason}
                    onChange={(e) => setDeleteReason(e.target.value)}
                    fieldClassName="min-w-[240px] flex-1"
                  />
                  <Input
                    label="Type the tenant name"
                    placeholder={tenant.name}
                    value={confirmName}
                    onChange={(e) => setConfirmName(e.target.value)}
                    fieldClassName="min-w-[220px] flex-1"
                  />
                  <Button
                    variant="danger"
                    disabled={!deleteReason.trim() || confirmName !== tenant.name}
                    busy={remove.busy}
                    busyLabel="Deleting"
                    onClick={handleDelete}
                  >
                    Delete {tenant.name}
                  </Button>
                </div>
                {remove.error && (
                  <ErrorState title="The tenant was not deleted" message={remove.error} className="mt-3" />
                )}
              </>
            )}
          </CardBody>
        </Card>
      )}
    </div>
  );
}
