"""Seed the single dim_entity row for pilot one.

Per corpus/04 table inventory: "Single row in pilot one. Present so
multi-entity needs no migration." entity_id=1 is the convention every
loader in src/ingest defaults to.

Usage: python3 scripts/seed_entity.py --schema tenant_xxx --tenant-id UUID --name "Company Name"
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg

DB_URL = os.environ.get("DATABASE_URL", "postgresql://spequla:spequla@localhost:5432/spequla")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--schema", required=True)
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--entity-id", type=int, default=1)
    args = p.parse_args()

    with psycopg.connect(DB_URL, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT 1 FROM "{args.schema}".dim_entity WHERE tenant_id=%s AND source_record_id=%s',
                (args.tenant_id, str(args.entity_id)),
            )
            if cur.fetchone():
                print(f"entity {args.entity_id} already seeded for {args.schema}")
                return 0
            cur.execute(
                f'INSERT INTO "{args.schema}".dim_entity '
                f'(tenant_id, entity_name, load_run_id, source_record_id) VALUES (%s, %s, 0, %s)',
                (args.tenant_id, args.name, str(args.entity_id)),
            )
    print(f"Seeded entity_id={args.entity_id} ({args.name}) into {args.schema}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
