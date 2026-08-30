"""Integration test: the period state machine is actually driven by the
events corpus/09 section 5 says drive it.

tests/integration/test_period_state_machine.py covers the transitions
themselves -- their preconditions, and the arrows they refuse. This file
covers the wiring: a GL load validates the periods it touched, freezing a
mapping version maps the periods that version governs, and the two human
transitions run from their endpoints with nothing about the period's
condition supplied by the caller.

Needs Postgres (see tests/conftest.py) -- skips cleanly otherwise.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from src.api.deps.auth import Session
from src.api.routes.mapping import freeze_run
from src.api.routes.periods import lock, reconcile, reconciliation_run
from src.config.loader import load_taxonomy
from src.ingest.canonical import get_placeholder_mapping_version
from src.ingest.load_pipeline import load_gl_file
from src.mapping.review import create_draft_version, run_mapping_pass
from src.quality.books_to_bank import (latest_reconciliation_run_id, run_books_to_bank,
                                          write_reconciliation_run)
from src.quality.checks import ExceptionCandidate, write_exceptions
from src.quality.exception_queue import list_exceptions, open_blocking_exceptions, resolve_exception
from src.quality.period_state import get_current_period_lock, validate_period
from tests.helpers import ingest_manufacturer

ENTITY_ID = 1
SESSION = Session(user_id="pytest-analyst", org_id="org_pytest", role="spequla_analyst")

_HEADER = ("voucher_no,voucher_type,voucher_date,entry_date,line_no,account_code,account_name,debit,credit,"
            "narration,cost_centre,party_name,is_cancelled\n")


def _gl(*vouchers: tuple[str, str, str]) -> bytes:
    """One balanced sales voucher per (voucher_no, date, amount) -- a debit to
    debtors and an equal credit to sales, so every period built here ties to
    zero (D-051) unless a test deliberately makes it not."""
    rows = _HEADER
    for vno, day, amount in vouchers:
        rows += (f"{vno},Sales,{day},{day},1,4001,Sales - North,0,{amount},Inv,SALES-N,Acme,No\n"
                   f"{vno},Sales,{day},{day},2,1200,Sundry Debtors,{amount},0,Inv,SALES-N,Acme,No\n")
    return rows.encode()


def _transitions(result) -> dict:
    return {t.period_key: t for t in result.period_transitions}


# --------------------------------------------------------------------------
# OPEN -> VALIDATED, at the end of a GL load
# --------------------------------------------------------------------------

def test_a_gl_load_takes_every_period_it_touched_open_to_validated(conn, tenant):
    tenant_id, schema = tenant
    result = load_gl_file(conn, schema, tenant_id, ENTITY_ID, "GL.csv",
                              _gl(("SI/1", "2026-04-18", "845000"), ("SI/2", "2026-05-12", "610000")), "pytest")
    conn.commit()

    assert result.status == "succeeded"
    assert result.periods_touched == ["2026-04", "2026-05"]

    transitions = _transitions(result)
    assert sorted(transitions) == ["2026-04", "2026-05"], "one outcome per period touched, not one per load"
    for period_key, outcome in transitions.items():
        assert outcome.transitioned is True, outcome.detail
        assert outcome.status == "validated"
        assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, period_key).status == "validated"


def test_the_validated_lock_row_points_at_the_version_its_own_facts_carry(conn, tenant):
    """corpus/09 section 5 calls VALIDATED "structurally sound, mapping not
    yet frozen," and period_lock.mapping_version_id is NOT NULL -- so the row
    records the placeholder version (version_no 0) that the facts written by
    the same load already carry, rather than a version chosen at transition
    time. Asserted because it is a choice, not an inevitability."""
    tenant_id, schema = tenant
    load_gl_file(conn, schema, tenant_id, ENTITY_ID, "GL.csv", _gl(("SI/1", "2026-04-18", "845000")), "pytest")
    conn.commit()

    lock_row = get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, "2026-04")
    with conn.cursor() as cur:
        cur.execute(f'SELECT version_no FROM "{schema}".mapping_version WHERE mapping_version_id = %s',
                       (lock_row.mapping_version_id,))
        assert cur.fetchone()[0] == 0


def test_a_second_load_of_an_already_validated_period_is_skipped_and_reported(conn, tenant):
    """OQ-009(a). A second GL file for the same month is ordinary usage, and
    corpus/09 section 5 draws no self-arrow, so the load skips the transition
    and records it rather than raising or pretending it transitioned."""
    tenant_id, schema = tenant
    first = load_gl_file(conn, schema, tenant_id, ENTITY_ID, "GL_1.csv", _gl(("SI/1", "2026-04-18", "845000")),
                             "pytest")
    conn.commit()
    assert _transitions(first)["2026-04"].transitioned is True

    second = load_gl_file(conn, schema, tenant_id, ENTITY_ID, "GL_2.csv", _gl(("SI/2", "2026-04-25", "310000")),
                              "pytest")
    conn.commit()

    # The load itself is unaffected -- the new facts are written; it is only
    # the transition that is skipped.
    assert second.status == "succeeded"
    assert second.inserted == 2

    outcome = _transitions(second)["2026-04"]
    assert outcome.transitioned is False
    assert outcome.status == "validated"
    assert "already validated" in outcome.detail
    assert "did not re-run" in outcome.detail, "the cost of OQ-009(a) is stated where it is paid"

    # Skipped means skipped: no second 'validated' row was appended, so the
    # state machine still has exactly one way into VALIDATED.
    with conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM "{schema}".period_lock WHERE period_key = %s', ("2026-04",))
        assert cur.fetchone()[0] == 1


def test_a_period_with_an_open_blocking_exception_is_held_at_open(conn, tenant):
    """corpus/09 section 5's OPEN -> VALIDATED condition is "all blocking
    checks pass," read off the exception queue -- the same query corpus/08
    section 10's sign-off gate uses. The gate is held against a completeness
    exception raised by this test rather than the trial balance one the load
    now raises itself (tests/integration/test_trial_balance_blocks.py), so
    what it demonstrates stays what it says: the gate answers to the queue,
    not to any one check that writes into it."""
    tenant_id, schema = tenant
    [exception_id] = write_exceptions(conn, schema, tenant_id, ENTITY_ID, [ExceptionCandidate(
        exception_class="completeness", severity="blocking", period_key="2026-04",
        description="raised by this test to hold a period at OPEN",
    )])
    conn.commit()

    held = load_gl_file(conn, schema, tenant_id, ENTITY_ID, "GL_1.csv", _gl(("SI/1", "2026-04-18", "845000")),
                            "pytest")
    conn.commit()
    outcome = _transitions(held)["2026-04"]
    assert outcome.transitioned is False
    assert outcome.status == "open"
    assert "1 blocking exception(s)" in outcome.detail
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, "2026-04") is None

    # Resolved, the period validates on the next load -- the gate reads the
    # exception's current version, not the row as raised.
    resolve_exception(conn, schema, tenant_id, exception_id, "resolved",
                         "fixed at source and reloaded", "pytest-analyst")
    conn.commit()
    after = load_gl_file(conn, schema, tenant_id, ENTITY_ID, "GL_2.csv", _gl(("SI/2", "2026-04-25", "310000")),
                             "pytest")
    conn.commit()
    assert _transitions(after)["2026-04"].transitioned is True
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, "2026-04").status == "validated"


def test_a_bank_load_does_not_transition_anything(conn, tenant):
    """A period becomes reportable on its GL. Other streams touch periods too
    (LoadResult.periods_touched is populated for them), and none of them
    evaluates corpus/09 section 5's blocking-check condition."""
    from src.ingest.load_pipeline import load_bank_file
    tenant_id, schema = tenant
    # corpus/01's Bank template columns, verbatim from src/ingest/templates.BANK.
    bank = ("bank_account_ref,txn_date,value_date,description,reference,debit,credit,running_balance\n"
             "HDFC-001,2026-04-18,2026-04-18,NEFT Acme Traders,REF1,0,845000,845000\n")
    result = load_bank_file(conn, schema, tenant_id, ENTITY_ID, "Bank.csv", bank.encode(), "pytest")
    conn.commit()
    assert result.status == "succeeded", result.blocked_reason
    assert result.periods_touched == ["2026-04"]
    assert result.period_transitions == []
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, "2026-04") is None


# --------------------------------------------------------------------------
# VALIDATED -> MAPPED, inside the freeze endpoint
# --------------------------------------------------------------------------

def _run_pass_and_freeze(conn, schema, tenant_id, entity_id, effective_from: date):
    """Everything POST /mapping/runs does, then the freeze endpoint itself --
    the transition under test lives in the endpoint, so the endpoint is what
    is called."""
    taxonomy = {t.class_: {"statement_section": t.statement_section, "statement_line": t.statement_line or t.class_}
                  for t in load_taxonomy()}
    version_id = create_draft_version(conn, schema, tenant_id, entity_id, 1, effective_from, "pytest-analyst")
    run_mapping_pass(conn, schema, tenant_id, entity_id, version_id, taxonomy, "pytest-analyst")
    conn.commit()
    body = freeze_run(version_id, entity_id=entity_id, session=SESSION, tenant_ctx=(conn, tenant_id, schema))
    return version_id, body


def test_freezing_a_mapping_version_maps_only_validated_periods_inside_its_window(conn, tenant):
    """corpus/09 section 5's VALIDATED -> MAPPED condition is "mapping version
    approved, coverage above threshold" -- which is the freeze gate passing.
    Two things it must not do: reach outside the version's own effective
    window (corpus/06 section 6 rule 3), and drag forward a period that never
    passed its blocking checks."""
    tenant_id, schema = tenant
    held = "2025-03"
    write_exceptions(conn, schema, tenant_id, ENTITY_ID, [ExceptionCandidate(
        exception_class="completeness", severity="blocking", period_key=held,
        description="raised by this test so one period is held at OPEN through the freeze",
    )])
    conn.commit()

    ingest_manufacturer(conn, schema, tenant_id, ENTITY_ID)
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, held) is None, \
        "the blocking exception should have held this period at OPEN during its load"

    version_id, body = _run_pass_and_freeze(conn, schema, tenant_id, ENTITY_ID, date(2024, 4, 1))
    assert body["passed"] is True
    by_period = {t["period_key"]: t for t in body["period_transitions"]}

    # Outside the window: FY24 renders with whatever version covers it
    # forever, so freezing this one says nothing about those periods and
    # must not touch them.
    assert "2024-03" not in by_period
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, "2024-03").status == "validated"

    # 2023-12 is outside the window too, but it is not the witness for
    # "untouched" -- the synthetic manufacturer's defect #4 imbalances that
    # month, so its GL load raised corpus/09 section 2.4's blocking exception
    # and it never left OPEN. A period with no lock row proves nothing about
    # what the freeze did or did not reach.
    assert "2023-12" not in by_period
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, "2023-12") is None

    # Inside the window and still OPEN: reported, not moved.
    assert by_period[held]["transitioned"] is False
    assert by_period[held]["status"] == "open"
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, held) is None

    # Inside the window and VALIDATED: mapped.
    assert by_period["2025-04"]["transitioned"] is True
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, "2025-04").status == "mapped"
    for period_key, transition in by_period.items():
        assert period_key >= "2024-04", "no period outside the version's effective window was reported"
        if transition["transitioned"]:
            assert transition["status"] == "mapped"
            row = get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, period_key)
            assert row.status == "mapped"
            assert row.mapping_version_id == version_id, \
                "a mapped period points at the version that was just frozen, not the placeholder"
        else:
            assert transition["status"] == "open"


# --------------------------------------------------------------------------
# The books-to-bank run, its own endpoint (OQ-014)
# --------------------------------------------------------------------------

def test_the_reconciliation_run_endpoint_produces_the_run_reconcile_requires(conn, tenant):
    """OQ-014: before this endpoint existed, nothing in src/ wrote a
    books_to_bank reconciliation_run, so POST /periods/{key}/reconcile
    returned 422 for every period forever in any API-driven deployment. Every
    test that got past it called run_books_to_bank directly, which is exactly
    why the gap never surfaced as a failure. This drives the API path only."""
    tenant_id, schema = tenant
    ingest_manufacturer(conn, schema, tenant_id, ENTITY_ID)
    version_id, _body = _run_pass_and_freeze(conn, schema, tenant_id, ENTITY_ID, date(2022, 4, 1))
    period = "2025-03"
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, period).status == "mapped"

    body = reconciliation_run(period_key=period, entity_id=ENTITY_ID, session=SESSION,
                                  tenant_ctx=(conn, tenant_id, schema))
    assert body["check_type"] == "books_to_bank"
    assert body["run_by"] == "pytest-analyst", "the name comes from the verified session"
    assert body["mapping_version_id"] == version_id, \
        "resolved off the period's own lock row, never named by the caller"
    # D-052 is unset, so nothing here classifies the residual -- it is stated.
    assert body["status"] == "unreconciled"
    # corpus/09 section 3.2: residual = books - bank - modelled, and with no
    # modelled differences configured the whole gap is the residual.
    assert body["modelled_differences"] == []
    assert (Decimal(body["residual_inr"])
                == Decimal(body["books_total_inr"]) - Decimal(body["bank_total_inr"]))

    # The run it wrote is the one the reconcile endpoint finds.
    assert latest_reconciliation_run_id(conn, schema, tenant_id, ENTITY_ID, period,
                                             "books_to_bank") == body["reconciliation_run_id"]

    # And the period has not moved: this endpoint computes, it does not transition.
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, period).status == "mapped"


def test_the_reconciliation_run_endpoint_refuses_a_period_below_mapped(conn, tenant):
    """A VALIDATED period's lock row points at the ingestion-time placeholder
    mapping version, which carries no map_account rows -- class_movements
    through it returns nothing, so the run would record a books total of zero
    and a residual that is merely the negative of the bank total. OQ-014's
    resolution rejects option (a), at load, for precisely this reason, so the
    endpoint refuses rather than storing that artefact."""
    tenant_id, schema = tenant
    ingest_manufacturer(conn, schema, tenant_id, ENTITY_ID)
    period = "2025-03"
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, period).status == "validated"

    with pytest.raises(HTTPException) as refused:
        reconciliation_run(period_key=period, entity_id=ENTITY_ID, session=SESSION,
                              tenant_ctx=(conn, tenant_id, schema))
    assert refused.value.status_code == 422
    assert "is validated, not mapped" in refused.value.detail
    assert latest_reconciliation_run_id(conn, schema, tenant_id, ENTITY_ID, period, "books_to_bank") is None


# --------------------------------------------------------------------------
# MAPPED -> RECONCILED -> LOCKED, from their endpoints
# --------------------------------------------------------------------------

def test_the_reconcile_and_lock_endpoints_compute_their_own_preconditions(conn, tenant):
    tenant_id, schema = tenant
    ingest_manufacturer(conn, schema, tenant_id, ENTITY_ID)
    version_id, _body = _run_pass_and_freeze(conn, schema, tenant_id, ENTITY_ID, date(2022, 4, 1))
    period = "2025-03"
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, period).status == "mapped"

    # No books-to-bank run exists yet. The endpoint looks for one itself, so
    # there is no request field a caller could set to get past this.
    with pytest.raises(HTTPException) as refused:
        reconcile(period_key=period, entity_id=ENTITY_ID, session=SESSION, tenant_ctx=(conn, tenant_id, schema))
    assert refused.value.status_code == 422
    assert "no books-to-bank reconciliation_run" in refused.value.detail

    # Produced through its own endpoint, not by calling run_books_to_bank
    # here: a fixture that reaches RECONCILED without the API is what let
    # OQ-014 sit unnoticed.
    run_id = reconciliation_run(period_key=period, entity_id=ENTITY_ID, session=SESSION,
                                    tenant_ctx=(conn, tenant_id, schema))["reconciliation_run_id"]

    body = reconcile(period_key=period, entity_id=ENTITY_ID, session=SESSION, tenant_ctx=(conn, tenant_id, schema))
    assert body["status"] == "reconciled"
    assert body["reconciliation_run_id"] == run_id, "the endpoint found the run itself"
    assert Decimal(body["trial_balance_total"]) == Decimal("0"), "the endpoint computed this, nobody sent it"
    assert body["approved_by"] == "pytest-analyst", "the name comes from the verified session"
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, period).status == "reconciled"

    body = lock(period_key=period, entity_id=ENTITY_ID, session=SESSION, tenant_ctx=(conn, tenant_id, schema))
    assert body["status"] == "locked"
    assert body["locked_by"] == "pytest-analyst"
    locked = get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, period)
    assert locked.snapshot_at is not None, "corpus/04 section 3.8: locking pins the knowledge-time cut"
    assert locked.mapping_version_id == version_id, \
        "the mapping version is carried off the period's own row, never named by the caller"


def test_reconcile_refuses_a_period_whose_trial_balance_does_not_tie(conn, tenant):
    """D-051, zero tolerance. The endpoint runs check_trial_balance itself, so
    a period that does not tie cannot be reconciled by a caller who simply
    does not mention it. The synthetic manufacturer's defect #4 (corpus/11
    section 2.2) posts one deliberately one-sided voucher, so exactly one
    month of the reference dataset genuinely fails.

    That month no longer reaches MAPPED by itself: its GL load raises
    corpus/09 section 2.4's blocking exception and holds it at OPEN. This
    endpoint's gate sits BEHIND that one, so the period is walked past the
    first gate the only way a human could -- corpus/09 section 4's "accept
    with a written reason" -- and the second gate still refuses. Accepting an
    exception does not make a trial balance tie, and D-051 is enforced twice
    rather than once."""
    tenant_id, schema = tenant
    data = ingest_manufacturer(conn, schema, tenant_id, ENTITY_ID)
    [broken] = [e["month"] for e in data.defect_log.entries if e["defect_id"] == 4]
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, broken) is None, \
        "the load's trial balance exception should have held this period at OPEN"

    [raised] = [e for e in list_exceptions(conn, schema, tenant_id, "open")
                  if e.period_key == broken and e.exception_class == "consistency"]
    resolve_exception(conn, schema, tenant_id, raised.exception_key, "accepted",
                         "accepted so the gate behind this one is reachable", "pytest-analyst")
    conn.commit()
    still_open = open_blocking_exceptions(conn, schema, tenant_id, ENTITY_ID, broken)
    assert still_open == [], "accepting it should clear the queue, so the refusal below is only the TB"
    validate_period(conn, schema, tenant_id, ENTITY_ID, broken,
                       get_placeholder_mapping_version(conn, schema, tenant_id, ENTITY_ID),
                       blocking_exception_count=len(still_open))
    conn.commit()

    version_id, _body = _run_pass_and_freeze(conn, schema, tenant_id, ENTITY_ID, date(2022, 4, 1))
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, broken).status == "mapped"

    # A reconciliation run exists, so the refusal below can only be the trial
    # balance -- not the missing-run precondition standing in for it.
    recon = run_books_to_bank(conn, schema, tenant_id, ENTITY_ID, version_id, broken)
    write_reconciliation_run(conn, schema, tenant_id, ENTITY_ID, version_id,
                                "books_to_bank", recon, "pytest-analyst")
    conn.commit()

    with pytest.raises(HTTPException) as refused:
        reconcile(period_key=broken, entity_id=ENTITY_ID, session=SESSION, tenant_ctx=(conn, tenant_id, schema))
    assert refused.value.status_code == 422
    assert "trial balance does not tie" in refused.value.detail
    assert get_current_period_lock(conn, schema, tenant_id, ENTITY_ID, broken).status == "mapped"


def test_lock_refuses_a_period_that_has_not_been_reconciled(conn, tenant):
    """corpus/09 section 5's arrow into LOCKED starts at RECONCILED. The
    endpoint carries the mapping version off the current row, so this refusal
    has to come from the state machine, not from a missing argument."""
    tenant_id, schema = tenant
    ingest_manufacturer(conn, schema, tenant_id, ENTITY_ID)
    _run_pass_and_freeze(conn, schema, tenant_id, ENTITY_ID, date(2022, 4, 1))

    with pytest.raises(HTTPException) as refused:
        lock(period_key="2025-03", entity_id=ENTITY_ID, session=SESSION, tenant_ctx=(conn, tenant_id, schema))
    assert refused.value.status_code == 422
    assert "is mapped, not reconciled" in refused.value.detail
