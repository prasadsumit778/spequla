"""Edits per pack -- corpus/02 section 8, corpus/11 section 4.

corpus/02 section 8 defines the measure as "count of commentary and number
corrections made by the analyst before signing" and calls it the primary
commercial metric. corpus/11 section 4 lists it under "metrics tracked but
not gated": read, never enforced, and explicitly without a target, because
"setting a target on any of them before pilot one would be inventing a
number." Nothing in this module compares the count to a threshold, and
nothing should be added that does until the corpus declares one.

The two halves of the count come from different places, for a structural
reason rather than a stylistic one:

  * commentary edits -- report_artefact.commentary is rewritten in place
    while the pack is a draft, so the count would be lost without an event
    log. src/reports/signoff.edit_commentary appends one pack_edit_event row
    per edit, carrying the superseded wording.

  * number corrections -- report_artefact already stores one row per
    generation, so a period that was generated three times has three rows.
    A correction is a regeneration whose `sections` differ from the previous
    generation's. Regenerating with no change to the numbers (because the
    analyst was checking, or only the commentary moved) is not a correction
    and is not counted.

This is an operational measure of analyst effort, not a financial metric over
canonical columns, so it is deliberately not a metric contract in
config/metrics/ (CLAUDE.md invariant 2 governs financial formulas).
"""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class PackEdits:
    """The edit count for one (entity, period)'s pack.

    `signed` says whether the count is final. corpus/02 section 8 counts edits
    "before signing", so a draft's number can still rise.
    """
    period_key: str
    entity_id: int
    commentary_edits: int
    number_corrections: int
    generations: int
    signed: bool

    @property
    def total_edits(self) -> int:
        return self.commentary_edits + self.number_corrections


def record_commentary_edit(conn, schema: str, tenant_id: str, entity_id: int,
                              report_artefact_id: int, period_key: str, edited_by: str,
                              previous_commentary: str | None, new_commentary: str | None) -> None:
    """Append one commentary edit. Called by signoff.edit_commentary; not a
    public entry point of its own, so the count cannot drift from reality by
    someone editing commentary through another path."""
    if not edited_by:
        raise ValueError("record_commentary_edit requires a named editor -- corpus/02 section 8 "
                            "counts edits 'made by the analyst', which means the analyst is named")
    with conn.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{schema}".pack_edit_event '
            f'(tenant_id, entity_id, report_artefact_id, period_key, edit_type, edited_by, '
            f' previous_commentary, new_commentary) '
            f"VALUES (%s, %s, %s, %s, 'commentary', %s, %s, %s)",
            (tenant_id, entity_id, report_artefact_id, period_key, edited_by,
             previous_commentary, new_commentary),
        )


# Two parts of a pack change without any number changing, and both have to be
# excluded or every regeneration would read as a correction.
#
#   2_executive_summary -- signoff.edit_commentary writes the analyst's prose
#     here as well as into report_artefact.commentary. Counting it would score
#     one commentary edit twice, once in each half of the measure.
#
#   1_cover.freshness -- corpus/08 section 7 #1 puts data freshness per source
#     on the cover, and `hours_since` is a reading of the wall clock at
#     generation time. It moves every time the pack is generated, whether or
#     not a rupee moved.
COMMENTARY_SECTION = "2_executive_summary"
COVER_SECTION = "1_cover"
CLOCK_FIELD = "freshness"


def _strip_non_numeric(sections: dict) -> dict:
    """The parts of a pack whose change means a number changed."""
    out = {k: v for k, v in sections.items() if k != COMMENTARY_SECTION}
    cover = out.get(COVER_SECTION)
    if isinstance(cover, dict) and CLOCK_FIELD in cover:
        out[COVER_SECTION] = {k: v for k, v in cover.items() if k != CLOCK_FIELD}
    return out


def _canonical(sections) -> str:
    """Stable JSON of a generation's numbers.

    Uses the same shape as src/reports/pack.content_hash so "the sections
    changed" means the same thing in both places, minus the two non-numeric
    parts above.
    """
    if isinstance(sections, str):
        sections = json.loads(sections)
    return json.dumps(_strip_non_numeric(sections), sort_keys=True,
                          separators=(",", ":"), default=str)


def pack_edits(conn, schema: str, tenant_id: str, entity_id: int, period_key: str) -> PackEdits:
    """The edit count for one period's pack."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT report_artefact_id, sections, status FROM "{schema}".report_artefact '
            f'WHERE tenant_id = %s AND entity_id = %s AND period_key = %s '
            f'ORDER BY generated_at, report_artefact_id',
            (tenant_id, entity_id, period_key),
        )
        artefacts = cur.fetchall()

        cur.execute(
            f'SELECT count(*) FROM "{schema}".pack_edit_event '
            f'WHERE tenant_id = %s AND entity_id = %s AND period_key = %s '
            f"  AND edit_type = 'commentary'",
            (tenant_id, entity_id, period_key),
        )
        commentary_edits = cur.fetchone()[0]

    number_corrections = 0
    previous = None
    for _artefact_id, sections, _status in artefacts:
        current = _canonical(sections)
        if previous is not None and current != previous:
            number_corrections += 1
        previous = current

    return PackEdits(
        period_key=period_key,
        entity_id=entity_id,
        commentary_edits=commentary_edits,
        number_corrections=number_corrections,
        generations=len(artefacts),
        signed=any(status == "signed" for _id, _s, status in artefacts),
    )


def edits_by_period(conn, schema: str, tenant_id: str, entity_id: int) -> list[PackEdits]:
    """Every period that has a pack, oldest first.

    corpus/02 section 8's target is "baseline in month one, falling month on
    month", so the series matters more than any single month. No trend is
    computed or judged here -- that is a reading the analyst makes.
    """
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT DISTINCT period_key FROM "{schema}".report_artefact '
            f'WHERE tenant_id = %s AND entity_id = %s ORDER BY period_key',
            (tenant_id, entity_id),
        )
        periods = [r[0] for r in cur.fetchall()]
    return [pack_edits(conn, schema, tenant_id, entity_id, p) for p in periods]
