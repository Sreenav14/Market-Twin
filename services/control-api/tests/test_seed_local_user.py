from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from markettwin_control_api.dev import seed_local_user as seed_module
from markettwin_control_api.persistence.models import (
    User,
    UserIdentity,
    Workspace,
    WorkspaceMember,
)


class AsyncContext:
    """Minimal asynchronous context manager for mocked sessions."""

    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> bool:
        return False


def make_result(
    *,
    scalar_one_or_none: object = None,
    scalar_one: object = None,
    scalar_first: object = None,
) -> MagicMock:
    """Create a SQLAlchemy-like result mock."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.scalar_one.return_value = scalar_one
    result.scalars.return_value.first.return_value = scalar_first
    return result


def make_database(session: MagicMock) -> SimpleNamespace:
    """Create a database runtime mock around a session."""
    return SimpleNamespace(
        session_factory=MagicMock(return_value=AsyncContext(session)),
        close=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_seed_local_user_creates_user_identity_workspace_and_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    session.begin.return_value = AsyncContext(None)
    session.execute = AsyncMock(
        side_effect=[
            make_result(),
            make_result(),
            make_result(),
        ]
    )
    session.flush = AsyncMock()

    def assign_generated_id(model: object) -> None:
        if isinstance(model, (User, Workspace)):
            model.id = uuid4()

    session.add.side_effect = assign_generated_id
    database = make_database(session)

    def make_database_runtime(_settings: object) -> SimpleNamespace:
        return database

    monkeypatch.setattr(seed_module, "get_settings", lambda: SimpleNamespace(app_env="local"))
    monkeypatch.setattr(seed_module, "DatabaseRuntime", make_database_runtime)

    await seed_module.seed_local_user(
        email="  User@Example.COM ",
        display_name=" Test User ",
    )

    added_models = [call.args[0] for call in session.add.call_args_list]
    assert [type(model) for model in added_models] == [
        User,
        UserIdentity,
        Workspace,
        WorkspaceMember,
    ]
    assert added_models[0].normalized_email == "user@example.com"
    assert added_models[1].subject == "user@example.com"
    database.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_seed_local_user_repairs_membership_for_existing_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    identity = UserIdentity(
        id=uuid4(),
        user_id=user_id,
        issuer="markettwin-local",
        subject="user@example.com",
    )
    user = User(
        id=user_id,
        email="User@Example.COM",
        normalized_email="user@example.com",
        display_name="Test User",
        status="active",
        deleted_at=None,
    )

    session = MagicMock()
    session.begin.return_value = AsyncContext(None)
    session.execute = AsyncMock(
        side_effect=[
            make_result(scalar_one_or_none=identity),
            make_result(scalar_one=user),
            make_result(),
        ]
    )
    session.flush = AsyncMock()

    def assign_generated_id(model: object) -> None:
        if isinstance(model, Workspace):
            model.id = uuid4()

    session.add.side_effect = assign_generated_id
    database = make_database(session)

    def make_database_runtime(_settings: object) -> SimpleNamespace:
        return database

    monkeypatch.setattr(seed_module, "get_settings", lambda: SimpleNamespace(app_env="local"))
    monkeypatch.setattr(seed_module, "DatabaseRuntime", make_database_runtime)

    await seed_module.seed_local_user(
        email="user@example.com",
        display_name="Test User",
    )

    added_models = [call.args[0] for call in session.add.call_args_list]
    assert [type(model) for model in added_models] == [Workspace, WorkspaceMember]
    database.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_seed_local_user_requires_display_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_module, "get_settings", lambda: SimpleNamespace(app_env="local"))

    with pytest.raises(ValueError, match="Display name is required"):
        await seed_module.seed_local_user(email="user@example.com")


@pytest.mark.asyncio
async def test_seed_local_user_is_disabled_outside_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        seed_module,
        "get_settings",
        lambda: SimpleNamespace(app_env="production"),
    )

    with pytest.raises(RuntimeError, match="only available in the local environment"):
        await seed_module.seed_local_user(
            email="user@example.com",
            display_name="Test User",
        )
