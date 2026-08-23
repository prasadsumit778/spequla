"""Tests for WorkOS session verification, corpus/02 section 2 / CLAUDE.md
section 6.

JWT signature verification is pure cryptography -- it does not need a live
WorkOS account to test correctly. This module generates its own RSA keypair,
signs test tokens with it, and monkeypatches the JWKS client so
current_session() verifies against a key it actually controls. That proves
the verification logic itself (valid signature accepted, forged signature
rejected, expired token rejected, role/org claims read correctly) without
touching the network.
"""
from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jwt import PyJWK

from src.api.deps import auth as auth_module
from src.api.deps.auth import current_session, require_role, require_upload_role

PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _sign(claims: dict, key=PRIVATE_KEY) -> str:
    return jwt.encode(claims, key, algorithm="RS256")


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key.public_key()


class _FakeJWKSClient:
    """Stands in for jwt.PyJWKClient -- returns our own test public key
    instead of fetching one over the network from a live WorkOS tenant."""

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(PRIVATE_KEY)


@pytest.fixture(autouse=True)
def fake_jwks(monkeypatch):
    auth_module._jwks_client.cache_clear()
    monkeypatch.setattr(auth_module, "_jwks_client", lambda: _FakeJWKSClient())
    yield
    # monkeypatch restores the original _jwks_client automatically; its
    # lru_cache was already cleared above, before the real function was
    # ever called in this test, so there is nothing stale to clear here.


def test_valid_token_is_accepted_and_claims_extracted():
    token = _sign({"sub": "user_123", "org_id": "org_abc", "role": "spequla_analyst"})
    session = current_session(_creds(token))
    assert session.user_id == "user_123"
    assert session.org_id == "org_abc"
    assert session.role == "spequla_analyst"


def test_token_signed_by_a_different_key_is_rejected():
    forged = _sign({"sub": "attacker", "org_id": "org_abc", "role": "admin"}, key=OTHER_PRIVATE_KEY)
    with pytest.raises(HTTPException) as exc_info:
        current_session(_creds(forged))
    assert exc_info.value.status_code == 401


def test_expired_token_is_rejected():
    expired = _sign({"sub": "user_123", "org_id": "org_abc", "role": "admin", "exp": int(time.time()) - 3600})
    with pytest.raises(HTTPException) as exc_info:
        current_session(_creds(expired))
    assert exc_info.value.status_code == 401


def test_token_with_no_role_claim_fails_require_role():
    token = _sign({"sub": "user_123", "org_id": "org_abc"})  # no role claim
    session = current_session(_creds(token))
    with pytest.raises(HTTPException) as exc_info:
        require_role(session)
    assert exc_info.value.status_code == 403


def test_promoter_role_cannot_upload():
    token = _sign({"sub": "user_123", "org_id": "org_abc", "role": "promoter"})
    session = current_session(_creds(token))
    session = require_role(session)
    with pytest.raises(HTTPException) as exc_info:
        require_upload_role(session)
    assert exc_info.value.status_code == 403


def test_spequla_analyst_can_upload():
    token = _sign({"sub": "user_123", "org_id": "org_abc", "role": "spequla_analyst"})
    session = current_session(_creds(token))
    session = require_role(session)
    result = require_upload_role(session)
    assert result.role == "spequla_analyst"


def test_env_var_missing_fails_loudly(monkeypatch):
    monkeypatch.delenv("WORKOS_API_KEY", raising=False)
    monkeypatch.delenv("WORKOS_CLIENT_ID", raising=False)
    auth_module._workos_client.cache_clear()
    with pytest.raises(RuntimeError, match="WORKOS_API_KEY"):
        auth_module._workos_client()
    auth_module._workos_client.cache_clear()
