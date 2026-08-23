"""Tokenisation of party names at ingestion.

Implements corpus/02 section 8 and D-058 (resolved): "On ingestion, every
person and party name is written to token_map and replaced in the canonical
fact tables with a stable per-tenant token." Employees are excluded from
model-reachable views entirely, not tokenised (D-058) -- this module only
ever tokenises entity_type 'customer' or 'vendor'.

Scope note for sprint 1. fact_gl_entry's customer_key/vendor_key columns
reference dim_customer/dim_vendor, neither of which is in sprint 1 (see the
sequencing decision in the sprint 0 plan: those FKs are deferred, nullable).
So sprint 1 tokenisation does the part that is buildable now -- for every
party_name found in a staged GL row, ensure a token exists in token_map and
never let the real name reach anywhere else in the canonical schema -- without
yet attaching that token to a specific fact row via a surrogate key. Once
dim_customer/dim_vendor land in a later sprint, existing token_map rows are
reused, not regenerated: the mapping from real name to token is stable per
tenant from the moment a name is first seen.

The storage backend is behind a small Protocol so the token-generation logic
itself (format, per-tenant sequencing) is unit-testable without a live
Postgres connection.
"""
from __future__ import annotations

from typing import Protocol

TOKEN_PREFIX = {"customer": "CUST", "vendor": "VENDOR"}


class TokenStore(Protocol):
    def find_token(self, tenant_id: str, entity_type: str, real_name: str) -> str | None: ...
    def next_sequence(self, tenant_id: str, entity_type: str) -> int: ...
    def insert(self, tenant_id: str, entity_type: str, real_name: str, token: str) -> None: ...


class InMemoryTokenStore:
    """Test double. Mirrors app.token_map's (tenant_id, token) uniqueness."""

    def __init__(self):
        self._by_name: dict[tuple, str] = {}
        self._seq: dict[tuple, int] = {}

    def find_token(self, tenant_id, entity_type, real_name):
        return self._by_name.get((tenant_id, entity_type, real_name))

    def next_sequence(self, tenant_id, entity_type):
        key = (tenant_id, entity_type)
        self._seq[key] = self._seq.get(key, 0) + 1
        return self._seq[key]

    def insert(self, tenant_id, entity_type, real_name, token):
        self._by_name[(tenant_id, entity_type, real_name)] = token


class PgTokenStore:
    """Real backend: app.token_map, per db/migrations/shared/0005_token_map.sql."""

    def __init__(self, conn):
        self.conn = conn

    def find_token(self, tenant_id, entity_type, real_name):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT token FROM app.token_map WHERE tenant_id=%s AND entity_type=%s AND real_name=%s",
                (tenant_id, entity_type, real_name),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def next_sequence(self, tenant_id, entity_type):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM app.token_map WHERE tenant_id=%s AND entity_type=%s",
                (tenant_id, entity_type),
            )
            return cur.fetchone()[0] + 1

    def insert(self, tenant_id, entity_type, real_name, token):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app.token_map (tenant_id, entity_type, token, real_name) VALUES (%s, %s, %s, %s)",
                (tenant_id, entity_type, token, real_name),
            )

    def find_tokens(self, tenant_id: str, entity_type: str, real_names: list[str]) -> dict[str, str]:
        """Batch form of find_token: one round trip for every name already
        seen, instead of one round trip per name -- what a GL file with a
        few hundred distinct parties across thousands of lines actually
        needs."""
        if not real_names:
            return {}
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT real_name, token FROM app.token_map "
                "WHERE tenant_id=%s AND entity_type=%s AND real_name = ANY(%s)",
                (tenant_id, entity_type, real_names),
            )
            return {r[0]: r[1] for r in cur.fetchall()}

    def insert_many(self, tenant_id: str, entity_type: str, name_token_pairs: list[tuple[str, str]]) -> None:
        """Batch form of insert: one multi-row INSERT for every new name in
        this file, instead of one INSERT per name."""
        if not name_token_pairs:
            return
        values_sql = ", ".join(["(%s,%s,%s,%s)"] * len(name_token_pairs))
        params = []
        for real_name, token in name_token_pairs:
            params.extend([tenant_id, entity_type, token, real_name])
        with self.conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO app.token_map (tenant_id, entity_type, token, real_name) VALUES {values_sql}",
                params,
            )


def tokenise_batch(store: PgTokenStore, tenant_id: str, entity_type: str,
                     real_names: list[str | None]) -> dict[str, str]:
    """Batch form of tokenise(): returns {real_name: token} for every
    distinct non-empty name in real_names, creating token_map rows for any
    not already seen. Three round trips total (find existing, count for the
    starting sequence number, insert the new ones) regardless of how many
    rows or how many distinct names are in the file, versus tokenise()'s up
    to three round trips PER NAME. Same D-058 restriction: entity_type must
    be 'customer' or 'vendor', never 'employee'."""
    if entity_type not in TOKEN_PREFIX:
        raise ValueError(f"entity_type must be 'customer' or 'vendor', never 'employee' (D-058): got {entity_type!r}")

    distinct_names = sorted({n.strip() for n in real_names if n and n.strip()})
    if not distinct_names:
        return {}

    result = store.find_tokens(tenant_id, entity_type, distinct_names)
    missing = [n for n in distinct_names if n not in result]
    if missing:
        start_seq = store.next_sequence(tenant_id, entity_type)
        new_pairs = [(name, f"{TOKEN_PREFIX[entity_type]}_{start_seq + i:04d}") for i, name in enumerate(missing)]
        store.insert_many(tenant_id, entity_type, new_pairs)
        result.update(new_pairs)
    return result


def tokenise(store: TokenStore, tenant_id: str, entity_type: str, real_name: str | None) -> str | None:
    """Returns a stable per-tenant token for real_name, creating one if this
    is the first time this name has been seen for this tenant. Returns None
    unchanged if real_name is empty -- there is nothing to tokenise."""
    if entity_type not in TOKEN_PREFIX:
        raise ValueError(f"entity_type must be 'customer' or 'vendor', never 'employee' (D-058): got {entity_type!r}")
    if not real_name or not real_name.strip():
        return None
    real_name = real_name.strip()

    existing = store.find_token(tenant_id, entity_type, real_name)
    if existing:
        return existing

    seq = store.next_sequence(tenant_id, entity_type)
    token = f"{TOKEN_PREFIX[entity_type]}_{seq:04d}"
    store.insert(tenant_id, entity_type, real_name, token)
    return token
