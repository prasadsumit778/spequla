"""SQL compilation and execution for the Ask surface, corpus/07 section 2
stages 6-9 (SQL compilation, admission control, execution, result sanity).

Reuses src/semantic/compiler.py's compile_metric wherever a metric's own
value is needed -- that function already implements the transitive
dependency-gate, the override chain and the mapping-approval gate (Sprint
3), and this module does not duplicate any of that. What THIS module adds
is specific to the Ask surface: turning a validated IRRequest into
(a) the record of what compiling it actually sent to Postgres, which the
admission gates and the "view SQL" panel both read, and (b) an AskResult
carrying whichever of ok / blocked / unavailable / error actually describes
what happened, for each of corpus/07 section 4's twelve intents.

A derived metric like ebitda is not "one query" in any literal sense --
compile_metric resolves it as a small tree of leaf queries composed in
Python. ebitda is eight metric nodes and five leaves; dso, dpo and dio
recompile their base metric over twelve trailing months on top of that.
Until 2026-08-31 this module answered that by keeping
`_representative_gl_class_sql`, a hand-maintained string whose docstring
claimed to mirror compiler.py's `_fetch_leaf_amounts` "exactly" -- one
invented statement standing in for dozens of real ones, checked by nothing.
The gates read the copy and Postgres read the original, so any divergence
between them was invisible by construction. That function is gone.
compile_metric now returns every statement it ran
(CompiledMetric.executed_sql, src/semantic/statements.py) and the gates run
against those, one gate pass per statement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from src.config.loader import ConfigRegistry
from src.quality.period_gate import STATEMENTS_REPORTABLE, resolve_period_reportability
from src.quality.period_state import get_current_period_lock
from src.reports.balance_sheet import assemble_balance_sheet
from src.reports.pnl import assemble_consumer_cm_ladder, assemble_manufacturing_pnl
from src.reports.query import NoApprovedMappingError, resolve_mapping_version_for_period
from src.semantic.bridges import (
    BridgeResult,
    compute_cash_bridge,
    compute_ebitda_bridge,
    not_configured,
)
from src.semantic.compiler import CompiledMetric, _admit, compile_metric, period_bounds
from src.semantic.ir import IRRequest
from src.semantic.statements import (
    AdmissionHook,
    ExecutedStatement,
    distinct_statements,
    joined_sql,
    referenced_tables,
)
from src.semantic.refusal import Refusal, refusal_for_unreportable_period

UNAVAILABLE_DIMENSIONS = {
    "customer": "customer-level breakdown needs dim_customer and fact_gl_entry.customer_key, deferred since "
                  "Sprint 1 (nullable, unconstrained FK -- corpus/12 sprint 0 plan's sequencing decision)",
    "product": "product-level breakdown needs dim_item/map_item, not yet built",
    "vendor": "vendor-level breakdown needs dim_vendor and fact_gl_entry.vendor_key, deferred since Sprint 1",
}


@dataclass
class AskResult:
    status: str  # 'ok' | 'refused' | 'blocked' | 'unavailable' | 'error'
    intent: str
    # Every statement this question sent to Postgres, deduplicated, in
    # execution order. This is what corpus/07 section 7's gates inspect --
    # per statement, on the text `cursor.execute` received. `sql_text` is
    # the same list rendered as one string for app.query_log's sql_text
    # column and corpus/08 section 2's "view SQL" panel, and
    # `tables_referenced` is the union of what those statements read,
    # informational only: the gates read each statement's own tables.
    executed_sql: list[ExecutedStatement] = field(default_factory=list)
    sql_text: str | None = None
    tables_referenced: list[str] = field(default_factory=list)
    value: object = None
    series: list[dict] = field(default_factory=list)
    bridge: BridgeResult | None = None
    reason: str | None = None
    blocking_decisions: list[str] = field(default_factory=list)
    compiled_metric: CompiledMetric | None = None
    row_count: int = 0
    # Set only by the deterministic period gate below. Every other refusal in
    # Ask is classified in src/semantic/ask.py from the result's status --
    # this one cannot be, because "period not reportable" is a distinct
    # corpus/07 section 6 class that a bare 'unavailable' would collapse into
    # "requires data not held", losing the reconciliation status and the
    # unmapped rupee value that class is required to state.
    refusal: Refusal | None = None


def _sql_fields(*statements: ExecutedStatement | list[ExecutedStatement] | CompiledMetric) -> dict:
    """The three SQL fields of an AskResult, built from what actually ran.

    Takes CompiledMetrics, statement lists, or single statements, in the
    order they were executed, and flattens them into one deduplicated
    record. Every intent that touches the database builds its AskResult
    through this, so no intent can report SQL it did not run, and none can
    run SQL it does not report -- which is the whole difference between this
    and the `_representative_gl_class_sql` it replaced."""
    flat: list[ExecutedStatement] = []
    for item in statements:
        if isinstance(item, CompiledMetric):
            flat.extend(item.executed_sql)
        elif isinstance(item, ExecutedStatement):
            flat.append(item)
        else:
            flat.extend(item)
    distinct = distinct_statements(flat)
    return {"executed_sql": distinct, "sql_text": joined_sql(distinct),
              "tables_referenced": referenced_tables(distinct)}


def compile_and_execute(conn, schema: str, tenant_id: str, entity_id: int, ir: IRRequest,
                           config: ConfigRegistry, tenant_profile: str = "manufacturing",
                           admission: AdmissionHook | None = None) -> AskResult:
    """`admission` is corpus/07 section 2's stage 7, handed down so it runs
    at stage 7 -- immediately before each statement executes -- rather than
    after stage 8 has already been to the database. It raises
    AdmissionRejected (src/semantic/admission.py) out through here, which
    src/semantic/ask.py catches; nothing in this module swallows it, because
    a rejection is not one intent's business to interpret."""
    handler = _INTENT_HANDLERS.get(ir.intent)
    if handler is None:
        return AskResult(status="error", intent=ir.intent, reason=f"no handler for intent {ir.intent!r}")
    return handler(conn, schema, tenant_id, entity_id, ir, config, tenant_profile, admission)


def _period_key_from_ir(ir: IRRequest) -> str:
    if ir.period is None:
        raise ValueError("period is required for this intent")
    if ir.period.type == "month":
        return ir.period.value
    raise ValueError(f"period type {ir.period.type!r} not yet resolvable to a single month")


def _refuse_unreportable(conn, schema: str, tenant_id: str, entity_id: int, intent: str,
                            period_key: str) -> AskResult | None:
    """corpus/07 section 6's "period not reportable" class, applied
    deterministically before a period's numbers are computed.

    Returns None when the period may be read, so a caller reads as
    `if refused := _refuse_unreportable(...): return refused`.

    **This runs first in every handler that produces a number**, ahead of
    each handler's own availability checks. Where both apply -- "revenue by
    customer" for an unmapped period, which is both unreportable and needs a
    dimension this build has not got -- the period is the one to state.
    Answering "customer breakdown is not built yet" carries the implication
    that the period behind it is otherwise fine and the number would appear
    once the feature lands, and that is not true. The dimension's own
    refusal is still reached for any period that IS reportable.

    Intents that never produce a number are deliberately not gated:
    definition_lookup (a registry lookup, corpus/07 section 4: "No SQL
    runs"), data_health (the screen that exists to explain the gate -- see
    _data_health), and ageing/concentration (unconditionally unavailable in
    this build, on a missing data source rather than on this period).
    """
    reportability = resolve_period_reportability(conn, schema, tenant_id, entity_id, period_key,
                                                       STATEMENTS_REPORTABLE)
    if reportability.reportable:
        return None
    return AskResult(
        status="refused", intent=intent,
        reason=reportability.detail(),
        refusal=refusal_for_unreportable_period(
            reportability.period_key, reportability.status, reportability.unmapped_value_inr,
            reportability.unmapped_value_unavailable_reason,
        ),
    )


def _metric_value(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing",
                     admission: AdmissionHook | None = None) -> AskResult:
    period_key = _period_key_from_ir(ir)
    if refused := _refuse_unreportable(conn, schema, tenant_id, entity_id, ir.intent, period_key):
        return refused
    result = compile_metric(conn, schema, tenant_id, entity_id, ir.metric, period_key, config,
                                admission=admission)
    # A decision-gated metric returns before it issues a single statement,
    # so its record is empty and sql_text is None. That is the honest
    # answer: the previous code reported a query for a question that never
    # reached the database.
    if result.status != "ok":
        return AskResult(status="blocked" if result.status == "blocked" else "unavailable", intent=ir.intent,
                            reason=result.reason, blocking_decisions=result.blocking_decisions,
                            compiled_metric=result, **_sql_fields(result))
    return AskResult(status="ok", intent=ir.intent, value=result.value, compiled_metric=result,
                        row_count=result.row_count, **_sql_fields(result))


def _metric_trend(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing",
                     admission: AdmissionHook | None = None) -> AskResult:
    if ir.period is None or ir.period.resolved_range is None:
        return AskResult(status="error", intent=ir.intent, reason="metric_trend requires period.resolved_range")
    start = date.fromisoformat(ir.period.resolved_range[0])
    end = date.fromisoformat(ir.period.resolved_range[1])
    period_keys = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        period_keys.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1

    # The period gate runs per month here rather than over the window as a
    # whole. A trend already reports a labelled status per month and has done
    # since it was written, so an unreportable month becomes another labelled
    # month rather than a reason to refuse the eleven around it -- nothing is
    # silently dropped, which is the property that matters. Contrast
    # src/quality/period_gate.first_unreportable, used by the statement
    # routes, where the output is one set of totals and a missing month would
    # disappear into them.
    series = []
    last_result = None
    last_refusal: Refusal | None = None
    # Every month's statements, not the last month's. A twelve-month trend is
    # twelve compiles, and reporting one of them as though it were the query
    # is the same substitution `_representative_gl_class_sql` made.
    executed: list[ExecutedStatement] = []
    for pk in period_keys:
        if refused := _refuse_unreportable(conn, schema, tenant_id, entity_id, ir.intent, pk):
            last_refusal = refused.refusal
            series.append({"period": pk, "status": "refused", "value": None, "reason": refused.reason})
            continue
        r = compile_metric(conn, schema, tenant_id, entity_id, ir.metric, pk, config, admission=admission)
        executed.extend(r.executed_sql)
        last_result = r
        series.append({"period": pk, "status": r.status, "value": str(r.value) if r.value is not None else None,
                          "reason": r.reason})

    any_ok = any(s["status"] == "ok" for s in series)
    if not any_ok and last_result is None and last_refusal is not None:
        # Every month in the window was refused by the gate. The refusal
        # names the last month -- a real period with a real status and a real
        # unmapped value -- and `series` carries the per-month detail behind
        # it, rather than inventing a status for the window as a whole.
        return AskResult(status="refused", intent=ir.intent, series=series,
                            reason=series[-1]["reason"], refusal=last_refusal, **_sql_fields(executed))
    return AskResult(status="ok" if any_ok else (last_result.status if last_result else "error"),
                        intent=ir.intent, series=series,
                        reason=None if any_ok else (last_result.reason if last_result else None),
                        blocking_decisions=last_result.blocking_decisions if last_result and not any_ok else [],
                        **_sql_fields(executed))


def _metric_comparison(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing",
                     admission: AdmissionHook | None = None) -> AskResult:
    period_key = _period_key_from_ir(ir)
    if refused := _refuse_unreportable(conn, schema, tenant_id, entity_id, ir.intent, period_key):
        return refused
    current = compile_metric(conn, schema, tenant_id, entity_id, ir.metric, period_key, config,
                                admission=admission)
    if current.status != "ok":
        return AskResult(status="blocked" if current.status == "blocked" else "unavailable", intent=ir.intent,
                            reason=current.reason, blocking_decisions=current.blocking_decisions,
                            compiled_metric=current, **_sql_fields(current))

    if ir.compare_to is None:
        return AskResult(status="error", intent=ir.intent, reason="metric_comparison requires compare_to",
                            **_sql_fields(current))
    y, m = (int(p) for p in period_key.split("-"))
    if ir.compare_to.type in ("prior_period", "mom"):
        cy, cm = (y, m - 1) if m > 1 else (y - 1, 12)
    elif ir.compare_to.type == "yoy":
        cy, cm = y - 1, m
    else:
        return AskResult(status="error", intent=ir.intent,
                            reason=f"unsupported compare_to {ir.compare_to.type!r}", **_sql_fields(current))
    compare_key = f"{cy:04d}-{cm:02d}"

    # The comparison period is gated too, but reports its state in place
    # rather than refusing the whole answer: the question asked for THIS
    # period's number, and the payload already carries a status/reason for
    # the comparison half. What it must never do is put a number there for a
    # period that may not be read.
    executed: list[ExecutedStatement] = list(current.executed_sql)
    compare_refused = _refuse_unreportable(conn, schema, tenant_id, entity_id, ir.intent, compare_key)
    if compare_refused is not None:
        compare_cell = {"period": compare_key, "value": None, "status": "refused",
                          "reason": compare_refused.reason}
    else:
        compare = compile_metric(conn, schema, tenant_id, entity_id, ir.metric, compare_key, config,
                                    admission=admission)
        executed.extend(compare.executed_sql)
        compare_cell = {"period": compare_key, "value": str(compare.value) if compare.status == "ok" else None,
                          "status": compare.status, "reason": compare.reason}

    return AskResult(
        status="ok", intent=ir.intent,
        value={"current": {"period": period_key, "value": str(current.value)}, "compare": compare_cell},
        compiled_metric=current, **_sql_fields(executed),
    )


def _metric_breakdown_or_ranking(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing",
                     admission: AdmissionHook | None = None) -> AskResult:
    # Ahead of the dimension check on purpose -- see _refuse_unreportable on
    # why an unreportable period is the thing to state when both apply.
    if refused := _refuse_unreportable(conn, schema, tenant_id, entity_id, ir.intent,
                                            _period_key_from_ir(ir)):
        return refused
    for dim in ir.breakdown:
        if dim in UNAVAILABLE_DIMENSIONS:
            return AskResult(status="unavailable", intent=ir.intent,
                                reason=f"breakdown by {dim!r} is not available yet: {UNAVAILABLE_DIMENSIONS[dim]}")
    # No breakdown dimension this build can actually resolve yet (date/entity
    # are the only currently-populated dimensions, and grouping by them is
    # not a meaningful "breakdown" in the golden-question sense) -- report
    # the aggregate value honestly rather than fabricate a grouped result.
    return _metric_value(conn, schema, tenant_id, entity_id, ir, config, tenant_profile, admission)


def _statement_view(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing",
                     admission: AdmissionHook | None = None) -> AskResult:
    if ir.period is None:
        return AskResult(status="error", intent=ir.intent, reason="statement_view requires a period")
    period_start, period_end = period_bounds(_period_key_from_ir(ir)) if ir.period.type == "month" else (None, None)
    if period_start is None:
        return AskResult(status="unavailable", intent=ir.intent,
                            reason="only single-month statement_view is implemented in this sprint")
    if refused := _refuse_unreportable(conn, schema, tenant_id, entity_id, ir.intent,
                                            _period_key_from_ir(ir)):
        return refused
    try:
        mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, period_end)
    except NoApprovedMappingError as e:
        return AskResult(status="unavailable", intent=ir.intent, reason=str(e))

    if tenant_profile == "consumer":
        pnl = assemble_consumer_cm_ladder(conn, schema, tenant_id, entity_id, mapping_version_id,
                                              period_start, period_end)
    else:
        pnl = assemble_manufacturing_pnl(conn, schema, tenant_id, entity_id, mapping_version_id,
                                            period_start, period_end)
    bs = assemble_balance_sheet(conn, schema, tenant_id, entity_id, mapping_version_id, period_end)

    # **No executed_sql, and therefore no admission gate.** Statement
    # assembly reads through src/reports/{pnl,balance_sheet,query}.py, which
    # do not record what they run, so this intent reaches Postgres with
    # nothing in front of it -- as every intent did before 2026-08-31. The
    # tables below are a declaration of intent, not a record of execution,
    # and are kept only because the API already returns them; nothing gates
    # on them. Threading the record through report assembly is a wider
    # change than this one, because those functions are shared with the
    # monthly pack and the overview tiles. Disclosed here and in
    # src/semantic/statements.py rather than left for a reader to discover
    # from the absence of a field.
    return AskResult(
        status="ok", intent=ir.intent,
        value={"pnl": {k: str(v) for k, v in pnl.lines.items()},
                "pnl_subtotals": {k: (str(v) if v is not None else None) for k, v in pnl.subtotals.items()},
                "balance_sheet_balances": bs.balances,
                "unmapped_value_inr": str(pnl.unmapped_value_inr)},
        tables_referenced=[f'"{schema}".fact_gl_entry', f'"{schema}".map_account'],
    )


def _data_health(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing",
                     admission: AdmissionHook | None = None) -> AskResult:
    """corpus/07 section 4: 'Is June reconciled?' -- reads period_lock and
    reconciliation_run.

    **Deliberately not period-gated.** This intent reports the period's state
    rather than reporting through it, and it is the answer a user needs
    precisely when every other intent has just refused them. Gating it would
    make the system decline to say why it is declining. Nothing here is a
    financial number computed from facts: it returns the status, the
    reconciliation runs and the unmapped value -- the same three things the
    refusal itself states.
    """
    executed: list[ExecutedStatement] = []
    if ir.period is not None:
        period_key = _period_key_from_ir(ir)
        lock = get_current_period_lock(conn, schema, tenant_id, entity_id, period_key,
                                            statement_log=executed, admission=admission)
        checks_sql = (f'SELECT check_type, status, residual_inr FROM "{schema}".reconciliation_run '
                         f'WHERE tenant_id=%s AND entity_id=%s AND period_key=%s ORDER BY run_at DESC')
        checks_stmt = _admit(admission, checks_sql, (f'"{schema}".reconciliation_run',))
        executed.append(ExecutedStatement(checks_stmt.sql, (f'"{schema}".reconciliation_run',), gated=True))
        with conn.cursor() as cur:
            cur.execute(checks_stmt.sql, (tenant_id, entity_id, period_key))
            checks = [{"check_type": r[0], "status": r[1], "residual_inr": str(r[2])} for r in cur.fetchall()]
        return AskResult(status="ok", intent=ir.intent,
                            value={"period": period_key, "status": lock.status if lock else "open", "checks": checks},
                            **_sql_fields(executed))

    try:
        mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, date.today(),
                                                                     statement_log=executed)
    except NoApprovedMappingError as e:
        return AskResult(status="unavailable", intent=ir.intent, reason=str(e), **_sql_fields(executed))
    # `AND tenant_id = %s` added 2026-08-31, when this statement first came
    # under admission control and gate 4 rejected it: it scoped only by
    # mapping_version_id, which IS tenant-scoped (and entity-scoped) through
    # the mapping_version row resolved just above, but the tenant predicate
    # corpus/07 section 7 gate 4 requires was nowhere in the text. The filter
    # is a no-op against today's data by construction and is meant to stay
    # one; what changed is that the query now says so. This is the first
    # thing the gates caught that a reconstruction could not have -- the
    # reconstruction was of a different statement entirely.
    unmapped_sql = (f'SELECT COALESCE(SUM(period_value_inr), 0), '
                       f"       COALESCE(SUM(period_value_inr) FILTER (WHERE canonical_class='suspense.unmapped'), 0) "
                       f'FROM "{schema}".map_account WHERE mapping_version_id = %s AND tenant_id = %s')
    # Two aggregates over the whole table, so this returns exactly one row
    # whatever gate 7 appends -- no truncation to check for, unlike
    # compiler.py's leaf reads, whose rows are summed after the cap.
    unmapped_stmt = _admit(admission, unmapped_sql, (f'"{schema}".map_account',))
    executed.append(ExecutedStatement(unmapped_stmt.sql, (f'"{schema}".map_account',), gated=True))
    with conn.cursor() as cur:
        cur.execute(unmapped_stmt.sql, (mapping_version_id, tenant_id))
        total, unmapped = cur.fetchone()
    pct = float(unmapped / total) if total else 0.0
    return AskResult(status="ok", intent=ir.intent,
                        value={"unmapped_pct": pct, "unmapped_value_inr": str(unmapped)},
                        **_sql_fields(executed))


def _definition_lookup(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing",
                     admission: AdmissionHook | None = None) -> AskResult:
    """corpus/07 section 4: 'Registry lookup, returns the resolved contract.
    No SQL runs.' Genuinely no database touch at all."""
    if ir.metric not in config.metrics:
        return AskResult(status="unavailable", intent=ir.intent, reason=f"unknown metric {ir.metric!r}")
    contract = config.metrics[ir.metric]
    body = contract.model_extra.get("contract") if contract.model_extra else None
    return AskResult(status="ok", intent=ir.intent,
                        value={"registry": contract.registry.model_dump(), "contract": body})


def _variance_explain(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing",
                     admission: AdmissionHook | None = None) -> AskResult:
    if ir.metric not in ("ebitda", "closing_cash"):
        return AskResult(status="unavailable", intent=ir.intent,
                            reason=f"variance_explain for {ir.metric!r} has no bridge implemented yet "
                                    f"(see src/semantic/bridges.py: only the revenue, ebitda and cash bridges exist)")

    period_key = _period_key_from_ir(ir)
    y, m = (int(p) for p in period_key.split("-"))
    py, pm = (y, m - 1) if m > 1 else (y - 1, 12)
    prior_key = f"{py:04d}-{pm:02d}"

    # Both periods, and both refuse outright: a bridge is a decomposition of
    # the movement BETWEEN them, so an unreadable period on either side makes
    # the whole delta unreportable. There is no half of this answer that is
    # still true (CLAUDE.md invariant 15).
    for gated in (period_key, prior_key):
        if refused := _refuse_unreportable(conn, schema, tenant_id, entity_id, ir.intent, gated):
            return refused

    current = compile_metric(conn, schema, tenant_id, entity_id, ir.metric, period_key, config,
                                admission=admission)
    prior = compile_metric(conn, schema, tenant_id, entity_id, ir.metric, prior_key, config, admission=admission)
    if current.status != "ok" or prior.status != "ok":
        blocked = current if current.status != "ok" else prior
        return AskResult(status="blocked" if blocked.status == "blocked" else "unavailable", intent=ir.intent,
                            reason=blocked.reason, blocking_decisions=blocked.blocking_decisions,
                            **_sql_fields(current, prior))

    if ir.metric == "ebitda":
        gp_current = compile_metric(conn, schema, tenant_id, entity_id, "gross_profit", period_key, config,
                                       admission=admission)
        gp_prior = compile_metric(conn, schema, tenant_id, entity_id, "gross_profit", prior_key, config,
                                       admission=admission)
        opex_current = compile_metric(conn, schema, tenant_id, entity_id, "opex", period_key, config,
                                       admission=admission)
        opex_prior = compile_metric(conn, schema, tenant_id, entity_id, "opex", prior_key, config,
                                       admission=admission)
        # Six compiles across two periods -- the widest single Ask question
        # in the build, and the clearest case for why the record is the
        # union of a tree rather than one statement standing for it.
        sql_fields = _sql_fields(current, prior, gp_current, gp_prior, opex_current, opex_prior)
        if any(r.status != "ok" for r in (gp_current, gp_prior, opex_current, opex_prior)):
            return AskResult(status="unavailable", intent=ir.intent,
                                reason="gross_profit/opex breakdown unavailable for the bridge", **sql_fields)
        bridge = compute_ebitda_bridge(gp_current.value - gp_prior.value,
                                          {"opex_total": opex_current.value - opex_prior.value},
                                          current.value - prior.value)
        return AskResult(status="ok", intent=ir.intent, bridge=bridge,
                            value={"current": str(current.value), "prior": str(prior.value)}, **sql_fields)

    return AskResult(status="unavailable", intent=ir.intent, reason="cash bridge not wired to compile_metric yet",
                        **_sql_fields(current, prior))


def _ageing(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing",
                     admission: AdmissionHook | None = None) -> AskResult:
    return AskResult(status="unavailable", intent=ir.intent,
                        reason="ageing needs AR/AP open-item detail (fact_ar_open/fact_ap_open or the AR/AP "
                                "ageing template), which has no ingestion pipeline built yet -- only COA, TB, "
                                "GL and Bank are ingested in this build")


def _concentration(conn, schema, tenant_id, entity_id, ir: IRRequest, config: ConfigRegistry, tenant_profile: str = "manufacturing",
                     admission: AdmissionHook | None = None) -> AskResult:
    return AskResult(status="unavailable", intent=ir.intent,
                        reason="concentration needs a customer/vendor breakdown, which needs dim_customer/"
                                "dim_vendor -- deferred since Sprint 1 (see UNAVAILABLE_DIMENSIONS)")


_INTENT_HANDLERS = {
    "metric_value": _metric_value,
    "metric_trend": _metric_trend,
    "metric_comparison": _metric_comparison,
    "metric_breakdown": _metric_breakdown_or_ranking,
    "metric_ranking": _metric_breakdown_or_ranking,
    "variance_explain": _variance_explain,
    "statement_view": _statement_view,
    "concentration": _concentration,
    "ageing": _ageing,
    "definition_lookup": _definition_lookup,
    "data_health": _data_health,
}
