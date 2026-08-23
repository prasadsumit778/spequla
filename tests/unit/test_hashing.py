"""Tests for row_hash, corpus/04 section 1.2 / corpus/09 section 2.3."""
from src.ingest.hashing import compute_row_hash

BASE_ROW = {
    "voucher_no": "SI/23-24/0001", "voucher_type": "Sales", "voucher_date": "2023-04-18",
    "entry_date": "2023-04-18", "line_no": 1, "account_code": "4001", "debit": "0",
    "credit": "845000.00", "narration": "Inv 412 Acme Traders", "cost_centre": "SALES-N",
    "party_name": "Acme Traders Pvt Ltd", "is_cancelled": "No",
}


def test_identical_rows_hash_identically():
    assert compute_row_hash(dict(BASE_ROW)) == compute_row_hash(dict(BASE_ROW))


def test_different_amount_hashes_differently():
    changed = dict(BASE_ROW, credit="845001.00")
    assert compute_row_hash(BASE_ROW) != compute_row_hash(changed)


def test_lineage_fields_do_not_affect_hash():
    # load_run_id / tenant_id / source_record_id are not business columns and
    # are never passed to compute_row_hash, but even if present in the dict
    # they must not change the hash (only fields in the whitelist matter).
    with_lineage = dict(BASE_ROW, tenant_id="abc-123", load_run_id=99, source_record_id="XYZ")
    assert compute_row_hash(BASE_ROW) == compute_row_hash(with_lineage)


def test_missing_field_treated_as_empty_not_a_crash():
    sparse = {"voucher_no": "SI/1", "line_no": 1}
    compute_row_hash(sparse)  # must not raise


def test_hash_is_bytes_and_stable_length():
    h = compute_row_hash(BASE_ROW)
    assert isinstance(h, bytes)
    assert len(h) == 32  # sha256 digest
