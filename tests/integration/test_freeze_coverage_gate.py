"""corpus/12 sprint 2 test: the coverage gate blocks statements below
threshold. Uses the real synthetic manufacturer, whose ~330-ledger long tail
is deliberately unmapped (corpus/06 section 4.4) but small in value -- so
freeze should PASS for it; a hand-built company with a large unmapped ledger
should FAIL."""
from datetime import date
from decimal import Decimal

from src.ingest.load_pipeline import load_coa_file, load_gl_file
from src.mapping.review import freeze_mapping_version
from tests.helpers import GL_FIELDS, COA_FIELDS, ingest_manufacturer, run_and_freeze_mapping, write_csv_bytes


def test_synthetic_manufacturer_clears_the_coverage_gate(conn, tenant):
    """The long tail is realistic-small (corpus/11 section 2.1: 'a long tail
    carrying almost none'), so total unmapped value should stay comfortably
    under the 2% corpus/06a coverage gate even though ~330 of 400 ledgers
    have no rule and land in suspense."""
    tenant_id, schema = tenant
    ingest_manufacturer(conn, schema, tenant_id, entity_id=1)
    version_id, summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, 1, date(2023, 4, 1))
    assert freeze.passed, freeze.reason
    assert freeze.coverage_pct >= Decimal("0.98")


def test_a_large_unmapped_ledger_blocks_the_freeze_gate(conn, tenant):
    """Hand-built minimal company: one large, deliberately unrulable ledger
    dominates period value, so coverage must fail."""
    tenant_id, schema = tenant
    entity_id = 1

    coa_rows = [
        {"account_code": "1", "account_name": "Sales - Direct (North)", "parent_group": "Sales Accounts",
          "account_type": "Income", "opening_balance": "0", "opening_dr_cr": "Cr", "cost_centre": "", "is_active": "Yes"},
        {"account_code": "2", "account_name": "Sundry Debtors", "parent_group": "Sundry Debtors",
          "account_type": "Asset", "opening_balance": "0", "opening_dr_cr": "Dr", "cost_centre": "", "is_active": "Yes"},
        {"account_code": "3", "account_name": "Completely Unrulable Ledger XYZ", "parent_group": "Misc",
          "account_type": "Expense", "opening_balance": "0", "opening_dr_cr": "Dr", "cost_centre": "", "is_active": "Yes"},
        {"account_code": "4", "account_name": "Cash and Bank - HDFC Current A/c", "parent_group": "Bank Accounts",
          "account_type": "Asset", "opening_balance": "0", "opening_dr_cr": "Dr", "cost_centre": "", "is_active": "Yes"},
    ]
    r = load_coa_file(conn, schema, tenant_id, entity_id, "COA.csv", write_csv_bytes(COA_FIELDS, coa_rows), "pytest")
    conn.commit()
    assert r.status == "succeeded"

    gl_rows = [
        {"voucher_no": "SI/1", "voucher_type": "Sales", "voucher_date": "2023-04-05", "entry_date": "2023-04-05",
          "line_no": 1, "account_code": "1", "account_name": "Sales - Direct (North)", "debit": "0", "credit": "100000",
          "narration": "", "cost_centre": "", "party_name": "", "is_cancelled": "No"},
        {"voucher_no": "SI/1", "voucher_type": "Sales", "voucher_date": "2023-04-05", "entry_date": "2023-04-05",
          "line_no": 2, "account_code": "2", "account_name": "Sundry Debtors", "debit": "100000", "credit": "0",
          "narration": "", "cost_centre": "", "party_name": "", "is_cancelled": "No"},
        # This ledger carries MORE value than the mapped revenue ledger, and
        # has no rule -- coverage should drop well below 98%.
        {"voucher_no": "JV/1", "voucher_type": "Journal", "voucher_date": "2023-04-06", "entry_date": "2023-04-06",
          "line_no": 1, "account_code": "3", "account_name": "Completely Unrulable Ledger XYZ", "debit": "500000",
          "credit": "0", "narration": "", "cost_centre": "", "party_name": "", "is_cancelled": "No"},
        {"voucher_no": "JV/1", "voucher_type": "Journal", "voucher_date": "2023-04-06", "entry_date": "2023-04-06",
          "line_no": 2, "account_code": "4", "account_name": "Cash and Bank - HDFC Current A/c", "debit": "0",
          "credit": "500000", "narration": "", "cost_centre": "", "party_name": "", "is_cancelled": "No"},
    ]
    r = load_gl_file(conn, schema, tenant_id, entity_id, "GL_2023-04.csv", write_csv_bytes(GL_FIELDS, gl_rows), "pytest")
    conn.commit()
    assert r.status == "succeeded"

    version_id, summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id, date(2023, 4, 1))
    assert freeze.passed is False
    assert "coverage" in freeze.reason.lower()
