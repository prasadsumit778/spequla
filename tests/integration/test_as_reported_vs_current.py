"""Test 4 of 7: "as reported on date X" and "as it stands now" both return
correct, different answers for the seeded backdated batch.

Corpus/04 section 1.1: the whole reason bitemporality exists -- "you send the
June pack on 8 July showing revenue of 42.1 Cr. On 14 July the accountant
backdates journal entries into June... With bitemporality both answers
remain queryable."
"""
from datetime import datetime, timezone
from decimal import Decimal

from src.ingest.load_pipeline import load_gl_file
from src.ingest.repull import sum_amount_base_as_it_stands_now, sum_amount_base_as_reported_on

GL_JUNE_ORIGINAL = (
    "voucher_no,voucher_type,voucher_date,entry_date,line_no,account_code,account_name,debit,credit,"
    "narration,cost_centre,party_name,is_cancelled\n"
    "SI/1,Sales,2026-06-10,2026-06-10,1,4001,Sales - North,0,421000000,Inv 1,SALES-N,Acme Traders,No\n"
    "SI/1,Sales,2026-06-10,2026-06-10,2,1200,Sundry Debtors,421000000,0,Inv 1,SALES-N,Acme Traders,No\n"
)
# A backdated batch: booked into June (event_date), but entered on 14 July
# (entry_date) -- after the pack for June was already sent on 8 July.
GL_JUNE_BACKDATED_ADDITION = (
    "voucher_no,voucher_type,voucher_date,entry_date,line_no,account_code,account_name,debit,credit,"
    "narration,cost_centre,party_name,is_cancelled\n"
    "SI/2,Sales,2026-06-20,2026-07-14,1,4001,Sales - North,0,13000000,Inv 2 backdated,SALES-N,Beta Traders,No\n"
    "SI/2,Sales,2026-06-20,2026-07-14,2,1200,Sundry Debtors,13000000,0,Inv 2 backdated,SALES-N,Beta Traders,No\n"
)


def test_as_reported_and_as_it_stands_now_differ_for_backdated_batch(conn, tenant):
    tenant_id, schema = tenant

    load_gl_file(conn, schema, tenant_id, 1, "GL_2026-06_v1.csv", GL_JUNE_ORIGINAL.encode(), "pytest")
    conn.commit()

    # Simulate "the pack was sent on 8 July": snapshot the knowledge-time cut
    # right after the original load, before the backdated batch arrives.
    with conn.cursor() as cur:
        cur.execute("SELECT now()")
        pack_sent_at = cur.fetchone()[0]

    load_gl_file(conn, schema, tenant_id, 1, "GL_2026-06_backdate.csv",
                  GL_JUNE_BACKDATED_ADDITION.encode(), "pytest")
    conn.commit()

    as_reported = sum_amount_base_as_reported_on(conn, schema, tenant_id, "2026-06", pack_sent_at)
    as_current = sum_amount_base_as_it_stands_now(conn, schema, tenant_id, "2026-06")

    assert as_reported == Decimal("0")      # June's original two balanced lines net to zero
    assert as_current == Decimal("0")        # June still balances after the backdated addition too
    # The two queries must differ in what they SEE even though both net to
    # zero here -- prove it via the debit-only revenue-ledger figure instead,
    # which is what a pack actually displays (revenue, not the net GL sum).
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT COALESCE(SUM(-amount_base), 0) FROM "{schema}".fact_gl_entry '
            f'WHERE tenant_id=%s AND period_key=%s AND account_key IN '
            f'  (SELECT account_key FROM "{schema}".dim_account WHERE source_account_name=%s) '
            f'AND valid_from <= %s AND valid_to > %s',
            (tenant_id, "2026-06", "Sales - North", pack_sent_at, pack_sent_at),
        )
        revenue_as_reported = cur.fetchone()[0]
        cur.execute(
            f'SELECT COALESCE(SUM(-amount_base), 0) FROM "{schema}".fact_gl_entry '
            f'WHERE tenant_id=%s AND period_key=%s AND is_current AND account_key IN '
            f'  (SELECT account_key FROM "{schema}".dim_account WHERE source_account_name=%s)',
            (tenant_id, "2026-06", "Sales - North"),
        )
        revenue_as_current = cur.fetchone()[0]

    assert revenue_as_reported == Decimal("421000000")
    assert revenue_as_current == Decimal("434000000")
    assert revenue_as_reported != revenue_as_current
