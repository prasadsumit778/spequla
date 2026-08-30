"""Admin: tenancy operations, corpus/12 sprint 7. "As the founder, I can run
three pilots concurrently without any client-specific code."

Every route here is require_admin_role -- these are cross-tenant by nature
(the tenant is a path parameter, not derived from the caller's own WorkOS
org via resolve_tenant), so they sit outside the per-tenant RLS-scoped
connection every other route uses. Access to actual client data through
this surface is gated on an active employee_access_grant and logged
separately from the grant itself (src/access/grants.py); listing tenants
or managing grants is not "client data" and needs no grant, only the admin
role.
"""
from __future__ import annotations

import os
from datetime import datetime

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.access.grants import GrantNotActive, grant_access, list_grants, log_access, require_active_grant, revoke_access
from src.admin.backup_rehearsal import rehearse_restore
from src.admin.tenant_lifecycle import TenantAlreadyDeleted, TenantNotFound, delete_tenant
from src.api.deps.auth import Session, require_admin_role

router = APIRouter()
DB_URL = os.environ.get("DATABASE_URL", "postgresql://spequla:spequla@localhost:5432/spequla")


def _conn():
    return psycopg.connect(DB_URL, connect_timeout=10)


def _tenant_schema(conn, tenant_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT schema_name FROM app.tenant WHERE tenant_id = %s AND deleted_at IS NULL", (tenant_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no tenant {tenant_id} (or it has been deleted)")
    return row[0]


@router.get("/admin/tenants")
def list_tenants(session: Session = Depends(require_admin_role)):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id, name, schema_name, is_synthetic, created_at, deleted_at FROM app.tenant "
                "ORDER BY created_at DESC"
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [
        {"tenant_id": str(r[0]), "name": r[1], "schema_name": r[2], "is_synthetic": r[3],
          "created_at": r[4].isoformat(), "deleted_at": r[5].isoformat() if r[5] else None}
        for r in rows
    ]


class GrantRequest(BaseModel):
    employee_user_id: str
    employee_name: str
    reason: str
    expires_at: datetime


@router.post("/admin/tenants/{tenant_id}/access-grants")
def create_access_grant(tenant_id: str, body: GrantRequest, session: Session = Depends(require_admin_role)):
    conn = _conn()
    try:
        g = grant_access(conn, tenant_id, body.employee_user_id, body.employee_name,
                             granted_by=session.user_id, reason=body.reason, expires_at=body.expires_at)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        conn.close()
    return {"grant_id": g.grant_id, "employee_name": g.employee_name, "expires_at": g.expires_at.isoformat(),
              "is_active": g.is_active}


@router.get("/admin/tenants/{tenant_id}/access-grants")
def get_access_grants(tenant_id: str, session: Session = Depends(require_admin_role)):
    conn = _conn()
    try:
        grants = list_grants(conn, tenant_id)
    finally:
        conn.close()
    return [
        {"grant_id": g.grant_id, "employee_user_id": g.employee_user_id, "employee_name": g.employee_name,
          "granted_by": g.granted_by, "reason": g.reason, "granted_at": g.granted_at.isoformat(),
          "expires_at": g.expires_at.isoformat(), "revoked_at": g.revoked_at.isoformat() if g.revoked_at else None,
          "revoked_by": g.revoked_by, "is_active": g.is_active}
        for g in grants
    ]


@router.post("/admin/access-grants/{grant_id}/revoke")
def revoke_access_grant(grant_id: int, session: Session = Depends(require_admin_role)):
    conn = _conn()
    try:
        try:
            g = revoke_access(conn, grant_id, revoked_by=session.user_id)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    finally:
        conn.close()
    return {"grant_id": g.grant_id, "revoked_at": g.revoked_at.isoformat()}


@router.get("/admin/tenants/{tenant_id}/audit-log")
def get_audit_log(tenant_id: str, limit: int = 200, session: Session = Depends(require_admin_role)):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT audit_id, actor, role_key, action, object_type, object_ref, detail, occurred_at "
                "FROM app.audit_log WHERE tenant_id = %s ORDER BY occurred_at DESC LIMIT %s",
                (tenant_id, min(limit, 1000)),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [
        {"audit_id": r[0], "actor": r[1], "role_key": r[2], "action": r[3], "object_type": r[4],
          "object_ref": r[5], "detail": r[6], "occurred_at": r[7].isoformat()}
        for r in rows
    ]


@router.get("/admin/tenants/{tenant_id}/support-data-health")
def get_support_data_health(tenant_id: str, session: Session = Depends(require_admin_role)):
    """The one concrete demonstration of a grant-gated cross-tenant client-
    data read: reuses data_health.py's panels (freshness, completeness,
    reconciliation, exceptions -- informative, not raw ledger detail) for a
    named admin supporting a named tenant. Refuses without an active grant;
    every successful read is logged as its own access event, separate from
    the grant itself."""
    conn = _conn()
    try:
        try:
            require_active_grant(conn, tenant_id, session.user_id)
        except GrantNotActive as e:
            raise HTTPException(status_code=403, detail=str(e))

        schema = _tenant_schema(conn, tenant_id)
        from src.quality.checks import fetch_freshness
        freshness = fetch_freshness(conn, tenant_id, entity_id=1)
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT severity, count(*), COALESCE(SUM(value_inr), 0) FROM "{schema}".exception_current '
                f"WHERE tenant_id = %s AND status = 'open' GROUP BY severity",
                (tenant_id,),
            )
            exceptions_by_severity = {sev: {"count": n, "value_inr": str(v)} for sev, n, v in cur.fetchall()}

        log_access(conn, tenant_id, session.user_id, "client_data_access",
                      {"endpoint": "support-data-health"})
    finally:
        conn.close()

    return {
        "tenant_id": tenant_id,
        "freshness": [{"source_system": f.source_system,
                          "last_successful_load_at": f.last_successful_load_at.isoformat() if f.last_successful_load_at else None,
                          "hours_since": f.hours_since} for f in freshness],
        "open_exceptions_by_severity": exceptions_by_severity,
    }


class DeleteTenantRequest(BaseModel):
    reason: str


@router.post("/admin/tenants/{tenant_id}/delete")
def delete_tenant_route(tenant_id: str, body: DeleteTenantRequest, session: Session = Depends(require_admin_role)):
    """Irreversible. See src/admin/tenant_lifecycle.py -- never time-triggered,
    always an explicit named request (OPEN_QUESTIONS.md OQ-005: no retention
    period is declared anywhere in the corpus, so nothing here fires on a
    timer)."""
    conn = _conn()
    try:
        try:
            result = delete_tenant(conn, tenant_id, requested_by=session.user_id, reason=body.reason)
        except (TenantNotFound, TenantAlreadyDeleted) as e:
            raise HTTPException(status_code=404 if isinstance(e, TenantNotFound) else 409, detail=str(e))
    finally:
        conn.close()
    return {"tenant_id": result.tenant_id, "deleted_at": result.deleted_at.isoformat()}


@router.get("/admin/tenants/{tenant_id}/model-cost")
def get_model_cost(tenant_id: str, session: Session = Depends(require_admin_role)):
    """corpus/12 sprint 7: 'Model cost tracking per tenant.' Rolls up
    app.query_log's cost columns (db/migrations/shared/0010) -- all null
    today, since no ModelClient anywhere in this codebase calls a real
    model yet (src/semantic/model_client.py's AnthropicModelClient is
    deliberately unconfigured). total_cost_inr is 0 until that changes;
    this endpoint is the connection point for the rollup, not a claim that
    real spend is happening."""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*), COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0), "
                "       COALESCE(SUM(cost_inr), 0), count(*) FILTER (WHERE cost_inr IS NOT NULL) "
                "FROM app.query_log WHERE tenant_id = %s",
                (tenant_id,),
            )
            total_queries, input_tokens, output_tokens, cost_inr, priced_queries = cur.fetchone()
    finally:
        conn.close()
    return {
        "tenant_id": tenant_id, "total_queries": total_queries, "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens, "total_cost_inr": str(cost_inr), "priced_queries": priced_queries,
    }


@router.post("/admin/tenants/{tenant_id}/restore-rehearsal")
def restore_rehearsal_route(tenant_id: str, session: Session = Depends(require_admin_role)):
    """corpus/02 section 7: 'restore tested.' Runs the logical clone-and-
    verify rehearsal (src/admin/backup_rehearsal.py) against this tenant's
    live schema and reports per-table results. Read-only from the tenant's
    point of view -- the rehearsal schema it creates is always dropped
    before this returns."""
    conn = _conn()
    try:
        schema = _tenant_schema(conn, tenant_id)
        result = rehearse_restore(conn, schema)
    finally:
        conn.close()
    return {
        "source_schema": result.source_schema, "passed": result.passed,
        "tables": [{"table_name": t.table_name, "source_row_count": t.source_row_count,
                      "restored_row_count": t.restored_row_count, "matches": t.matches}
                     for t in result.tables],
    }
