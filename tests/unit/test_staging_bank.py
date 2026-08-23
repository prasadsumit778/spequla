"""Tests for Bank staging, corpus/01 Bank template + fact_bank_txn's sign
convention (money in positive, money out negative)."""
from datetime import date
from decimal import Decimal

from src.ingest.staging import stage_bank

BANK_CSV = (
    "bank_account_ref,txn_date,value_date,description,reference,debit,credit,running_balance\n"
    "HDFC-4471,2026-04-22,2026-04-22,NEFT CR ACME TRADERS PVT LTD HDFC0000123,UTRN2604220098,0,997100,24318450\n"
    "HDFC-4471,2026-04-23,2026-04-23,NEFT DR NORTHERN STEEL SUPPLIERS,UTRN2604230011,250000,0,24068450\n"
)


def test_stage_bank_basic_and_sign_convention():
    result = stage_bank(BANK_CSV.encode())
    assert len(result.quarantined) == 0
    assert len(result.valid_rows) == 2
    credit_line, debit_line = result.valid_rows
    assert credit_line["amount_base"] == Decimal("997100")    # money in, positive
    assert debit_line["amount_base"] == Decimal("-250000")     # money out, negative


def test_stage_bank_quarantines_both_debit_and_credit():
    csv_text = (
        "bank_account_ref,txn_date,value_date,description,reference,debit,credit,running_balance\n"
        "HDFC-4471,2026-04-22,2026-04-22,Bad line,REF1,100,100,0\n"
    )
    result = stage_bank(csv_text.encode())
    assert len(result.valid_rows) == 0
    assert "both debit and credit" in result.quarantined[0].reason


def test_stage_bank_row_hash_stable():
    r1 = stage_bank(BANK_CSV.encode())
    r2 = stage_bank(BANK_CSV.encode())
    assert r1.valid_rows[0]["row_hash"] == r2.valid_rows[0]["row_hash"]


def test_stage_bank_dedup_within_same_file():
    csv_text = BANK_CSV + BANK_CSV.splitlines()[1] + "\n"
    result = stage_bank(csv_text.encode())
    assert len(result.valid_rows) == 2
    assert any("duplicate" in q.reason for q in result.quarantined)
