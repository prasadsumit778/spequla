"""Tests for typed staging, corpus/04 section 5 and corpus/09 section 2.2."""
from datetime import date
from decimal import Decimal

from src.ingest.staging import stage_coa, stage_gl, stage_store_master, stage_tb

COA_CSV = (
    "account_code,account_name,parent_group,account_type,opening_balance,opening_dr_cr,cost_centre,is_active\n"
    "4001,Sales - Retail (Delhi),Sales Accounts,Income,0,Cr,SALES-N,Yes\n"
)

TB_CSV = (
    "period_end,account_code,account_name,opening_balance,debit_movement,credit_movement,closing_balance\n"
    "2026-04-30,4001,Sales - Domestic (North),-18450000,220000,34120000,-52350000\n"
)

GL_CSV = (
    "voucher_no,voucher_type,voucher_date,entry_date,line_no,account_code,account_name,debit,credit,"
    "narration,cost_centre,party_name,is_cancelled\n"
    "SI/26-27/0412,Sales,2026-04-18,2026-04-19,1,4001,Sales - Domestic (North),0,845000,"
    "Inv 412 Acme Traders,SALES-N,Acme Traders Pvt Ltd,No\n"
    "SI/26-27/0412,Sales,2026-04-18,2026-04-19,2,1200,Sundry Debtors,845000,0,"
    "Inv 412 Acme Traders,SALES-N,Acme Traders Pvt Ltd,No\n"
)


def test_stage_coa_basic():
    result = stage_coa(COA_CSV.encode())
    assert len(result.quarantined) == 0
    assert result.valid_rows[0]["account_name"] == "Sales - Retail (Delhi)"
    assert result.valid_rows[0]["opening_balance"] == Decimal("0")


def test_stage_tb_basic():
    result = stage_tb(TB_CSV.encode())
    assert len(result.quarantined) == 0
    row = result.valid_rows[0]
    assert row["period_end"] == date(2026, 4, 30)
    assert row["closing_balance"] == Decimal("-52350000")


def test_stage_gl_basic_and_sign_convention():
    result = stage_gl(GL_CSV.encode())
    assert len(result.quarantined) == 0
    assert len(result.valid_rows) == 2
    credit_line = result.valid_rows[0]
    debit_line = result.valid_rows[1]
    assert credit_line["amount_base"] == Decimal("-845000")  # Cr negative, corpus/03 section 1
    assert debit_line["amount_base"] == Decimal("845000")    # Dr positive


STORE_MASTER_CSV = (
    "store_code,store_name,store_format,city,state,site_type,area_sqft,opening_date,closure_date,status\n"
    "COCO-001,Malhar - Delhi COCO-001,COCO,Delhi,Delhi,mall,1200,2023-06-15,,active\n"
)


def test_stage_store_master_basic():
    result = stage_store_master(STORE_MASTER_CSV.encode())
    assert len(result.quarantined) == 0
    row = result.valid_rows[0]
    assert row["store_code"] == "COCO-001"
    assert row["store_format"] == "COCO"
    assert row["opening_date"] == date(2023, 6, 15)
    assert row["closure_date"] is None
    assert row["area_sqft"] == Decimal("1200")


def test_stage_store_master_quarantines_missing_opening_date():
    bad = ("store_code,store_name,store_format,city,state,site_type,area_sqft,opening_date,closure_date,status\n"
           "COCO-002,Malhar - Pune COCO-002,COCO,Pune,Maharashtra,mall,900,,,active\n")
    result = stage_store_master(bad.encode())
    assert len(result.valid_rows) == 0
    assert len(result.quarantined) == 1


def test_stage_store_master_quarantines_duplicate_store_code():
    dup = STORE_MASTER_CSV + "COCO-001,Malhar - Delhi COCO-001 dup,COCO,Delhi,Delhi,mall,1200,2023-06-15,,active\n"
    result = stage_store_master(dup.encode())
    assert len(result.valid_rows) == 1
    assert len(result.quarantined) == 1


def test_stage_gl_quarantines_both_debit_and_credit_populated():
    bad = GL_CSV.replace("0,845000,\nSI", "500,845000,\nSI")  # won't match; construct directly instead
    csv_text = (
        "voucher_no,voucher_type,voucher_date,entry_date,line_no,account_code,account_name,debit,credit,"
        "narration,cost_centre,party_name,is_cancelled\n"
        "JV/1,Journal,2026-04-18,2026-04-18,1,4001,Some Ledger,100,100,Bad line,,,No\n"
    )
    result = stage_gl(csv_text.encode())
    assert len(result.valid_rows) == 0
    assert len(result.quarantined) == 1
    assert "both debit and credit" in result.quarantined[0].reason


def test_stage_gl_quarantines_unparseable_number():
    csv_text = (
        "voucher_no,voucher_type,voucher_date,entry_date,line_no,account_code,account_name,debit,credit,"
        "narration,cost_centre,party_name,is_cancelled\n"
        "JV/2,Journal,2026-04-18,2026-04-18,1,4001,Some Ledger,#DIV/0!,,Bad line,,,No\n"
    )
    result = stage_gl(csv_text.encode())
    assert len(result.valid_rows) == 0
    assert "not a valid number" in result.quarantined[0].reason


def test_stage_gl_quarantines_implausible_future_date():
    csv_text = (
        "voucher_no,voucher_type,voucher_date,entry_date,line_no,account_code,account_name,debit,credit,"
        "narration,cost_centre,party_name,is_cancelled\n"
        "JV/3,Journal,2099-04-18,2099-04-18,1,4001,Some Ledger,100,0,Future line,,,No\n"
    )
    result = stage_gl(csv_text.encode())
    assert len(result.valid_rows) == 0
    assert "plausible range" in result.quarantined[0].reason


def test_stage_gl_computes_stable_row_hash():
    result = stage_gl(GL_CSV.encode())
    h1 = result.valid_rows[0]["row_hash"]
    result2 = stage_gl(GL_CSV.encode())
    h2 = result2.valid_rows[0]["row_hash"]
    assert h1 == h2


def test_stage_gl_dedup_within_same_file():
    csv_text = GL_CSV + GL_CSV.splitlines()[1] + "\n"  # duplicate the first data line
    result = stage_gl(csv_text.encode())
    assert len(result.valid_rows) == 2  # the exact duplicate is quarantined
    assert any("duplicate" in q.reason for q in result.quarantined)
