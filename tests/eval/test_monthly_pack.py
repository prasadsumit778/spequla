"""Sprint 5 acceptance criteria, corpus/08 section 11 and corpus/12's
Sprint 5 row:

  - re-rendering a signed pack reproduces it byte-identically
  - the pack cannot generate [sign] with an open blocking exception,
    without a logged override
  - section 9 (data quality appendix) is present in every generated pack
  - owner remuneration and related party charges appear as separate lines
  - every chart is a stored spec (a dict), never an image

Needs live Postgres -- skips cleanly otherwise, same posture as every other
sprint's acceptance test in this repo.
"""
from __future__ import annotations

from datetime import date

from src.config.loader import load_registry
from src.quality.checks import ExceptionCandidate, write_exceptions
from src.reports.pack import generate_pack
from src.reports.signoff import SignOffBlocked, edit_commentary, render_pack, sign_pack, write_report_artefact
from tests.helpers import ingest_manufacturer, run_and_freeze_mapping

PERIOD_KEY = "2024-06"


def _setup(conn, schema, tenant_id, entity_id=1):
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    run_and_freeze_mapping(conn, schema, tenant_id, entity_id, effective_from=date(2022, 4, 1))
    return load_registry()


def test_section_9_present_and_pack_generates(conn, tenant):
    tenant_id, schema = tenant
    config = _setup(conn, schema, tenant_id)

    pack = generate_pack(conn, schema, tenant_id, 1, "manufacturing", PERIOD_KEY, config, generated_by="pytest")
    assert "9_data_quality_appendix" in pack["sections"]
    for i in range(1, 9):
        assert any(k.startswith(f"{i}_") for k in pack["sections"]), f"section {i} missing"

    artefact = write_report_artefact(conn, schema, pack)
    assert artefact.status == "draft"
    assert artefact.report_artefact_id > 0


def test_owner_remuneration_and_related_party_are_separate_lines_in_the_pack(conn, tenant):
    tenant_id, schema = tenant
    config = _setup(conn, schema, tenant_id)
    pack = generate_pack(conn, schema, tenant_id, 1, "manufacturing", PERIOD_KEY, config, generated_by="pytest")
    pnl_lines = pack["sections"]["8_statements"]["pnl"]["current"]["lines"]
    assert "Owner remuneration" in pnl_lines
    assert "Related party charges" in pnl_lines
    assert "Owner remuneration" != "Related party charges"


def test_every_chart_is_a_stored_spec_not_an_image(conn, tenant):
    tenant_id, schema = tenant
    config = _setup(conn, schema, tenant_id)
    pack = generate_pack(conn, schema, tenant_id, 1, "manufacturing", PERIOD_KEY, config, generated_by="pytest")
    assert len(pack["chart_specs"]) > 0
    for spec in pack["chart_specs"]:
        assert isinstance(spec, dict)
        assert "chart_type" in spec
        assert spec["chart_type"] in ("line", "kpi_tile", "waterfall", "table")


def test_cannot_sign_with_open_blocking_exception_unless_overridden(conn, tenant):
    tenant_id, schema = tenant
    config = _setup(conn, schema, tenant_id)
    pack = generate_pack(conn, schema, tenant_id, 1, "manufacturing", PERIOD_KEY, config, generated_by="pytest")
    artefact = write_report_artefact(conn, schema, pack)

    write_exceptions(conn, schema, tenant_id, 1, [
        ExceptionCandidate("reconciliation", "blocking", "test-injected blocking exception",
                              period_key=PERIOD_KEY, value_inr=None),
    ])
    conn.commit()

    try:
        sign_pack(conn, schema, artefact.report_artefact_id, reviewer="pytest-reviewer")
        assert False, "sign_pack should have refused"
    except SignOffBlocked:
        pass

    signed = sign_pack(conn, schema, artefact.report_artefact_id, reviewer="pytest-reviewer",
                          override_reason="test override -- known synthetic exception", override_by="pytest-founder")
    assert signed.status == "signed"
    assert signed.sections["9_data_quality_appendix"]["signoff_override"]["reason"] == \
        "test override -- known synthetic exception"
    assert signed.sections["9_data_quality_appendix"]["signoff_override"]["by"] == "pytest-founder"


def test_rerender_is_byte_identical_even_after_the_underlying_data_changes(conn, tenant):
    tenant_id, schema = tenant
    config = _setup(conn, schema, tenant_id)
    pack = generate_pack(conn, schema, tenant_id, 1, "manufacturing", PERIOD_KEY, config, generated_by="pytest")
    artefact = write_report_artefact(conn, schema, pack)
    edited = edit_commentary(conn, schema, artefact.report_artefact_id,
                                "- Revenue grew month over month.\n- Margins held steady.")
    signed = sign_pack(conn, schema, edited.report_artefact_id, reviewer="pytest-reviewer")

    import json
    render_1 = render_pack(conn, schema, signed.report_artefact_id)

    # Mutate live GL data for the reported period -- a real restatement.
    with conn.cursor() as cur:
        cur.execute(
            f'UPDATE "{schema}".fact_gl_entry SET amount_base = amount_base + 999999 '
            f'WHERE fact_id = ('
            f'  SELECT fact_id FROM "{schema}".fact_gl_entry '
            f'  WHERE tenant_id = %s AND period_key = %s AND is_current LIMIT 1'
            f')',
            (tenant_id, PERIOD_KEY),
        )
    conn.commit()

    render_2 = render_pack(conn, schema, signed.report_artefact_id)

    assert render_1["content_hash"] == render_2["content_hash"]
    assert json.dumps(render_1["sections"], sort_keys=True) == json.dumps(render_2["sections"], sort_keys=True)
    assert render_2["sections"]["8_statements"]["pnl"]["current"] == render_1["sections"]["8_statements"]["pnl"]["current"]
