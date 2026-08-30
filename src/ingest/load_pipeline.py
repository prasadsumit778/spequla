"""Orchestrates one file through the full sprint 1 pipeline.

Implements corpus/04 section 5:
  source file -> source_file (hash, immutable landing) -> load_run ->
  staging (typed, dedup) -> canonical facts (close-not-update) ->
  quality checks (blocking ones halt) -> period state (OPEN -> VALIDATED)

Two blocking checks are wired in sprint 1, at two different points, because
they block two different things (corpus/09 section 2):
  - Schema hash change (section 2.6) blocks the LOAD itself, before staging
    ever runs -- "never auto-adopted, a silent column change corrupts
    metrics quietly." Nothing is written if this fires.
  - Trial balance imbalance (section 2.4/3.1) blocks STATEMENT ASSEMBLY, not
    ingestion -- the facts must exist in fact_gl_entry for the check to be
    computable at all. It is reported on the result, not rolled back, and it
    raises the catalogue's blocking exception, which holds the period at OPEN
    (section 5) so nothing downstream assembles a statement off it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from src.ingest.canonical import (
    get_placeholder_mapping_version,
    write_bank_rows,
    write_channel_order_rows,
    write_coa_rows,
    write_gl_rows,
    write_production_output_rows,
    write_store_master_rows,
)
from src.ingest.hashing import compute_row_hash
from src.ingest.landing import content_hash as compute_content_hash
from src.ingest.landing import land_file
from src.ingest.staging import (
    stage_bank,
    stage_channel_order,
    stage_coa,
    stage_gl,
    stage_mfg_production,
    stage_store_master,
    stage_tb,
)
from src.quality.books_to_bank import write_reconciliation_run
from src.quality.checks import write_exceptions
from src.quality.exception_queue import open_blocking_exceptions
from src.quality.period_state import (
    PeriodTransitionOutcome,
    get_current_period_lock,
    validate_period,
)
from src.quality.trial_balance import (
    TRIAL_BALANCE_TOLERANCE_PCT,
    TrialBalanceCheckResult,
    as_reconciliation_result,
    check_trial_balance,
    imbalance_exception,
)


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
    # One entry per period in periods_touched, for GL loads only -- what the
    # OPEN -> VALIDATED attempt did, including the periods it deliberately
    # did not move. Empty for every other stream: a period becomes reportable
    # on its GL, not on a bank file or an order file.
    period_transitions: list[PeriodTransitionOutcome] = field(default_factory=list)


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


def _validate_loaded_periods(conn, schema: str, tenant_id: str, entity_id: int,
                                 periods: list[str]) -> list[PeriodTransitionOutcome]:
    """OPEN -> VALIDATED once per period a GL load touched, corpus/09 section
    5: "all blocking checks pass."

    **What counts as a blocking check here.** The condition is evaluated
    against the exception queue -- src/quality/exception_queue.
    open_blocking_exceptions, the same query corpus/08 section 10's sign-off
    gate uses, so "a blocking exception is open for this period" has one
    meaning in this system rather than two that drift.

    **This gate now carries current.** It used to be a live wire with
    nothing behind it: no production code called
    src/quality/checks.write_exceptions, so the query returned zero for
    every period and the gate admitted everything its predecessor state
    allowed. load_gl_file is now the exception table's first production
    writer -- corpus/09 section 2.4's trial balance row, raised as a
    blocking 'consistency' exception before this function runs -- so a
    period whose trial balance does not tie is genuinely held at OPEN, and
    the reference dataset has one such period (the synthetic manufacturer's
    seeded defect #4 month). Reading a period's VALIDATED row as "the check
    catalogue passed" is still an overstatement: one catalogue row writes
    here, not all of them.

    The trial balance check that ran moments earlier in load_gl_file is
    still deliberately NOT folded in on the side. It arrives here through
    the queue like every other blocking check; counting its result
    separately would build a second path to the same condition, which is the
    drift open_blocking_exceptions was consolidated to prevent. The
    ordering that makes this work lives at the call site: the exception is
    written before this function is called, or the period validates and only
    then learns it should not have.

    MAPPED -> RECONCILED remains an independent gate: it computes the trial
    balance itself and refuses on any non-zero total (D-051). Two gates on
    the same condition, not one -- a period that reaches MAPPED with facts
    that have since stopped tying (see the skip rule below) is still refused
    there.

    **An already-validated period is skipped, not refused** -- OQ-009(a),
    resolved 2026-08-30. corpus/09 section 5 draws no self-arrow, so
    validate_period refuses a period that already holds a lock row, while a
    second GL file for the same month is ordinary usage rather than an error.
    The skip is recorded and returned instead of raised, and its cost is real
    and knowingly accepted: the blocking checks do not re-run, so such a
    period keeps a `validated` row that was earned against facts which have
    since changed. A LOCKED period touched by new data is corpus/09 section
    5's restatement path (LOCKED -> RESTATED, src/ingest/repull.py), not
    wired yet -- it is skipped and reported here like any other occupied
    state, never walked backwards.
    """
    # period_lock.mapping_version_id is NOT NULL, and at VALIDATED there is by
    # definition no frozen version to point at -- corpus/09 section 5 calls
    # this state "structurally sound, mapping not yet frozen." The placeholder
    # (version_no = 0, db/migrations/tenant/0005) is exactly what the facts
    # this load just wrote already carry (src/ingest/canonical.write_gl_rows),
    # so the lock row records the same ingestion-time version its own facts
    # do, rather than one chosen here. map_period supersedes it with the real
    # frozen version at the next transition.
    mapping_version_id = get_placeholder_mapping_version(conn, schema, tenant_id, entity_id)

    outcomes: list[PeriodTransitionOutcome] = []
    for period_key in periods:
        current = get_current_period_lock(conn, schema, tenant_id, entity_id, period_key)
        if current is not None:
            outcomes.append(PeriodTransitionOutcome(
                period_key, False, current.status,
                f"already {current.status} before this load: the transition was skipped and the blocking "
                f"checks did not re-run against the facts this load wrote (OQ-009(a))",
            ))
            continue
        blocking_exception_count = len(open_blocking_exceptions(conn, schema, tenant_id, entity_id, period_key))
        if blocking_exception_count > 0:
            outcomes.append(PeriodTransitionOutcome(
                period_key, False, "open",
                f"held at open: {blocking_exception_count} blocking exception(s) open for this period -- "
                f"corpus/09 section 5 requires all blocking checks to pass before VALIDATED",
            ))
            continue
        validate_period(conn, schema, tenant_id, entity_id, period_key, mapping_version_id,
                           blocking_exception_count=blocking_exception_count)
        outcomes.append(PeriodTransitionOutcome(period_key, True, "validated", "open -> validated"))
    return outcomes


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

    # Every trial balance result is recorded, and every failure has raised its
    # blocking exception, BEFORE _validate_loaded_periods runs. corpus/09
    # section 5 gates OPEN -> VALIDATED on "all blocking checks pass", read
    # off the exception queue -- a check that wrote its exception after that
    # gate would let the period validate and only then learn it should not
    # have, and nothing walks a period backwards silently (section 5).
    #
    # The reconciliation_run row is written for a tie as well as a failure:
    # corpus/04 grains the table as "result of EACH reconciliation check per
    # period", and a check that only records itself when it fails cannot tell
    # "passed" apart from "never ran".
    #
    # Reloading a period that still does not tie raises the exception again
    # rather than deduplicating against the open one. Deliberate, and it is
    # what invariant #8 means: accepting an exception does not make a trial
    # balance tie, so accepting one and re-uploading the same broken export
    # must not be a way past a zero tolerance. Each row carries its own
    # load_run_id, so the versions are attributable rather than anonymous.
    mapping_version_id = get_placeholder_mapping_version(conn, schema, tenant_id, entity_id)
    for period_key in periods:
        tb = check_trial_balance(conn, schema, tenant_id, period_key)
        result.tb_results.append(tb)
        write_reconciliation_run(conn, schema, tenant_id, entity_id, mapping_version_id,
                                    "trial_balance", as_reconciliation_result(tb), triggered_by,
                                    tolerance_pct=TRIAL_BALANCE_TOLERANCE_PCT)
        if tb.blocking:
            write_exceptions(conn, schema, tenant_id, entity_id, [imbalance_exception(tb)], load_run_id)

    result.period_transitions = _validate_loaded_periods(conn, schema, tenant_id, entity_id, periods)

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


def load_store_master_file(conn, schema: str, tenant_id: str, entity_id: int, file_name: str, raw_bytes: bytes,
                               triggered_by: str) -> LoadResult:
    """Store Master, corpus/04 section 3.10 / corpus/13 section 2. Populates
    dim_location's retail attributes -- no fact table involved, same shape
    as load_coa_file. No schema-hash load-blocking here: unlike GL/Bank/
    Consumer Sales, a Store Master re-upload updating a handful of stores'
    attributes in place is expected, ordinary usage, not a silent
    corruption risk the way an unnoticed column rename on a transactional
    file is."""
    result = LoadResult()
    load_run_id = _create_load_run(conn, tenant_id, entity_id, "excel_upload", triggered_by)
    result.load_run_id = load_run_id

    staged = stage_store_master(raw_bytes)
    c_hash = compute_content_hash(raw_bytes)
    storage_path = land_file(tenant_id, load_run_id, file_name, raw_bytes)
    _record_source_file(conn, tenant_id, entity_id, load_run_id, file_name, "StoreMaster",
                          c_hash, staged.schema_hash, storage_path, len(staged.valid_rows))

    result.quarantined_count = len(staged.quarantined)
    result.inserted = write_store_master_rows(conn, schema, tenant_id, entity_id, load_run_id, staged.valid_rows)
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
