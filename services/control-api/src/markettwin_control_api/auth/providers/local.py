"""Development-only authentication provider."""

from typing import Final

from markettwin_control_api.auth.models import AuthenticatedIdentity

LOCAL_AUTH_ISSUER: Final[str] = "markettwin-local"


class LocalAuthDisabledError(RuntimeError):
    """Local authentication was attempted outside the local environment."""


class InvalidLocalIdentityError(ValueError):
    """The supplied local identity is invalid."""


class LocalAuthProvider:
    """Development-only identity provider."""

    def __init__(self, *, app_env: str) -> None:
        self._app_env = app_env

    async def authenticate(
        self,
        *,
        email: str,
        display_name: str | None = None,
    ) -> AuthenticatedIdentity:
        """Authenticate a local development identity."""

        if self._app_env != "local":
            raise LocalAuthDisabledError(
                "Local authentication is only available in the local environment."
            )

        cleaned_email = email.strip()

        if not cleaned_email:
            raise InvalidLocalIdentityError("Email is required.")

        normalized_email = cleaned_email.casefold()

        cleaned_display_name = (
            display_name.strip() if display_name is not None and display_name.strip() else None
        )

        return AuthenticatedIdentity(
            issuer=LOCAL_AUTH_ISSUER,
            subject=normalized_email,
            email=cleaned_email,
            normalized_email=normalized_email,
            display_name=cleaned_display_name,
        )
