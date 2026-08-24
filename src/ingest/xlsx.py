"""Read-only .xlsx reader for the fixed-schema templates in corpus/01.

Implements the Excel half of corpus/02 section 3 P0 #1: "Excel and CSV
against the templates in file 01 ... No parsing intelligence, no format
guessing. The analyst normalises anything that does not match." Everything
here is deliberately strict: a workbook either contains a sheet whose header
row is exactly a declared template, or it is rejected with a readable reason.
Nothing is coerced, inferred or repaired.

Why the standard library rather than openpyxl: an .xlsx is a zip of XML, the
subset the corpus templates use is small, and this keeps the runtime
dependency list unchanged (CLAUDE.md section 6, "boring on purpose"). This
module reads; it never writes.

Cell values are returned as **strings, verbatim from the file**, so that
`Decimal` in src/ingest/staging.py parses the number the customer actually
typed. Numeric cells are never routed through `float` -- that would round a
rupee figure on the way in, which is exactly the class of silent error
CLAUDE.md exists to prevent.

Three cell kinds need translation rather than pass-through, and each is
translated into the vocabulary corpus/01's own templates use:

  * date-formatted numbers  -> ISO `YYYY-MM-DD`, because Excel stores a date
    the customer typed as a serial number plus a display format, and
    staging's `_parse_date` accepts `%Y-%m-%d` only.
  * booleans                -> `Yes` / `No`, the literal values corpus/01
    uses in `is_active` and `is_cancelled`.
  * error cells             -> their text (`#DIV/0!`), passed through so
    staging quarantines the row instead of reading a zero.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from xml.etree import ElementTree as ET

MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

XLSX_MAGIC = b"PK\x03\x04"
XLS_MAGIC = b"\xd0\xcf\x11\xe0"  # OLE2: the pre-2007 binary .xls format

# Built-in numFmt ids that mean "this number is a date or a time"
# (ECMA-376 part 1, 18.8.30 numFmt, the reserved 0-163 range).
_BUILTIN_DATE_FMT_IDS = frozenset({14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47})


class XlsxError(Exception):
    """Raised when a workbook cannot be read at all."""


class XlsxTemplateError(XlsxError):
    """Raised when no sheet in the workbook carries the expected template header."""


@dataclass
class Sheet:
    name: str
    rows: list[list[str]]


def looks_like_xlsx(raw_bytes: bytes) -> bool:
    """True if these bytes are a zip container, i.e. a .xlsx/.xlsm workbook."""
    return raw_bytes[:4] == XLSX_MAGIC


def looks_like_legacy_xls(raw_bytes: bytes) -> bool:
    """True for the pre-2007 binary .xls format, which this reader does not support."""
    return raw_bytes[:4] == XLS_MAGIC


# ------------------------------------------------------------------ internals

def _col_index(cell_ref: str) -> int:
    """'A' -> 0, 'B' -> 1, 'AA' -> 26. Ignores the row part of the reference."""
    idx = 0
    for ch in cell_ref:
        if not ch.isalpha():
            break
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return idx - 1


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        blob = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []  # a workbook can legitimately have none
    root = ET.fromstring(blob)
    out = []
    for si in root.iter(MAIN_NS + "si"):
        # A shared string can be split across formatting runs; concatenate them.
        out.append("".join(t.text or "" for t in si.iter(MAIN_NS + "t")))
    return out


def _is_date_format_code(code: str) -> bool:
    """True if a numFmt format code renders a date or time.

    Quoted literals and escaped characters are stripped first, so a currency
    format like `"Rs"#,##0.00` is not mistaken for a date because of its 's'.
    """
    stripped, i, n = [], 0, len(code)
    while i < n:
        ch = code[i]
        if ch == '"':                       # quoted literal: skip to the closing quote
            i += 1
            while i < n and code[i] != '"':
                i += 1
        elif ch == "\\":                    # escaped single character
            i += 1
        elif ch == "[":                     # [Red], [$-409] and friends
            while i < n and code[i] != "]":
                i += 1
        else:
            stripped.append(ch)
        i += 1
    return any(ch in "ymdhs" for ch in "".join(stripped).lower())


def _date_styles(zf: zipfile.ZipFile) -> set[int]:
    """Style indices (the `s` attribute on a cell) whose number format is a date."""
    try:
        root = ET.fromstring(zf.read("xl/styles.xml"))
    except KeyError:
        return set()

    custom_date_ids = set()
    for fmt in root.iter(MAIN_NS + "numFmt"):
        fmt_id, code = fmt.get("numFmtId"), fmt.get("formatCode") or ""
        if fmt_id is not None and _is_date_format_code(code):
            custom_date_ids.add(int(fmt_id))

    date_style_indices = set()
    cell_xfs = root.find(MAIN_NS + "cellXfs")
    if cell_xfs is None:
        return date_style_indices
    for style_index, xf in enumerate(cell_xfs.findall(MAIN_NS + "xf")):
        num_fmt_id = xf.get("numFmtId")
        if num_fmt_id is None:
            continue
        num_fmt_id = int(num_fmt_id)
        if num_fmt_id in _BUILTIN_DATE_FMT_IDS or num_fmt_id in custom_date_ids:
            date_style_indices.add(style_index)
    return date_style_indices


def _serial_to_iso(serial_text: str, date_system_1904: bool) -> str:
    """Excel date serial -> 'YYYY-MM-DD'.

    Returns the original text unchanged if it is not a number this function can
    place on the calendar -- the caller passes it through so staging quarantines
    the row rather than this module inventing a date.
    """
    try:
        serial = float(serial_text)
    except ValueError:
        return serial_text

    days = int(serial)  # template date columns carry no time-of-day component
    if date_system_1904:
        return (date(1904, 1, 1) + timedelta(days=days)).isoformat()

    # The 1900 system deliberately contains a non-existent 29 Feb 1900 (serial
    # 60) for Lotus 1-2-3 compatibility, so the epoch differs either side of it.
    if days == 60:
        return serial_text  # 1900-02-29 never existed; refuse rather than guess
    if days < 60:
        if days < 1:
            return serial_text
        return (date(1899, 12, 31) + timedelta(days=days)).isoformat()
    return (date(1899, 12, 30) + timedelta(days=days)).isoformat()


def _cell_text(cell, shared: list[str], date_styles: set[int], date_system_1904: bool) -> str:
    cell_type = cell.get("t")

    if cell_type == "inlineStr":
        inline = cell.find(MAIN_NS + "is")
        if inline is None:
            return ""
        return "".join(t.text or "" for t in inline.iter(MAIN_NS + "t"))

    value_el = cell.find(MAIN_NS + "v")
    if value_el is None or value_el.text is None:
        return ""
    raw = value_el.text

    if cell_type == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError) as e:
            raise XlsxError(f"cell {cell.get('r')} references shared string {raw!r}, "
                             f"which is not in sharedStrings.xml") from e
    if cell_type == "b":
        # corpus/01 spells booleans 'Yes' / 'No' in is_active and is_cancelled.
        return "Yes" if raw == "1" else "No"
    if cell_type in ("e", "str"):
        return raw  # error text (#DIV/0!) or a formula's cached string result

    # Numeric, or a formula whose cached result is numeric. Emit the digits
    # verbatim -- never via float -- unless the cell is formatted as a date.
    style = cell.get("s")
    if style is not None and int(style) in date_styles:
        return _serial_to_iso(raw, date_system_1904)
    return raw


def read_sheets(raw_bytes: bytes) -> list[Sheet]:
    """Every worksheet in the workbook, in workbook order.

    Each row is a list of cell strings positioned by column, so index 0 is
    always column A and gaps are empty strings. Trailing empty cells are not
    padded; callers align against a known header width.
    """
    if looks_like_legacy_xls(raw_bytes):
        raise XlsxError(
            "this is a pre-2007 binary .xls file. Re-save it as .xlsx or export it as CSV; "
            "this reader does not decode the legacy binary format."
        )
    if not looks_like_xlsx(raw_bytes):
        raise XlsxError("not an .xlsx workbook (the file does not begin with a zip header)")

    try:
        zf = zipfile.ZipFile(_BytesIO(raw_bytes))
    except zipfile.BadZipFile as e:
        raise XlsxError(f"the workbook is not a readable zip container: {e}") from e

    with zf:
        try:
            workbook = ET.fromstring(zf.read("xl/workbook.xml"))
            rel_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        except KeyError as e:
            raise XlsxError(f"the workbook is missing a required part: {e}") from e
        except ET.ParseError as e:
            raise XlsxError(f"the workbook contains malformed XML: {e}") from e

        rels = {r.get("Id"): r.get("Target") for r in rel_root.iter(PKG_REL_NS + "Relationship")}
        shared = _shared_strings(zf)
        date_styles = _date_styles(zf)

        pr = workbook.find(MAIN_NS + "workbookPr")
        date_system_1904 = pr is not None and (pr.get("date1904") in ("1", "true"))

        sheets: list[Sheet] = []
        for sheet_el in workbook.iter(MAIN_NS + "sheet"):
            name = sheet_el.get("name") or ""
            target = rels.get(sheet_el.get(REL_NS + "id"))
            if target is None:
                continue
            # A relationship Target is package-relative to xl/ (e.g.
            # "worksheets/sheet1.xml", the common case) or an absolute
            # in-package path (e.g. "/xl/worksheets/sheet1.xml" -- openpyxl
            # writes this form). Strip any leading "/" first, then only
            # prepend "xl/" if the result doesn't already have it, so both
            # forms resolve to the same real zip member -- getting this
            # wrong doesn't raise, it silently skips every sheet (the
            # KeyError below is caught), which is a much worse failure mode
            # than a loud one.
            target = target.lstrip("/")
            path = target if target.startswith("xl/") else "xl/" + target
            try:
                ws = ET.fromstring(zf.read(path))
            except KeyError:
                continue  # a declared sheet with no part is not fatal; skip it
            except ET.ParseError as e:
                raise XlsxError(f"sheet {name!r} contains malformed XML: {e}") from e

            rows: list[list[str]] = []
            for row_el in ws.iter(MAIN_NS + "row"):
                row: list[str] = []
                for cell in row_el.iter(MAIN_NS + "c"):
                    ref = cell.get("r") or ""
                    idx = _col_index(ref) if ref else len(row)
                    if idx < 0:
                        idx = len(row)
                    while len(row) < idx:
                        row.append("")
                    text = _cell_text(cell, shared, date_styles, date_system_1904)
                    if len(row) == idx:
                        row.append(text)
                    else:
                        row[idx] = text
                rows.append(row)
            sheets.append(Sheet(name=name, rows=rows))

    return sheets


def _BytesIO(data: bytes):
    import io
    return io.BytesIO(data)


def _normalise(row: list[str]) -> list[str]:
    """Trim cells and drop trailing blanks, so a header row padded out by Excel
    still compares equal to the template it is."""
    trimmed = [(c or "").strip() for c in row]
    while trimmed and trimmed[-1] == "":
        trimmed.pop()
    return trimmed


def extract_template(raw_bytes: bytes, columns: list[str]) -> tuple[list[str], list[dict]]:
    """Find the sheet whose header row is exactly `columns` and return its rows.

    Returns `(header, records)` in the same shape as the CSV reader, so the
    schema hash computed downstream is identical for a template supplied as
    .xlsx and the same template supplied as CSV.

    The match is exact and order-sensitive by design. corpus/09 section 2.6
    requires schema drift to alarm rather than be adopted silently; in a
    workbook that surfaces as this function refusing to find its template,
    which is the same refusal, earlier.
    """
    sheets = read_sheets(raw_bytes)
    for sheet in sheets:
        for row_index, row in enumerate(sheet.rows):
            if _normalise(row) != columns:
                continue
            records = []
            for data_row in sheet.rows[row_index + 1:]:
                if not any((c or "").strip() for c in data_row):
                    continue  # a blank spacer row is not a record
                padded = list(data_row) + [""] * (len(columns) - len(data_row))
                records.append({col: (padded[i] or "").strip() for i, col in enumerate(columns)})
            return list(columns), records

    found = "; ".join(
        f"{s.name!r}: {_normalise(s.rows[0]) if s.rows else []}" for s in sheets
    ) or "(no sheets)"
    raise XlsxTemplateError(
        f"no sheet in this workbook has the expected header row {columns}. "
        f"First row of each sheet was -- {found}. "
        f"Per corpus/02 section 3 P0 #1 the file must match the template in corpus/01 exactly; "
        f"normalise it before uploading."
    )
