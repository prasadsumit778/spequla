"""Real session verification via WorkOS.

Implements CLAUDE.md section 6 ("Bought auth: Clerk or WorkOS. Never build
auth") -- WorkOS was the provider chosen in chat. Replaces the sprint 1 stub
that trusted a caller-supplied header.

The frontend (web/, via @workos-inc/authkit-nextjs) forwards the WorkOS
AuthKit access token as a standard `Authorization: Bearer <token>` header.
This module verifies that token's signature against WorkOS's JWKS (so a
forged token is rejected, not just an absent one) and reads the user id,
organization id and role directly from its verified claims -- never from
anything the client asserts unsigned.

Role and organization claims depend on WorkOS dashboard configuration, not on
anything this code can set: the four roles from corpus/02 section 2 must
exist as WorkOS custom Roles, and each pilot user's Organization Membership
must be assigned one of them, for the `role` claim to be populated. See the
sprint 2 handoff note / README for the exact dashboard steps -- this code
cannot create them itself, "bought auth" means WorkOS owns that surface.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

import jwt
import workos
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

VALID_ROLES = {"promoter", "client_finance_lead", "spequla_analyst", "admin"}
# Per corpus/02 section 2: only these two roles touch ingestion in P0.
UPLOAD_ALLOWED_ROLES = {"spequla_analyst", "client_finance_lead"}

_bearer = HTTPBearer(auto_error=True)


@dataclass
class Session:
    user_id: str
    org_id: str | None
    role: str | None


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. WorkOS integration cannot start without it -- see "
            f"the WorkOS dashboard setup steps in the sprint 2 handoff notes. "
            f"Fail loudly, per CLAUDE.md section 8: no default that masks a missing input."
        )
    return value


@lru_cache(maxsize=1)
def _workos_client() -> "workos.WorkOSClient":
    return workos.WorkOSClient(
        api_key=_require_env("WORKOS_API_KEY"),
        client_id=_require_env("WORKOS_CLIENT_ID"),
    )


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    jwks_url = _workos_client().user_management.get_jwks_url()
    return PyJWKClient(jwks_url, cache_keys=True)


def current_session(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> Session:
    token = creds.credentials
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        # WorkOS AuthKit access tokens are RS256-signed and do not set a
        # single fixed `aud` claim to check against, per WorkOS's own docs --
        # the JWKS endpoint itself is already scoped to WORKOS_CLIENT_ID, so
        # signature verification against it is the trust boundary here.
        claims = jwt.decode(token, signing_key.key, algorithms=["RS256"], options={"verify_aud": False})
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"invalid or expired session: {e}")

    return Session(user_id=claims["sub"], org_id=claims.get("org_id"), role=claims.get("role"))


def require_role(session: Session = Depends(current_session)) -> Session:
    if session.role not in VALID_ROLES:
        raise HTTPException(
            status_code=403,
            detail=f"unknown or unconfigured role: {session.role!r}. "
                    f"Check the WorkOS custom Roles and this user's Organization Membership.",
        )
    return session


def require_upload_role(session: Session = Depends(require_role)) -> Session:
    if session.role not in UPLOAD_ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail=f"role {session.role!r} cannot upload files, per corpus/02 section 2")
    return session


def require_admin_role(session: Session = Depends(require_role)) -> Session:
    """corpus/02 section 2: admin is 'Engineering. Tenancy, connectors,
    deploys. No default access to client data' -- granting/revoking
    cross-tenant employee access and viewing the audit log are tenancy
    operations, gated to this role specifically, not to spequla_analyst
    (which has broad access WITHIN its own tenant, a different thing)."""
    if session.role != "admin":
        raise HTTPException(status_code=403, detail=f"role {session.role!r} is not admin -- corpus/02 section 2")
    return session
