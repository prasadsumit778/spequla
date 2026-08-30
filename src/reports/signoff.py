"""Report artefact persistence and the sign-off workflow, corpus/08 section
7 (commentary is edited, not generated), section 9 (provenance, immutable
re-render) and section 10 ("A pack cannot be signed while a blocking
exception is open for the period. The reviewer can override with a written
reason, which is logged and appears in section 9 of the pack itself.").

One report_artefact row per generation (db/migrations/tenant/0013). Mutable
only through edit_commentary while status='draft'; sign_pack is the only
transition to 'signed', after which nothing here writes to the row again.
render_pack never recomputes -- it reads the stored sections/chart_specs/
commentary verbatim, which is what makes re-rendering months later
byte-identical even across an intervening restatement (corpus/08 section 9).
"""
from __future__ import annotations

from dataclasses import dataclass

# open_blocking_exceptions lives in src/quality/exception_queue.py, next to
# the queue it reads: corpus/08 section 10's sign-off gate and corpus/09
# section 5's OPEN -> VALIDATED condition are two callers of one query, not
# two queries that happen to agree today. Re-exported here because this
# module's own callers (src/api/routes/reports.py) have always reached it
# through sign-off.
from src.quality.exception_queue import open_blocking_exceptions
from src.reports.edits import record_commentary_edit
from src.reports.pack import content_hash

__all__ = ["ReportArtefact", "SignOffBlocked", "edit_commentary", "get_report_artefact",
           "open_blocking_exceptions", "render_pack", "sign_pack", "write_report_artefact"]


class SignOffBlocked(Exception):
    """A blocking exception is open for the period and no override reason
    was given -- corpus/08 section 10's gate, refused rather than silently
    bypassed."""


@dataclass
class ReportArtefact:
    report_artefact_id: int
    tenant_id: str
    entity_id: int
    period_key: str
    profile: str
    generated_at: object
    generated_by: str
    mapping_version_id: int
    metric_versions: dict
    freshness_snapshot: list
    reconciliation_snapshot: list
    sections: dict
    chart_specs: list
    commentary: str | None
    unmapped_value_inr: object
    content_hash: str
    status: str
    reviewer: str | None
    signed_at: object
    blocking_exception_override_reason: str | None
    blocking_exception_override_by: str | None
    blocking_exception_override_at: object


_COLUMNS = ["report_artefact_id", "tenant_id", "entity_id", "period_key", "profile", "generated_at",
             "generated_by", "mapping_version_id", "metric_versions", "freshness_snapshot",
             "reconciliation_snapshot", "sections", "chart_specs", "commentary", "unmapped_value_inr",
             "content_hash", "status", "reviewer", "signed_at", "blocking_exception_override_reason",
             "blocking_exception_override_by", "blocking_exception_override_at"]


def _row_to_artefact(row) -> ReportArtefact:
    return ReportArtefact(**dict(zip(_COLUMNS, row)))


def write_report_artefact(conn, schema: str, pack: dict) -> ReportArtefact:
    """Inserts the output of src/reports/pack.generate_pack as one new,
    immutable-once-signed row. status starts 'draft'."""
    import json
    hash_ = content_hash(pack["sections"], pack["chart_specs"], pack["commentary"])
    with conn.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{schema}".report_artefact '
            f'(tenant_id, entity_id, period_key, profile, generated_by, mapping_version_id, metric_versions, '
            f' freshness_snapshot, reconciliation_snapshot, sections, chart_specs, commentary, '
            f' unmapped_value_inr, content_hash) '
            f'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) '
            f'RETURNING {", ".join(_COLUMNS)}',
            (pack["tenant_id"], pack["entity_id"], pack["period_key"], pack["profile"], pack["generated_by"],
             pack["mapping_version_id"], json.dumps(pack["metric_versions"]), json.dumps(pack["freshness_snapshot"]),
             json.dumps(pack["reconciliation_snapshot"]), json.dumps(pack["sections"]),
             json.dumps(pack["chart_specs"]), pack["commentary"], pack["unmapped_value_inr"], hash_),
        )
        row = cur.fetchone()
    conn.commit()
    return _row_to_artefact(row)


def get_report_artefact(conn, schema: str, report_artefact_id: int) -> ReportArtefact | None:
    with conn.cursor() as cur:
        cur.execute(f'SELECT {", ".join(_COLUMNS)} FROM "{schema}".report_artefact WHERE report_artefact_id = %s',
                       (report_artefact_id,))
        row = cur.fetchone()
    return _row_to_artefact(row) if row else None


def edit_commentary(conn, schema: str, report_artefact_id: int, commentary: str,
                       edited_by: str) -> ReportArtefact:
    """corpus/08 section 7 #2: 'Commentary is human-written... build the
    editor, not a generator.' Allowed only while status='draft' -- a signed
    pack's commentary is frozen, same as everything else in it.

    Every edit is appended to pack_edit_event with the superseded wording, so
    "edits per pack" (corpus/02 section 8, the primary commercial metric) is
    countable and no prior text is lost. The editor is named for the same
    reason sign_pack names its reviewer.
    """
    import json
    if not edited_by:
        raise ValueError("edit_commentary requires a named editor -- corpus/02 section 8 counts "
                            "edits 'made by the analyst'")
    artefact = get_report_artefact(conn, schema, report_artefact_id)
    if artefact is None:
        raise ValueError(f"no report_artefact {report_artefact_id}")
    if artefact.status != "draft":
        raise SignOffBlocked(f"report_artefact {report_artefact_id} is {artefact.status}, not draft -- "
                                f"a signed pack's commentary cannot be edited")
    hash_ = content_hash(artefact.sections, artefact.chart_specs, commentary)
    sections = dict(artefact.sections)
    sections["2_executive_summary"] = {"bullets_markdown": commentary, "written_by": "human"}
    with conn.cursor() as cur:
        cur.execute(
            f'UPDATE "{schema}".report_artefact SET commentary = %s, sections = %s, content_hash = %s '
            f'WHERE report_artefact_id = %s RETURNING {", ".join(_COLUMNS)}',
            (commentary, json.dumps(sections), hash_, report_artefact_id),
        )
        row = cur.fetchone()
    record_commentary_edit(
        conn, schema, artefact.tenant_id, artefact.entity_id, report_artefact_id,
        artefact.period_key, edited_by,
        previous_commentary=artefact.commentary, new_commentary=commentary,
    )
    conn.commit()
    return _row_to_artefact(row)


def sign_pack(conn, schema: str, report_artefact_id: int, reviewer: str,
                 override_reason: str | None = None, override_by: str | None = None) -> ReportArtefact:
    """corpus/08 section 10. Refuses to sign while a blocking exception is
    open for the period unless override_reason is given -- in which case
    the override is logged on the row itself and folded into section 9
    (data_quality_appendix.signoff_override), 'appears in section 9 of the
    pack itself' being a literal instruction, not just an audit-trail nicety."""
    import json
    from datetime import datetime, timezone

    artefact = get_report_artefact(conn, schema, report_artefact_id)
    if artefact is None:
        raise ValueError(f"no report_artefact {report_artefact_id}")
    if artefact.status != "draft":
        raise SignOffBlocked(f"report_artefact {report_artefact_id} is already {artefact.status}")
    if not reviewer:
        raise SignOffBlocked("sign_pack requires a named reviewer, per corpus/08 section 10")

    blocking = open_blocking_exceptions(conn, schema, artefact.tenant_id, artefact.entity_id, artefact.period_key)
    if blocking and not override_reason:
        raise SignOffBlocked(
            f"{len(blocking)} open blocking exception(s) for {artefact.period_key} -- corpus/08 section 10: "
            f"'a pack cannot be signed while a blocking exception is open for the period,' override with a "
            f"written reason to proceed"
        )
    if blocking and not override_by:
        raise SignOffBlocked("an override reason requires a named overriding person")

    now = datetime.now(timezone.utc)
    sections = dict(artefact.sections)
    if blocking:
        appendix = dict(sections.get("9_data_quality_appendix", {}))
        appendix["signoff_override"] = {
            "reason": override_reason, "by": override_by, "at": now.isoformat(),
            "open_blocking_exceptions_at_override": blocking,
        }
        sections["9_data_quality_appendix"] = appendix
        hash_ = content_hash(sections, artefact.chart_specs, artefact.commentary)
    else:
        hash_ = artefact.content_hash

    with conn.cursor() as cur:
        cur.execute(
            f'UPDATE "{schema}".report_artefact SET status = %s, reviewer = %s, signed_at = %s, '
            f'   sections = %s, content_hash = %s, '
            f'   blocking_exception_override_reason = %s, blocking_exception_override_by = %s, '
            f'   blocking_exception_override_at = %s '
            f'WHERE report_artefact_id = %s RETURNING {", ".join(_COLUMNS)}',
            ("signed", reviewer, now, json.dumps(sections), hash_, override_reason, override_by,
             now if blocking else None, report_artefact_id),
        )
        row = cur.fetchone()
    conn.commit()
    return _row_to_artefact(row)


def render_pack(conn, schema: str, report_artefact_id: int) -> dict:
    """Re-render: reads the stored row verbatim, never recomputes from live
    tables. corpus/08 section 9's acceptance test -- calling this twice, or
    calling it once now and once after the underlying GL data changes,
    returns byte-identical output either way."""
    artefact = get_report_artefact(conn, schema, report_artefact_id)
    if artefact is None:
        raise ValueError(f"no report_artefact {report_artefact_id}")
    return {
        "report_artefact_id": artefact.report_artefact_id, "tenant_id": artefact.tenant_id,
        "entity_id": artefact.entity_id, "period_key": artefact.period_key, "profile": artefact.profile,
        "generated_at": artefact.generated_at, "generated_by": artefact.generated_by,
        "mapping_version_id": artefact.mapping_version_id, "metric_versions": artefact.metric_versions,
        "freshness_snapshot": artefact.freshness_snapshot, "reconciliation_snapshot": artefact.reconciliation_snapshot,
        "sections": artefact.sections, "chart_specs": artefact.chart_specs, "commentary": artefact.commentary,
        "unmapped_value_inr": artefact.unmapped_value_inr, "content_hash": artefact.content_hash,
        "status": artefact.status, "reviewer": artefact.reviewer, "signed_at": artefact.signed_at,
        "blocking_exception_override_reason": artefact.blocking_exception_override_reason,
        "blocking_exception_override_by": artefact.blocking_exception_override_by,
        "blocking_exception_override_at": artefact.blocking_exception_override_at,
    }
