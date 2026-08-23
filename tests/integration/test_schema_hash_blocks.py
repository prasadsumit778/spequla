"""Test 6 of 7: a schema hash change blocks the load rather than adapting.

Corpus/09 section 2.6: "Schema hash of a source file changes -> BLOCKING.
Never auto-adopted. A silent column change corrupts metrics quietly."
"""
from src.ingest.load_pipeline import load_gl_file

GL_V1 = (
    "voucher_no,voucher_type,voucher_date,entry_date,line_no,account_code,account_name,debit,credit,"
    "narration,cost_centre,party_name,is_cancelled\n"
    "SI/1,Sales,2026-04-18,2026-04-18,1,4001,Sales - North,0,845000,Inv 1,SALES-N,Acme Traders,No\n"
    "SI/1,Sales,2026-04-18,2026-04-18,2,1200,Sundry Debtors,845000,0,Inv 1,SALES-N,Acme Traders,No\n"
)
# 'narration' renamed to 'remarks' -- exactly defect #6 from the synthetic
# manufacturer generator.
GL_V2_RENAMED_HEADER = GL_V1.replace("narration,cost_centre", "remarks,cost_centre")


def test_schema_hash_change_blocks_the_load(conn, tenant):
    tenant_id, schema = tenant

    r1 = load_gl_file(conn, schema, tenant_id, 1, "GL_2026-04.csv", GL_V1.encode(), "pytest")
    conn.commit()
    assert r1.status == "succeeded"

    r2 = load_gl_file(conn, schema, tenant_id, 1, "GL_2026-05.csv", GL_V2_RENAMED_HEADER.encode(), "pytest")
    conn.commit()
    assert r2.status == "blocked"
    assert "schema hash" in r2.blocked_reason.lower() or "Schema hash" in r2.blocked_reason

    # Nothing from the blocked file was written.
    with conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM "{schema}".fact_gl_entry WHERE tenant_id=%s AND period_key=%s',
                     (tenant_id, "2026-05"))
        assert cur.fetchone()[0] == 0
