"""corpus/12 sprint 2 test: auto-accept never fires on a judgement class,
end to end against a real ingested company and a real mapping run."""
from datetime import date

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
    tenant_id, schema = tenant
    ingest_manufacturer(conn, schema, tenant_id, entity_id=1)
    version_id, summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, 1, date(2023, 4, 1))

    with conn.cursor() as cur:
        cur.execute(
            f'SELECT approved_by FROM "{schema}".map_account '
            f"WHERE mapping_version_id = %s AND source_account_name = 'Sales - Direct (North)'",
            (version_id,),
        )
        approved_by = cur.fetchone()[0]
    assert approved_by == "system-auto-accept"
    # ~85 material ledgers have exact rules; 4 are judgement classes (human-approved,
    # not auto-accepted), so auto-accepted should land comfortably in the high 70s/low 80s.
    assert 70 <= summary.auto_accepted <= 85
    assert summary.human_approved == len(JUDGEMENT_LEDGERS)
    assert summary.deferred_to_suspense > 300  # the procedurally generated long tail + 12 suspense ledgers
