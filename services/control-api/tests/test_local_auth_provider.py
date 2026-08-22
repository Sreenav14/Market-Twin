import pytest
from markettwin_control_api.auth.providers.local import (
    InvalidLocalIdentityError,
    LocalAuthDisabledError,
    LocalAuthProvider,
)


@pytest.mark.asyncio
async def test_local_auth_creates_normalized_identity() -> None:
    provider = LocalAuthProvider(app_env="local")

    identity = await provider.authenticate(
        email="  User@Example.COM ",
        display_name=" Test User ",
    )

    assert identity.issuer == "markettwin-local"
    assert identity.subject == "user@example.com"

    assert identity.email == "User@Example.COM"
    assert identity.normalized_email == "user@example.com"

    assert identity.display_name == "Test User"


@pytest.mark.asyncio
async def test_local_auth_rejects_empty_email() -> None:
    provider = LocalAuthProvider(app_env="local")

    with pytest.raises(InvalidLocalIdentityError):
        await provider.authenticate(
            email="   ",
        )


@pytest.mark.asyncio
async def test_local_auth_is_disabled_in_production() -> None:
    provider = LocalAuthProvider(
        app_env="production",
    )

    with pytest.raises(LocalAuthDisabledError):
        await provider.authenticate(
            email="user@example.com",
        )
