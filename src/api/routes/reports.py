"""Reports screen, corpus/08 section 2: "Generate, review, sign, export."

Generation and commentary edits are gated the same way mapping.py's freeze
endpoint is (require_upload_role: spequla_analyst or client_finance_lead),
and the actor is always session.user_id -- never a client-supplied name --
same posture as freeze_mapping_version's named approver. Signing follows
corpus/08 section 10: "the reviewer can override" ties override authority to
the person signing, so override_by is always the same session identity as
reviewer, never a separate field the client could set independently.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.deps.auth import Session, require_upload_role
from src.api.deps.tenant import resolve_tenant
from src.config.loader import load_registry
from src.reports.pack import generate_pack
from src.reports.query import NoApprovedMappingError
from src.reports.signoff import (
    SignOffBlocked,
    edit_commentary,
    get_report_artefact,
    open_blocking_exceptions,
    render_pack,
    sign_pack,
    write_report_artefact,
)

router = APIRouter()


def _jsonable_render(rendered: dict) -> dict:
    """render_pack's unmapped_value_inr is a Decimal (numeric(18,2) column,
    not inside the already-stringified sections jsonb) -- stringified here
    for the same reason every other route in this codebase does it
    (src/api/routes/ask.py, statements.py, ...): 'Decimal for money, never
    float' (CLAUDE.md section 8) extends to never letting FastAPI's default
    encoder silently round-trip it through float on the way out."""
    out = dict(rendered)
    if out.get("unmapped_value_inr") is not None:
        out["unmapped_value_inr"] = str(out["unmapped_value_inr"])
    return out


def _summary(artefact) -> dict:
    return {
        "report_artefact_id": artefact.report_artefact_id, "period_key": artefact.period_key,
        "entity_id": artefact.entity_id, "profile": artefact.profile,
        "generated_at": artefact.generated_at.isoformat() if artefact.generated_at else None,
        "generated_by": artefact.generated_by, "status": artefact.status,
        "reviewer": artefact.reviewer, "signed_at": artefact.signed_at.isoformat() if artefact.signed_at else None,
        "content_hash": artefact.content_hash,
    }


class GenerateRequest(BaseModel):
    period: str  # YYYY-MM
    entity_id: int = 1
    profile: str  # 'manufacturing' | 'consumer' -- always caller-supplied, never defaulted (corpus/12 sprint 7)


@router.post("/reports/generate")
def generate_report(body: GenerateRequest, session: Session = Depends(require_upload_role),
                        tenant_ctx=Depends(resolve_tenant)):
    conn, tenant_id, schema = tenant_ctx
    date.fromisoformat(f"{body.period}-01")  # validate YYYY-MM
    config = load_registry()
    try:
        pack = generate_pack(conn, schema, tenant_id, body.entity_id, body.profile, body.period, config,
                                 generated_by=session.user_id)
    except NoApprovedMappingError as e:
        raise HTTPException(status_code=422, detail=str(e))
    artefact = write_report_artefact(conn, schema, pack)
    return _summary(artefact)


@router.get("/reports/{report_artefact_id}")
def get_report(report_artefact_id: int, session: Session = Depends(require_upload_role),
                  tenant_ctx=Depends(resolve_tenant)):
    conn, _tenant_id, schema = tenant_ctx
    try:
        rendered = render_pack(conn, schema, report_artefact_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _jsonable_render(rendered)


@router.get("/reports/{report_artefact_id}/export")
def export_report(report_artefact_id: int, session: Session = Depends(require_upload_role),
                      tenant_ctx=Depends(resolve_tenant)):
    """corpus/08 section 2: 'export.' P0's export renderer is the pack's
    full stored JSON -- chart specs included as specs, per corpus/08 section
    8, never rasterised -- suitable for the frontend to render as a
    printable page or attach as-is; no separate document format is declared
    anywhere in the corpus."""
    conn, _tenant_id, schema = tenant_ctx
    try:
        rendered = render_pack(conn, schema, report_artefact_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if rendered["status"] != "signed":
        raise HTTPException(status_code=422, detail="only a signed pack can be exported")
    return _jsonable_render(rendered)


class CommentaryRequest(BaseModel):
    commentary: str


@router.patch("/reports/{report_artefact_id}/commentary")
def update_commentary(report_artefact_id: int, body: CommentaryRequest,
                          session: Session = Depends(require_upload_role), tenant_ctx=Depends(resolve_tenant)):
    conn, _tenant_id, schema = tenant_ctx
    try:
        artefact = edit_commentary(conn, schema, report_artefact_id, body.commentary)
    except (ValueError, SignOffBlocked) as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _summary(artefact)


class SignRequest(BaseModel):
    override_reason: str | None = None


@router.get("/reports/{report_artefact_id}/blocking-exceptions")
def get_blocking_exceptions(report_artefact_id: int, session: Session = Depends(require_upload_role),
                                tenant_ctx=Depends(resolve_tenant)):
    """Lets the Reports screen show the sign-off gate's state before the
    reviewer attempts to sign, per corpus/08's own 'state is always visible'
    principle (section 1)."""
    conn, tenant_id, schema = tenant_ctx
    artefact = get_report_artefact(conn, schema, report_artefact_id)
    if artefact is None:
        raise HTTPException(status_code=404, detail=f"no report_artefact {report_artefact_id}")
    exceptions = open_blocking_exceptions(conn, schema, tenant_id, artefact.entity_id, artefact.period_key)
    for e in exceptions:
        if e["value_inr"] is not None:
            e["value_inr"] = str(e["value_inr"])
    return {"blocking_exceptions": exceptions}


@router.post("/reports/{report_artefact_id}/sign")
def sign_report(report_artefact_id: int, body: SignRequest, session: Session = Depends(require_upload_role),
                    tenant_ctx=Depends(resolve_tenant)):
    conn, _tenant_id, schema = tenant_ctx
    try:
        artefact = sign_pack(conn, schema, report_artefact_id, reviewer=session.user_id,
                                 override_reason=body.override_reason,
                                 override_by=session.user_id if body.override_reason else None)
    except SignOffBlocked as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _summary(artefact)


@router.get("/reports")
def list_reports(period: str = Query(..., pattern=r"^\d{4}-\d{2}$"), entity_id: int = 1,
                     session: Session = Depends(require_upload_role), tenant_ctx=Depends(resolve_tenant)):
    conn, tenant_id, schema = tenant_ctx
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT report_artefact_id, period_key, entity_id, profile, generated_at, generated_by, status, '
            f'   reviewer, signed_at, content_hash '
            f'FROM "{schema}".report_artefact WHERE tenant_id = %s AND entity_id = %s AND period_key = %s '
            f'ORDER BY generated_at DESC',
            (tenant_id, entity_id, period),
        )
        rows = cur.fetchall()
    return [
        {"report_artefact_id": r[0], "period_key": r[1], "entity_id": r[2], "profile": r[3],
          "generated_at": r[4].isoformat() if r[4] else None, "generated_by": r[5], "status": r[6],
          "reviewer": r[7], "signed_at": r[8].isoformat() if r[8] else None, "content_hash": r[9]}
        for r in rows
    ]
