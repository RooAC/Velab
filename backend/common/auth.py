"""Lightweight API key authentication for protected backend endpoints."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from config import settings


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def require_api_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Require a configured API key when AUTH_ENABLED=true.

    Local development defaults to AUTH_ENABLED=false. Production should set
    AUTH_ENABLED=true and provide AUTH_API_KEY through the environment.
    """
    if not settings.AUTH_ENABLED:
        return

    expected = (settings.AUTH_API_KEY or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is enabled but AUTH_API_KEY is not configured",
        )

    supplied = (x_api_key or _extract_bearer_token(authorization) or "").strip()
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
