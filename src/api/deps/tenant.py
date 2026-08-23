"""Tenant resolution and RLS-scoped connections.

Implements corpus/04 section 6: "App data is shared tables with row-level
security, forced at the connection role, not in the query text." Every
request sets the app.tenant_id session variable before touching a shared app
table; the RLS policies created in db/migrations/shared/*.sql read it.

The tenant itself is now resolved from the verified WorkOS session's org_id
claim (via app.tenant.workos_organization_id, db/migrations/shared/
0006_tenant_workos_org.sql) -- never from a client-supplied header. A caller
cannot claim to be a different tenant by sending a different header; the
claim comes from a WorkOS-signed token tied to their actual Organization
Membership.
"""
from __future__ import annotations

import os

import psycopg
from fastapi import Depends, HTTPException

from src.api.deps.auth import Session, current_session

DB_URL = os.environ.get("DATABASE_URL", "postgresql://spequla:spequla@localhost:5432/spequla")


def resolve_tenant(session: Session = Depends(current_session)):
    """FastAPI dependency: looks up the tenant linked to the session's WorkOS
    organization, and sets app.tenant_id on a fresh connection for the
    duration of the request, so every subsequent query on a shared app table
    is RLS-scoped to this tenant automatically."""
    if not session.org_id:
        raise HTTPException(
            status_code=403,
            detail="this session has no WorkOS organization context -- the user must belong "
                    "to an Organization Membership linked to a SPEQULA tenant",
        )

    conn = psycopg.connect(DB_URL, connect_timeout=10)
    with conn.cursor() as cur:
        cur.execute("SELECT tenant_id, schema_name FROM app.tenant WHERE workos_organization_id = %s",
                     (session.org_id,))
        row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(
            status_code=404,
            detail=f"no SPEQULA tenant is linked to WorkOS organization {session.org_id}. "
                    f"Run scripts/link_tenant_workos_org.py first.",
        )
    tenant_id, schema_name = str(row[0]), row[1]

    with conn.cursor() as cur:
        # Postgres's SET does not accept a bind parameter for the value ("SET
        # x = $1" is a syntax error) -- set_config() is the parameterized
        # equivalent. is_local=false matches SET's session-wide scope (as
        # opposed to SET LOCAL's transaction-only scope).
        cur.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant_id,))
    try:
        yield conn, tenant_id, schema_name
    finally:
        conn.close()
