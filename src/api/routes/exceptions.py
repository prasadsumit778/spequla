"""The exception queue, corpus/09 section 4: a product surface, sorted by
severity then rupee value descending -- "always by money, never by count."

Resolution paths per that section: fix at source and reload (not modelled
here -- that's a re-upload), map or reclassify (the mapping review queue),
accept with a written reason (this endpoint's POST), defer with an owner and
a date (also this endpoint's POST, status='deferred'). "Nothing is
dismissed without a reason" -- resolution_note is required on every
resolve, not optional.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.deps.auth import Session, require_role
from src.api.deps.tenant import resolve_tenant

router = APIRouter()


@router.get("/exceptions")
def list_exceptions(
    status: str = Query("open", pattern="^(open|resolved|deferred|accepted)$"),
    session: Session = Depends(require_role), tenant_ctx=Depends(resolve_tenant),
):
    conn, tenant_id, schema = tenant_ctx
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT exception_id, exception_class, severity, period_key, object_type, object_ref, '
            f'       value_inr, description, suggested_action, status, raised_at '
            f'FROM "{schema}".exception '
            f'WHERE tenant_id = %s AND status = %s '
            f"ORDER BY CASE severity WHEN 'blocking' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, "
            f'value_inr DESC NULLS LAST',
            (tenant_id, status),
        )
        rows = cur.fetchall()
    return {
        "exceptions": [
            {
                "exception_id": r[0], "exception_class": r[1], "severity": r[2], "period_key": r[3],
                "object_type": r[4], "object_ref": r[5], "value_inr": str(r[6]) if r[6] is not None else None,
                "description": r[7], "suggested_action": r[8], "status": r[9], "raised_at": r[10].isoformat(),
            }
            for r in rows
        ],
    }


class ResolveExceptionRequest(BaseModel):
    resolution: str  # 'accepted' | 'deferred' | 'resolved'
    resolution_note: str  # mandatory -- "nothing is dismissed without a reason"


@router.post("/exceptions/{exception_id}/resolve")
def resolve_exception(
    exception_id: int, body: ResolveExceptionRequest,
    session: Session = Depends(require_role), tenant_ctx=Depends(resolve_tenant),
):
    conn, tenant_id, schema = tenant_ctx
    if body.resolution not in ("accepted", "deferred", "resolved"):
        raise HTTPException(status_code=422, detail="resolution must be accepted, deferred or resolved")
    if not body.resolution_note.strip():
        raise HTTPException(status_code=422, detail="resolution_note is required -- nothing is dismissed "
                                                        "without a reason, per corpus/09 section 4")
    with conn.cursor() as cur:
        cur.execute(
            f'UPDATE "{schema}".exception SET status = %s, resolved_by = %s, resolved_at = now(), '
            f'resolution_note = %s WHERE exception_id = %s AND tenant_id = %s RETURNING exception_id',
            (body.resolution, session.user_id, body.resolution_note, exception_id, tenant_id),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="exception not found")
    return {"exception_id": exception_id, "status": body.resolution}
