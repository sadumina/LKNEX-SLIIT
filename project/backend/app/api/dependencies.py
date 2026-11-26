"""Shared API security dependencies."""

import os
import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
)


def require_api_key(
    provided_key: str | None = Security(api_key_header),
):
    expected_key = os.getenv("AEGIS_API_KEY")

    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail="API security is not configured",
        )

    if not provided_key or not secrets.compare_digest(
        provided_key, expected_key
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )

    return True



def require_audit_role(
    provided_key: str | None = Security(api_key_header),
):
    """Authenticate admin or reviewer using server-configured API keys."""
    admin_key = os.getenv("AEGIS_API_KEY")
    reviewer_key = os.getenv("AEGIS_REVIEWER_API_KEY")

    if not admin_key or not reviewer_key:
        raise HTTPException(
            status_code=503,
            detail="API security is not configured",
        )

    if not provided_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )

    if secrets.compare_digest(provided_key, admin_key):
        return "admin"

    if secrets.compare_digest(provided_key, reviewer_key):
        return "reviewer"

    raise HTTPException(
        status_code=401,
        detail="Invalid or missing API key",
    )


def require_admin(
    role: str = Security(require_audit_role),
):
    """Allow only authenticated admins."""
    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )
    return role
