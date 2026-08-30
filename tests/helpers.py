"""Shared helpers for sprint 2's integration/eval tests: ingest a full
synthetic company (COA + all months of GL) into a live tenant schema."""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

from src.ingest.load_pipeline import load_channel_order_file, load_coa_file, load_gl_file, load_production_output_file
from src.mapping.review import create_draft_version, freeze_mapping_version, run_mapping_pass

COA_FIELDS = ["account_code", "account_name", "parent_group", "account_type",
              "opening_balance", "opening_dr_cr", "cost_centre", "is_active"]
GL_FIELDS = ["voucher_no", "voucher_type", "voucher_date", "entry_date", "line_no",
             "account_code", "account_name", "debit", "credit", "narration",
             "cost_centre", "party_name", "is_cancelled"]


def write_csv_bytes(fieldnames, rows) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode()


def ingest_manufacturer(conn, schema: str, tenant_id: str, entity_id: int = 1, seed: int = 42):
    from synthetic.manufacturer.engine import build_company
    data = build_company(seed=seed)

    coa_rows = [{
        "account_code": l.account_code, "account_name": l.account_name,
        "parent_group": l.parent_group, "account_type": l.account_type,
        "opening_balance": "0", "opening_dr_cr": "Dr", "cost_centre": l.cost_centre or "",
        "is_active": l.is_active,
    } for l in data.coa]
    r = load_coa_file(conn, schema, tenant_id, entity_id, "COA.csv", write_csv_bytes(COA_FIELDS, coa_rows), "pytest")
    conn.commit()
    assert r.status == "succeeded"

    for i, d in enumerate(data.months):
        tag = f"{d.year:04d}-{d.month:02d}"
        r = load_gl_file(conn, schema, tenant_id, entity_id, f"GL_{tag}.csv",
                           write_csv_bytes(GL_FIELDS, data.gl_rows[i]), "pytest")
        conn.commit()
        assert r.status == "succeeded", f"month {tag} failed: {r.blocked_reason}"

    return data


def ingest_consumer(conn, schema: str, tenant_id: str, entity_id: int = 1, seed: int = 42):
    from synthetic.consumer.engine import build_consumer_company
    data = build_consumer_company(seed=seed)

    coa_rows = [{
        "account_code": l.account_code, "account_name": l.account_name,
        "parent_group": l.parent_group, "account_type": l.account_type,
        "opening_balance": "0", "opening_dr_cr": "Dr", "cost_centre": "", "is_active": "Yes",
    } for l in data.coa]
    r = load_coa_file(conn, schema, tenant_id, entity_id, "COA.csv", write_csv_bytes(COA_FIELDS, coa_rows), "pytest")
    conn.commit()
    assert r.status == "succeeded"

    for i, d in enumerate(data.months):
        tag = f"{d.year:04d}-{d.month:02d}"
        r = load_gl_file(conn, schema, tenant_id, entity_id, f"GL_{tag}.csv",
                           write_csv_bytes(GL_FIELDS, data.gl_rows[i]), "pytest")
        conn.commit()
        assert r.status == "succeeded", f"month {tag} failed: {r.blocked_reason}"

    return data


def seed_dim_channel(conn, schema: str, tenant_id: str, entity_id: int, profile: str):
    from scripts.seed_dim_channel import CONSUMER_CHANNELS, MANUFACTURING_CHANNELS
    channels = CONSUMER_CHANNELS if profile == "consumer" else MANUFACTURING_CHANNELS
    with conn.cursor() as cur:
        for channel_type, channel_name in channels:
            cur.execute(
                f'INSERT INTO "{schema}".dim_channel '
                f'(tenant_id, entity_id, channel_type, channel_name, load_run_id, source_record_id) '
                f'VALUES (%s, %s, %s, %s, 0, %s)',
                (tenant_id, entity_id, channel_type, channel_name, channel_type),
            )
    conn.commit()


def ingest_consumer_channel_orders(conn, schema: str, tenant_id: str, entity_id: int, data, month_idx: int = 0):
    """Loads one month of the consumer synthetic company's order file into
    fact_channel_order_line. Assumes seed_dim_channel(profile='consumer')
    has already run for this tenant."""
    from synthetic.consumer.write import CONSUMER_SALES_FIELDS
    d = data.months[month_idx]
    tag = f"{d.year:04d}-{d.month:02d}"
    r = load_channel_order_file(conn, schema, tenant_id, entity_id, f"ConsumerSales_{tag}.csv",
                                    write_csv_bytes(CONSUMER_SALES_FIELDS, data.order_rows[month_idx]), "pytest")
    conn.commit()
    assert r.status == "succeeded", f"channel order load failed: {r.blocked_reason}"
    return r


def ingest_manufacturer_production(conn, schema: str, tenant_id: str, entity_id: int, data, month_idx: int = 0):
    """Loads one month of the manufacturer synthetic company's MFG
    Production file into fact_production_output."""
    from synthetic.manufacturer.write import MFG_FIELDS
    r = load_production_output_file(
        conn, schema, tenant_id, entity_id, f"MFGProduction_month{month_idx}.csv",
        write_csv_bytes(MFG_FIELDS, data.mfg_rows[month_idx]), "pytest",
    )
    conn.commit()
    assert r.status == "succeeded", f"production output load failed: {r.blocked_reason}"
    return r


def run_and_freeze_mapping(conn, schema: str, tenant_id: str, entity_id: int, effective_from: date,
                              approver: str = "pytest-analyst", version_no: int = 1):
    from src.config.loader import load_taxonomy
    taxonomy = {
        t.class_: {"statement_section": t.statement_section, "statement_line": t.statement_line or t.class_}
        for t in load_taxonomy()
    }
    version_id = create_draft_version(conn, schema, tenant_id, entity_id, version_no, effective_from, approver)
    summary = run_mapping_pass(conn, schema, tenant_id, entity_id, version_id, taxonomy, approver)
    conn.commit()
    freeze = freeze_mapping_version(conn, schema, tenant_id, entity_id, version_id, approver)
    conn.commit()
    return version_id, summary, freeze


def advance_periods_to_reconciled(conn, schema: str, tenant_id: str, entity_id: int,
                                     mapping_version_id: int, freeze, period_keys: list[str],
                                     approver: str = "pytest-analyst") -> dict[str, str]:
    """Drives named periods VALIDATED -> MAPPED -> RECONCILED through exactly
    the functions the real callers use, so a fixture that wants a reportable
    period gets one the same way production does.

    corpus/09 section 5's arrows, and who drives each: MAPPED comes from
    map_periods_for_mapping_version (what POST /mapping/runs/{id}/freeze
    calls, src/api/routes/mapping.py); RECONCILED comes from
    reconcile_period_from_current_checks (what POST /periods/{key}/reconcile
    calls, src/api/routes/periods.py), which computes the trial balance
    itself and finds the period's own books-to-bank run -- so this helper
    runs run_books_to_bank + write_reconciliation_run first to put that run
    in the table, and asserts nothing about the period's condition.

    **Nothing here forces a period through.** A period whose trial balance
    does not tie (D-051, zero tolerance) is refused by reconcile_period and
    stays where it is; a period held at OPEN by a blocking exception is
    never mapped in the first place. The returned dict is the status each
    requested period ACTUALLY reached, so a caller asserts on it rather than
    assuming. See tests/eval/test_golden_questions.py for a fixture that
    asserts both outcomes.
    """
    from src.quality.books_to_bank import run_books_to_bank, write_reconciliation_run
    from src.quality.period_state import (
        InvalidTransition,
        get_current_period_lock,
        map_periods_for_mapping_version,
        reconcile_period_from_current_checks,
    )

    map_periods_for_mapping_version(conn, schema, tenant_id, entity_id, mapping_version_id,
                                       freeze_passed=freeze.passed, coverage_pct=freeze.coverage_pct)
    conn.commit()

    def _status(period_key: str) -> str:
        row = get_current_period_lock(conn, schema, tenant_id, entity_id, period_key)
        return row.status if row is not None else "open"

    reached: dict[str, str] = {}
    for period_key in period_keys:
        if _status(period_key) != "mapped":
            reached[period_key] = _status(period_key)
            continue
        result = run_books_to_bank(conn, schema, tenant_id, entity_id, mapping_version_id, period_key)
        write_reconciliation_run(conn, schema, tenant_id, entity_id, mapping_version_id,
                                    "books_to_bank", result, run_by=approver)
        conn.commit()
        try:
            reconcile_period_from_current_checks(conn, schema, tenant_id, entity_id, period_key,
                                                       approved_by=approver)
            conn.commit()
        except InvalidTransition:
            conn.rollback()
        reached[period_key] = _status(period_key)
    return reached
