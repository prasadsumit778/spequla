"""Mapping run, review queue, and freeze endpoints.

Implements corpus/12 sprint 2 frontend requirement: "Mapping review queue
sorted by period_value_inr descending, with running coverage and unmapped
rupee value always on screen."
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.deps.auth import Session, require_upload_role
from src.api.deps.tenant import resolve_tenant
from src.mapping.review import create_draft_version, freeze_mapping_version, review_queue, run_mapping_pass
from src.config.loader import load_taxonomy
from src.quality.period_state import map_periods_for_mapping_version

router = APIRouter()


def _taxonomy_lookup() -> dict:
    return {
        t.class_: {"statement_section": t.statement_section, "statement_line": t.statement_line or t.class_}
        for t in load_taxonomy()
    }


class CreateRunRequest(BaseModel):
    entity_id: int = 1
    version_no: int = 1
    effective_from: date
    change_reason: str | None = None


@router.post("/mapping/runs")
def create_mapping_run(body: CreateRunRequest, session: Session = Depends(require_upload_role),
                         tenant_ctx=Depends(resolve_tenant)):
    conn, tenant_id, schema = tenant_ctx
    mapping_version_id = create_draft_version(
        conn, schema, tenant_id, body.entity_id, body.version_no, body.effective_from,
        session.user_id, body.change_reason,
    )
    summary = run_mapping_pass(conn, schema, tenant_id, body.entity_id, mapping_version_id,
                                  _taxonomy_lookup(), session.user_id)
    conn.commit()
    return {
        "mapping_version_id": mapping_version_id,
        "auto_accepted": summary.auto_accepted,
        "human_approved": summary.human_approved,
        "deferred_to_suspense": summary.deferred_to_suspense,
        "total_value_inr": str(summary.total_value_inr),
        "mapped_value_inr": str(summary.mapped_value_inr),
    }


@router.get("/mapping/runs/{mapping_version_id}/queue")
def get_review_queue(mapping_version_id: int, session: Session = Depends(require_upload_role),
                       tenant_ctx=Depends(resolve_tenant)):
    conn, _tenant_id, schema = tenant_ctx
    return review_queue(conn, schema, _tenant_id, mapping_version_id)


@router.post("/mapping/runs/{mapping_version_id}/freeze")
def freeze_run(mapping_version_id: int, entity_id: int = 1, session: Session = Depends(require_upload_role),
                 tenant_ctx=Depends(resolve_tenant)):
    conn, tenant_id, schema = tenant_ctx
    result = freeze_mapping_version(conn, schema, tenant_id, entity_id, mapping_version_id, session.user_id)
    if not result.passed:
        # Commit first: freeze_mapping_version returns a BLOCKED gate without
        # writing anything on the failing paths, but a refused freeze must not
        # roll back the mapping pass that ran before it either.
        conn.commit()
        raise HTTPException(status_code=422, detail=result.reason)

    # corpus/09 section 5, VALIDATED -> MAPPED: "mapping version approved,
    # coverage above threshold." That is exactly the event that just passed,
    # so the periods this version governs advance in the same transaction as
    # the freeze -- a version that is approved while its periods sit at
    # VALIDATED would be two facts that have to be reconciled by hand later.
    # Which periods those are is read from the version's own effective dates
    # and the facts inside them; a period held at OPEN is skipped, never
    # dragged forward. See map_periods_for_mapping_version.
    transitions = map_periods_for_mapping_version(
        conn, schema, tenant_id, entity_id, mapping_version_id,
        freeze_passed=result.passed, coverage_pct=result.coverage_pct,
    )
    conn.commit()
    return {
        "passed": result.passed, "reason": result.reason,
        "coverage_pct": float(result.coverage_pct) if result.coverage_pct is not None else None,
        "unmapped_value_inr": str(result.unmapped_value_inr) if result.unmapped_value_inr is not None else None,
        "period_transitions": [
            {"period_key": t.period_key, "transitioned": t.transitioned, "status": t.status,
              "detail": t.detail}
            for t in transitions
        ],
    }
