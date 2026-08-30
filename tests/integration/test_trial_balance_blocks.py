"""Test 5 of 7: the month with the seeded imbalance fails the trial balance
check and blocks.

Corpus/09 sections 2.4/3.1, D-051: zero tolerance. "A period that fails does
not proceed to statement assembly."
"""
from decimal import Decimal

from src.ingest.load_pipeline import load_gl_file
from src.quality.exception_queue import list_exceptions
from src.quality.period_state import get_current_period_lock
from tests.helpers import ingest_manufacturer

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


def test_an_imbalanced_period_raises_the_catalogue_s_blocking_exception(conn, tenant):
    """corpus/09 section 2.4 catalogues a trial balance imbalance as BLOCKING,
    and the catalogue's mechanism for a blocking check is an exception row
    (section 4). Section 3.1 requires the failure to name the accounts."""
    tenant_id, schema = tenant
    load_gl_file(conn, schema, tenant_id, 1, "GL_2026-05.csv", GL_IMBALANCED.encode(), "pytest")
    conn.commit()

    [raised] = list_exceptions(conn, schema, tenant_id, "open")
    assert raised.exception_class == "consistency"
    assert raised.severity == "blocking"
    assert raised.period_key == "2026-05"
    assert raised.value_inr == Decimal("12500.00")
    # corpus/09 section 3.1: "the failure names the accounts contributing the
    # largest imbalance". The account is named, and the figure is not rounded
    # away -- at a zero tolerance the paise are the whole point.
    assert "Bank Charges" in raised.description
    assert "Rs 12,500.00" in raised.description


def test_an_imbalanced_period_is_held_at_open(conn, tenant):
    """The consequence corpus/09 section 5 attaches to that exception: OPEN ->
    VALIDATED requires "all blocking checks pass", so a period that does not
    tie never becomes reportable. The exception is written before the
    transition is attempted, not after."""
    tenant_id, schema = tenant
    r = load_gl_file(conn, schema, tenant_id, 1, "GL_2026-05.csv", GL_IMBALANCED.encode(), "pytest")
    conn.commit()

    [outcome] = r.period_transitions
    assert outcome.transitioned is False
    assert outcome.status == "open"
    assert "1 blocking exception(s)" in outcome.detail
    assert get_current_period_lock(conn, schema, tenant_id, 1, "2026-05") is None


def test_a_balanced_period_raises_nothing_and_still_validates(conn, tenant):
    tenant_id, schema = tenant
    r = load_gl_file(conn, schema, tenant_id, 1, "GL_2026-04.csv", GL_BALANCED.encode(), "pytest")
    conn.commit()

    assert list_exceptions(conn, schema, tenant_id, "open") == []
    assert r.period_transitions[0].transitioned is True
    assert get_current_period_lock(conn, schema, tenant_id, 1, "2026-04").status == "validated"


def _recon_runs(conn, schema, period_key):
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT status, books_amount_inr, bank_amount_inr, residual_inr, tolerance_pct '
            f'FROM "{schema}".reconciliation_run WHERE period_key = %s AND check_type = %s',
            (period_key, "trial_balance"),
        )
        return cur.fetchall()


def test_every_gl_load_records_a_trial_balance_reconciliation_run(conn, tenant):
    """corpus/04 grains reconciliation_run as "result of each reconciliation
    check per period", and corpus/09 section 2.5 lists the trial balance tie
    as one of P0's two reconciliation checks -- so the pass is recorded as
    well as the failure. A check that only writes itself down when it fails
    cannot tell "passed" apart from "never ran"."""
    tenant_id, schema = tenant
    load_gl_file(conn, schema, tenant_id, 1, "GL_2026-04.csv", GL_BALANCED.encode(), "pytest")
    load_gl_file(conn, schema, tenant_id, 1, "GL_2026-05.csv", GL_IMBALANCED.encode(), "pytest")
    conn.commit()

    [(status, books, bank, residual, tolerance)] = _recon_runs(conn, schema, "2026-04")
    assert status == "reconciled"
    assert residual == Decimal("0")
    # D-051 is a stated value, unlike D-052's deliberately blank books-to-bank
    # tolerance -- so it is written down, not left null.
    assert tolerance == Decimal("0")
    # One source, not two: db/migrations/tenant/0011's own comment.
    assert bank is None
    assert books == Decimal("0")

    [(status, books, bank, residual, tolerance)] = _recon_runs(conn, schema, "2026-05")
    assert status == "unreconciled"
    assert residual == Decimal("12500.00")
    assert books == Decimal("12500.00")
    assert bank is None


def test_only_the_seeded_defect_month_of_the_manufacturer_is_held_at_open(conn, tenant):
    """The reference dataset, end to end. corpus/11 section 2.2 defect #4
    imbalances exactly one of the 36 months, so exactly one month must fail
    to reach VALIDATED -- and it must be that one. Both halves matter: a
    check that held every period would also satisfy "the broken month is
    held"."""
    tenant_id, schema = tenant
    data = ingest_manufacturer(conn, schema, tenant_id, 1)
    [broken] = [e["month"] for e in data.defect_log.entries if e["defect_id"] == 4]

    held = [f"{d.year:04d}-{d.month:02d}" for d in data.months
            if get_current_period_lock(conn, schema, tenant_id, 1, f"{d.year:04d}-{d.month:02d}") is None]
    assert held == [broken]

    [raised] = list_exceptions(conn, schema, tenant_id, "open")
    assert raised.period_key == broken
    assert raised.exception_class == "consistency"
    assert raised.severity == "blocking"
    assert raised.value_inr == Decimal("12500.00")  # defect #4's own figure
