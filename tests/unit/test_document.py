"""The pack as a document -- corpus/02 section 3 P0 #10, corpus/08 sections 8 and 9.

The two properties worth testing are the two that could put a wrong number in
front of a board: the document must be deterministic (corpus/08 section 9's
byte-identical re-render has to survive the trip to HTML), and it must be
complete (every value in the artefact reaches the page).
"""
from __future__ import annotations

import re
from decimal import Decimal

from src.reports.charts import kpi_tile_chart, line_chart, table_chart, waterfall_chart
from src.reports.document import render_html


def _pack(**overrides) -> dict:
    pack = {
        "report_artefact_id": 7,
        "period_key": "2025-03",
        "profile": "manufacturing",
        "status": "signed",
        "generated_at": "2025-04-08T10:00:00+00:00",
        "generated_by": "analyst@example.com",
        "mapping_version_id": 1,
        "content_hash": "abc123",
        "reviewer": "cfo@example.com",
        "signed_at": "2025-04-09T09:00:00+00:00",
        "unmapped_value_inr": Decimal("18488350.26"),
        "sections": {
            "1_cover": {"period_key": "2025-03", "basis": "accrual",
                          "reconciliation_status": "reconciled"},
            "2_executive_summary": {"bullets_markdown": "- Revenue grew.\n- Margin held.",
                                       "written_by": "human"},
            "3_financial_summary": {"net_revenue": Decimal("52350000.00"),
                                       "ebitda": Decimal("4800000.00")},
            "8_statements": {"pnl": [{"line": "Gross revenue", "amount": Decimal("52350000.00")},
                                        {"line": "Returns", "amount": Decimal("0.00")}]},
        },
        "chart_specs": [],
    }
    pack.update(overrides)
    return pack


def test_the_same_artefact_renders_byte_identical_html():
    """corpus/08 section 9. If the document drifted between renders the pack
    would stop being reproducible at the last step."""
    assert render_html(_pack()) == render_html(_pack())


def test_nothing_in_the_document_reads_the_clock():
    """A timestamp of 'now' would break determinism silently -- the numbers
    would still be right, so nobody would notice until an audit."""
    html = render_html(_pack())
    # Only the artefact's own frozen timestamps may appear.
    for stamp in re.findall(r"\d{4}-\d{2}-\d{2}T[\d:+.-]+", html):
        assert stamp in ("2025-04-08T10:00:00+00:00", "2025-04-09T09:00:00+00:00"), stamp


def test_every_number_in_the_artefact_reaches_the_page():
    html = render_html(_pack())
    for expected in ("52,350,000.00", "4,800,000.00", "18,488,350.26"):
        assert expected in html, f"{expected} is in the artefact but not in the document"


def test_a_zero_line_is_printed_as_zero_and_a_missing_one_as_a_dash():
    """Zero and absent are different facts. Rendering both as blank would let a
    reader assume a line was nil when it was actually not computed."""
    html = render_html(_pack(sections={"3_financial_summary": {"returns": Decimal("0.00"),
                                                                   "cash_flow": None}}))
    assert "0.00" in html
    assert "—" in html


def test_commentary_renders_as_prose_not_as_a_field_dump():
    html = render_html(_pack())
    assert "<li>Revenue grew.</li>" in html
    assert "bullets_markdown" not in html


def test_an_unsigned_pack_is_labelled_draft():
    """corpus/08 section 10 gates signing. An unlabelled draft leaving the
    building is how an unreviewed number reaches a board."""
    assert "DRAFT" in render_html(_pack(status="draft"))
    assert "DRAFT" not in render_html(_pack(status="signed"))


def test_provenance_travels_with_the_document():
    """corpus/08 section 9: the pack carries what produced it."""
    html = render_html(_pack())
    for token in ("abc123", "analyst@example.com", "cfo@example.com"):
        assert token in html


def test_charts_are_drawn_from_specs_and_never_embedded_as_pictures():
    """corpus/08 section 8: store the specification, not the picture. An
    <img> or a data: URI here would mean a chart had been rasterised."""
    specs = [
        kpi_tile_chart("EBITDA", Decimal("4800000.00"), Decimal("120000.00"),
                          Decimal("-90000.00"), "INR"),
        line_chart("Net revenue", "net_revenue",
                      [("2025-01", Decimal("50000000")), ("2025-02", Decimal("51000000")),
                       ("2025-03", Decimal("52350000"))]),
        waterfall_chart("Margin bridge", Decimal("-300"),
                           [("RM price", Decimal("-210"), False), ("Mix", Decimal("-70"), False),
                            ("Unexplained", Decimal("-20"), True)]),
        table_chart("Top ledgers", ["Ledger", "Value"], [["Sales", Decimal("52350000.00")]]),
    ]
    html = render_html(_pack(chart_specs=specs))

    assert "<svg" in html
    assert "<img" not in html
    assert "data:image" not in html
    assert "base64" not in html
    for title in ("EBITDA", "Net revenue", "Margin bridge", "Top ledgers"):
        assert title in html


def test_a_residual_bar_is_drawn_distinctly():
    """CLAUDE.md invariant 15: a decomposition reports its gap. Drawing the
    residual in the same fill as a real driver would hide it in plain sight."""
    spec = waterfall_chart("Bridge", Decimal("-300"),
                              [("RM price", Decimal("-280"), False),
                               ("Unexplained", Decimal("-20"), True)])
    html = render_html(_pack(chart_specs=[spec]))
    fills = re.findall(r'<rect[^>]*fill="([^"]+)"', html)
    assert len(fills) == 2
    assert fills[0] != fills[1], "the residual bar uses the same fill as the driver bar"


def test_an_unknown_chart_type_falls_back_rather_than_disappearing():
    """corpus/08 section 8: 'anything the rules cannot handle falls back to a
    table, which is always a correct answer.'"""
    html = render_html(_pack(chart_specs=[
        {"chart_type": "sunburst", "title": "Unsupported", "value": Decimal("42.00")}
    ]))
    assert "Unsupported" in html
    assert "42.00" in html


def test_text_from_the_data_cannot_inject_markup():
    html = render_html(_pack(sections={
        "3_financial_summary": {"ledger": "<script>alert(1)</script>"}
    }))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_an_empty_list_says_none_rather_than_rendering_nothing():
    html = render_html(_pack(sections={"9_data_quality_appendix": {"open_exceptions": []}}))
    assert "None." in html


def test_the_document_is_self_contained():
    """No external stylesheet, script or image: the pack has to render the
    same on a board member's laptop with no network."""
    html = render_html(_pack())
    assert "http://" not in html
    assert "https://" not in html
    assert "<script" not in html
