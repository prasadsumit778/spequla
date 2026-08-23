"""Test 7 of 7: the model-reachable role cannot read token_map.

CLAUDE.md invariant 6: "The model-reachable database role has no grant on
token_map, audit_log, or any app table." Corpus/04 section 6.
"""
import psycopg
import pytest


def test_model_reachable_role_denied_on_token_map(conn, tenant):
    tenant_id, schema = tenant
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO app.token_map (tenant_id, entity_type, token, real_name) VALUES (%s, %s, %s, %s)",
            (tenant_id, "customer", "CUST_0001", "Acme Traders Pvt Ltd"),
        )

    with conn.cursor() as cur:
        cur.execute("SET ROLE model_reachable")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("SELECT * FROM app.token_map LIMIT 1")
        conn.rollback()
        cur.execute("RESET ROLE")


def test_model_reachable_role_can_read_canonical_facts(conn, tenant):
    """The negative test alone would pass trivially if the role had no
    grants anywhere -- confirm it CAN read canonical (tenant-schema) tables,
    per corpus/04 section 6: 'grants on canonical schemas only'."""
    tenant_id, schema = tenant
    with conn.cursor() as cur:
        cur.execute("SET ROLE model_reachable")
        cur.execute(f'SELECT count(*) FROM "{schema}".dim_date')
        cur.fetchone()  # must not raise
        cur.execute("RESET ROLE")
