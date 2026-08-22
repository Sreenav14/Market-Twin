from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_control_api.auth.providers.local import LocalAuthProvider
from markettwin_control_api.auth.services import (
    LocalAuthService,
    LocalIdentityNotApprovedError,
)
from markettwin_control_api.persistence.repositories import ResolvedIdentity


@pytest.mark.asyncio
async def test_local_auth_service_returns_approved_identity() -> None:
    repository = AsyncMock()

    resolved_identity = ResolvedIdentity(
        identity_id=uuid4(),
        user_id=uuid4(),
        email="User@Example.COM",
        normalized_email="user@example.com",
        display_name="Test User",
    )

    repository.resolve_active_identity.return_value = resolved_identity

    service = LocalAuthService(
        provider=LocalAuthProvider(app_env="local"),
        identity_repository=repository,
    )

    result = await service.authenticate(
        email="  User@Example.COM ",
    )

    assert result == resolved_identity

    repository.resolve_active_identity.assert_awaited_once_with(
        issuer="markettwin-local",
        subject="user@example.com",
    )


@pytest.mark.asyncio
async def test_local_auth_service_rejects_unapproved_identity() -> None:
    repository = AsyncMock()
    repository.resolve_active_identity.return_value = None

    service = LocalAuthService(
        provider=LocalAuthProvider(app_env="local"),
        identity_repository=repository,
    )

    with pytest.raises(LocalIdentityNotApprovedError):
        await service.authenticate(
            email="unknown@example.com",
        )


@pytest.mark.asyncio
async def test_local_auth_service_cannot_bypass_environment_guard() -> None:
    repository = AsyncMock()

    service = LocalAuthService(
        provider=LocalAuthProvider(app_env="production"),
        identity_repository=repository,
    )

    with pytest.raises(RuntimeError):
        await service.authenticate(
            email="user@example.com",
        )

    repository.resolve_active_identity.assert_not_awaited()
