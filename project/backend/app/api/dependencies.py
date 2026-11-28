"""Shared API security dependencies."""

import hashlib
import os
import secrets
import sqlite3
import time

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.database import db
from app.schemas.auth import RegisteredUser, role_for_email

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
)
session_bearer = HTTPBearer(auto_error=False)


def require_account(
    credentials: HTTPAuthorizationCredentials | None = Security(session_bearer),
    connection: sqlite3.Connection = Depends(db.get_db),
) -> RegisteredUser:
    """Authenticate the session and use the account's current database role."""
    if credentials:
        token_hash = hashlib.sha256(credentials.credentials.encode("utf-8")).hexdigest()
        account = connection.execute(
            "SELECT u.id, u.email, u.account_role AS role FROM user_sessions s "
            "JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ?",
            (token_hash, int(time.time())),
        ).fetchone()
        if account and account["role"] == role_for_email(account["email"]):
            return RegisteredUser(**dict(account))
    raise HTTPException(
        status_code=401,
        detail="Missing, invalid, or expired bearer token",
        headers={"WWW-Authenticate": "Bearer"},
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
    request: Request,
    provided_key: str | None = Security(api_key_header),
    credentials: HTTPAuthorizationCredentials | None = Security(session_bearer),
    connection: sqlite3.Connection = Depends(db.get_db),
):
    """Allow systems engineer and admin accounts and existing audit API-key clients."""
    if "authorization" in request.headers:
        account = require_account(credentials, connection)
        if account.role not in ("systems_engineer", "admin"):
            raise HTTPException(status_code=403, detail="Systems engineer or admin access required")
        return account.role

    if not provided_key:
        raise HTTPException(
            status_code=401,
            detail="Missing bearer token or API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    admin_key = os.getenv("AEGIS_API_KEY")
    reviewer_key = os.getenv("AEGIS_REVIEWER_API_KEY")

    if not admin_key or not reviewer_key:
        raise HTTPException(
            status_code=503,
            detail="API security is not configured",
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
