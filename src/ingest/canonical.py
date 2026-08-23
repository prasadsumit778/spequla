"""Canonical write: dim_account resolution and fact_gl_entry writes that close
the prior row rather than updating it.

Implements corpus/04 section 5 ("canonical facts: written with valid_from =
now(), prior versions closed") and CLAUDE.md invariant 4 ("Nothing is ever
overwritten or deleted. A changed fact closes the prior row and inserts a new
one"). Also implements the tokenisation side effect at ingestion (corpus/02
section 8) for whichever party names appear in the GL's party_name column --
see src/ingest/tokenise.py's module docstring for the sprint 1 scope note on
why the token is not yet attached to a surrogate key on the fact row.

Every write here is idempotent (corpus/04 section 5 guarantee #2): re-running
canonical write with rows whose row_hash already matches the current fact row
for that voucher/line is a no-op.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.ingest.tokenise import PgTokenStore, tokenise_batch


@dataclass
class CanonicalWriteResult:
    inserted: int = 0
    closed_and_reinserted: int = 0
    unchanged: int = 0



# PostgreSQL's wire protocol binds at most 65535 parameters to one statement
# (the count is an int16 in libpq). A multi-row INSERT of N rows by C columns
# sends N*C of them, so batching without a cap silently works on a small file
# and fails outright on a real one -- fact_gl_entry has 22 columns, which puts
# the ceiling at 2,978 journal lines in a single statement. A year of a real
# mid-market GL is far past that. Rows are therefore inserted in chunks sized
# to stay under the cap, still inside one transaction, so batching keeps its
# speed without imposing a row limit on the customer's file.
MAX_BIND_PARAMS = 65535


def _row_chunks(rows: list, params_per_row: int):
    """Yield slices of `rows` small enough to bind in one statement."""
    if params_per_row < 1:
        raise ValueError(f"params_per_row must be at least 1, got {params_per_row}")
    size = max(1, MAX_BIND_PARAMS // params_per_row)
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def resolve_account_key(conn, schema: str, tenant_id: str, entity_id: int,
                          account_code: str, account_name: str, load_run_id: int) -> int:
    """Find-or-create the current dim_account row for this source account.
    Type-2 SCD per corpus/04 section 1.2 -- not exercised by sprint 1 (no
    mapping edits happen yet), but the lookup-by-source_record_id pattern is
    what a later change would close and re-insert against.

    Single-row form, kept for callers resolving one account in isolation
    (e.g. an interactive lookup). write_gl_rows uses
    resolve_account_keys_batch instead -- see that function's docstring for
    why a per-row version of this does not scale to a real GL file."""
    source_record_id = account_code or account_name
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT account_key FROM "{schema}".dim_account '
            f'WHERE tenant_id=%s AND entity_id=%s AND source_record_id=%s AND is_current',
            (tenant_id, entity_id, source_record_id),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            f'INSERT INTO "{schema}".dim_account '
            f'(tenant_id, entity_id, source_account_code, source_account_name, load_run_id, source_record_id) '
            f'VALUES (%s, %s, %s, %s, %s, %s) RETURNING account_key',
            (tenant_id, entity_id, account_code, account_name, load_run_id, source_record_id),
        )
        return cur.fetchone()[0]


def resolve_account_keys_batch(conn, schema: str, tenant_id: str, entity_id: int,
                                  accounts: list[tuple[str, str]], load_run_id: int) -> dict[str, int]:
    """Batch form of resolve_account_key. accounts: a (account_code,
    account_name) pair per GL line -- typically thousands of pairs
    resolving to a few hundred distinct accounts, since the same ledger
    posts many lines. Returns {source_record_id: account_key} for every
    distinct account referenced. One SELECT for everything already known
    plus one multi-row INSERT...RETURNING for whatever's new, instead of up
    to two round trips for every GL line in the file -- against a database
    with real network latency, that difference is the gap between a COA
    load finishing in under a second and taking over a minute."""
    distinct: dict[str, tuple[str, str]] = {}
    for account_code, account_name in accounts:
        source_record_id = account_code or account_name
        distinct[source_record_id] = (account_code, account_name)
    if not distinct:
        return {}

    result: dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT source_record_id, account_key FROM "{schema}".dim_account '
            f'WHERE tenant_id=%s AND entity_id=%s AND is_current AND source_record_id = ANY(%s)',
            (tenant_id, entity_id, list(distinct.keys())),
        )
        for source_record_id, account_key in cur.fetchall():
            result[source_record_id] = account_key

        missing = [sr for sr in distinct if sr not in result]
        for _chunk in _row_chunks(missing, params_per_row=6):
            values_sql = ", ".join(["(%s,%s,%s,%s,%s,%s)"] * len(_chunk))
            params: list = []
            for source_record_id in _chunk:
                account_code, account_name = distinct[source_record_id]
                params.extend([tenant_id, entity_id, account_code, account_name, load_run_id, source_record_id])
            cur.execute(
                f'INSERT INTO "{schema}".dim_account '
                f'(tenant_id, entity_id, source_account_code, source_account_name, load_run_id, source_record_id) '
                f'VALUES {values_sql} RETURNING source_record_id, account_key',
                params,
            )
            for source_record_id, account_key in cur.fetchall():
                result[source_record_id] = account_key
    return result


NORMAL_BALANCE_BY_ACCOUNT_TYPE = {
    # Standard accounting (STANDARD category, corpus/03 section 1 -- one right
    # answer, not a per-company convention): assets and expenses carry a
    # natural debit balance, liabilities/income/equity a natural credit one.
    "asset": "Dr", "expense": "Dr", "liability": "Cr", "income": "Cr", "equity": "Cr",
}


def write_coa_rows(conn, schema: str, tenant_id: str, entity_id: int, load_run_id: int,
                     staged_rows: list[dict]) -> int:
    """Upsert dim_account from an uploaded chart of accounts, per corpus/04
    section 3.2. Uses the same source_record_id derivation as
    resolve_account_key (account_code or account_name) so a COA upload
    followed by a GL upload resolves to the same dim_account rows rather than
    creating duplicates.

    Batched: one SELECT for every ledger already known, one multi-row UPDATE
    (via a VALUES list joined back to the table) for existing ledgers, one
    multi-row INSERT for new ones -- a real chart of accounts is hundreds of
    ledgers (corpus/06: "a company with 900 ledgers"), and a round trip per
    ledger is the difference between this finishing in under a second and
    taking over a minute against a database with real network latency.
    Assumes at most one row per source_record_id in staged_rows, which a COA
    file inherently satisfies (one row per ledger)."""
    if not staged_rows:
        return 0

    by_source_record_id = {(row["account_code"] or row["account_name"]): row for row in staged_rows}

    with conn.cursor() as cur:
        cur.execute(
            f'SELECT source_record_id, account_key FROM "{schema}".dim_account '
            f'WHERE tenant_id=%s AND entity_id=%s AND is_current AND source_record_id = ANY(%s)',
            (tenant_id, entity_id, list(by_source_record_id.keys())),
        )
        existing_keys = {source_record_id: account_key for source_record_id, account_key in cur.fetchall()}

        to_update = [(sr, row) for sr, row in by_source_record_id.items() if sr in existing_keys]
        to_insert = [(sr, row) for sr, row in by_source_record_id.items() if sr not in existing_keys]

        for _chunk in _row_chunks(to_update, params_per_row=3):
            values_sql = ", ".join(["(%s,%s,%s)"] * len(_chunk))
            params: list = []
            for source_record_id, row in _chunk:
                normal_balance = NORMAL_BALANCE_BY_ACCOUNT_TYPE.get((row.get("account_type") or "").strip().lower())
                params.extend([existing_keys[source_record_id], row.get("parent_group"), normal_balance])
            cur.execute(
                f'UPDATE "{schema}".dim_account AS da SET source_parent_group = v.parent_group, '
                f'normal_balance = v.normal_balance '
                f'FROM (VALUES {values_sql}) AS v(account_key, parent_group, normal_balance) '
                f'WHERE da.account_key = v.account_key',
                params,
            )

        for _chunk in _row_chunks(to_insert, params_per_row=8):
            values_sql = ", ".join(["(%s,%s,%s,%s,%s,%s,%s,%s)"] * len(_chunk))
            params = []
            for source_record_id, row in _chunk:
                normal_balance = NORMAL_BALANCE_BY_ACCOUNT_TYPE.get((row.get("account_type") or "").strip().lower())
                params.extend([tenant_id, entity_id, row["account_code"], row["account_name"],
                                row.get("parent_group"), normal_balance, load_run_id, source_record_id])
            cur.execute(
                f'INSERT INTO "{schema}".dim_account '
                f'(tenant_id, entity_id, source_account_code, source_account_name, source_parent_group, '
                f' normal_balance, load_run_id, source_record_id) VALUES {values_sql}',
                params,
            )

    return len(to_update) + len(to_insert)


def get_placeholder_mapping_version(conn, schema: str, tenant_id: str, entity_id: int) -> int:
    """The version-0 system placeholder seeded by
    db/migrations/tenant/0005_mapping_version.sql -- see the sprint 0 plan's
    sequencing decision for why fact_gl_entry.mapping_version_id (NOT NULL)
    has something to point at before sprint 2 approves a real mapping."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT mapping_version_id FROM "{schema}".mapping_version '
            f'WHERE tenant_id=%s AND entity_id=%s AND version_no=0',
            (tenant_id, entity_id),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(
                "no placeholder mapping_version (version_no=0) found for this tenant/entity -- "
                "was db/migrations/tenant/0005_mapping_version.sql applied and seeded?"
            )
        return row[0]


def write_gl_rows(conn, schema: str, tenant_id: str, entity_id: int, load_run_id: int,
                    source_system: str, staged_rows: list[dict]) -> CanonicalWriteResult:
    """Batched: account resolution, tokenisation and the existing-fact lookup
    each happen once for the whole file (resolve_account_keys_batch,
    tokenise_batch, one SELECT ... = ANY(...)), then the close and insert
    steps are each a single multi-row statement. Against a database with
    real network latency this is the difference between a month of GL
    finishing in a couple of seconds and taking minutes -- a per-row version
    of this exact logic is what src/ingest/canonical.py had until this was
    caught running against a live database for the first time in the
    project's history.

    Assumes at most one row per (voucher_no, line_no) in staged_rows.
    stage_gl's own in-file dedup already guarantees this for identical
    content; two rows sharing a voucher_no/line_no with genuinely different
    content is a data-quality case corpus/09's uniqueness checks (section
    2.3) surface separately, not something this function needs to resolve --
    the last such row in the batch wins, same as it would if the source file
    itself just had a typo'd duplicate line number."""
    result = CanonicalWriteResult()
    if not staged_rows:
        return result

    token_store = PgTokenStore(conn)
    mapping_version_id = get_placeholder_mapping_version(conn, schema, tenant_id, entity_id)

    account_keys = resolve_account_keys_batch(
        conn, schema, tenant_id, entity_id,
        [(row["account_code"], row["account_name"]) for row in staged_rows], load_run_id,
    )
    # Tokenisation side effect only in sprint 1 -- see module docstring.
    tokenise_batch(token_store, tenant_id, "customer", [row.get("party_name") for row in staged_rows])

    by_source_record_id = {f'{row["voucher_no"]}#{row["line_no"]}': row for row in staged_rows}

    with conn.cursor() as cur:
        cur.execute(
            f'SELECT source_record_id, fact_id, row_hash FROM "{schema}".fact_gl_entry '
            f'WHERE tenant_id=%s AND entity_id=%s AND is_current AND source_record_id = ANY(%s)',
            (tenant_id, entity_id, list(by_source_record_id.keys())),
        )
        existing = {sr: (fact_id, bytes(row_hash)) for sr, fact_id, row_hash in cur.fetchall()}

        to_close: list[int] = []
        to_insert: list[tuple[str, dict]] = []
        for source_record_id, row in by_source_record_id.items():
            match = existing.get(source_record_id)
            if match and match[1] == row["row_hash"]:
                result.unchanged += 1
                continue
            if match:
                to_close.append(match[0])
                result.closed_and_reinserted += 1
            else:
                result.inserted += 1
            to_insert.append((source_record_id, row))

        if to_close:
            cur.execute(
                f'UPDATE "{schema}".fact_gl_entry SET valid_to = now(), is_current = false '
                f'WHERE fact_id = ANY(%s)',
                (to_close,),
            )

        for chunk in _row_chunks(to_insert, params_per_row=22):
            values_sql = ", ".join(["(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"]
                                      * len(chunk))
            params: list = []
            for source_record_id, row in chunk:
                account_key = account_keys[row["account_code"] or row["account_name"]]
                period_key = f'{row["voucher_date"].year:04d}-{row["voucher_date"].month:02d}'
                params.extend([
                    tenant_id, entity_id, row["voucher_no"], row["voucher_type"], row["line_no"],
                    row["voucher_date"], row["entry_date"], period_key, account_key,
                    row["amount_base"], row["amount_txn"], row["currency_code"], row["fx_rate"],
                    row["fx_rate_source"], row["narration"], row["is_cancelled"], row["is_opening_balance"],
                    load_run_id, source_system, source_record_id, row["row_hash"], mapping_version_id,
                ])
            cur.execute(
                f'INSERT INTO "{schema}".fact_gl_entry '
                f'(tenant_id, entity_id, voucher_no, voucher_type, line_no, event_date, entry_date, '
                f' period_key, account_key, amount_base, amount_txn, currency_code, fx_rate, fx_rate_source, '
                f' narration, is_cancelled, is_opening_balance, load_run_id, source_system, source_record_id, '
                f' row_hash, mapping_version_id) VALUES {values_sql}',
                params,
            )
    return result


def write_bank_rows(conn, schema: str, tenant_id: str, entity_id: int, load_run_id: int,
                      source_system: str, staged_rows: list[dict]) -> CanonicalWriteResult:
    """fact_bank_txn has no dim_account/mapping dependency -- a bank line is
    not classified against the taxonomy, it's reconciled against the books
    (src/quality/books_to_bank.py). Same close-not-update discipline as
    write_gl_rows, keyed on (bank_account_ref, row_hash) since a bank line
    has no natural voucher/line number of its own."""
    result = CanonicalWriteResult()
    if not staged_rows:
        return result
    mapping_version_id = get_placeholder_mapping_version(conn, schema, tenant_id, entity_id)

    by_source_record_id = {f'{row["bank_account_ref"]}#{row["row_hash"].hex()[:16]}': row for row in staged_rows}

    with conn.cursor() as cur:
        cur.execute(
            f'SELECT source_record_id, fact_id, row_hash FROM "{schema}".fact_bank_txn '
            f'WHERE tenant_id=%s AND entity_id=%s AND is_current AND source_record_id = ANY(%s)',
            (tenant_id, entity_id, list(by_source_record_id.keys())),
        )
        existing = {sr: (fact_id, bytes(row_hash)) for sr, fact_id, row_hash in cur.fetchall()}

        to_close: list[int] = []
        to_insert: list[tuple[str, dict]] = []
        for source_record_id, row in by_source_record_id.items():
            match = existing.get(source_record_id)
            if match and match[1] == row["row_hash"]:
                result.unchanged += 1
                continue
            if match:
                to_close.append(match[0])
                result.closed_and_reinserted += 1
            else:
                result.inserted += 1
            to_insert.append((source_record_id, row))

        if to_close:
            cur.execute(
                f'UPDATE "{schema}".fact_bank_txn SET valid_to = now(), is_current = false WHERE fact_id = ANY(%s)',
                (to_close,),
            )

        for _chunk in _row_chunks(to_insert, params_per_row=16):
            values_sql = ", ".join(["(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"] * len(_chunk))
            params: list = []
            for source_record_id, row in _chunk:
                period_key = f'{row["event_date"].year:04d}-{row["event_date"].month:02d}'
                params.extend([
                    tenant_id, entity_id, row["bank_account_ref"], row["event_date"], row["value_date"],
                    row["entry_date"], period_key, row["description"], row["reference"], row["amount_base"],
                    row["running_balance_reported"], load_run_id, source_system, source_record_id,
                    row["row_hash"], mapping_version_id,
                ])
            cur.execute(
                f'INSERT INTO "{schema}".fact_bank_txn '
                f'(tenant_id, entity_id, bank_account_ref, event_date, value_date, entry_date, period_key, '
                f' description, reference, amount_base, running_balance_reported, load_run_id, source_system, '
                f' source_record_id, row_hash, mapping_version_id) VALUES {values_sql}',
                params,
            )
    return result


# ------------------------------------------------------------------ Sprint 6

def _classify_channel_type(channel_name: str) -> str:
    """Free-text channel display name (whatever a source file calls it) ->
    D-046's fixed seven-value taxonomy (corpus/00, resolved), the same
    'classify to a small controlled vocabulary' job
    src/ingest/tokenise.py and manufacturer/engine.py's _channel_for already
    do for their own domains. dim_channel is pre-seeded with exactly these
    seven rows (scripts/seed_dim_channel.py) -- this function decides which
    one a given channel name belongs to, it does not create new ones."""
    n = channel_name.lower()
    if "quick commerce" in n:
        return "quick_commerce"
    if "marketplace" in n:
        return "marketplace"
    if "owned retail" in n or "retail" in n and "franchise" not in n:
        return "owned_retail"
    if "franchise" in n:
        return "franchise_retail"
    if "distributor" in n:
        return "distributor"
    if "export" in n:
        return "exports"
    if "website" in n or "d2c" in n or "own" in n:
        return "own_website"
    return "distributor"  # the manufacturing single-default-row case, and any unclassified fallback


def resolve_channel_key(conn, schema: str, tenant_id: str, entity_id: int, channel_name: str) -> int:
    channel_type = _classify_channel_type(channel_name)
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT channel_key FROM "{schema}".dim_channel '
            f'WHERE tenant_id=%s AND entity_id=%s AND source_record_id=%s AND is_current',
            (tenant_id, entity_id, channel_type),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError(
            f"no dim_channel row for channel_type={channel_type!r} (classified from {channel_name!r}) -- "
            f"was scripts/seed_dim_channel.py run for this tenant?"
        )
    return row[0]


def resolve_product_keys_batch(conn, schema: str, tenant_id: str, entity_id: int,
                                   items: list[tuple[str, str]], load_run_id: int) -> dict[str, int]:
    """Batch find-or-create for dim_product, same shape as
    resolve_account_keys_batch. items: (item_code, item_name) pairs."""
    distinct: dict[str, tuple[str, str]] = {}
    for item_code, item_name in items:
        source_record_id = item_code or item_name
        distinct[source_record_id] = (item_code, item_name)
    if not distinct:
        return {}

    result: dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT source_record_id, product_key FROM "{schema}".dim_product '
            f'WHERE tenant_id=%s AND entity_id=%s AND is_current AND source_record_id = ANY(%s)',
            (tenant_id, entity_id, list(distinct.keys())),
        )
        for source_record_id, product_key in cur.fetchall():
            result[source_record_id] = product_key

        missing = [sr for sr in distinct if sr not in result]
        for _chunk in _row_chunks(missing, params_per_row=6):
            values_sql = ", ".join(["(%s,%s,%s,%s,%s,%s)"] * len(_chunk))
            params: list = []
            for source_record_id in _chunk:
                item_code, item_name = distinct[source_record_id]
                params.extend([tenant_id, entity_id, item_code, item_name, load_run_id, source_record_id])
            cur.execute(
                f'INSERT INTO "{schema}".dim_product '
                f'(tenant_id, entity_id, source_item_code, source_item_name, load_run_id, source_record_id) '
                f'VALUES {values_sql} RETURNING source_record_id, product_key',
                params,
            )
            for source_record_id, product_key in cur.fetchall():
                result[source_record_id] = product_key
    return result


def resolve_location_keys_batch(conn, schema: str, tenant_id: str, entity_id: int,
                                    location_names: list[str], load_run_id: int) -> dict[str, int]:
    """Batch find-or-create for dim_location, keyed on location_name."""
    distinct = sorted({name for name in location_names if name})
    if not distinct:
        return {}

    result: dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT source_record_id, location_key FROM "{schema}".dim_location '
            f'WHERE tenant_id=%s AND entity_id=%s AND is_current AND source_record_id = ANY(%s)',
            (tenant_id, entity_id, distinct),
        )
        for source_record_id, location_key in cur.fetchall():
            result[source_record_id] = location_key

        missing = [name for name in distinct if name not in result]
        for _chunk in _row_chunks(missing, params_per_row=5):
            values_sql = ", ".join(["(%s,%s,%s,%s,%s)"] * len(_chunk))
            params: list = []
            for name in _chunk:
                params.extend([tenant_id, entity_id, name, load_run_id, name])
            cur.execute(
                f'INSERT INTO "{schema}".dim_location '
                f'(tenant_id, entity_id, location_name, load_run_id, source_record_id) '
                f'VALUES {values_sql} RETURNING source_record_id, location_key',
                params,
            )
            for source_record_id, location_key in cur.fetchall():
                result[source_record_id] = location_key
    return result


def write_channel_order_rows(conn, schema: str, tenant_id: str, entity_id: int, load_run_id: int,
                                 source_system: str, staged_rows: list[dict]) -> CanonicalWriteResult:
    """fact_channel_order_line, corpus/04 section 3.5. Same batched
    close-not-update discipline as write_gl_rows. customer_key is left NULL
    throughout -- dim_customer is not built (see the migration's own
    docstring), and this column is nullable in the literal DDL for exactly
    that reason."""
    result = CanonicalWriteResult()
    if not staged_rows:
        return result
    mapping_version_id = get_placeholder_mapping_version(conn, schema, tenant_id, entity_id)

    product_keys = resolve_product_keys_batch(
        conn, schema, tenant_id, entity_id,
        [(row["item_code"], row["item_name"]) for row in staged_rows], load_run_id,
    )
    channel_keys = {name: resolve_channel_key(conn, schema, tenant_id, entity_id, name)
                       for name in {row["channel"] for row in staged_rows}}

    by_source_record_id = {f'{row["order_id"]}#{row["line_no"]}': row for row in staged_rows}

    with conn.cursor() as cur:
        cur.execute(
            f'SELECT source_record_id, fact_id, row_hash FROM "{schema}".fact_channel_order_line '
            f'WHERE tenant_id=%s AND entity_id=%s AND is_current AND source_record_id = ANY(%s)',
            (tenant_id, entity_id, list(by_source_record_id.keys())),
        )
        existing = {sr: (fact_id, bytes(row_hash)) for sr, fact_id, row_hash in cur.fetchall()}

        to_close: list[int] = []
        to_insert: list[tuple[str, dict]] = []
        for source_record_id, row in by_source_record_id.items():
            match = existing.get(source_record_id)
            if match and match[1] == row["row_hash"]:
                result.unchanged += 1
                continue
            if match:
                to_close.append(match[0])
                result.closed_and_reinserted += 1
            else:
                result.inserted += 1
            to_insert.append((source_record_id, row))

        if to_close:
            cur.execute(
                f'UPDATE "{schema}".fact_channel_order_line SET valid_to = now(), is_current = false '
                f'WHERE fact_id = ANY(%s)',
                (to_close,),
            )

        for _chunk in _row_chunks(to_insert, params_per_row=31):
            values_sql = ", ".join(["(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"] * len(_chunk))
            params: list = []
            for source_record_id, row in _chunk:
                period_key = f'{row["event_date"].year:04d}-{row["event_date"].month:02d}'
                product_key = product_keys[row["item_code"] or row["item_name"]]
                channel_key = channel_keys[row["channel"]]
                params.extend([
                    tenant_id, entity_id, row["order_id"], row["line_no"], row["event_date"], period_key,
                    channel_key, row["channel_sub"], product_key, row["quantity"], row["gross_amount"],
                    row["discount_amount"], row["net_amount"], row["shipping_charged"], row["commission_amount"],
                    row["shipping_cost"], row["payment_fee"], row["revenue_model"], row["order_type"],
                    row["commission_earned"], row["advertising_earned"], row["platform_fee_earned"],
                    row["is_returned"], row["return_date"], row["return_reason"], row["settlement_date"],
                    load_run_id, source_system, source_record_id, row["row_hash"], mapping_version_id,
                ])
            cur.execute(
                f'INSERT INTO "{schema}".fact_channel_order_line '
                f'(tenant_id, entity_id, order_id, line_no, event_date, period_key, channel_key, channel_sub, '
                f' product_key, quantity, gross_amount, discount_amount, net_amount, shipping_charged, '
                f' commission_amount, shipping_cost, payment_fee, revenue_model, order_type, commission_earned, '
                f' advertising_earned, platform_fee_earned, is_returned, return_date, return_reason, settlement_date, '
                f' load_run_id, source_system, source_record_id, row_hash, mapping_version_id'
                f') VALUES {values_sql}',
                params,
            )
    return result


def stamp_declared_uom(conn, schema: str, tenant_id: str, entity_id: int,
                          product_keys_and_uoms: list[tuple[int, str]]) -> dict[int, str]:
    """D-041: 'a single declared unit per product family.' dim_product.
    declared_uom is set from the FIRST uom ever seen for a product and never
    changed afterward (corpus/04 section 3.6: 'a second unit arriving for
    the same product raises an exception rather than being converted' --
    SPEQULA has no authority to convert tonnes to pieces, so the reference
    point itself must stay fixed, not drift to whatever arrived most
    recently). Returns {product_key: declared_uom} for every product
    referenced, for the caller to compare incoming rows against and decide
    which ones mismatch -- src/quality/checks.check_mixed_uom does that
    comparison as an actual exception, this function only establishes and
    returns the reference point."""
    product_keys = sorted({pk for pk, _uom in product_keys_and_uoms})
    if not product_keys:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT product_key, declared_uom FROM "{schema}".dim_product '
            f'WHERE tenant_id=%s AND entity_id=%s AND product_key = ANY(%s) AND is_current',
            (tenant_id, entity_id, product_keys),
        )
        declared = {pk: uom for pk, uom in cur.fetchall()}

        first_seen_uom: dict[int, str] = {}
        for product_key, uom in product_keys_and_uoms:
            first_seen_uom.setdefault(product_key, uom)

        to_stamp = [(pk, first_seen_uom[pk]) for pk in product_keys
                       if declared.get(pk) is None and pk in first_seen_uom]
        for product_key, uom in to_stamp:
            cur.execute(
                f'UPDATE "{schema}".dim_product SET declared_uom = %s '
                f'WHERE tenant_id=%s AND entity_id=%s AND product_key=%s AND is_current',
                (uom, tenant_id, entity_id, product_key),
            )
            declared[product_key] = uom
    return declared


def write_production_output_rows(conn, schema: str, tenant_id: str, entity_id: int, load_run_id: int,
                                     source_system: str, staged_rows: list[dict]) -> CanonicalWriteResult:
    """fact_production_output, corpus/04 section 3.6. Same batched
    close-not-update discipline as write_gl_rows. Every row is written
    regardless of whether its uom matches dim_product.declared_uom --
    'nothing is ever overwritten or deleted' (CLAUDE.md invariant 4) applies
    to the data itself; the mismatch is surfaced separately as a blocking
    exception (src/quality/checks.check_mixed_uom, D-041) so per-unit
    metrics can refuse to compute rather than silently averaging across
    units, without the ingestion pipeline discarding the row that revealed
    the problem."""
    result = CanonicalWriteResult()
    if not staged_rows:
        return result
    mapping_version_id = get_placeholder_mapping_version(conn, schema, tenant_id, entity_id)

    product_keys = resolve_product_keys_batch(
        conn, schema, tenant_id, entity_id,
        [(row["item_code"], row["item_name"]) for row in staged_rows], load_run_id,
    )
    location_keys = resolve_location_keys_batch(
        conn, schema, tenant_id, entity_id, [row["plant_or_line"] for row in staged_rows], load_run_id,
    )
    stamp_declared_uom(conn, schema, tenant_id, entity_id, [
        (product_keys[row["item_code"] or row["item_name"]], row["uom"]) for row in staged_rows
    ])

    by_source_record_id = {f'{row["period_key"]}#{row["plant_or_line"]}#{row["item_code"]}': row
                              for row in staged_rows}

    with conn.cursor() as cur:
        cur.execute(
            f'SELECT source_record_id, fact_id, row_hash FROM "{schema}".fact_production_output '
            f'WHERE tenant_id=%s AND entity_id=%s AND is_current AND source_record_id = ANY(%s)',
            (tenant_id, entity_id, list(by_source_record_id.keys())),
        )
        existing = {sr: (fact_id, bytes(row_hash)) for sr, fact_id, row_hash in cur.fetchall()}

        to_close: list[int] = []
        to_insert: list[tuple[str, dict]] = []
        for source_record_id, row in by_source_record_id.items():
            match = existing.get(source_record_id)
            if match and match[1] == row["row_hash"]:
                result.unchanged += 1
                continue
            if match:
                to_close.append(match[0])
                result.closed_and_reinserted += 1
            else:
                result.inserted += 1
            to_insert.append((source_record_id, row))

        if to_close:
            cur.execute(
                f'UPDATE "{schema}".fact_production_output SET valid_to = now(), is_current = false '
                f'WHERE fact_id = ANY(%s)',
                (to_close,),
            )

        for _chunk in _row_chunks(to_insert, params_per_row=20):
            values_sql = ", ".join(["(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"] * len(_chunk))
            params: list = []
            for source_record_id, row in _chunk:
                product_key = product_keys[row["item_code"] or row["item_name"]]
                location_key = location_keys[row["plant_or_line"]]
                params.extend([
                    tenant_id, entity_id, row["event_date"], row["period_key"], location_key, row["plant_or_line"],
                    product_key, row["qty_produced"], row["qty_rejected"], row["uom"], row["input_qty"],
                    row["input_uom"], row["available_hours"], row["running_hours"], row["power_units"],
                    load_run_id, source_system, source_record_id, row["row_hash"], mapping_version_id,
                ])
            cur.execute(
                f'INSERT INTO "{schema}".fact_production_output '
                f'(tenant_id, entity_id, event_date, period_key, location_key, line_code, product_key, '
                f' qty_produced, qty_rejected, uom, input_qty, input_uom, available_hours, running_hours, '
                f' power_units, load_run_id, source_system, source_record_id, row_hash, mapping_version_id'
                f') VALUES {values_sql}',
                params,
            )
    return result
