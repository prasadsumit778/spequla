#!/usr/bin/env bash
# One command: clone, install, migrate, seed.
# Implements corpus/12 sprint 0 exit criterion: "a developer can clone, run
# one command, and have a working environment with the synthetic company
# loaded."
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== bootstrap: starting Postgres + object storage =="
docker compose up -d
echo "waiting for Postgres..."
until docker compose exec -T postgres pg_isready -U spequla >/dev/null 2>&1; do sleep 1; done
echo "waiting for object storage..."
until curl -sf http://localhost:9000/minio/health/live >/dev/null 2>&1; do sleep 1; done

echo "== bootstrap: installing python dependencies =="
pip install -q -r requirements.txt

export DATABASE_URL="${DATABASE_URL:-postgresql://spequla:spequla@localhost:5432/spequla}"
export PYTHONPATH=.

echo "== bootstrap: applying shared migrations =="
python3 db/migrations/runner.py

echo "== bootstrap: registering tenants =="
TEST_TENANT=$(python3 scripts/create_tenant.py "sprint0-test-tenant")
MFG_TENANT=$(python3 scripts/create_tenant.py "Synthetic Manufacturer Co" --synthetic)
CONSUMER_TENANT=$(python3 scripts/create_tenant.py "Synthetic Consumer Co" --synthetic)

echo "== bootstrap: applying tenant migrations to all registered schemas =="
python3 db/migrations/runner.py

echo "== bootstrap: seeding dim_date (FY24 to FY30) for both synthetic tenants =="
MFG_TENANT_ID=$(echo "$MFG_TENANT" | grep tenant_id= | cut -d= -f2)
MFG_SCHEMA=$(echo "$MFG_TENANT" | grep schema_name= | cut -d= -f2)
CONSUMER_TENANT_ID=$(echo "$CONSUMER_TENANT" | grep tenant_id= | cut -d= -f2)
CONSUMER_SCHEMA=$(echo "$CONSUMER_TENANT" | grep schema_name= | cut -d= -f2)
python3 scripts/seed_dim_date.py --schema "$MFG_SCHEMA" --start 2022-04-01 --end 2029-03-31
python3 scripts/seed_dim_date.py --schema "$CONSUMER_SCHEMA" --start 2022-04-01 --end 2029-03-31
python3 scripts/seed_entity.py --schema "$MFG_SCHEMA" --tenant-id "$MFG_TENANT_ID" --name "Synthetic Manufacturer Co"
python3 scripts/seed_entity.py --schema "$CONSUMER_SCHEMA" --tenant-id "$CONSUMER_TENANT_ID" --name "Synthetic Consumer Co"

echo "== bootstrap: seeding the version_no=0 placeholder mapping_version (corpus/04 s3.7) =="
python3 scripts/seed_mapping_version_placeholder.py --schema "$MFG_SCHEMA" --tenant-id "$MFG_TENANT_ID"
python3 scripts/seed_mapping_version_placeholder.py --schema "$CONSUMER_SCHEMA" --tenant-id "$CONSUMER_TENANT_ID"

echo "== bootstrap: generating synthetic reference dataset (seed=42) =="
python3 synthetic/generate.py --company manufacturer --seed 42 --tenant-id "$MFG_TENANT_ID" --land
python3 synthetic/generate.py --company consumer --seed 42 --tenant-id "$CONSUMER_TENANT_ID" --land

echo "== bootstrap complete =="
echo "Test tenant:      $TEST_TENANT"
echo "Manufacturer:     $MFG_TENANT"
echo "Consumer:         $CONSUMER_TENANT"
echo "Both synthetic companies are generated, landed in object storage under their"
echo "tenant-prefixed paths, and ready for sprint 1 ingestion."
