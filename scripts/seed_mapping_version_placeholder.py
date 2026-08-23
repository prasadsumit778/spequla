"""Seed the version_no=0 placeholder mapping_version row for a tenant/entity.

db/migrations/tenant/0005_mapping_version.sql's own comment states "Every
tenant is seeded with exactly one placeholder row -- version_no = 0,
status = 'draft'" so that fact_gl_entry.mapping_version_id (NOT NULL) has
something to reference before Sprint 2's mapping loop approves a real
version (src/ingest/canonical.py's get_placeholder_mapping_version reads
exactly this row). The migration only creates the TABLE; nothing in the
codebase actually ran the INSERT -- caught only once this project ran
against a live Postgres for the first time, since every DB-dependent test
skips cleanly without one.

Usage: python3 scripts/seed_mapping_version_placeholder.py --schema tenant_xxx --tenant-id UUID [--entity-id 1]
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import psycopg

DB_URL = os.environ.get("DATABASE_URL", "postgresql://spequla:spequla@localhost:5432/spequla")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--schema", required=True)
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--entity-id", type=int, default=1)
    args = p.parse_args()

    with psycopg.connect(DB_URL, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT 1 FROM "{args.schema}".mapping_version WHERE tenant_id=%s AND entity_id=%s AND version_no=0',
                (args.tenant_id, args.entity_id),
            )
            if cur.fetchone():
                print(f"placeholder version_no=0 already seeded for entity {args.entity_id} in {args.schema}")
                return 0
            cur.execute(
                f'INSERT INTO "{args.schema}".mapping_version '
                f'(tenant_id, entity_id, version_no, status, effective_from, created_by) '
                f"VALUES (%s, %s, 0, 'draft', %s, 'system')",
                (args.tenant_id, args.entity_id, date(1900, 1, 1)),
            )
    print(f"Seeded placeholder mapping_version (version_no=0) for entity {args.entity_id} into {args.schema}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
