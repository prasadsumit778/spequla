"""Tenant deletion, corpus/12 sprint 7: "Retention and deletion paths."

Nothing about a financial fact is ever overwritten or deleted (CLAUDE.md
invariant 4) -- this is a different operation entirely: a tenant leaving
the pilot and asking for their data gone. delete_tenant() is destructive
and irreversible by design (DROP SCHEMA ... CASCADE cannot be undone), so
every caller path into it must be an explicit, confirmed, named request --
this module does not schedule or auto-trigger deletion on any timer. No
retention PERIOD is invented here: the corpus never states one (see
OPEN_QUESTIONS.md OQ-005), so this module exposes only an on-request
deletion path, never a background job that decides when to fire it.

What survives: app.tenant's own row (tombstoned via deleted_at, per
db/migrations/shared/0008), and app.audit_log (SPEQULA's own record that
the tenant existed and was deleted, including who requested it and why --
retained permanently, deliberately never purged).

What is destroyed: the tenant's entire analytical schema (every financial
fact, every mapping, every report) via DROP SCHEMA CASCADE, and every
PII-bearing app-schema row for that tenant (token_map -- literally the
token-to-real-name resolution -- source_file, load_run, query_log).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone


class TenantAlreadyDeleted(Exception):
    pass


class TenantNotFound(Exception):
    pass


@dataclass
class DeletionResult:
    tenant_id: str
    schema_name: str
    deleted_at: datetime
    requested_by: str
    reason: str


def delete_tenant(conn, tenant_id: str, requested_by: str, reason: str) -> DeletionResult:
    """Irreversible. conn must be a connection with privileges to DROP
    SCHEMA and DELETE across app-schema tables -- the same connection
    db/migrations/runner.py uses, not a per-request tenant-scoped one.

    D-068 (corpus/00, resolved 2026-08-24, OQ-005): this is deliberately the
    ONLY deletion path. Request-triggered only -- named requester, named
    reason, both required by this signature -- confirmed as policy, not a
    placeholder pending a retention-window decision. No background job
    anywhere purges a tenant automatically after any elapsed time; if a
    time-based policy is later declared, that's new scheduled-job code, not
    a change to this function.

    Order matters and is deliberate:
      1. Look up and validate the tenant (not already deleted, exists).
      2. Write the audit_log record FIRST, while the tenant_id FK target
         (app.tenant's row) still definitely exists and before anything is
         destroyed -- if a later step fails, the fact that deletion was
         requested is not lost.
      3. Drop the tenant's analytical schema.
      4. Purge PII-bearing app-schema rows for this tenant. source_file
         before load_run (source_file.load_run_id references load_run,
         same FK-safe order tests/conftest.py's tenant fixture teardown
         already uses).
      5. Tombstone app.tenant: deleted_at set, workos_organization_id
         cleared (so a future WorkOS session for that org can no longer
         resolve into a dead schema), name and schema_name left as the
         historical record.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT schema_name, deleted_at FROM app.tenant WHERE tenant_id = %s", (tenant_id,))
        row = cur.fetchone()
    if row is None:
        raise TenantNotFound(f"no tenant {tenant_id}")
    schema_name, deleted_at = row
    if deleted_at is not None:
        raise TenantAlreadyDeleted(f"tenant {tenant_id} was already deleted at {deleted_at}")
    if not requested_by:
        raise ValueError("delete_tenant requires a named requester")
    if not reason:
        raise ValueError("delete_tenant requires a reason")

    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO app.audit_log (tenant_id, actor, action, object_type, object_ref, detail) "
            "VALUES (%s, %s, 'tenant_deletion', 'tenant', %s, %s)",
            (tenant_id, requested_by, tenant_id,
             json.dumps({"schema_name": schema_name, "reason": reason, "requested_at": now.isoformat()})),
        )
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        cur.execute("DELETE FROM app.source_file WHERE tenant_id = %s", (tenant_id,))
        cur.execute("DELETE FROM app.load_run WHERE tenant_id = %s", (tenant_id,))
        cur.execute("DELETE FROM app.token_map WHERE tenant_id = %s", (tenant_id,))
        cur.execute("DELETE FROM app.query_log WHERE tenant_id = %s", (tenant_id,))
        cur.execute(
            "UPDATE app.tenant SET deleted_at = %s, workos_organization_id = NULL WHERE tenant_id = %s",
            (now, tenant_id),
        )
    conn.commit()
    return DeletionResult(tenant_id=tenant_id, schema_name=schema_name, deleted_at=now,
                              requested_by=requested_by, reason=reason)
