"""Orchestrates one file through the full sprint 1 pipeline.

Implements corpus/04 section 5:
  source file -> source_file (hash, immutable landing) -> load_run ->
  staging (typed, dedup) -> canonical facts (close-not-update) ->
  quality checks (blocking ones halt) -> [period status is sprint 3]

Two blocking checks are wired in sprint 1, at two different points, because
they block two different things (corpus/09 section 2):
  - Schema hash change (section 2.6) blocks the LOAD itself, before staging
    ever runs -- "never auto-adopted, a silent column change corrupts
    metrics quietly." Nothing is written if this fires.
  - Trial balance imbalance (section 2.4/3.1) blocks STATEMENT ASSEMBLY, not
    ingestion -- the facts must exist in fact_gl_entry for the check to be
    computable at all. It is reported on the result, not rolled back.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from src.ingest.canonical import (
    write_bank_rows,
    write_channel_order_rows,
    write_coa_rows,
    write_gl_rows,
    write_production_output_rows,
)
from src.ingest.hashing import compute_row_hash
from src.ingest.landing import content_hash as compute_content_hash
from src.ingest.landing import land_file
from src.ingest.staging import stage_bank, stage_channel_order, stage_coa, stage_gl, stage_mfg_production, stage_tb
from src.quality.trial_balance import TrialBalanceCheckResult, check_trial_balance


@dataclass
class LoadResult:
    load_run_id: int | None = None
    status: str = "running"  # 'running' | 'succeeded' | 'blocked' | 'failed'
    blocked_reason: str | None = None
    quarantined_count: int = 0
    inserted: int = 0
    closed_and_reinserted: int = 0
    unchanged: int = 0
    periods_touched: list[str] = field(default_factory=list)
    tb_results: list[TrialBalanceCheckResult] = field(default_factory=list)


def _create_load_run(conn, tenant_id: str, entity_id: int, source_system: str, triggered_by: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO app.load_run (tenant_id, entity_id, source_system, status, triggered_by) "
            "VALUES (%s, %s, %s, 'running', %s) RETURNING load_run_id",
            (tenant_id, entity_id, source_system, triggered_by),
        )
        return cur.fetchone()[0]


def _finish_load_run(conn, load_run_id: int, status: str):
    with conn.cursor() as cur:
        cur.execute("UPDATE app.load_run SET status=%s, completed_at=now() WHERE load_run_id=%s",
                     (status, load_run_id))


def _last_schema_hash(conn, tenant_id: str, template_type: str) -> bytes | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT schema_hash FROM app.source_file WHERE tenant_id=%s AND template_type=%s "
            "ORDER BY received_at DESC LIMIT 1",
            (tenant_id, template_type),
        )
        row = cur.fetchone()
        return bytes(row[0]) if row else None


def _record_source_file(conn, tenant_id: str, entity_id: int, load_run_id: int, file_name: str,
                          template_type: str, content_hash: bytes, schema_hash: bytes,
                          storage_path: str, row_count: int):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO app.source_file (tenant_id, entity_id, load_run_id, file_name, template_type, "
            "content_hash, schema_hash, storage_path, row_count) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (tenant_id, entity_id, load_run_id, file_name, template_type, content_hash, schema_hash,
             storage_path, row_count),
        )


def load_gl_file(conn, schema: str, tenant_id: str, entity_id: int, file_name: str, raw_bytes: bytes,
                   triggered_by: str, today: date | None = None) -> LoadResult:
    result = LoadResult()
    load_run_id = _create_load_run(conn, tenant_id, entity_id, "excel_upload", triggered_by)
    result.load_run_id = load_run_id

    staged = stage_gl(raw_bytes, today=today)

    last_hash = _last_schema_hash(conn, tenant_id, "GL")
    if last_hash is not None and last_hash != staged.schema_hash:
        result.status = "blocked"
        result.blocked_reason = (
            "Schema hash of this GL file differs from the last GL file received for this tenant. "
            "Never auto-adopted -- corpus/09 section 2.6. The load is blocked, not adapted."
        )
        _finish_load_run(conn, load_run_id, "failed")
        return result

    c_hash = compute_content_hash(raw_bytes)
    storage_path = land_file(tenant_id, load_run_id, file_name, raw_bytes)
    _record_source_file(conn, tenant_id, entity_id, load_run_id, file_name, "GL",
                          c_hash, staged.schema_hash, storage_path, len(staged.valid_rows))

    result.quarantined_count = len(staged.quarantined)
    write_result = write_gl_rows(conn, schema, tenant_id, entity_id, load_run_id, "excel_upload", staged.valid_rows)
    result.inserted = write_result.inserted
    result.closed_and_reinserted = write_result.closed_and_reinserted
    result.unchanged = write_result.unchanged

    periods = sorted({f'{r["voucher_date"].year:04d}-{r["voucher_date"].month:02d}' for r in staged.valid_rows})
    result.periods_touched = periods
    for period_key in periods:
        result.tb_results.append(check_trial_balance(conn, schema, tenant_id, period_key))

    result.status = "succeeded"
    _finish_load_run(conn, load_run_id, "succeeded")
    return result


def load_coa_file(conn, schema: str, tenant_id: str, entity_id: int, file_name: str, raw_bytes: bytes,
                    triggered_by: str) -> LoadResult:
    """Chart of accounts: staged and upserted into dim_account, per corpus/04
    section 3.2. No fact table involved -- COA populates a dimension."""
    result = LoadResult()
    load_run_id = _create_load_run(conn, tenant_id, entity_id, "excel_upload", triggered_by)
    result.load_run_id = load_run_id

    staged = stage_coa(raw_bytes)
    c_hash = compute_content_hash(raw_bytes)
    storage_path = land_file(tenant_id, load_run_id, file_name, raw_bytes)
    _record_source_file(conn, tenant_id, entity_id, load_run_id, file_name, "COA",
                          c_hash, staged.schema_hash, storage_path, len(staged.valid_rows))

    result.quarantined_count = len(staged.quarantined)
    result.inserted = write_coa_rows(conn, schema, tenant_id, entity_id, load_run_id, staged.valid_rows)
    result.status = "succeeded"
    _finish_load_run(conn, load_run_id, "succeeded")
    return result


def load_tb_file(conn, tenant_id: str, entity_id: int, file_name: str, raw_bytes: bytes,
                   triggered_by: str) -> tuple[LoadResult, list[dict]]:
    """Trial balance: landed and staged as the reference to reconcile
    fact_gl_entry against (corpus/12 sprint 1 acceptance criterion). There is
    no fact_trial_balance table -- a trial balance is a report derived FROM
    fact_gl_entry, per corpus/03; the uploaded TB is a comparison target, not
    an independent source of canonical facts, so nothing is written beyond
    source_file. Returns the staged rows for the caller to diff."""
    result = LoadResult()
    load_run_id = _create_load_run(conn, tenant_id, entity_id, "excel_upload", triggered_by)
    result.load_run_id = load_run_id

    staged = stage_tb(raw_bytes)
    c_hash = compute_content_hash(raw_bytes)
    storage_path = land_file(tenant_id, load_run_id, file_name, raw_bytes)
    _record_source_file(conn, tenant_id, entity_id, load_run_id, file_name, "TB",
                          c_hash, staged.schema_hash, storage_path, len(staged.valid_rows))

    result.quarantined_count = len(staged.quarantined)
    result.status = "succeeded"
    _finish_load_run(conn, load_run_id, "succeeded")
    return result, staged.valid_rows


def load_bank_file(conn, schema: str, tenant_id: str, entity_id: int, file_name: str, raw_bytes: bytes,
                     triggered_by: str, today: date | None = None) -> LoadResult:
    """Bank statement: staged and written to fact_bank_txn, the input to
    books-to-bank reconciliation (src/quality/books_to_bank.py). Same
    schema-hash load-blocking discipline as load_gl_file, per corpus/09
    section 2.6 -- a silent column change on a bank export is exactly the
    kind of thing that corrupts a reconciliation quietly."""
    result = LoadResult()
    load_run_id = _create_load_run(conn, tenant_id, entity_id, "bank_file", triggered_by)
    result.load_run_id = load_run_id

    staged = stage_bank(raw_bytes, today=today)

    last_hash = _last_schema_hash(conn, tenant_id, "Bank")
    if last_hash is not None and last_hash != staged.schema_hash:
        result.status = "blocked"
        result.blocked_reason = (
            "Schema hash of this Bank file differs from the last Bank file received for this tenant. "
            "Never auto-adopted -- corpus/09 section 2.6. The load is blocked, not adapted."
        )
        _finish_load_run(conn, load_run_id, "failed")
        return result

    c_hash = compute_content_hash(raw_bytes)
    storage_path = land_file(tenant_id, load_run_id, file_name, raw_bytes)
    _record_source_file(conn, tenant_id, entity_id, load_run_id, file_name, "Bank",
                          c_hash, staged.schema_hash, storage_path, len(staged.valid_rows))

    result.quarantined_count = len(staged.quarantined)
    write_result = write_bank_rows(conn, schema, tenant_id, entity_id, load_run_id, "bank_file", staged.valid_rows)
    result.inserted = write_result.inserted
    result.closed_and_reinserted = write_result.closed_and_reinserted
    result.unchanged = write_result.unchanged

    result.periods_touched = sorted({f'{r["event_date"].year:04d}-{r["event_date"].month:02d}' for r in staged.valid_rows})
    result.status = "succeeded"
    _finish_load_run(conn, load_run_id, "succeeded")
    return result


def load_channel_order_file(conn, schema: str, tenant_id: str, entity_id: int, file_name: str, raw_bytes: bytes,
                                triggered_by: str, today: date | None = None) -> LoadResult:
    """Consumer Sales / channel order line, corpus/04 section 3.5. Same
    schema-hash load-blocking discipline as load_gl_file/load_bank_file."""
    result = LoadResult()
    load_run_id = _create_load_run(conn, tenant_id, entity_id, "excel_upload", triggered_by)
    result.load_run_id = load_run_id

    staged = stage_channel_order(raw_bytes, today=today)

    last_hash = _last_schema_hash(conn, tenant_id, "ConsumerSales")
    if last_hash is not None and last_hash != staged.schema_hash:
        result.status = "blocked"
        result.blocked_reason = (
            "Schema hash of this Consumer Sales file differs from the last one received for this tenant. "
            "Never auto-adopted -- corpus/09 section 2.6. The load is blocked, not adapted."
        )
        _finish_load_run(conn, load_run_id, "failed")
        return result

    c_hash = compute_content_hash(raw_bytes)
    storage_path = land_file(tenant_id, load_run_id, file_name, raw_bytes)
    _record_source_file(conn, tenant_id, entity_id, load_run_id, file_name, "ConsumerSales",
                          c_hash, staged.schema_hash, storage_path, len(staged.valid_rows))

    result.quarantined_count = len(staged.quarantined)
    write_result = write_channel_order_rows(conn, schema, tenant_id, entity_id, load_run_id, "excel_upload",
                                                staged.valid_rows)
    result.inserted = write_result.inserted
    result.closed_and_reinserted = write_result.closed_and_reinserted
    result.unchanged = write_result.unchanged

    result.periods_touched = sorted({f'{r["event_date"].year:04d}-{r["event_date"].month:02d}' for r in staged.valid_rows})
    result.status = "succeeded"
    _finish_load_run(conn, load_run_id, "succeeded")
    return result


def load_production_output_file(conn, schema: str, tenant_id: str, entity_id: int, file_name: str, raw_bytes: bytes,
                                    triggered_by: str, today: date | None = None) -> LoadResult:
    """MFG Production, corpus/04 section 3.6. Same schema-hash load-blocking
    discipline as load_gl_file/load_bank_file."""
    result = LoadResult()
    load_run_id = _create_load_run(conn, tenant_id, entity_id, "excel_upload", triggered_by)
    result.load_run_id = load_run_id

    staged = stage_mfg_production(raw_bytes, today=today)

    last_hash = _last_schema_hash(conn, tenant_id, "MFGProduction")
    if last_hash is not None and last_hash != staged.schema_hash:
        result.status = "blocked"
        result.blocked_reason = (
            "Schema hash of this MFG Production file differs from the last one received for this tenant. "
            "Never auto-adopted -- corpus/09 section 2.6. The load is blocked, not adapted."
        )
        _finish_load_run(conn, load_run_id, "failed")
        return result

    c_hash = compute_content_hash(raw_bytes)
    storage_path = land_file(tenant_id, load_run_id, file_name, raw_bytes)
    _record_source_file(conn, tenant_id, entity_id, load_run_id, file_name, "MFGProduction",
                          c_hash, staged.schema_hash, storage_path, len(staged.valid_rows))

    result.quarantined_count = len(staged.quarantined)
    write_result = write_production_output_rows(conn, schema, tenant_id, entity_id, load_run_id, "excel_upload",
                                                     staged.valid_rows)
    result.inserted = write_result.inserted
    result.closed_and_reinserted = write_result.closed_and_reinserted
    result.unchanged = write_result.unchanged

    result.periods_touched = sorted({r["period_key"] for r in staged.valid_rows})
    result.status = "succeeded"
    _finish_load_run(conn, load_run_id, "succeeded")
    return result
