"""Load run status and file list.

Implements corpus/12 sprint 1 frontend requirement: "Upload screen, load run
status, basic file list." This module is the read side those two screens
call.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.deps.tenant import resolve_tenant

router = APIRouter()


@router.get("/load-runs")
def list_load_runs(tenant_ctx=Depends(resolve_tenant)):
    conn, tenant_id, _schema = tenant_ctx
    with conn.cursor() as cur:
        cur.execute(
            "SELECT load_run_id, entity_id, source_system, status, triggered_by, started_at, completed_at "
            "FROM app.load_run WHERE tenant_id = %s ORDER BY started_at DESC",
            (tenant_id,),
        )
        rows = cur.fetchall()
    return [
        {"load_run_id": r[0], "entity_id": r[1], "source_system": r[2], "status": r[3],
          "triggered_by": r[4], "started_at": r[5].isoformat() if r[5] else None,
          "completed_at": r[6].isoformat() if r[6] else None}
        for r in rows
    ]


@router.get("/files")
def list_files(tenant_ctx=Depends(resolve_tenant)):
    conn, tenant_id, _schema = tenant_ctx
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_file_id, load_run_id, file_name, template_type, row_count, received_at "
            "FROM app.source_file WHERE tenant_id = %s ORDER BY received_at DESC",
            (tenant_id,),
        )
        rows = cur.fetchall()
    return [
        {"source_file_id": r[0], "load_run_id": r[1], "file_name": r[2], "template_type": r[3],
          "row_count": r[4], "received_at": r[5].isoformat() if r[5] else None}
        for r in rows
    ]
