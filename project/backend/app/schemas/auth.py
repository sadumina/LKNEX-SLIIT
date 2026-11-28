"""Request and response models for account registration and login."""

from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator

UserRole = Literal["user", "systems_engineer", "hr", "admin"]

DOMAIN_ROLES: dict[str, UserRole] = {
    "admin.com": "admin",
    "systemengineer.com": "systems_engineer",
    "hr.com": "hr",
}


def role_for_email(email: str) -> UserRole:
    return DOMAIN_ROLES.get(email.rpartition("@")[2], "user")


class Credentials(BaseModel):
    email: str = Field(max_length=254, pattern=r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$")
    password: SecretStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class RegisteredUser(BaseModel):
    id: int
    email: str
    role: UserRole


class SignupCredentials(Credentials):
    signup_code: SecretStr | None = None


class LoginResponse(BaseModel):
    user: RegisteredUser
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
