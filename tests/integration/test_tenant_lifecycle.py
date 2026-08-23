"""Sprint 7: retention and deletion paths, and the restore rehearsal,
corpus/12 sprint 7 / corpus/02 section 7."""
from __future__ import annotations

from src.admin.backup_rehearsal import rehearse_restore
from src.admin.tenant_lifecycle import TenantAlreadyDeleted, delete_tenant


def test_delete_tenant_drops_schema_tombstones_registry_and_logs(conn, tenant):
    tenant_id, schema_name = tenant

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (schema_name,))
        assert cur.fetchone() is not None, "the tenant fixture's schema must exist before deletion"

    result = delete_tenant(conn, tenant_id, requested_by="pytest-admin", reason="end of pilot")
    assert result.schema_name == schema_name

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (schema_name,))
        assert cur.fetchone() is None, "the schema must be gone after deletion"

        cur.execute("SELECT deleted_at, workos_organization_id FROM app.tenant WHERE tenant_id = %s", (tenant_id,))
        deleted_at, org_id = cur.fetchone()
        assert deleted_at is not None
        assert org_id is None

        cur.execute(
            "SELECT actor, action FROM app.audit_log WHERE tenant_id = %s AND action = 'tenant_deletion'",
            (tenant_id,),
        )
        row = cur.fetchone()
        assert row == ("pytest-admin", "tenant_deletion")

        cur.execute("SELECT count(*) FROM app.token_map WHERE tenant_id = %s", (tenant_id,))
        assert cur.fetchone()[0] == 0


def test_delete_tenant_is_not_repeatable(conn, tenant):
    tenant_id, _schema = tenant
    delete_tenant(conn, tenant_id, requested_by="pytest-admin", reason="first deletion")
    try:
        delete_tenant(conn, tenant_id, requested_by="pytest-admin", reason="second attempt")
        assert False, "a second deletion of the same tenant must be refused"
    except TenantAlreadyDeleted:
        pass


def test_delete_tenant_requires_a_named_requester_and_reason(conn, tenant):
    tenant_id, _schema = tenant
    try:
        delete_tenant(conn, tenant_id, requested_by="", reason="no requester")
        assert False
    except ValueError:
        pass
    try:
        delete_tenant(conn, tenant_id, requested_by="pytest-admin", reason="")
        assert False
    except ValueError:
        pass


def test_restore_rehearsal_row_counts_match_and_cleans_up(conn, tenant):
    tenant_id, schema_name = tenant
    result = rehearse_restore(conn, schema_name)
    assert result.passed
    assert len(result.tables) > 0
    for t in result.tables:
        assert t.matches, f"{t.table_name}: source={t.source_row_count} restored={t.restored_row_count}"

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (result.rehearsal_schema,))
        assert cur.fetchone() is None, "the rehearsal schema must be dropped after the run"
