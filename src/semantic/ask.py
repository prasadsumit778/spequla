"""The Ask orchestrator: corpus/07 section 2's eleven stages, end to end.

    1. Intent classification          AI (ModelClient.classify_intent)
    2. Metric resolution              DET (inside validate_ir)
    3. Time resolution                DET (IR's own period fields, resolved by the caller/model before this)
    4. Semantic IR generation         AI (ModelClient.generate_ir)
    5. IR validation                  DET (src/semantic/ir.py)
    6. SQL compilation                DET (src/semantic/ask_compiler.py)
    7. Admission control              DET (src/semantic/admission.py)
    8. Execution                      DET, under the model_reachable role
    9. Result sanity                  DET (this module's _sanity_check)
   10. Decomposition bridges          DET (src/semantic/bridges.py, inside ask_compiler for variance_explain)
   11. Narration and citation         AI for wording / DET for citation (src/semantic/citation.py)

"Nothing that touches a number is a model call" (section 2) -- stages 6-10
never import a ModelClient.

Gates 2 (read-only) and 5 (PII exclusion) are enforced by admission.py's
string-pattern checks on the compiled SQL text, not yet by Postgres's own
model_reachable grants (corpus/07 section 7: "The model-reachable role is a
database object, not a code path") -- see _execute_as_model_reachable's
docstring for why that's a disclosed gap rather than done: model_reachable
is explicitly revoked from map_account, mapping_version, period_lock and
reconciliation_run, which compile_metric and data_health need for
essentially every call, so running execution under that role today would
break Ask rather than secure it. Gate 4 (tenant predicate) is enforced
directly -- every compiled query includes a bound tenant_id filter,
independent of which role executes it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from src.config.loader import ConfigRegistry
from src.semantic.admission import run_admission_gates
from src.semantic.ask_compiler import AskResult, compile_and_execute
from src.semantic.citation import Citation, NotCitable, build_citation
from src.semantic.compiler import CompiledMetric
from src.semantic.ir import IRRequest, IRValidationError, validate_ir
from src.semantic.model_client import IntentClassification, ModelClient
from src.semantic.refusal import Refusal, build_refusal, refusal_for_blocked_decision
from src.semantic.compiler import compile_metric  # noqa: F401  -- re-exported for callers that need it directly
from src.reports.query import resolve_mapping_version_for_period


@dataclass
class AskResponse:
    status: str  # 'ok' | 'refused' | 'rejected' | 'blocked' | 'unavailable' | 'error'
    question: str
    intent: str | None = None
    ir: dict | None = None
    result: AskResult | None = None
    citation: dict | None = None
    refusal: Refusal | None = None
    admission: dict | None = None
    query_log_id: int | None = None


def _sanity_check(result: AskResult) -> str | None:
    """corpus/07 section 2 stage 9. Deterministic, cheap checks on an
    otherwise-ok result -- not a repeat of the compiler's own gates, a
    second look at the shape of what came back."""
    if result.status != "ok":
        return None
    if isinstance(result.value, Decimal) and result.value.is_nan():
        return "value is NaN -- suspicious, not displayed as a number"
    if result.bridge is not None and not result.bridge.components_sum_to_total and result.bridge.configured:
        return "decomposition components do not sum to the total movement -- reported as incomplete, per corpus/07 section 5 step 4"
    return None


def _write_query_log(conn, tenant_id: str, entity_id: int | None, user_id: str, role: str,
                        question: str | None, intent: str, ir_dict: dict, sql_text: str | None,
                        admitted: bool, rejection_gate: str | None, rejection_reason: str | None,
                        row_count: int | None, duration_ms: int, model_version: str | None,
                        query_hash: str | None, input_tokens: int | None = None,
                        output_tokens: int | None = None, cost_inr=None) -> int:
    """input_tokens/output_tokens/cost_inr (corpus/12 sprint 7, 'model cost
    tracking per tenant') stay null for every call today -- see
    db/migrations/shared/0010_query_log_cost_tracking.sql's own comment for
    why: no ModelClient wired up anywhere yet actually calls a model."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO app.query_log (tenant_id, entity_id, user_id, role, question, intent, ir, sql_text, "
            "admitted, rejection_gate, rejection_reason, row_count, duration_ms, model_version, query_hash, "
            "input_tokens, output_tokens, cost_inr) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING query_log_id",
            (tenant_id, entity_id, user_id, role, question, intent, json.dumps(ir_dict), sql_text,
             admitted, rejection_gate, rejection_reason, row_count, duration_ms, model_version, query_hash,
             input_tokens, output_tokens, cost_inr),
        )
        return cur.fetchone()[0]


def ask(conn, schema: str, tenant_id: str, entity_id: int, question: str, model_client: ModelClient,
         config: ConfigRegistry, user_id: str, role: str, tenant_profile: str) -> AskResponse:
    started = datetime.now(timezone.utc)

    classification: IntentClassification = model_client.classify_intent(question)
    if classification.intent == "unsupported":
        refusal = build_refusal("out_of_scope", classification.reason,
                                   nearest_supported_question="What was our revenue last month?")
        _log(conn, tenant_id, entity_id, user_id, role, question, "unsupported", {}, None, False,
               "intent_classification", classification.reason, None, started, None, None)
        return AskResponse(status="refused", question=question, intent="unsupported", refusal=refusal)

    try:
        ir_dict = model_client.generate_ir(question, classification.intent)
    except Exception as e:
        _log(conn, tenant_id, entity_id, user_id, role, question, classification.intent, {}, None, False,
               "ir_generation", str(e), None, started, None, None)
        return AskResponse(status="error", question=question, intent=classification.intent,
                              refusal=build_refusal("ambiguous", f"could not generate a valid query for this "
                                                                    f"question: {e}"))

    try:
        ir = IRRequest(**ir_dict)
    except Exception as e:
        _log(conn, tenant_id, entity_id, user_id, role, question, classification.intent, ir_dict, None, False,
               "ir_schema", str(e), None, started, None, None)
        return AskResponse(status="rejected", question=question, intent=classification.intent, ir=ir_dict,
                              refusal=build_refusal("ambiguous", f"the generated query does not match the IR schema: {e}"))

    try:
        validate_ir(ir, config, tenant_profile)
    except IRValidationError as e:
        _log(conn, tenant_id, entity_id, user_id, role, question, ir.intent, ir_dict, None, False,
               "ir_validation", str(e), None, started, None, None)
        return AskResponse(status="rejected", question=question, intent=ir.intent, ir=ir_dict,
                              refusal=build_refusal("ambiguous", str(e)))

    result = _execute_as_model_reachable(conn, schema, tenant_id, entity_id, ir, config, tenant_profile)

    sanity_issue = _sanity_check(result)
    if sanity_issue:
        result.reason = sanity_issue

    # One gate pass per statement that actually ran, on the exact text
    # `cursor.execute` received (src/semantic/statements.py). A derived
    # metric is a tree of leaf queries, not one query, so gating one
    # representative statement would leave the rest unchecked -- which is
    # what happened until 2026-08-31, when ask_compiler.py handed these
    # gates a hand-maintained string that no code path ever executed.
    #
    # estimated_cost_inr defaults to None here: gate 6's ₹5 cap (D-066,
    # OPEN_QUESTIONS.md OQ-003) is real and declared, but nothing upstream
    # produces a cost figure to check it against yet, since
    # AnthropicModelClient (src/semantic/model_client.py) is still an
    # explicitly unconfigured connection point -- a separate, disclosed
    # gap. Once a real ModelClient reports token usage for the intent
    # classification and IR generation calls already made above, pass the
    # resulting cost_inr through here.
    admission = None
    for statement in result.executed_sql:
        if not statement.gated:
            continue
        admission = run_admission_gates(statement.sql, list(statement.tables), tenant_id)
        if not admission.admitted:
            _log(conn, tenant_id, entity_id, user_id, role, question, ir.intent, ir_dict, result.sql_text, False,
                   admission.gate, admission.reason, None, started, None, None)
            return AskResponse(status="rejected", question=question, intent=ir.intent, ir=ir_dict,
                                  refusal=build_refusal("ambiguous", f"admission control rejected this query "
                                                                        f"at gate {admission.gate!r}: {admission.reason}"))

    if result.status == "refused":
        # The one refusal the compiler classifies itself, because it is the
        # one this layer cannot: corpus/07 section 6's "period not
        # reportable" needs the reconciliation status and the unmapped rupee
        # value, which the compiler resolved at the gate. `result` is carried
        # through so a partially-gated answer (metric_trend's per-month
        # series) is still visible behind the refusal.
        _log(conn, tenant_id, entity_id, user_id, role, question, ir.intent, ir_dict, result.sql_text,
               True, None, result.reason, 0, started, None, None)
        return AskResponse(status="refused", question=question, intent=ir.intent, ir=ir_dict, result=result,
                              refusal=result.refusal)

    if result.status == "blocked":
        refusal = refusal_for_blocked_decision(ir.metric or "this metric", result.blocking_decisions)
        _log(conn, tenant_id, entity_id, user_id, role, question, ir.intent, ir_dict, result.sql_text,
               True, None, None, 0, started, None, None)
        return AskResponse(status="blocked", question=question, intent=ir.intent, ir=ir_dict, result=result,
                              refusal=refusal)

    if result.status == "unavailable":
        refusal = build_refusal("requires_data_not_held", result.reason or "the required data is not available yet")
        _log(conn, tenant_id, entity_id, user_id, role, question, ir.intent, ir_dict, result.sql_text,
               True, None, None, 0, started, None, None)
        return AskResponse(status="unavailable", question=question, intent=ir.intent, ir=ir_dict, result=result,
                              refusal=refusal)

    if result.status == "error":
        _log(conn, tenant_id, entity_id, user_id, role, question, ir.intent, ir_dict, result.sql_text,
               True, None, None, 0, started, None, None)
        return AskResponse(status="error", question=question, intent=ir.intent, ir=ir_dict, result=result)

    citation_dict = None
    if result.compiled_metric is not None and result.compiled_metric.status == "ok":
        try:
            mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id,
                                                                        _period_end_for_citation(ir))
            citation: Citation = build_citation(conn, schema, tenant_id, entity_id, mapping_version_id,
                                                    result.compiled_metric, "reconciled")
            citation_dict = citation.as_dict()
            citation_dict["value"] = str(citation_dict["value"])
        except NotCitable as e:
            # The metric compiled, but nothing backs it -- no source rows, or
            # no source file behind the rows (src/semantic/citation.py's
            # guards). Falling through to the 'ok' return below would answer
            # the question with a number and citation=None, which is the one
            # thing CLAUDE.md invariant 7 forbids: "a number without one is
            # not displayed. Not badged, not greyed out. Not displayed."
            #
            # This is an ordinary question, not a corner case: any period_sum
            # metric asked for a month not yet loaded resolves to 0 over zero
            # rows. "What was our revenue in June?" before June is ingested.
            # corpus/07 section 6's "requires data not held" is exactly that
            # -- the same class the sibling branch above uses, and e already
            # names the metric and what is missing, so it is passed through
            # rather than restated.
            refusal = build_refusal("requires_data_not_held", str(e))
            _log(conn, tenant_id, entity_id, user_id, role, question, ir.intent, ir_dict, result.sql_text,
                   True, None, None, result.compiled_metric.row_count, started, None, None)
            return AskResponse(status="unavailable", question=question, intent=ir.intent, ir=ir_dict,
                                  result=result, refusal=refusal)

    _log(conn, tenant_id, entity_id, user_id, role, question, ir.intent, ir_dict, result.sql_text,
           True, None, None, result.row_count, started,
           citation_dict.get("query_hash") if citation_dict else None, None)

    return AskResponse(status="ok", question=question, intent=ir.intent, ir=ir_dict, result=result,
                          citation=citation_dict)


def _execute_as_model_reachable(conn, schema, tenant_id, entity_id, ir, config, tenant_profile) -> AskResult:
    """corpus/07 section 7: 'The model-reachable role is a database object,
    not a code path' -- execution SHOULD run under model_reachable so gates
    2 (read-only) and 5 (PII exclusion) are enforced by Postgres's own
    grants, not only by admission.py's string-pattern checks. That is not
    what this function does yet, and the gap is real, not cosmetic: every
    migration explicitly REVOKEs model_reachable from map_account,
    mapping_version, period_lock and reconciliation_run (Sprint 2/3) --
    tables compile_metric and the data_health intent read on essentially
    every call. SET ROLE model_reachable here would make every Ask query
    fail with a permission error, not make Ask safer.

    The REVOKEs on map_account look aimed at one specific thing:
    source_account_name, the raw ledger text, is confidential in a way
    canonical_class is not (corpus/07 section 9 draws exactly this line for
    the mapping proposer: ledger names are model-visible there because
    they're the whole signal, deliberately, but that doesn't extend to
    Ask). The likely real fix is a view over map_account exposing
    (source_record_id, canonical_class, statement_section, statement_line)
    without source_account_name, granted to model_reachable, plus the same
    treatment for whichever period_lock/reconciliation_run columns
    data_health actually needs -- not a blanket grant on the base tables.
    That is a genuine design change to Sprint 2/3 grants, not a one-line
    fix, and is not made here without understanding why those REVOKEs were
    written the way they were. Logged rather than silently worked around;
    gates 2 and 5 are enforced by admission.py's pattern checks only, for
    now, same posture as OQ-003's cost/row caps -- a real, disclosed gap,
    not a silent default."""
    return compile_and_execute(conn, schema, tenant_id, entity_id, ir, config, tenant_profile)


def _period_end_for_citation(ir: IRRequest):
    from datetime import date
    if ir.period and ir.period.type == "month":
        from src.semantic.compiler import period_bounds
        return period_bounds(ir.period.value)[1]
    return date.today()


def _log(conn, tenant_id, entity_id, user_id, role, question, intent, ir_dict, sql_text, admitted,
           rejection_gate, rejection_reason, row_count, started, query_hash, model_version):
    duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    try:
        _write_query_log(conn, tenant_id, entity_id, user_id, role, question, intent, ir_dict, sql_text,
                            admitted, rejection_gate, rejection_reason, row_count, duration_ms, model_version,
                            query_hash)
    except Exception:
        pass  # logging must never break the Ask response itself
