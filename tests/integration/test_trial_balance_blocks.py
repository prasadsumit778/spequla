"""Test 5 of 7: the month with the seeded imbalance fails the trial balance
check and blocks.

Corpus/09 sections 2.4/3.1, D-051: zero tolerance. "A period that fails does
not proceed to statement assembly."
"""
from src.ingest.load_pipeline import load_gl_file

GL_BALANCED = (
    "voucher_no,voucher_type,voucher_date,entry_date,line_no,account_code,account_name,debit,credit,"
    "narration,cost_centre,party_name,is_cancelled\n"
    "SI/1,Sales,2026-04-18,2026-04-18,1,4001,Sales - North,0,845000,Inv 1,SALES-N,Acme Traders,No\n"
    "SI/1,Sales,2026-04-18,2026-04-18,2,1200,Sundry Debtors,845000,0,Inv 1,SALES-N,Acme Traders,No\n"
)
GL_IMBALANCED = (
    "voucher_no,voucher_type,voucher_date,entry_date,line_no,account_code,account_name,debit,credit,"
    "narration,cost_centre,party_name,is_cancelled\n"
    "JV/1,Journal,2026-05-10,2026-05-10,1,6001,Bank Charges,12500,0,One-sided adjustment,,,No\n"
)


def test_balanced_period_does_not_block(conn, tenant):
    tenant_id, schema = tenant
    r = load_gl_file(conn, schema, tenant_id, 1, "GL_2026-04.csv", GL_BALANCED.encode(), "pytest")
    conn.commit()
    assert r.status == "succeeded"
    assert len(r.tb_results) == 1
    assert r.tb_results[0].balanced is True
    assert r.tb_results[0].blocking is False


def test_imbalanced_period_blocks(conn, tenant):
    tenant_id, schema = tenant
    r = load_gl_file(conn, schema, tenant_id, 1, "GL_2026-05.csv", GL_IMBALANCED.encode(), "pytest")
    conn.commit()
    # The load itself still succeeds (facts must exist for the check to be
    # computable) -- it is the period's trial balance result that blocks.
    assert r.status == "succeeded"
    assert len(r.tb_results) == 1
    assert r.tb_results[0].balanced is False
    assert r.tb_results[0].blocking is True
    assert r.tb_results[0].total == 12500
