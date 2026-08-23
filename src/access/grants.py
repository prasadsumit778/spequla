"""Named, time-bound, logged employee access to client data, corpus/02
section 7: "Employee-level access to client data is time-bound, named and
logged... this is the control clients actually ask about."

Two distinct events, both logged, never conflated: GRANTING access (an
administrative act -- someone with authority decided a named employee may
look at a named tenant's data until a named time) and USING it (an actual
access event). A grant existing is not the same claim as an access having
happened; log_access records the second kind separately so "who looked at
this tenant's data, and when" is answerable without inferring it from grant
metadata.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone


class GrantNotActive(Exception):
    """Raised when an access attempt has no active (unexpired, unrevoked)
    grant to justify it -- refused, never silently allowed through."""


@dataclass
class AccessGrant:
    grant_id: int
    tenant_id: str
    employee_user_id: str
    employee_name: str
    granted_by: str
    reason: str
    granted_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    revoked_by: str | None

    @property
    def is_active(self) -> bool:
        now = datetime.now(timezone.utc)
        return self.revoked_at is None and self.expires_at > now


_COLUMNS = ["grant_id", "tenant_id", "employee_user_id", "employee_name", "granted_by", "reason",
             "granted_at", "expires_at", "revoked_at", "revoked_by"]


def grant_access(conn, tenant_id: str, employee_user_id: str, employee_name: str, granted_by: str,
                    reason: str, expires_at: datetime) -> AccessGrant:
    if not employee_name:
        raise ValueError("grant_access requires a named employee, per corpus/02 section 7")
    if not granted_by:
        raise ValueError("grant_access requires a named granter")
    if not reason:
        raise ValueError("grant_access requires a reason")
    if expires_at <= datetime.now(timezone.utc):
        raise ValueError("expires_at must be in the future -- a grant that is already expired is not a grant")

    with conn.cursor() as cur:
        cur.execute(
            f'INSERT INTO app.employee_access_grant '
            f'(tenant_id, employee_user_id, employee_name, granted_by, reason, expires_at) '
            f'VALUES (%s,%s,%s,%s,%s,%s) RETURNING {", ".join(_COLUMNS)}',
            (tenant_id, employee_user_id, employee_name, granted_by, reason, expires_at),
        )
        row = cur.fetchone()
        cur.execute(
            "INSERT INTO app.audit_log (tenant_id, actor, action, object_type, object_ref, detail) "
            "VALUES (%s, %s, 'access_grant', 'employee_access_grant', %s, %s)",
            (tenant_id, granted_by, str(row[0]),
             json.dumps({"employee_user_id": employee_user_id, "employee_name": employee_name,
                            "reason": reason, "expires_at": expires_at.isoformat()})),
        )
    conn.commit()
    return AccessGrant(**dict(zip(_COLUMNS, row)))


def revoke_access(conn, grant_id: int, revoked_by: str) -> AccessGrant:
    if not revoked_by:
        raise ValueError("revoke_access requires a named revoker")
    with conn.cursor() as cur:
        cur.execute(
            f'UPDATE app.employee_access_grant SET revoked_at = now(), revoked_by = %s '
            f'WHERE grant_id = %s AND revoked_at IS NULL RETURNING {", ".join(_COLUMNS)}',
            (revoked_by, grant_id),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"no active grant {grant_id} to revoke")
        cur.execute(
            "INSERT INTO app.audit_log (tenant_id, actor, action, object_type, object_ref, detail) "
            "VALUES (%s, %s, 'access_revoke', 'employee_access_grant', %s, %s)",
            (row[1], revoked_by, str(grant_id), json.dumps({})),
        )
    conn.commit()
    return AccessGrant(**dict(zip(_COLUMNS, row)))


def active_grant(conn, tenant_id: str, employee_user_id: str) -> AccessGrant | None:
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT {", ".join(_COLUMNS)} FROM app.employee_access_grant '
            f'WHERE tenant_id = %s AND employee_user_id = %s '
            f'  AND revoked_at IS NULL AND expires_at > now() '
            f'ORDER BY granted_at DESC LIMIT 1',
            (tenant_id, employee_user_id),
        )
        row = cur.fetchone()
    return AccessGrant(**dict(zip(_COLUMNS, row))) if row else None


def require_active_grant(conn, tenant_id: str, employee_user_id: str) -> AccessGrant:
    """Refuses (GrantNotActive) rather than allowing access through when no
    active grant exists -- the enforcement point every cross-tenant access
    path must call before touching client data."""
    grant = active_grant(conn, tenant_id, employee_user_id)
    if grant is None:
        raise GrantNotActive(
            f"no active access grant for employee {employee_user_id!r} on tenant {tenant_id} -- "
            f"a named, time-bound grant must exist before this data can be accessed"
        )
    return grant


def log_access(conn, tenant_id: str, employee_user_id: str, action: str, detail: dict | None = None) -> None:
    """Records an actual access event, separate from the grant that
    authorised it. Called at the point of use, not at grant time."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO app.audit_log (tenant_id, actor, action, object_type, object_ref, detail) "
            "VALUES (%s, %s, %s, 'tenant', %s, %s)",
            (tenant_id, employee_user_id, action, tenant_id, json.dumps(detail or {})),
        )
    conn.commit()


def list_grants(conn, tenant_id: str) -> list[AccessGrant]:
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT {", ".join(_COLUMNS)} FROM app.employee_access_grant '
            f'WHERE tenant_id = %s ORDER BY granted_at DESC',
            (tenant_id,),
        )
        return [AccessGrant(**dict(zip(_COLUMNS, row))) for row in cur.fetchall()]
