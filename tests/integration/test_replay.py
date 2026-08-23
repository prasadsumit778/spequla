"""Test 2 of 7: a full re-run from raw produces byte-identical canonical
output.

Corpus/04 section 5 guarantee #1: "Replayable. Re-running from raw with the
same mapping version produces byte-identical canonical output."
"""
from src.ingest.load_pipeline import load_gl_file

GL_CSV = (
    "voucher_no,voucher_type,voucher_date,entry_date,line_no,account_code,account_name,debit,credit,"
    "narration,cost_centre,party_name,is_cancelled\n"
    "SI/1,Sales,2026-04-18,2026-04-18,1,4001,Sales - North,0,845000,Inv 1,SALES-N,Acme Traders,No\n"
    "SI/1,Sales,2026-04-18,2026-04-18,2,1200,Sundry Debtors,845000,0,Inv 1,SALES-N,Acme Traders,No\n"
    "PB/1,Purchase,2026-04-11,2026-04-11,1,5001,Raw Material,250000,0,Bill 1,PROC,Northern Steel,No\n"
    "PB/1,Purchase,2026-04-11,2026-04-11,2,1300,Sundry Creditors,0,250000,Bill 1,PROC,Northern Steel,No\n"
)


def _snapshot(conn, schema, tenant_id):
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT voucher_no, line_no, account_key, amount_base, event_date, entry_date, row_hash '
            f'FROM "{schema}".fact_gl_entry WHERE tenant_id=%s AND is_current ORDER BY voucher_no, line_no',
            (tenant_id,),
        )
        return [tuple(bytes(v) if isinstance(v, memoryview) else v for v in row) for row in cur.fetchall()]


def test_replay_from_raw_is_byte_identical(conn, tenant):
    tenant_id, schema = tenant

    r1 = load_gl_file(conn, schema, tenant_id, 1, "GL_2026-04.csv", GL_CSV.encode(), "pytest")
    conn.commit()
    assert r1.status == "succeeded"
    snapshot_1 = _snapshot(conn, schema, tenant_id)

    # Full replay: re-run the identical raw bytes through the pipeline again.
    r2 = load_gl_file(conn, schema, tenant_id, 1, "GL_2026-04.csv", GL_CSV.encode(), "pytest")
    conn.commit()
    snapshot_2 = _snapshot(conn, schema, tenant_id)

    assert snapshot_1 == snapshot_2
    assert r2.inserted == 0
    assert r2.unchanged == len(snapshot_1)
