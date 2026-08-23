"""Forward-only migration runner.

Implements corpus/04 section 6 ("Migrations. Loop over schemas in one deploy")
and corpus/12 sprint 0 item 2. Applies db/migrations/shared/*.sql once against
the `app` schema, then loops db/migrations/tenant/*.sql once per row in
app.tenant, substituting __SCHEMA__ for that tenant's schema_name. Nothing here
updates a migration in place -- a new numbered file is how a change ships.

--schema restricts the tenant loop to one schema instead of every registered
tenant. Production/CI's real migrate job never passes it -- "loop over
schemas in one deploy" is the correct behaviour there. It exists for
tests/conftest.py's per-test tenant fixture: without it, every single test's
setup re-applies (or re-checks) migrations for every tenant ANY earlier test
has ever created against that database, which is invisible against a
disposable local Postgres but turns into O(number of tests run so far) real
network round trips against a persistent remote one -- caught only once this
project's test suite ran against a live database for the first time.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent
DB_URL = os.environ.get("DATABASE_URL", "postgresql://spequla:spequla@localhost:5432/spequla")


def _applied_table_ddl() -> str:
    return """
    CREATE SCHEMA IF NOT EXISTS app;
    CREATE TABLE IF NOT EXISTS app.schema_migration (
        id          text PRIMARY KEY,   -- 'shared:0001_tenant_registry.sql' or '<schema>:0001_dim_date.sql'
        applied_at  timestamptz NOT NULL DEFAULT now()
    );
    """


def _apply_one(cur, migration_id: str, sql: str):
    cur.execute("SELECT 1 FROM app.schema_migration WHERE id = %s", (migration_id,))
    if cur.fetchone():
        print(f"  skip (already applied): {migration_id}")
        return
    print(f"  apply: {migration_id}")
    cur.execute(sql)
    cur.execute("INSERT INTO app.schema_migration (id) VALUES (%s)", (migration_id,))


def run_shared(cur):
    print("Shared migrations:")
    for path in sorted((MIGRATIONS_DIR / "shared").glob("*.sql")):
        _apply_one(cur, f"shared:{path.name}", path.read_text())


def ensure_tenant_schema(cur, schema_name: str):
    cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
    cur.execute(f'GRANT USAGE ON SCHEMA "{schema_name}" TO model_reachable')


def run_tenant(cur, schema_name: str):
    print(f"Tenant migrations for {schema_name}:")
    ensure_tenant_schema(cur, schema_name)
    for path in sorted((MIGRATIONS_DIR / "tenant").glob("*.sql")):
        sql = path.read_text().replace("__SCHEMA__", f'"{schema_name}"')
        _apply_one(cur, f"{schema_name}:{path.name}", sql)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", help="Apply tenant migrations to only this schema, "
                                           "instead of every registered tenant.")
    args = parser.parse_args()

    with psycopg.connect(DB_URL, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(_applied_table_ddl())
            run_shared(cur)
            if args.schema:
                schemas = [args.schema]
            else:
                cur.execute("SELECT schema_name FROM app.tenant ORDER BY created_at")
                schemas = [r[0] for r in cur.fetchall()]
                if not schemas:
                    print("No tenants registered yet -- shared migrations applied, "
                          "nothing to loop over. Run scripts/create_tenant.py first.")
            for schema_name in schemas:
                run_tenant(cur, schema_name)
    print("Migrations complete.")


if __name__ == "__main__":
    sys.exit(main())
