"""Integration test: the check catalogue against the synthetic
manufacturer's seeded defects. Needs live Postgres -- skips cleanly
otherwise. See src/quality/checks.py's module docstring for which of the
thirteen seeded defects are reachable given what's actually ingested
(COA/TB/GL/Bank only) -- this test covers exactly those.
"""
from __future__ import annotations

from datetime import date

from src.quality.checks import (
    check_duplicate_content_different_voucher,
    check_new_ledger_mid_year,
    check_stream_supplied,
    check_unmapped_value,
)
from tests.helpers import ingest_manufacturer, run_and_freeze_mapping


def _defect_month(data, defect_id: int) -> str:
    entry = next(e for e in data.defect_log.entries if e["defect_id"] == defect_id)
    return entry["month"]


def test_defect_3_bank_missing_entirely_is_blocking(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    data = ingest_manufacturer(conn, schema, tenant_id, entity_id)
    month = _defect_month(data, 3)

    result = check_stream_supplied(conn, schema, tenant_id, entity_id, month, "bank")
    assert len(result) == 1
    assert result[0].severity == "blocking"
    assert result[0].exception_class == "completeness"


def test_defect_2_duplicate_content_different_voucher_is_blocking(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    data = ingest_manufacturer(conn, schema, tenant_id, entity_id)
    month = _defect_month(data, 2)

    result = check_duplicate_content_different_voucher(conn, schema, tenant_id, entity_id, month)
    assert len(result) >= 1
    assert all(r.severity == "blocking" and r.exception_class == "uniqueness" for r in result)


def test_defect_5_new_ledger_mid_year_is_warning(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    data = ingest_manufacturer(conn, schema, tenant_id, entity_id)
    entry = next(e for e in data.defect_log.entries if e["defect_id"] == 5)
    month = entry["month"]

    result = check_new_ledger_mid_year(conn, schema, tenant_id, entity_id, month)
    assert len(result) >= 1
    assert any(entry["ledger"] in r.description for r in result)
    assert all(r.severity == "warning" and r.exception_class == "continuity" for r in result)


def test_defect_10_suspense_ledgers_show_in_unmapped_value(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    data = ingest_manufacturer(conn, schema, tenant_id, entity_id)
    suspense_entry = next(e for e in data.defect_log.entries if e["defect_id"] == 10)
    assert len(suspense_entry["ledger_codes"]) == 12  # corpus/11 section 2.2 defect #10

    version_id, summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                             effective_from=date(2022, 4, 1))
    assert freeze.passed, freeze.reason  # the twelve unclassifiable ledgers must not block the 98% gate
    assert summary.deferred_to_suspense >= 12

    with conn.cursor() as cur:
        cur.execute(
            f'SELECT source_record_id FROM "{schema}".map_account '
            f"WHERE mapping_version_id = %s AND canonical_class = 'suspense.unmapped'",
            (version_id,),
        )
        suspense_ids = {r[0] for r in cur.fetchall()}
    assert set(suspense_entry["ledger_codes"]) <= suspense_ids

    # Unmapped value stays visible and quantified (corpus/06 section 3.6),
    # never silently zero-filled -- may or may not cross a D-053 severity
    # boundary depending on how much rupee value those 12 ledgers carry.
    check_unmapped_value(conn, schema, tenant_id, entity_id, version_id, "2025-03")
