"""Build minimal .xlsx bytes in memory, for testing src/ingest/xlsx.py.

Writing the fixture by hand rather than reusing the reader keeps the test
honest: if the reader's idea of the format drifts, the fixture does not drift
with it. The subset emitted here (shared strings, numbers, date-styled
numbers, booleans, error cells, sparse rows) is exactly the subset the
corpus/01 templates and a customer's edited copy of them can contain.

Cell spellings accepted per cell:
    "text"              -> a shared string
    ("n", "845000")     -> a number, written verbatim
    ("d", 46130)        -> a number carrying a date number format
    ("b", True)         -> a boolean
    ("e", "#DIV/0!")    -> an error cell
    ("inline", "text")  -> an inline (not shared) string
    None                -> the cell is omitted entirely, leaving a gap
"""
from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

STYLES = """<?xml version="1.0" encoding="UTF-8"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="&quot;Rs&quot;#,##0.00"/></numFmts>
<cellXfs count="3">
<xf numFmtId="0"/>
<xf numFmtId="14"/>
<xf numFmtId="164"/>
</cellXfs>
</styleSheet>"""
# style index 0 = General, 1 = built-in date (numFmtId 14), 2 = a rupee currency
# format whose format code contains an 's', to prove it is not read as a date.

DATE_STYLE = 1
CURRENCY_STYLE = 2


def _col_letter(idx: int) -> str:
    letters = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def build_xlsx(sheets: dict[str, list[list]], date_system_1904: bool = False) -> bytes:
    """sheets: {sheet_name: [[cell, cell, ...], ...]} -> .xlsx bytes."""
    shared: list[str] = []
    shared_index: dict[str, int] = {}

    def share(text: str) -> int:
        if text not in shared_index:
            shared_index[text] = len(shared)
            shared.append(text)
        return shared_index[text]

    sheet_xml: list[str] = []
    for rows in sheets.values():
        body = []
        for r, row in enumerate(rows, start=1):
            cells = []
            for c, cell in enumerate(row):
                if cell is None:
                    continue
                ref = f"{_col_letter(c)}{r}"
                if isinstance(cell, tuple):
                    kind, value = cell
                    if kind == "n":
                        cells.append(f'<c r="{ref}"><v>{escape(str(value))}</v></c>')
                    elif kind == "d":
                        cells.append(f'<c r="{ref}" s="{DATE_STYLE}"><v>{escape(str(value))}</v></c>')
                    elif kind == "currency":
                        cells.append(f'<c r="{ref}" s="{CURRENCY_STYLE}"><v>{escape(str(value))}</v></c>')
                    elif kind == "b":
                        cells.append(f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>')
                    elif kind == "e":
                        cells.append(f'<c r="{ref}" t="e"><v>{escape(str(value))}</v></c>')
                    elif kind == "inline":
                        cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
                    else:
                        raise ValueError(f"unknown cell kind {kind!r}")
                else:
                    cells.append(f'<c r="{ref}" t="s"><v>{share(str(cell))}</v></c>')
            body.append(f'<row r="{r}">{"".join(cells)}</row>')
        sheet_xml.append(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(body)}</sheetData></worksheet>'
        )

    pr = '<workbookPr date1904="1"/>' if date_system_1904 else ""
    sheet_tags = "".join(
        f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
        for i, name in enumerate(sheets, start=1)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'{pr}<sheets>{sheet_tags}</sheets></workbook>'
    )
    rel_tags = "".join(
        f'<Relationship Id="rId{i}" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{i}.xml"/>'
        for i in range(1, len(sheets) + 1)
    )
    n = len(sheets)
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{rel_tags}'
        f'<Relationship Id="rId{n + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        f'<Relationship Id="rId{n + 2}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" '
        'Target="sharedStrings.xml"/>'
        '</Relationships>'
    )
    si = "".join(f"<si><t>{escape(s)}</t></si>" for s in shared)
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(shared)}" uniqueCount="{len(shared)}">{si}</sst>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", ROOT_RELS)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/styles.xml", STYLES)
        zf.writestr("xl/sharedStrings.xml", shared_xml)
        for i, xml in enumerate(sheet_xml, start=1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", xml)
    return buf.getvalue()


def template_sheet(columns, data_rows, with_preamble: bool = True) -> list[list]:
    """A sheet laid out the way corpus/01 lays one out: description, note,
    header, then data."""
    rows: list[list] = []
    if with_preamble:
        rows.append(["Every ledger in the books, including inactive ones."])
        rows.append(["Row 3 is a synthetic example. Delete it and paste your data."])
    rows.append(list(columns))
    rows.extend(data_rows)
    return rows
