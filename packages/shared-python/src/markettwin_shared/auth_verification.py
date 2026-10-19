"""Frozen, target-approved identity verification contract for HITL resumes."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AuthVerificationPolicy(BaseModel):
    """Exact origin and marker approved before a run starts.

    The marker value and account reference are configuration secrets-adjacent and
    therefore excluded from repr. Neither may be populated from page content.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    origin: str = Field(min_length=8, max_length=300)
    marker_selector: str = Field(min_length=1, max_length=200)
    expected_marker: str = Field(min_length=1, max_length=200, repr=False)
    role: str = Field(min_length=1, max_length=64)
    account_reference: str = Field(min_length=1, max_length=128, repr=False)
    auth_only_origins: tuple[str, ...] = Field(default=(), max_length=8, strict=False)

    @field_validator("auth_only_origins")
    @classmethod
    def auth_origins_are_exact(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("Authentication-only origins must be unique.")
        return tuple(cls.exact_origin_only(value) for value in values)

    @model_validator(mode="after")
    def target_is_not_an_identity_provider(self) -> AuthVerificationPolicy:
        if self.origin in self.auth_only_origins:
            raise ValueError("The verified application origin cannot be authentication-only.")
        return self

    @field_validator("origin")
    @classmethod
    def exact_origin_only(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.hostname != parsed.hostname.lower()
            or value.endswith("://")
        ):
            raise ValueError("Authentication origin must be a canonical exact origin.")
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError("Authentication origin has an invalid port.") from error
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("Authentication origin has an invalid port.")
        default_port = 443 if parsed.scheme == "https" else 80
        if port == default_port:
            raise ValueError("Authentication origin must omit its default port.")
        return value

    @field_validator("marker_selector")
    @classmethod
    def selector_is_bounded_and_static(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or "\x00" in cleaned:
            raise ValueError("Authentication marker selector is invalid.")
        return cleaned

    @field_validator("expected_marker")
    @classmethod
    def marker_is_static(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Authentication marker must be a nonempty exact value.")
        return value

    @field_validator("role")
    @classmethod
    def role_is_identifier(cls, value: str) -> str:
        cleaned = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}", cleaned):
            raise ValueError("Authentication role must be a nonsecret identifier.")
        return cleaned

    @field_validator("account_reference")
    @classmethod
    def account_reference_is_nonsecret(cls, value: str) -> str:
        cleaned = value.strip()
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", cleaned)
            or any(
                term in cleaned.casefold()
                for term in ("password", "token", "secret", "credential", "cookie", "bearer")
            )
        ):
            raise ValueError("Account reference must be a nonsecret identifier.")
        return cleaned
