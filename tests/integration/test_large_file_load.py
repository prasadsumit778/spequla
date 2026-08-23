"""A single file bigger than one bound-parameter batch must load.

PostgreSQL binds at most 65535 parameters to one statement. fact_gl_entry has
22 columns, so an unchunked multi-row INSERT fails above 2,978 journal lines.
Every existing test loaded the synthetic company one month at a time (about
120 lines per file) and so never crossed it, while a real customer uploading a
year of GL in one file would fail immediately.

corpus/02 section 3 P0 #1 puts no row limit on a customer's file, and
corpus/12 sprint 1's story is a whole company's ledger, so the size of the
file the analyst happens to receive must not decide whether it loads.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.ingest.canonical import MAX_BIND_PARAMS, _row_chunks
from src.ingest.load_pipeline import load_coa_file, load_gl_file
from tests.helpers import COA_FIELDS, GL_FIELDS, write_csv_bytes

GL_COLUMN_COUNT = 22          # fact_gl_entry's insert column list
ROWS_PER_STATEMENT = MAX_BIND_PARAMS // GL_COLUMN_COUNT   # 2,978


def test_row_chunks_never_exceeds_the_bind_parameter_cap():
    for params_per_row in (3, 6, 16, 20, 22, 31):
        rows = list(range(10_000))
        chunks = list(_row_chunks(rows, params_per_row))
        assert sum(len(c) for c in chunks) == len(rows), "chunking dropped rows"
        assert [r for c in chunks for r in c] == rows, "chunking reordered rows"
        for c in chunks:
            assert len(c) * params_per_row <= MAX_BIND_PARAMS


def test_row_chunks_rejects_a_nonsensical_width():
    with pytest.raises(ValueError):
        list(_row_chunks([1, 2, 3], params_per_row=0))


@pytest.mark.parametrize("rows", [0, 1])
def test_row_chunks_handles_the_edges(rows):
    assert [len(c) for c in _row_chunks([1] * rows, 22)] == ([1] if rows else [])


def test_one_gl_file_larger_than_a_single_statement_loads_completely(conn, tenant):
    """The regression itself: more journal lines in one file than fit in one
    INSERT. Before chunking this raised
    'number of parameters must be between 0 and 65535' and nothing loaded."""
    tenant_id, schema = tenant
    entity_id = 1

    coa = [{
        "account_code": "4001", "account_name": "Sales - Domestic",
        "parent_group": "Sales Accounts", "account_type": "Income",
        "opening_balance": "0", "opening_dr_cr": "Cr", "cost_centre": "", "is_active": "Yes",
    }, {
        "account_code": "1201", "account_name": "Sundry Debtors",
        "parent_group": "Current Assets", "account_type": "Asset",
        "opening_balance": "0", "opening_dr_cr": "Dr", "cost_centre": "", "is_active": "Yes",
    }]
    load_coa_file(conn, schema, tenant_id, entity_id, "COA.csv",
                     write_csv_bytes(COA_FIELDS, coa), "pytest")
    conn.commit()

    # Comfortably past one statement's worth, as balanced pairs so the ledger
    # still trial-balances (D-051, zero tolerance).
    pairs = (ROWS_PER_STATEMENT // 2) + 200
    start = date(2025, 3, 1)
    gl_rows = []
    for i in range(pairs):
        voucher_date = (start + timedelta(days=i % 28)).isoformat()
        common = {
            "voucher_no": f"SI/25-26/{i:05d}", "voucher_type": "Sales",
            "voucher_date": voucher_date, "entry_date": voucher_date,
            "narration": f"Invoice {i}", "cost_centre": "", "party_name": "Acme",
            "is_cancelled": "No",
        }
        gl_rows.append({**common, "line_no": "1", "account_code": "1201",
                           "account_name": "Sundry Debtors", "debit": "1000", "credit": "0"})
        gl_rows.append({**common, "line_no": "2", "account_code": "4001",
                           "account_name": "Sales - Domestic", "debit": "0", "credit": "1000"})

    assert len(gl_rows) > ROWS_PER_STATEMENT, "the fixture must exceed one statement's capacity"

    result = load_gl_file(conn, schema, tenant_id, entity_id, "GL.csv",
                             write_csv_bytes(GL_FIELDS, gl_rows), "pytest")
    conn.commit()

    assert result.status == "succeeded", result.blocked_reason
    assert result.quarantined_count == 0
    assert result.inserted == len(gl_rows), (
        f"only {result.inserted} of {len(gl_rows)} lines were written"
    )

    with conn.cursor() as cur:
        cur.execute(
            f'SELECT count(*), coalesce(sum(amount_base), 0) FROM "{schema}".fact_gl_entry '
            f'WHERE tenant_id = %s AND is_current',
            (tenant_id,),
        )
        count, total = cur.fetchone()

    assert count == len(gl_rows), "rows went missing at a chunk boundary"
    assert total == 0, "the loaded ledger no longer trial-balances (D-051 is zero tolerance)"
