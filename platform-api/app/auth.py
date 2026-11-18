"""Read-only bearer authentication for the platform API.

The dashboard never receives cluster-admin kubeconfig access; it only receives
a token that authorizes these read endpoints.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from .config import settings


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_token(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    if not settings.auth_enabled:
        return "auth-disabled"
    candidate = ""
    if authorization and authorization.lower().startswith("bearer "):
        candidate = authorization[7:].strip()
    elif x_api_key:
        candidate = x_api_key
    if not candidate:
        raise _unauthorized("Bearer token required")
    if not secrets.compare_digest(candidate, settings.api_token):
        raise _unauthorized("Invalid token")
    return "viewer"
