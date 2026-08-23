"""Register a tenant in app.tenant. Run before db/migrations/runner.py to give
the migration loop a schema to apply tenant/ migrations to.

Usage: python3 scripts/create_tenant.py <name> [--synthetic]
"""
from __future__ import annotations

import os
import sys
import uuid

import psycopg

DB_URL = os.environ.get("DATABASE_URL", "postgresql://spequla:spequla@localhost:5432/spequla")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    name = sys.argv[1]
    is_synthetic = "--synthetic" in sys.argv[2:]

    tenant_id = uuid.uuid4()
    schema_name = f"tenant_{tenant_id.hex}"

    with psycopg.connect(DB_URL, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app.tenant (tenant_id, name, schema_name, is_synthetic) "
                "VALUES (%s, %s, %s, %s)",
                (str(tenant_id), name, schema_name, is_synthetic),
            )
    print(f"tenant_id={tenant_id}")
    print(f"schema_name={schema_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
