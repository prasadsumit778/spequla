"""Test 3 of 7: a changed fact closes the prior row rather than updating it.

CLAUDE.md invariant 4 and corpus/04 section 5 guarantee #3: "Non-destructive.
A changed fact closes the prior row rather than updating it. Nothing is ever
overwritten."
"""
from src.ingest.load_pipeline import load_gl_file

GL_V1 = (
    "voucher_no,voucher_type,voucher_date,entry_date,line_no,account_code,account_name,debit,credit,"
    "narration,cost_centre,party_name,is_cancelled\n"
    "SI/1,Sales,2026-04-18,2026-04-18,1,4001,Sales - North,0,845000,Inv 1,SALES-N,Acme Traders,No\n"
    "SI/1,Sales,2026-04-18,2026-04-18,2,1200,Sundry Debtors,845000,0,Inv 1,SALES-N,Acme Traders,No\n"
)
# Same voucher/line, corrected amount -- a real accountant fix, not a duplicate.
GL_V2 = GL_V1.replace("845000", "850000")


def test_changed_fact_closes_prior_row_and_inserts_new(conn, tenant):
    tenant_id, schema = tenant

    load_gl_file(conn, schema, tenant_id, 1, "GL_2026-04.csv", GL_V1.encode(), "pytest")
    conn.commit()
    with conn.cursor() as cur:
        # Not selecting valid_to: psycopg's binary timestamptz loader cannot
        # represent Postgres's 'infinity' sentinel (the default for an
        # unclosed row's valid_to) as a Python datetime and raises DataError
        # -- no production code reads this column's value directly (only
        # ever compares against it in a WHERE clause), so this is a test
        # query concern only, not a real code path.
        cur.execute(f'SELECT fact_id, amount_base, is_current FROM "{schema}".fact_gl_entry '
                     f'WHERE tenant_id=%s AND source_record_id=%s', (tenant_id, "SI/1#1"))
        original = cur.fetchone()
    assert original[2] is True  # is_current

    r2 = load_gl_file(conn, schema, tenant_id, 1, "GL_2026-04.csv", GL_V2.encode(), "pytest")
    conn.commit()
    assert r2.closed_and_reinserted == 2

    with conn.cursor() as cur:
        # The original row must still exist, now closed -- never deleted, never overwritten.
        cur.execute(f'SELECT amount_base, is_current FROM "{schema}".fact_gl_entry WHERE fact_id=%s',
                     (original[0],))
        still_there = cur.fetchone()
        assert still_there[0] == original[1]  # original amount unchanged
        assert still_there[1] is False          # but closed

        cur.execute(f'SELECT fact_id, amount_base, is_current FROM "{schema}".fact_gl_entry '
                     f'WHERE tenant_id=%s AND source_record_id=%s AND is_current', (tenant_id, "SI/1#1"))
        current = cur.fetchone()
        assert current[0] != original[0]   # a genuinely new row
        assert current[1] == -850000        # the corrected amount (credit, so negative)
        assert current[2] is True
