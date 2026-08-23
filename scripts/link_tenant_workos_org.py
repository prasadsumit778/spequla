"""Link a SPEQULA tenant to a WorkOS Organization.

Run once per pilot customer, after creating both the tenant (see
scripts/create_tenant.py) and the WorkOS Organization (in the WorkOS
dashboard, or via the API). From this point on, every request for that
tenant is authorized by the WorkOS session's org_id claim matching this
column -- never by a client-supplied header.

Usage: python3 scripts/link_tenant_workos_org.py --tenant-id UUID --workos-org-id org_...
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg

DB_URL = os.environ.get("DATABASE_URL", "postgresql://spequla:spequla@localhost:5432/spequla")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--workos-org-id", required=True, help="e.g. org_01H...")
    args = p.parse_args()

    with psycopg.connect(DB_URL, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE app.tenant SET workos_organization_id = %s WHERE tenant_id = %s RETURNING name",
                (args.workos_org_id, args.tenant_id),
            )
            row = cur.fetchone()
    if not row:
        print(f"no tenant found with tenant_id={args.tenant_id}", file=sys.stderr)
        return 1
    print(f"Linked tenant {row[0]!r} ({args.tenant_id}) to WorkOS organization {args.workos_org_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
