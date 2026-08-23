"""Test 1 of 7: the same file uploaded twice produces no duplicate facts.

Corpus/09 section 2.3: "The same file uploaded twice -> INFORMATIONAL.
Content hash catches it. Idempotent by design, and a weekly event."
Corpus/04 section 5 guarantee #2.
"""
from src.ingest.load_pipeline import load_gl_file

GL_CSV = (
    "voucher_no,voucher_type,voucher_date,entry_date,line_no,account_code,account_name,debit,credit,"
    "narration,cost_centre,party_name,is_cancelled\n"
    "SI/1,Sales,2026-04-18,2026-04-18,1,4001,Sales - North,0,845000,Inv 1,SALES-N,Acme Traders,No\n"
    "SI/1,Sales,2026-04-18,2026-04-18,2,1200,Sundry Debtors,845000,0,Inv 1,SALES-N,Acme Traders,No\n"
)


def test_uploading_the_same_file_twice_creates_no_duplicate_facts(conn, tenant):
    tenant_id, schema = tenant

    r1 = load_gl_file(conn, schema, tenant_id, 1, "GL_2026-04.csv", GL_CSV.encode(), "pytest")
    conn.commit()
    assert r1.status == "succeeded"
    assert r1.inserted == 2

    r2 = load_gl_file(conn, schema, tenant_id, 1, "GL_2026-04.csv", GL_CSV.encode(), "pytest")
    conn.commit()
    assert r2.status == "succeeded"
    assert r2.inserted == 0
    assert r2.unchanged == 2

    with conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM "{schema}".fact_gl_entry WHERE is_current')
        assert cur.fetchone()[0] == 2
