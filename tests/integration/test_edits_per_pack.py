"""Edits per pack -- corpus/02 section 8, corpus/11 section 4.

corpus/02 section 8 calls this "the primary commercial metric" and defines it
as the "count of commentary and number corrections made by the analyst before
signing". corpus/11 section 4 keeps it deliberately ungated. These tests
assert the count, and that no target is asserted anywhere.

Expected counts are derived from the actions the test itself performs, not
read back from a prior run (CLAUDE.md section 9).
"""
from __future__ import annotations

from datetime import date

import pytest

from src.config.loader import load_registry
from src.reports.edits import PackEdits, edits_by_period, pack_edits
from src.reports.pack import generate_pack
from src.reports.signoff import edit_commentary, sign_pack, write_report_artefact
from tests.helpers import ingest_manufacturer, run_and_freeze_mapping

PERIOD_KEY = "2025-03"


def _setup(conn, schema, tenant_id):
    ingest_manufacturer(conn, schema, tenant_id, 1)
    run_and_freeze_mapping(conn, schema, tenant_id, 1, date(2022, 4, 1))
    return load_registry()


def _generate(conn, schema, tenant_id, config):
    pack = generate_pack(conn, schema, tenant_id, 1, "manufacturing", PERIOD_KEY,
                            config, generated_by="pytest")
    return write_report_artefact(conn, schema, pack)


def test_a_pack_generated_once_and_never_touched_has_no_edits(conn, tenant):
    tenant_id, schema = tenant
    config = _setup(conn, schema, tenant_id)
    _generate(conn, schema, tenant_id, config)

    edits = pack_edits(conn, schema, tenant_id, 1, PERIOD_KEY)
    assert edits.commentary_edits == 0
    assert edits.number_corrections == 0
    assert edits.total_edits == 0
    assert edits.generations == 1
    assert edits.signed is False


def test_each_commentary_edit_is_counted_once(conn, tenant):
    tenant_id, schema = tenant
    config = _setup(conn, schema, tenant_id)
    artefact = _generate(conn, schema, tenant_id, config)

    for text in ("- First draft.", "- Second draft.", "- Third draft."):
        edit_commentary(conn, schema, artefact.report_artefact_id, text, edited_by="pytest-analyst")

    edits = pack_edits(conn, schema, tenant_id, 1, PERIOD_KEY)
    assert edits.commentary_edits == 3
    # Editing commentary is not a number correction, even though it rewrites
    # the executive summary section on the artefact.
    assert edits.number_corrections == 0
    assert edits.total_edits == 3


def test_superseded_commentary_is_kept_not_overwritten(conn, tenant):
    """CLAUDE.md invariant 4. The count is the point of the table, but losing
    the prior wording to get it would trade one problem for another."""
    tenant_id, schema = tenant
    config = _setup(conn, schema, tenant_id)
    artefact = _generate(conn, schema, tenant_id, config)

    edit_commentary(conn, schema, artefact.report_artefact_id, "- First.", edited_by="analyst-a")
    edit_commentary(conn, schema, artefact.report_artefact_id, "- Second.", edited_by="analyst-b")

    with conn.cursor() as cur:
        cur.execute(
            f'SELECT edited_by, previous_commentary, new_commentary FROM "{schema}".pack_edit_event '
            f'WHERE report_artefact_id = %s ORDER BY pack_edit_event_id',
            (artefact.report_artefact_id,),
        )
        rows = cur.fetchall()

    assert [r[0] for r in rows] == ["analyst-a", "analyst-b"]
    assert rows[0][1] is None            # nothing was superseded by the first edit
    assert rows[0][2] == "- First."
    assert rows[1][1] == "- First."      # the superseded wording survives
    assert rows[1][2] == "- Second."


def test_an_edit_without_a_named_analyst_is_refused(conn, tenant):
    """corpus/02 section 8 counts edits 'made by the analyst'. An unattributed
    edit would make the count unauditable."""
    tenant_id, schema = tenant
    config = _setup(conn, schema, tenant_id)
    artefact = _generate(conn, schema, tenant_id, config)

    with pytest.raises(ValueError, match="named editor"):
        edit_commentary(conn, schema, artefact.report_artefact_id, "- Text.", edited_by="")


def test_regenerating_with_unchanged_numbers_is_not_a_correction(conn, tenant):
    """The analyst re-running the pack to check it is not a correction. Only a
    generation whose numbers differ from the previous one counts."""
    tenant_id, schema = tenant
    config = _setup(conn, schema, tenant_id)
    _generate(conn, schema, tenant_id, config)
    _generate(conn, schema, tenant_id, config)

    edits = pack_edits(conn, schema, tenant_id, 1, PERIOD_KEY)
    assert edits.generations == 2
    assert edits.number_corrections == 0


def test_regenerating_after_the_numbers_move_counts_one_correction(conn, tenant):
    """A restatement between two generations changes the pack's numbers. That
    is what corpus/02 section 8 calls a number correction."""
    tenant_id, schema = tenant
    config = _setup(conn, schema, tenant_id)
    _generate(conn, schema, tenant_id, config)

    # A real restatement: close one current GL row for the reported period.
    with conn.cursor() as cur:
        cur.execute(
            f'UPDATE "{schema}".fact_gl_entry SET is_current = false, valid_to = now() '
            f'WHERE fact_id = (SELECT fact_id FROM "{schema}".fact_gl_entry '
            f'                 WHERE period_key = %s AND is_current AND amount_base <> 0 LIMIT 1)',
            (PERIOD_KEY,),
        )
    conn.commit()

    _generate(conn, schema, tenant_id, config)

    edits = pack_edits(conn, schema, tenant_id, 1, PERIOD_KEY)
    assert edits.generations == 2
    assert edits.number_corrections == 1, (
        "a regeneration whose sections differ from the previous generation is a number correction"
    )


def test_the_count_covers_both_halves_and_survives_signing(conn, tenant):
    tenant_id, schema = tenant
    config = _setup(conn, schema, tenant_id)
    _generate(conn, schema, tenant_id, config)

    with conn.cursor() as cur:
        cur.execute(
            f'UPDATE "{schema}".fact_gl_entry SET is_current = false, valid_to = now() '
            f'WHERE fact_id = (SELECT fact_id FROM "{schema}".fact_gl_entry '
            f'                 WHERE period_key = %s AND is_current AND amount_base <> 0 LIMIT 1)',
            (PERIOD_KEY,),
        )
    conn.commit()
    second = _generate(conn, schema, tenant_id, config)
    edit_commentary(conn, schema, second.report_artefact_id, "- Explains the restatement.",
                       edited_by="pytest-analyst")
    sign_pack(conn, schema, second.report_artefact_id, reviewer="pytest-reviewer",
                 override_reason="pytest", override_by="pytest-reviewer")

    edits = pack_edits(conn, schema, tenant_id, 1, PERIOD_KEY)
    assert edits.commentary_edits == 1
    assert edits.number_corrections == 1
    assert edits.total_edits == 2
    assert edits.signed is True


def test_the_series_is_reported_per_period_with_no_target(conn, tenant):
    """corpus/11 section 4: tracked, not gated. Nothing in this path may
    compare the count to a threshold, because no threshold is declared."""
    tenant_id, schema = tenant
    config = _setup(conn, schema, tenant_id)
    _generate(conn, schema, tenant_id, config)

    series = edits_by_period(conn, schema, tenant_id, 1)
    assert [e.period_key for e in series] == [PERIOD_KEY]

    # The result carries counts and nothing that grades them. A field such as
    # `within_target` or `status` here would mean a threshold had been invented
    # (CLAUDE.md section 3.2), since corpus/11 section 4 declares none.
    fields = set(PackEdits.__dataclass_fields__)
    assert fields == {
        "period_key", "entity_id", "commentary_edits", "number_corrections",
        "generations", "signed",
    }, f"PackEdits grew a field that may encode a verdict: {fields}"
