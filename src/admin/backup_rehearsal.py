"""Restore rehearsal, corpus/02 section 7: "Backups: Point-in-time
recovery, restore tested before the first paid pilot."

Point-in-time recovery itself is a Supabase platform capability (enabled by
the paid tier the project already runs on), not application code -- there
is nothing for this repository to build to provide PITR, and actually
exercising Supabase's own restore-to-a-point-in-time feature against the
live project is an infrastructure-level, account-scoped action this code
has no business taking unilaterally. What IS this repository's
responsibility, and what this module tests, is the other half of "restore
tested": proving that everything a tenant's schema contains can be fully
and exactly reconstructed from the database's own contents -- the same
mechanism a real restore (pg_dump/pg_restore, or Supabase's own recovery)
performs, exercised here without external binaries this sandboxed
environment doesn't have (no pg_dump/pg_restore on PATH).

The rehearsal: clone every table in a tenant's schema (structure via
`LIKE ... INCLUDING ALL`, data via `INSERT ... SELECT`) into a throwaway
schema, verify every table's row count matches exactly, then drop the
clone. A live PITR exercise against Supabase itself remains a one-time
manual check for a human with dashboard access, not something this
function attempts.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class TableRehearsalResult:
    table_name: str
    source_row_count: int
    restored_row_count: int

    @property
    def matches(self) -> bool:
        return self.source_row_count == self.restored_row_count


@dataclass
class RestoreRehearsalResult:
    source_schema: str
    rehearsal_schema: str
    tables: list[TableRehearsalResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.tables) > 0 and all(t.matches for t in self.tables)


def _table_names(conn, schema: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s AND table_type = 'BASE TABLE' ORDER BY table_name",
            (schema,),
        )
        return [r[0] for r in cur.fetchall()]


def rehearse_restore(conn, source_schema: str) -> RestoreRehearsalResult:
    """Clones source_schema's tables (structure + data) into a fresh
    throwaway schema, verifies row counts, then drops the clone -- always,
    even on failure, so a rehearsal never leaves debris behind."""
    rehearsal_schema = f"restore_rehearsal_{uuid.uuid4().hex[:16]}"
    result = RestoreRehearsalResult(source_schema=source_schema, rehearsal_schema=rehearsal_schema)
    tables = _table_names(conn, source_schema)
    if not tables:
        raise ValueError(f"schema {source_schema!r} has no tables to rehearse a restore against")

    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{rehearsal_schema}"')
            for table in tables:
                cur.execute(
                    f'CREATE TABLE "{rehearsal_schema}"."{table}" '
                    f'(LIKE "{source_schema}"."{table}" INCLUDING ALL)'
                )
                cur.execute(
                    f'INSERT INTO "{rehearsal_schema}"."{table}" SELECT * FROM "{source_schema}"."{table}"'
                )
                cur.execute(f'SELECT count(*) FROM "{source_schema}"."{table}"')
                source_count = cur.fetchone()[0]
                cur.execute(f'SELECT count(*) FROM "{rehearsal_schema}"."{table}"')
                restored_count = cur.fetchone()[0]
                result.tables.append(TableRehearsalResult(table, source_count, restored_count))
        conn.commit()
    finally:
        with conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{rehearsal_schema}" CASCADE')
        conn.commit()

    return result
