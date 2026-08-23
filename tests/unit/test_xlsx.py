"""src/ingest/xlsx.py -- the Excel half of corpus/02 section 3 P0 #1.

Two things are being proved. First, that the reader decodes the parts of the
.xlsx format a customer's edited copy of corpus/01 can actually contain.
Second, and more important, that a template supplied as .xlsx and the same
template supplied as CSV produce byte-identical staged rows and the same
schema hash -- so the format a customer happens to send cannot change a
number.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from src.ingest import staging
from src.ingest.templates import COA, GL
from src.ingest.xlsx import (
    XlsxError,
    XlsxTemplateError,
    extract_template,
    looks_like_xlsx,
    read_sheets,
)
from tests.xlsx_fixture import build_xlsx, template_sheet

CORPUS_WORKBOOK = Path(__file__).resolve().parents[2] / "corpus" / "01_SPEQULA_DATA_REQUEST_PACK.xlsx"


# ------------------------------------------------------- the real corpus file

def test_reads_the_actual_corpus_data_request_pack():
    """The workbook customers are sent must be readable by the system that
    asks for it. corpus/01's GL sheet carries its header and one synthetic
    example row."""
    raw = CORPUS_WORKBOOK.read_bytes()
    header, rows = extract_template(raw, list(GL.columns))

    assert header == list(GL.columns)
    assert len(rows) == 1, "corpus/01's GL sheet holds exactly one example row"
    example = rows[0]
    # Values transcribed from corpus/01, sheet 'GL', row 4.
    assert example["voucher_no"] == "SI/26-27/0412"
    assert example["voucher_date"] == "2026-04-18"
    assert example["credit"] == "845000"
    assert example["debit"] == "0"
    assert example["is_cancelled"] == "No"


def test_picks_the_right_sheet_out_of_the_full_pack():
    """corpus/01 has fifteen sheets. Asking for the COA template must not
    return the GL one."""
    raw = CORPUS_WORKBOOK.read_bytes()
    _, coa_rows = extract_template(raw, list(COA.columns))
    assert coa_rows[0]["account_code"] == "4001"
    assert coa_rows[0]["account_name"] == "Sales - Domestic (North)"


# --------------------------------------------------------------- cell decoding

def test_header_is_found_below_the_corpus_preamble_rows():
    raw = build_xlsx({"COA": template_sheet(
        COA.columns,
        [["4001", "Sales", "Sales Accounts", "Income", "0", "Cr", "SALES-N", "Yes"]],
    )})
    header, rows = extract_template(raw, list(COA.columns))
    assert header == list(COA.columns)
    assert rows == [{
        "account_code": "4001", "account_name": "Sales", "parent_group": "Sales Accounts",
        "account_type": "Income", "opening_balance": "0", "opening_dr_cr": "Cr",
        "cost_centre": "SALES-N", "is_active": "Yes",
    }]


@pytest.mark.parametrize("serial,expected", [
    (1, "1900-01-01"),      # the 1900 epoch
    (59, "1900-02-28"),     # last real day before Excel's phantom 29 Feb 1900
    (61, "1900-03-01"),     # first day after it
    (25569, "1970-01-01"),  # the Unix epoch, the standard cross-check constant
])
def test_date_formatted_numbers_become_iso_dates(serial, expected):
    """Excel stores a typed date as a serial number plus a display format.
    staging's date parser accepts %Y-%m-%d only, so the conversion has to
    happen here or every real Excel file quarantines every row."""
    cols = ["voucher_date"]
    raw = build_xlsx({"S": [cols, [("d", serial)]]})
    _, rows = extract_template(raw, cols)
    assert rows[0]["voucher_date"] == expected


def test_excels_phantom_29_february_1900_is_refused_not_guessed():
    """Serial 60 is a date that never existed. Passing the raw number through
    sends the row to quarantine, which is correct; inventing 28 Feb or 1 Mar
    would be a silently wrong date."""
    cols = ["voucher_date"]
    raw = build_xlsx({"S": [cols, [("d", 60)]]})
    _, rows = extract_template(raw, cols)
    assert rows[0]["voucher_date"] == "60"


def test_1904_date_system_is_honoured():
    cols = ["voucher_date"]
    raw = build_xlsx({"S": [cols, [("d", 0)]]}, date_system_1904=True)
    _, rows = extract_template(raw, cols)
    assert rows[0]["voucher_date"] == "1904-01-01"


def test_a_currency_format_containing_s_is_not_read_as_a_date():
    """The fixture's rupee format code is "Rs"#,##0.00. Its 's' sits inside a
    quoted literal, so it must not make the cell a date."""
    cols = ["credit"]
    raw = build_xlsx({"S": [cols, [("currency", "845000")]]})
    _, rows = extract_template(raw, cols)
    assert rows[0]["credit"] == "845000"


def test_booleans_are_spelled_the_way_corpus_01_spells_them():
    """is_cancelled is read as cancelled only when it says 'yes'. A TRUE
    checkbox that arrived as 'TRUE' would silently read as not-cancelled."""
    cols = ["is_cancelled"]
    assert extract_template(build_xlsx({"S": [cols, [("b", True)]]}), cols)[1][0]["is_cancelled"] == "Yes"
    assert extract_template(build_xlsx({"S": [cols, [("b", False)]]}), cols)[1][0]["is_cancelled"] == "No"


def test_error_cells_pass_through_so_the_row_is_quarantined():
    cols = ["debit"]
    raw = build_xlsx({"S": [cols, [("e", "#DIV/0!")]]})
    _, rows = extract_template(raw, cols)
    assert rows[0]["debit"] == "#DIV/0!"
    # and staging refuses to read it as a number
    assert staging._parse_decimal("#DIV/0!") is None


def test_large_numbers_keep_every_digit():
    """Money must not round-trip through float on the way in (CLAUDE.md
    section 8). 12345678901234567 is not representable as a float64."""
    cols = ["closing_balance"]
    raw = build_xlsx({"S": [cols, [("n", "12345678901234567")]]})
    _, rows = extract_template(raw, cols)
    assert rows[0]["closing_balance"] == "12345678901234567"


def test_gaps_in_a_row_keep_later_columns_aligned():
    """A row where the middle cell is empty is written by Excel with that cell
    simply absent. Reading positionally is what stops every later value
    shifting one column left."""
    cols = ["a", "b", "c"]
    raw = build_xlsx({"S": [cols, ["1", None, "3"]]})
    _, rows = extract_template(raw, cols)
    assert rows[0] == {"a": "1", "b": "", "c": "3"}


def test_inline_strings_are_read():
    cols = ["account_name"]
    raw = build_xlsx({"S": [cols, [("inline", "Sales - Retail (Delhi)")]]})
    _, rows = extract_template(raw, cols)
    assert rows[0]["account_name"] == "Sales - Retail (Delhi)"


def test_blank_spacer_rows_are_not_records():
    cols = ["account_code"]
    raw = build_xlsx({"S": [cols, ["4001"], ["", ""], ["4002"]]})
    _, rows = extract_template(raw, cols)
    assert [r["account_code"] for r in rows] == ["4001", "4002"]


def test_read_sheets_returns_every_sheet_in_order():
    raw = build_xlsx({"First": [["a"]], "Second": [["b"]]})
    assert [s.name for s in read_sheets(raw)] == ["First", "Second"]


# ------------------------------------------------------------- loud rejections

def test_a_workbook_without_the_template_is_refused_with_the_expected_columns():
    raw = build_xlsx({"Sheet1": [["date", "amount"], ["2026-04-18", "100"]]})
    with pytest.raises(XlsxTemplateError) as e:
        extract_template(raw, list(GL.columns))
    assert "voucher_no" in str(e.value)
    assert "corpus/01" in str(e.value)


def test_a_renamed_column_is_refused_rather_than_adopted():
    """corpus/09 requires schema drift to alarm, never to be adopted silently."""
    drifted = list(COA.columns)
    drifted[1] = "ledger_name"  # was account_name
    raw = build_xlsx({"COA": template_sheet(drifted, [["4001", "Sales", "", "", "", "", "", ""]])})
    with pytest.raises(XlsxTemplateError):
        extract_template(raw, list(COA.columns))


def test_legacy_binary_xls_is_named_rather_than_garbled():
    with pytest.raises(XlsxError) as e:
        read_sheets(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32)
    assert ".xls" in str(e.value)


def test_a_file_that_is_not_a_workbook_is_refused():
    with pytest.raises(XlsxError):
        read_sheets(b"voucher_no,voucher_type\nSI/1,Sales\n")


def test_a_truncated_zip_is_refused():
    with pytest.raises(XlsxError):
        read_sheets(b"PK\x03\x04" + b"\x00" * 64)


def test_a_zip_that_is_not_a_workbook_is_refused():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "not a workbook")
    with pytest.raises(XlsxError) as e:
        read_sheets(buf.getvalue())
    assert "missing a required part" in str(e.value)


def test_looks_like_xlsx_reads_the_bytes_not_the_name():
    assert looks_like_xlsx(b"PK\x03\x04rest")
    assert not looks_like_xlsx(b"account_code,account_name\n")


# ------------------------------------------------- the property that matters

def _gl_rows():
    return [
        ["SI/26-27/0412", "Sales", "2026-04-18", "2026-04-19", "1", "4001",
         "Sales - Domestic (North)", "0", "845000", "Inv 412 Acme", "SALES-N", "Acme Traders", "No"],
        ["SI/26-27/0412", "Sales", "2026-04-18", "2026-04-19", "2", "1201",
         "Sundry Debtors", "845000", "0", "Inv 412 Acme", "SALES-N", "Acme Traders", "No"],
    ]


def _gl_csv() -> bytes:
    lines = [",".join(GL.columns)] + [",".join(r) for r in _gl_rows()]
    return ("\n".join(lines) + "\n").encode()


def test_csv_and_xlsx_stage_to_identical_rows_and_schema_hash():
    """The same GL, sent two ways, must produce the same staged facts. If this
    ever diverges, the format a customer chose changed a number."""
    from_csv = staging.stage_gl(_gl_csv())
    from_xlsx = staging.stage_gl(build_xlsx({"GL": template_sheet(GL.columns, _gl_rows())}))

    assert from_csv.valid_rows == from_xlsx.valid_rows
    assert from_csv.schema_hash == from_xlsx.schema_hash
    assert [q.reason for q in from_csv.quarantined] == [q.reason for q in from_xlsx.quarantined]
    assert len(from_xlsx.valid_rows) == 2


def test_xlsx_dates_typed_as_real_excel_dates_stage_identically():
    """A customer who types 18/04/2026 into Excel produces a serial, not text.
    That file must stage the same as one holding the ISO text."""
    text_rows = _gl_rows()
    serial_rows = [list(r) for r in _gl_rows()]
    for r in serial_rows:
        r[2] = ("d", 46130)   # voucher_date
        r[3] = ("d", 46131)   # entry_date

    typed = staging.stage_gl(build_xlsx({"GL": template_sheet(GL.columns, serial_rows)}))
    assert typed.quarantined == [], [q.reason for q in typed.quarantined]
    assert typed.valid_rows[0]["voucher_date"].isoformat() == "2026-04-18"
    assert typed.valid_rows[0]["entry_date"].isoformat() == "2026-04-19"

    as_text = staging.stage_gl(build_xlsx({"GL": template_sheet(GL.columns, text_rows)}))
    assert typed.valid_rows == as_text.valid_rows


def test_every_template_stages_from_xlsx():
    """Each of the six streams accepts a workbook, not just GL."""
    coa = staging.stage_coa(build_xlsx({"COA": template_sheet(
        COA.columns, [["4001", "Sales", "Sales Accounts", "Income", "0", "Cr", "", "Yes"]])}))
    assert len(coa.valid_rows) == 1 and coa.valid_rows[0]["account_code"] == "4001"
