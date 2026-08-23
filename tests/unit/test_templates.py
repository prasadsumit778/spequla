"""src/ingest/templates.py must agree with corpus/01, always.

The corpus is the authority on what a customer is asked to supply (CLAUDE.md
section 2), so the real workbook is the fixture here. If someone edits a
column name in templates.py to make a stubborn file load, this fails --
which is the point. Expected values are read from the corpus, never from
system output (CLAUDE.md section 9).
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from src.ingest.templates import ALL_TEMPLATES, BY_TYPE

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

WORKBOOK = Path(__file__).resolve().parents[2] / "corpus" / "01_SPEQULA_DATA_REQUEST_PACK.xlsx"


def _corpus_sheet_rows() -> dict[str, list[list[str]]]:
    """Read corpus/01 with an independent minimal parser.

    Deliberately not src/ingest/xlsx.py: a test that used the reader under
    test to build its own expected values would assert current behaviour
    rather than the corpus.
    """
    zf = zipfile.ZipFile(WORKBOOK)
    with zf:
        shared = [
            "".join(t.text or "" for t in si.iter(MAIN + "t"))
            for si in ET.fromstring(zf.read("xl/sharedStrings.xml")).iter(MAIN + "si")
        ]
        rels = {
            r.get("Id"): r.get("Target")
            for r in ET.fromstring(zf.read("xl/_rels/workbook.xml.rels")).iter(PKG_REL + "Relationship")
        }
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))

        def text(cell):
            if cell.get("t") == "s":
                v = cell.find(MAIN + "v")
                return shared[int(v.text)] if v is not None else ""
            if cell.get("t") == "inlineStr":
                return "".join(t.text or "" for t in cell.iter(MAIN + "t"))
            v = cell.find(MAIN + "v")
            return v.text if v is not None and v.text is not None else ""

        out: dict[str, list[list[str]]] = {}
        for sheet in workbook.iter(MAIN + "sheet"):
            target = rels[sheet.get(REL + "id")]
            path = target if target.startswith("xl/") else "xl/" + target.lstrip("/")
            ws = ET.fromstring(zf.read(path))
            out[sheet.get("name")] = [
                [text(c) for c in row.iter(MAIN + "c")] for row in ws.iter(MAIN + "row")
            ]
    return out


CORPUS_SHEETS = _corpus_sheet_rows()


@pytest.mark.parametrize("template", ALL_TEMPLATES, ids=lambda t: t.template_type)
def test_declared_columns_match_the_corpus_workbook(template):
    assert template.sheet_name in CORPUS_SHEETS, (
        f"corpus/01 has no sheet named {template.sheet_name!r}; "
        f"it has {sorted(CORPUS_SHEETS)}"
    )
    rows = CORPUS_SHEETS[template.sheet_name]
    declared = list(template.columns)

    # The header is whichever row in the corpus sheet carries these names. The
    # test does not hardcode "row 3", so a description line added or removed in
    # the workbook is not a spurious failure -- a renamed column still is.
    matches = [r for r in rows if [c.strip() for c in r if c.strip()] == declared]
    assert matches, (
        f"{template.sheet_name!r} in corpus/01 has no row equal to the columns declared in "
        f"src/ingest/templates.py.\n  declared: {declared}\n"
        f"  rows in the sheet: {[[c.strip() for c in r if c.strip()] for r in rows[:5]]}"
    )


def test_every_template_type_is_unique_and_indexed():
    types = [t.template_type for t in ALL_TEMPLATES]
    assert len(types) == len(set(types)), f"duplicate template_type: {types}"
    assert set(BY_TYPE) == set(types)


def test_template_types_match_the_values_the_pipeline_writes():
    """load_pipeline.py stamps app.source_file.template_type with these
    literals; templates.py is keyed on the same values so the two cannot
    drift apart silently."""
    pipeline = (Path(__file__).resolve().parents[2] / "src" / "ingest" / "load_pipeline.py").read_text()
    for template_type in BY_TYPE:
        assert f'"{template_type}"' in pipeline, (
            f"template_type {template_type!r} is declared in templates.py but never "
            f"written by load_pipeline.py"
        )
