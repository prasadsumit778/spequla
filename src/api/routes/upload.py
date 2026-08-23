"""File upload endpoint.

Implements corpus/12 sprint 1 story: "As the SPEQULA analyst, I can upload a
company's trial balance, chart of accounts and general ledger, and see
canonical GL facts in the system with full lineage back to the file."
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from src.api.deps.auth import Session, require_upload_role
from src.api.deps.tenant import resolve_tenant
from src.ingest.load_pipeline import (
    load_bank_file,
    load_channel_order_file,
    load_coa_file,
    load_gl_file,
    load_production_output_file,
    load_tb_file,
)
from src.ingest.xlsx import XlsxError

router = APIRouter()

# The sprint 1 story's three streams, sprint 6's two profile-specific
# operating streams (corpus/04 sections 3.5, 3.6), and Bank.
# Every template in corpus/01 that has a loader. "Bank" is here because
# corpus/02 section 3 P0 #7 requires books-to-bank to tie, and a bank file
# that cannot be uploaded cannot be reconciled.
TEMPLATE_TYPES = {"COA", "TB", "GL", "Bank", "ConsumerSales", "MFGProduction"}


@router.post("/upload")
async def upload_file(
    template_type: str = Form(...),
    entity_id: int = Form(1),
    file: UploadFile = File(...),
    session: Session = Depends(require_upload_role),
    tenant_ctx=Depends(resolve_tenant),
):
    # No tenant_id in the URL: the tenant is resolved entirely from the
    # verified session's org_id claim (src/api/deps/tenant.py). There is
    # nothing left for a client to assert about which tenant it is.
    conn, tenant_id, schema = tenant_ctx
    if template_type not in TEMPLATE_TYPES:
        raise HTTPException(status_code=400, detail=f"template_type must be one of {sorted(TEMPLATE_TYPES)}")

    raw_bytes = await file.read()
    triggered_by = session.user_id  # real identity now, not a role name -- corpus/02 section 2's logged-access requirement

    # corpus/02 section 3 P0 #1: "Excel and CSV against the templates in file
    # 01 ... The analyst normalises anything that does not match." A workbook
    # that does not match is a readable 422 for the analyst to act on, never a
    # 500 and never a partial load.
    try:
        if template_type == "GL":
            result = load_gl_file(conn, schema, tenant_id, entity_id, file.filename, raw_bytes, triggered_by)
        elif template_type == "COA":
            result = load_coa_file(conn, schema, tenant_id, entity_id, file.filename, raw_bytes, triggered_by)
        elif template_type == "Bank":
            result = load_bank_file(conn, schema, tenant_id, entity_id, file.filename, raw_bytes, triggered_by)
        elif template_type == "ConsumerSales":
            result = load_channel_order_file(conn, schema, tenant_id, entity_id, file.filename, raw_bytes, triggered_by)
        elif template_type == "MFGProduction":
            result = load_production_output_file(conn, schema, tenant_id, entity_id, file.filename, raw_bytes, triggered_by)
        else:
            result, _rows = load_tb_file(conn, tenant_id, entity_id, file.filename, raw_bytes, triggered_by)
    except XlsxError as e:
        conn.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    conn.commit()

    if result.status == "blocked":
        raise HTTPException(status_code=422, detail=result.blocked_reason)

    return {
        "load_run_id": result.load_run_id,
        "status": result.status,
        "quarantined_count": result.quarantined_count,
        "inserted": result.inserted,
        "closed_and_reinserted": result.closed_and_reinserted,
        "unchanged": result.unchanged,
        "periods_touched": result.periods_touched,
        "trial_balance": [
            {"period_key": r.period_key, "balanced": r.balanced, "total": str(r.total)}
            for r in result.tb_results
        ],
    }
