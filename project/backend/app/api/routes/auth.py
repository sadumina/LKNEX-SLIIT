"""Email and password registration and login."""

import hashlib
import os
import secrets
import sqlite3
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.database import db
from app.schemas.auth import (
    Credentials,
    LoginResponse,
    RegisteredUser,
    SignupCredentials,
    role_for_email,
)

PASSWORD_ITERATIONS = 600_000
SESSION_TTL_SECONDS = 3600
SIGNUP_CODE_ENV = {
    "admin": "AEGIS_ADMIN_SIGNUP_CODE",
    "systems_engineer": "AEGIS_SYSTEMS_ENGINEER_SIGNUP_CODE",
    "hr": "AEGIS_HR_SIGNUP_CODE",
}


class AuthRoute(APIRoute):
    """Exclude submitted credential values from validation errors."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                details = [
                    {key: error[key] for key in ("loc", "msg", "type")}
                    for error in exc.errors()
                ]
                raise HTTPException(status_code=422, detail=details) from None

        return handle


router = APIRouter(prefix="/api/auth", tags=["Authentication"], route_class=AuthRoute)


def _derive_password_hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    ).hex()


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(
    credentials: SignupCredentials,
    connection: sqlite3.Connection = Depends(db.get_db),
) -> RegisteredUser:
    """Create an account with an 8–128 character password containing uppercase and lowercase letters and a number.

    Admin, systems engineer, and HR domains require the corresponding signup code.
    """
    password = credentials.password.get_secret_value()
    if not (
        8 <= len(password) <= 128
        and any(character.isupper() for character in password)
        and any(character.islower() for character in password)
        and any(character.isdecimal() for character in password)
    ):
        raise HTTPException(
            status_code=422,
            detail="Password must be 8–128 characters and include an uppercase letter, a lowercase letter, and a number",
        )

    role = role_for_email(credentials.email)
    if role != "user":
        expected_code = os.getenv(SIGNUP_CODE_ENV[role])
        supplied_code = credentials.signup_code
        if not expected_code or supplied_code is None or not secrets.compare_digest(
            supplied_code.get_secret_value().encode("utf-8"), expected_code.encode("utf-8")
        ):
            raise HTTPException(status_code=403, detail="A valid signup code is required for this email domain")

    salt = secrets.token_bytes(16)
    password_hash = f"{salt.hex()}:{_derive_password_hash(password, salt)}"
    with connection:
        user = connection.execute(
            "INSERT INTO users (email, password_hash, created_at, account_role) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (email) DO NOTHING RETURNING id, email, account_role AS role",
            (credentials.email, password_hash, db.utc_now(), role),
        ).fetchone()

    if user is None:
        raise HTTPException(status_code=409, detail="Email is already registered")
    return RegisteredUser(**dict(user))


@router.post("/login")
def login(
    credentials: Credentials,
    response: Response,
    connection: sqlite3.Connection = Depends(db.get_db),
) -> LoginResponse:
    """Verify account credentials and issue a bearer token valid for one hour."""
    password = credentials.password.get_secret_value()
    if len(password) > 128:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = connection.execute(
        "SELECT id, email, account_role AS role, password_hash FROM users WHERE email = ?",
        (credentials.email,),
    ).fetchone()
    # Do the same password derivation for unknown accounts.
    salt_hex, expected = user["password_hash"].split(":") if user else ("00" * 16, "00" * 32)
    actual = _derive_password_hash(password, bytes.fromhex(salt_hex))
    if not secrets.compare_digest(actual, expected) or user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user["role"] != role_for_email(user["email"]):
        raise HTTPException(status_code=403, detail="Account role must be approved for this email domain")

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    now = int(time.time())
    with connection:
        connection.execute("DELETE FROM user_sessions WHERE expires_at <= ?", (now,))
        connection.execute(
            "INSERT INTO user_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user["id"], now + SESSION_TTL_SECONDS),
        )

    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(
        user=RegisteredUser(id=user["id"], email=user["email"], role=user["role"]),
        access_token=token,
        expires_in=SESSION_TTL_SECONDS,
    )
