"""Shared fixtures for sprint 1's integration tests.

These tests need a live Postgres (DATABASE_URL) with the migrations applied
-- exactly what CI's postgres service container provides (see
.github/workflows/ci.yml) and what `docker compose up` + `db/migrations/
runner.py` provides locally. If neither is reachable, tests here skip with a
clear reason rather than failing noisily, so `pytest tests/unit` (which has
no such dependency) is never affected.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

DB_URL = os.environ.get("DATABASE_URL", "postgresql://spequla:spequla@localhost:5432/spequla")
REPO_ROOT = Path(__file__).resolve().parent.parent


def _try_connect():
    import psycopg
    try:
        conn = psycopg.connect(DB_URL, connect_timeout=3)
        return conn
    except Exception as e:  # noqa: BLE001 -- deliberately broad: this is a reachability probe
        pytest.skip(f"Postgres not reachable at {DB_URL}: {e}. "
                     f"Run `docker compose up -d && python3 db/migrations/runner.py` first.")


@pytest.fixture(scope="session")
def db_available():
    conn = _try_connect()
    conn.close()
    return True


@pytest.fixture(scope="session")
def migrated(db_available):
    """Ensures shared migrations are applied at least once for the session."""
    result = subprocess.run(
        [sys.executable, "db/migrations/runner.py"],
        cwd=REPO_ROOT, env={**os.environ, "DATABASE_URL": DB_URL, "PYTHONPATH": "."},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"shared migration run failed:\n{result.stdout}\n{result.stderr}"
    return True


@pytest.fixture()
def tenant(migrated):
    """A fresh, isolated tenant schema for one test: registered, migrated,
    dim_date seeded. Torn down (schema dropped, tenant row deleted) after."""
    import psycopg

    tenant_id = str(uuid.uuid4())
    schema_name = f"tenant_{tenant_id.replace('-', '')}"
    conn = psycopg.connect(DB_URL, autocommit=True, connect_timeout=10)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO app.tenant (tenant_id, name, schema_name, is_synthetic) VALUES (%s, %s, %s, true)",
            (tenant_id, f"pytest-{tenant_id[:8]}", schema_name),
        )
    conn.close()

    result = subprocess.run(
        # --schema scopes this to just the tenant this fixture created --
        # see db/migrations/runner.py's module docstring for why looping
        # every registered tenant on every single test's setup does not
        # scale against a real, persistent database.
        [sys.executable, "db/migrations/runner.py", "--schema", schema_name],
        cwd=REPO_ROOT, env={**os.environ, "DATABASE_URL": DB_URL, "PYTHONPATH": "."},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"tenant migration run failed:\n{result.stdout}\n{result.stderr}"

    seed_result = subprocess.run(
        [sys.executable, "scripts/seed_dim_date.py", "--schema", schema_name,
          "--start", "2022-04-01", "--end", "2029-03-31"],
        cwd=REPO_ROOT, env={**os.environ, "DATABASE_URL": DB_URL, "PYTHONPATH": "."},
        capture_output=True, text=True,
    )
    assert seed_result.returncode == 0, f"dim_date seed failed:\n{seed_result.stdout}\n{seed_result.stderr}"

    entity_result = subprocess.run(
        [sys.executable, "scripts/seed_entity.py", "--schema", schema_name,
          "--tenant-id", tenant_id, "--name", "pytest entity"],
        cwd=REPO_ROOT, env={**os.environ, "DATABASE_URL": DB_URL, "PYTHONPATH": "."},
        capture_output=True, text=True,
    )
    assert entity_result.returncode == 0, f"entity seed failed:\n{entity_result.stdout}\n{entity_result.stderr}"

    mapping_placeholder_result = subprocess.run(
        [sys.executable, "scripts/seed_mapping_version_placeholder.py", "--schema", schema_name,
          "--tenant-id", tenant_id],
        cwd=REPO_ROOT, env={**os.environ, "DATABASE_URL": DB_URL, "PYTHONPATH": "."},
        capture_output=True, text=True,
    )
    assert mapping_placeholder_result.returncode == 0, (
        f"mapping_version placeholder seed failed:\n{mapping_placeholder_result.stdout}\n"
        f"{mapping_placeholder_result.stderr}"
    )

    yield tenant_id, schema_name

    conn = psycopg.connect(DB_URL, autocommit=True, connect_timeout=10)
    with conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        # source_file references load_run_id -- must delete in this order or
        # Postgres rejects the load_run delete with a foreign key violation.
        cur.execute("DELETE FROM app.source_file WHERE tenant_id = %s", (tenant_id,))
        cur.execute("DELETE FROM app.load_run WHERE tenant_id = %s", (tenant_id,))
        cur.execute("DELETE FROM app.audit_log WHERE tenant_id = %s", (tenant_id,))
        cur.execute("DELETE FROM app.token_map WHERE tenant_id = %s", (tenant_id,))
        cur.execute("DELETE FROM app.query_log WHERE tenant_id = %s", (tenant_id,))
        cur.execute("DELETE FROM app.employee_access_grant WHERE tenant_id = %s", (tenant_id,))
        cur.execute("DELETE FROM app.tenant WHERE tenant_id = %s", (tenant_id,))
    conn.close()


@pytest.fixture()
def conn(tenant):
    import psycopg
    tenant_id, _schema = tenant
    c = psycopg.connect(DB_URL, autocommit=True, connect_timeout=10)
    with c.cursor() as cur:
        # SET does not accept a bind parameter for its value -- set_config()
        # does. See src/api/deps/tenant.py's resolve_tenant for the same fix.
        cur.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant_id,))
    yield c
    c.close()
