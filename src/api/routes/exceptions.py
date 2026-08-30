"""The exception queue, corpus/09 section 4: a product surface, sorted by
severity then rupee value descending -- "always by money, never by count."

Resolution paths per that section: fix at source and reload (not modelled
here -- that's a re-upload), map or reclassify (the mapping review queue),
accept with a written reason (this endpoint's POST), defer with an owner and
a date (also this endpoint's POST, status='deferred'). "Nothing is
dismissed without a reason" -- resolution_note is required on every
resolve, not optional.

Resolving appends a new version of the exception; it never updates the
raised row. The queue reads exception_current, the view that derives the
latest version. See src/quality/exception_queue.py and CLAUDE.md
invariant #4.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.deps.auth import Session, require_role
from src.api.deps.tenant import resolve_tenant
from src.quality.exception_queue import (
    ExceptionNotFound,
    ExceptionRow,
    ResolutionRefused,
    list_exceptions as list_current_exceptions,
    resolve_exception as append_resolution,
)

router = APIRouter()


def _serialise(r: ExceptionRow) -> dict:
    """exception_id is the exception's stable identity (its first version's
    row id), not whichever physical row the current status came from -- so a
    client that listed the queue before a resolution and one that listed it
    after are talking about the same exception_id."""
    return {
        "exception_id": r.exception_key, "exception_class": r.exception_class, "severity": r.severity,
        "period_key": r.period_key, "object_type": r.object_type, "object_ref": r.object_ref,
        "value_inr": str(r.value_inr) if r.value_inr is not None else None,
        "description": r.description, "suggested_action": r.suggested_action, "status": r.status,
        "raised_at": r.raised_at.isoformat(),  # NOT NULL in the DDL, carried verbatim onto every version
    }


@router.get("/exceptions")
def list_exceptions(
    status: str = Query("open", pattern="^(open|resolved|deferred|accepted)$"),
    session: Session = Depends(require_role), tenant_ctx=Depends(resolve_tenant),
):
    conn, tenant_id, schema = tenant_ctx
    return {"exceptions": [_serialise(r) for r in list_current_exceptions(conn, schema, tenant_id, status)]}


class ResolveExceptionRequest(BaseModel):
    resolution: str  # 'accepted' | 'deferred' | 'resolved'
    resolution_note: str  # mandatory -- "nothing is dismissed without a reason"


@router.post("/exceptions/{exception_id}/resolve")
def resolve_exception(
    exception_id: int, body: ResolveExceptionRequest,
    session: Session = Depends(require_role), tenant_ctx=Depends(resolve_tenant),
):
    conn, tenant_id, schema = tenant_ctx
    try:
        current = append_resolution(conn, schema, tenant_id, exception_id, body.resolution,
                                    body.resolution_note, session.user_id)
    except ResolutionRefused as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ExceptionNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    conn.commit()
    return {"exception_id": current.exception_key, "status": current.status}
