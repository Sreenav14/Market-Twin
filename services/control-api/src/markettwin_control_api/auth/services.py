"""Authentication services."""

from markettwin_control_api.auth.providers.local import LocalAuthProvider
from markettwin_control_api.persistence.repositories import IdentityRepository, ResolvedIdentity


class LocalIdentityNotApprovedError(RuntimeError):
    """The local identity was not approved."""


class LocalAuthService:
    """Service for authenticating local identities."""

    def __init__(
        self,
        *,
        provider: LocalAuthProvider,
        identity_repository: IdentityRepository,
    ) -> None:
        self._provider = provider
        self._identity_repository = identity_repository

    async def authenticate(
        self,
        *,
        email: str,
    ) -> ResolvedIdentity:
        """Authenticate an approved local MarketTwin user."""

        identity = await self._provider.authenticate(
            email=email,
        )

        resolved_identity = await self._identity_repository.resolve_active_identity(
            issuer=identity.issuer,
            subject=identity.subject,
        )

        if resolved_identity is None:
            raise LocalIdentityNotApprovedError("The local identity was not approved.")

        return resolved_identity
