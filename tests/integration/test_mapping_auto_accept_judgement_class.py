"""corpus/12 sprint 2 test: auto-accept never fires on a judgement class,
end to end against a real ingested company and a real mapping run."""
from datetime import date

from src.mapping.engine import AUTO_ACCEPT_RUPEE_CEILING_INR, extract_coa, propose_mappings
from src.mapping.review import JUDGEMENT_CLASSES
from tests.helpers import ingest_manufacturer, run_and_freeze_mapping

JUDGEMENT_LEDGERS = {
    "Director Remuneration": "opex.owner_remuneration",
    "Rent Paid - Related Party": "opex.related_party_charges",
    "Absorption Variance": "cogs.absorption_variance",
    "Unsecured Loan - Director": "liability.debt_related_party",
}


def test_judgement_classes_are_never_auto_accepted(conn, tenant):
    tenant_id, schema = tenant
    ingest_manufacturer(conn, schema, tenant_id, entity_id=1)
    version_id, summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, 1, date(2023, 4, 1))

    with conn.cursor() as cur:
        for ledger_name, expected_class in JUDGEMENT_LEDGERS.items():
            cur.execute(
                f'SELECT canonical_class, proposal_source, approved_by FROM "{schema}".map_account '
                f'WHERE mapping_version_id = %s AND source_account_name = %s',
                (version_id, ledger_name),
            )
            row = cur.fetchone()
            assert row is not None, f"{ledger_name} was never mapped at all"
            canonical_class, proposal_source, approved_by = row
            assert canonical_class == expected_class
            assert proposal_source == "exact_rule"  # the rule DID match
            assert approved_by != "system-auto-accept", f"{ledger_name} was auto-accepted -- invariant #12 violated"


def test_non_judgement_exact_matches_do_auto_accept(conn, tenant):
    """corpus/06 section 4.2's four auto-accept conditions, asserted as the
    rule rather than as a count.

    Rewritten 2026-08-24, when D-065 declared the fourth condition's number
    (a flat rupee ceiling, previously undeclared -- OQ-001). This test used
    to name 'Sales - Direct (North)' as the ledger that must auto-accept and
    pin `auto_accepted` to a 70-85 band. Both were written when the ceiling
    condition was skipped entirely, and both are wrong now for the same
    reason: that ledger carries roughly INR 98 crore of movement, so under
    any reading of D-065 it is a ledger a human must confirm, not one the
    system waves through.

    So instead of a band, the reference recomputes the acceptance rule
    itself from the same accounts and compares set against set. Note that
    it deliberately reads `period_value_inr` as-is rather than asserting a
    particular basis for it -- D-065 declares the ceiling "per period" while
    `extract_coa` sums all movement seen so far, and reconciling those two
    is OQ-008, still open. This test passes either way; it checks that the
    gate applies whatever ceiling and basis are in force, not which."""
    tenant_id, schema = tenant
    ingest_manufacturer(conn, schema, tenant_id, entity_id=1)
    version_id, summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, 1, date(2023, 4, 1))

    # Independent reference: the four conditions, applied to the same
    # accounts. This is a first mapping run, so "no conflicting prior
    # approved mapping" holds vacuously for every account.
    proposed, _unmatched = propose_mappings(extract_coa(conn, schema, tenant_id, 1))
    should_auto_accept = {
        p.account.source_account_name for p in proposed
        if p.canonical_class not in JUDGEMENT_CLASSES
        and p.account.period_value_inr < AUTO_ACCEPT_RUPEE_CEILING_INR
    }
    should_go_to_a_human = {p.account.source_account_name for p in proposed} - should_auto_accept

    assert should_auto_accept, (
        "no rule-matched ledger sits below the declared ceiling, so this test would pass "
        "vacuously -- the ceiling or the reference company's scale has changed materially"
    )

    with conn.cursor() as cur:
        cur.execute(
            f'SELECT source_account_name, approved_by FROM "{schema}".map_account '
            f"WHERE mapping_version_id = %s AND canonical_class != 'suspense.unmapped'",
            (version_id,),
        )
        approver_by_name = dict(cur.fetchall())

    actually_auto_accepted = {n for n, by in approver_by_name.items() if by == "system-auto-accept"}
    assert actually_auto_accepted == should_auto_accept, (
        f"auto-accepted but should not have been: {sorted(actually_auto_accepted - should_auto_accept)}; "
        f"should have been but were not: {sorted(should_auto_accept - actually_auto_accepted)}"
    )

    # Every judgement ledger is in the human set regardless of value --
    # invariant #12 does not depend on the ceiling.
    assert set(JUDGEMENT_LEDGERS) <= should_go_to_a_human
    # ...and the material revenue ledger this test used to expect to be
    # auto-accepted is now, correctly, a human's call.
    assert approver_by_name["Sales - Direct (North)"] != "system-auto-accept"

    assert summary.auto_accepted == len(should_auto_accept)
    assert summary.human_approved == len(should_go_to_a_human)
    assert summary.deferred_to_suspense > 300  # the procedurally generated long tail + 12 suspense ledgers
