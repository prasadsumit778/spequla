"""Sprint 7: named, time-bound, logged employee access, corpus/02 section 7."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.access.grants import (
    GrantNotActive,
    active_grant,
    grant_access,
    list_grants,
    log_access,
    require_active_grant,
    revoke_access,
)


def test_access_refused_without_a_grant(conn, tenant):
    tenant_id, _schema = tenant
    with pytest.raises(GrantNotActive):
        require_active_grant(conn, tenant_id, "user_nobody")


def test_grant_is_named_and_time_bound(conn, tenant):
    tenant_id, _schema = tenant
    expires_at = datetime.now(timezone.utc) + timedelta(hours=2)
    g = grant_access(conn, tenant_id, "user_engineer", "Jane Engineer", granted_by="user_admin",
                        reason="investigating a support ticket", expires_at=expires_at)
    assert g.employee_name == "Jane Engineer"
    assert g.is_active

    found = require_active_grant(conn, tenant_id, "user_engineer")
    assert found.grant_id == g.grant_id

    with conn.cursor() as cur:
        cur.execute(
            "SELECT action, actor, detail FROM app.audit_log WHERE tenant_id = %s AND action = 'access_grant'",
            (tenant_id,),
        )
        row = cur.fetchone()
    assert row[0] == "access_grant"
    assert row[1] == "user_admin"
    assert row[2]["employee_name"] == "Jane Engineer"


def test_expired_grant_does_not_authorise_access(conn, tenant):
    tenant_id, _schema = tenant
    # grant_access refuses an already-past expiry outright...
    with pytest.raises(ValueError):
        grant_access(conn, tenant_id, "user_x", "X", granted_by="user_admin", reason="test",
                        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    # ...and a grant that expires a moment from now stops authorising once past that instant.
    g = grant_access(conn, tenant_id, "user_y", "Y", granted_by="user_admin", reason="test",
                        expires_at=datetime.now(timezone.utc) + timedelta(seconds=1))
    with conn.cursor() as cur:
        cur.execute("UPDATE app.employee_access_grant SET expires_at = now() - interval '1 second' WHERE grant_id = %s",
                       (g.grant_id,))
    conn.commit()
    assert active_grant(conn, tenant_id, "user_y") is None
    with pytest.raises(GrantNotActive):
        require_active_grant(conn, tenant_id, "user_y")


def test_revoked_grant_immediately_stops_authorising_and_is_logged(conn, tenant):
    tenant_id, _schema = tenant
    g = grant_access(conn, tenant_id, "user_z", "Z", granted_by="user_admin", reason="test",
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    require_active_grant(conn, tenant_id, "user_z")  # does not raise

    revoke_access(conn, g.grant_id, revoked_by="user_admin")
    with pytest.raises(GrantNotActive):
        require_active_grant(conn, tenant_id, "user_z")

    with conn.cursor() as cur:
        cur.execute("SELECT action, actor FROM app.audit_log WHERE tenant_id = %s AND action = 'access_revoke'",
                       (tenant_id,))
        row = cur.fetchone()
    assert row == ("access_revoke", "user_admin")


def test_access_events_are_logged_separately_from_the_grant(conn, tenant):
    tenant_id, _schema = tenant
    grant_access(conn, tenant_id, "user_w", "W", granted_by="user_admin", reason="test",
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    log_access(conn, tenant_id, "user_w", "client_data_access", {"endpoint": "test"})

    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM app.audit_log WHERE tenant_id = %s AND action = 'client_data_access'",
            (tenant_id,),
        )
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM app.audit_log WHERE tenant_id = %s AND action = 'access_grant'", (tenant_id,))
        assert cur.fetchone()[0] == 1  # the grant and the access are two distinct log rows


def test_list_grants_returns_all_grants_for_a_tenant(conn, tenant):
    tenant_id, _schema = tenant
    grant_access(conn, tenant_id, "user_a", "A", granted_by="user_admin", reason="r1",
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    grant_access(conn, tenant_id, "user_b", "B", granted_by="user_admin", reason="r2",
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    grants = list_grants(conn, tenant_id)
    assert {g.employee_user_id for g in grants} == {"user_a", "user_b"}
