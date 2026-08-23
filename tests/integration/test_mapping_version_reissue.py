"""corpus/12 sprint 2 test: a prior signed statement re-renders identically
after a version change. corpus/06 section 6 rule 3: effective dating is by
accounting period -- a later version's effective_from does not touch a period
it doesn't cover."""
from datetime import date

from src.mapping.review import create_draft_version, freeze_mapping_version, run_mapping_pass
from src.reports.pnl import assemble_manufacturing_pnl
from src.reports.query import resolve_mapping_version_for_period
from tests.helpers import ingest_manufacturer


def test_prior_period_statement_unchanged_after_a_later_version(conn, tenant):
    from src.config.loader import load_taxonomy
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    taxonomy = {t.class_: {"statement_section": t.statement_section, "statement_line": t.statement_line or t.class_}
                 for t in load_taxonomy()}

    v1 = create_draft_version(conn, schema, tenant_id, entity_id, 1, date(2023, 4, 1), "pytest-analyst")
    run_mapping_pass(conn, schema, tenant_id, entity_id, v1, taxonomy, "pytest-analyst")
    conn.commit()
    f1 = freeze_mapping_version(conn, schema, tenant_id, entity_id, v1, "pytest-analyst")
    conn.commit()
    assert f1.passed, f1.reason

    april_result_before = assemble_manufacturing_pnl(
        conn, schema, tenant_id, entity_id,
        resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, date(2023, 4, 30)),
        date(2023, 4, 1), date(2023, 4, 30),
    )

    # A later version, effective only from a period well after April --
    # simulates a correction found later that must not touch already-reported months.
    v2 = create_draft_version(conn, schema, tenant_id, entity_id, 2, date(2024, 4, 1), "pytest-analyst",
                                 change_reason="test: a later correction, must not touch April 2023")
    run_mapping_pass(conn, schema, tenant_id, entity_id, v2, taxonomy, "pytest-analyst")
    conn.commit()
    f2 = freeze_mapping_version(conn, schema, tenant_id, entity_id, v2, "pytest-analyst")
    conn.commit()
    assert f2.passed, f2.reason

    resolved_version_for_april = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, date(2023, 4, 30))
    assert resolved_version_for_april == v1, "April must still resolve to v1, not the new v2"

    april_result_after = assemble_manufacturing_pnl(
        conn, schema, tenant_id, entity_id, resolved_version_for_april, date(2023, 4, 1), date(2023, 4, 30),
    )

    assert april_result_after.lines == april_result_before.lines
    assert april_result_after.subtotals == april_result_before.subtotals

    # And a period covered by v2 resolves to v2, proving the effective-dating
    # boundary actually works both directions, not just "always v1."
    resolved_for_2024 = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, date(2024, 4, 30))
    assert resolved_for_2024 == v2
