"""The Ask endpoint, corpus/07 + corpus/08 section 2's Ask screen entry:
"Question, answer, chart, citation, view SQL." One POST, taking a natural-
language question and returning the full corpus/07 section 2 pipeline's
outcome -- ok with a cited answer, blocked on an open decision, unavailable
pending missing data, or refused.

model_client defaults to StubModelClient with no fixtures, which means
every question is refused as unsupported until a real ModelClient is
configured (src/semantic/model_client.py's AnthropicModelClient, currently
unconfigured by explicit instruction). This endpoint is real and working
end to end; the only missing piece is the model call itself, exactly the
"connection point" that module documents.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.deps.auth import Session, require_role
from src.api.deps.tenant import resolve_tenant
from src.config.loader import load_registry
from src.semantic.ask import ask as run_ask
from src.semantic.model_client import ModelClient, StubModelClient

router = APIRouter()

_NO_MODEL_CONFIGURED = StubModelClient({})


def get_model_client() -> ModelClient:
    """Swap this for a real client once one is configured -- see
    src/semantic/model_client.py's AnthropicModelClient."""
    return _NO_MODEL_CONFIGURED


class AskRequest(BaseModel):
    question: str
    entity_id: int = 1
    tenant_profile: str  # 'manufacturing' | 'consumer' -- always caller-supplied, never defaulted (corpus/12 sprint 7)


@router.post("/ask")
def ask_endpoint(
    body: AskRequest,
    session: Session = Depends(require_role), tenant_ctx=Depends(resolve_tenant),
    model_client: ModelClient = Depends(get_model_client),
):
    conn, tenant_id, schema = tenant_ctx
    config = load_registry()

    response = run_ask(conn, schema, tenant_id, body.entity_id, body.question, model_client, config,
                          user_id=session.user_id, role=session.role, tenant_profile=body.tenant_profile)

    def _jsonable_result(result):
        if result is None:
            return None
        return {
            "status": result.status, "intent": result.intent,
            "sql_text": result.sql_text,
            "value": str(result.value) if hasattr(result.value, "__class__") and
                       result.value.__class__.__name__ == "Decimal" else result.value,
            "series": result.series, "reason": result.reason,
            "blocking_decisions": result.blocking_decisions, "row_count": result.row_count,
            "bridge": None if result.bridge is None else {
                "total_delta": str(result.bridge.total_delta),
                "components_sum_to_total": result.bridge.components_sum_to_total,
                "configured": result.bridge.configured,
                "reason": result.bridge.reason,
                "components": [{"label": c.label, "value": str(c.value), "is_residual": c.is_residual}
                                 for c in result.bridge.ranked()],
            },
        }

    def _jsonable_refusal(refusal):
        if refusal is None:
            return None
        return {"refusal_class": refusal.refusal_class, "reason": refusal.reason,
                  "nearest_supported_question": refusal.nearest_supported_question,
                  "clarifying_options": refusal.clarifying_options}

    return {
        "status": response.status,
        "question": response.question,
        "intent": response.intent,
        "ir": response.ir,
        "result": _jsonable_result(response.result),
        "citation": response.citation,
        "refusal": _jsonable_refusal(response.refusal),
    }
