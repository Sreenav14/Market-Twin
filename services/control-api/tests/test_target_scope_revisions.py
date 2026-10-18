"""Exact-origin revision validation and authorization boundary regressions."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from markettwin_control_api.api import targets
from markettwin_control_api.api.target_authorizations import require_authorization_role
from markettwin_control_api.persistence.repositories import TargetRecord
from markettwin_control_api.persistence.repositories.authorization_repository import (
    TargetAuthorizationRepository,
)
from markettwin_control_api.persistence.repositories.target_repository import (
    AllowedOriginRecord,
    TargetRepository,
)
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession


def payload(*origins: str) -> targets.RequestScopeRevision:
    return targets.RequestScopeRevision(
        name="Reviewed application scope",
        origins=list(origins),
        request_basis="Owned synthetic test environment.",
    )


@pytest.mark.parametrize(
    "bad",
    [
        "https://*.example.invalid",
        "https://example.invalid/path",
        "https://example.invalid?token=secret",
        "https://example.invalid#secret",
        "https://user:password@example.invalid",
        "file://example.invalid",
        "https://example.invalid:0",
        "https://example.invalid:65536",
        "https://exa mple.invalid",
        "https://example.invalid\\evil",
        "https://example.invalid\n",
        "https://example.invalid:abc",
    ],
)
def test_unsafe_origin_rejected(bad: str) -> None:
    with pytest.raises(HTTPException) as error:
        targets.exact_scope_origins(
            payload("https://example.invalid", bad), "https://example.invalid"
        )
    assert error.value.status_code == 422


def test_scope_is_exact_and_normalized_without_automatic_subdomains() -> None:
    origins = targets.exact_scope_origins(
        payload("https://EXAMPLE.invalid:443/", "https://console.example.invalid"),
        "https://example.invalid/start",
    )
    assert origins == (
        AllowedOriginRecord("https", "example.invalid", None, False),
        AllowedOriginRecord("https", "console.example.invalid", None, False),
    )


@pytest.mark.parametrize(
    "values",
    [
        ("https://console.example.invalid",),
        ("https://example.invalid", "https://EXAMPLE.invalid:443/"),
    ],
)
def test_scope_requires_base_origin_and_no_duplicates(values: tuple[str, ...]) -> None:
    with pytest.raises(HTTPException):
        targets.exact_scope_origins(payload(*values), "https://example.invalid")


def test_request_basis_cannot_be_padding() -> None:
    with pytest.raises(ValidationError):
        targets.RequestScopeRevision(
            name="New scope", origins=["https://example.invalid"], request_basis="          x"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["member", "viewer"])
async def test_only_owner_admin_can_authorize_scope(
    monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    application = SimpleNamespace(workspace_id=uuid4())
    monkeypatch.setattr(
        "markettwin_control_api.api.target_authorizations.ApplicationRepository",
        MagicMock(return_value=SimpleNamespace(get_for_user=AsyncMock(return_value=application))),
    )
    monkeypatch.setattr(
        "markettwin_control_api.api.target_authorizations.WorkspaceRepository",
        MagicMock(
            return_value=SimpleNamespace(
                get_for_user=AsyncMock(return_value=SimpleNamespace(role=role))
            )
        ),
    )
    target = TargetRecord(
        uuid4(), uuid4(), "Original", "test", "https://example.invalid", False, "active", ()
    )
    with pytest.raises(HTTPException) as error:
        await require_authorization_role(
            database_session=cast(AsyncSession, MagicMock()), target=target, user_id=uuid4()
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_revision_creation_never_modifies_parent() -> None:
    session = MagicMock(spec=AsyncSession)

    async def flush() -> None:
        for call in session.add.call_args_list:
            record = call.args[0]
            if getattr(record, "id", None) is None:
                record.id = uuid4()

    session.flush = AsyncMock(side_effect=flush)
    parent = TargetRecord(
        uuid4(),
        uuid4(),
        "Original",
        "test",
        "https://example.invalid",
        False,
        "active",
        (AllowedOriginRecord("https", "example.invalid", None, False),),
    )
    old_origins = parent.allowed_origins
    requested = (*old_origins, AllowedOriginRecord("https", "console.example.invalid", None, False))
    revision = await TargetRepository(session).create_scope_revision(
        parent=parent, name="New scope", origins=requested
    )
    assert parent.allowed_origins == old_origins
    assert revision.target_id != parent.target_id
    assert revision.scope_parent_id == parent.target_id
    assert revision.allowed_origins == requested
    assert not any(origin.include_subdomains for origin in revision.allowed_origins)


@pytest.mark.asyncio
async def test_scope_request_is_pending_and_grants_no_authority() -> None:
    session = MagicMock(spec=AsyncSession)

    async def flush() -> None:
        record = session.add.call_args.args[0]
        record.id = uuid4()

    session.flush = AsyncMock(side_effect=flush)
    record = await TargetAuthorizationRepository(session).request_scope_authorization(
        target_id=uuid4(),
        user_id=uuid4(),
        request_basis="Owned local fixture scope.",
    )
    assert record.status == "pending"
    assert record.authorized_by_user_id is None
    assert record.authorized_at is None
