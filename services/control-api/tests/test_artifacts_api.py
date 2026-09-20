"""Security tests for evidence artifact access."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from markettwin_control_api.api import artifacts


class AsyncContext:
    """Minimal async context manager used by the endpoint tests."""

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


def request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
        }
    )


def database_runtime(_request: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        session_factory=lambda: AsyncContext(object())
    )


def repository_factory(repository: object) -> object:
    def factory(_session: object) -> object:
        return repository

    return factory


@pytest.mark.asyncio
async def test_inaccessible_test_run_never_signs_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A user without TestRun access must never receive artifact access."""

    test_run_id = uuid4()
    artifact_id = uuid4()
    user_id = uuid4()

    test_run_repository = SimpleNamespace(
        get_for_user=AsyncMock(return_value=None)
    )

    artifact_repository_factory = Mock()
    signer_factory = Mock()

    monkeypatch.setattr(
        artifacts,
        "get_authenticated_user_id",
        AsyncMock(return_value=user_id),
    )
    monkeypatch.setattr(
        artifacts,
        "get_database_runtime",
        database_runtime,
    )
    monkeypatch.setattr(
        artifacts,
        "TestRunRepository",
        repository_factory(test_run_repository),
    )
    monkeypatch.setattr(
        artifacts,
        "ArtifactAccessRepository",
        artifact_repository_factory,
    )
    monkeypatch.setattr(
        artifacts,
        "ArtifactUrlSigner",
        signer_factory,
    )

    with pytest.raises(HTTPException) as error:
        await artifacts.get_artifact_access(
            test_run_id=test_run_id,
            artifact_id=artifact_id,
            request=request(),
        )

    assert error.value.status_code == 404

    test_run_repository.get_for_user.assert_awaited_once_with(
        test_run_id=test_run_id,
        user_id=user_id,
    )

    artifact_repository_factory.assert_not_called()
    signer_factory.assert_not_called()


@pytest.mark.asyncio
async def test_artifact_from_other_test_run_is_not_signed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mismatched artifact must never receive a signed URL."""

    test_run_id = uuid4()
    artifact_id = uuid4()
    user_id = uuid4()

    test_run_repository = SimpleNamespace(
        get_for_user=AsyncMock(
            return_value=SimpleNamespace(
                test_run_id=test_run_id
            )
        )
    )

    artifact_repository = SimpleNamespace(
        get_for_test_run=AsyncMock(return_value=None)
    )

    signer_factory = Mock()

    monkeypatch.setattr(
        artifacts,
        "get_authenticated_user_id",
        AsyncMock(return_value=user_id),
    )
    monkeypatch.setattr(
        artifacts,
        "get_database_runtime",
        database_runtime,
    )
    monkeypatch.setattr(
        artifacts,
        "TestRunRepository",
        repository_factory(test_run_repository),
    )
    monkeypatch.setattr(
        artifacts,
        "ArtifactAccessRepository",
        repository_factory(artifact_repository),
    )
    monkeypatch.setattr(
        artifacts,
        "ArtifactUrlSigner",
        signer_factory,
    )

    with pytest.raises(HTTPException) as error:
        await artifacts.get_artifact_access(
            test_run_id=test_run_id,
            artifact_id=artifact_id,
            request=request(),
        )

    assert error.value.status_code == 404

    artifact_repository.get_for_test_run.assert_awaited_once_with(
        artifact_id=artifact_id,
        test_run_id=test_run_id,
    )

    signer_factory.assert_not_called()


@pytest.mark.asyncio
async def test_authorized_artifact_returns_temporary_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An authorized artifact should receive a short-lived signed URL."""

    test_run_id = uuid4()
    artifact_id = uuid4()
    execution_id = uuid4()
    user_id = uuid4()

    test_run_repository = SimpleNamespace(
        get_for_user=AsyncMock(
            return_value=SimpleNamespace(
                test_run_id=test_run_id
            )
        )
    )

    artifact_record = SimpleNamespace(
        artifact_id=artifact_id,
        test_run_id=test_run_id,
        execution_id=execution_id,
        step_id=113,
        artifact_type="screenshot",
        storage_provider="minio",
        bucket="markettwin-local",
        object_key=(
            "executions/example/steps/113/"
            "action-0001-navigate.png"
        ),
        content_type="image/png",
        size_bytes=481229,
        sha256="abc123",
    )

    artifact_repository = SimpleNamespace(
        get_for_test_run=AsyncMock(
            return_value=artifact_record
        )
    )

    signer = SimpleNamespace(
        create_download_url=Mock(
            return_value="http://example.invalid/signed"
        )
    )

    def make_signer(**_kwargs: object) -> SimpleNamespace:
        return signer

    monkeypatch.setattr(
        artifacts,
        "get_authenticated_user_id",
        AsyncMock(return_value=user_id),
    )
    monkeypatch.setattr(
        artifacts,
        "get_database_runtime",
        database_runtime,
    )
    monkeypatch.setattr(
        artifacts,
        "TestRunRepository",
        repository_factory(test_run_repository),
    )
    monkeypatch.setattr(
        artifacts,
        "ArtifactAccessRepository",
        repository_factory(artifact_repository),
    )
    monkeypatch.setattr(
        artifacts,
        "get_settings",
        lambda: SimpleNamespace(
            s3_region="us-east-1",
            s3_endpoint_url="http://localhost:9000",
        ),
    )
    monkeypatch.setattr(
        artifacts,
        "ArtifactUrlSigner",
        make_signer,
    )

    response = await artifacts.get_artifact_access(
        test_run_id=test_run_id,
        artifact_id=artifact_id,
        request=request(),
    )

    assert response.artifact_id == artifact_id
    assert response.artifact_type == "screenshot"
    assert response.content_type == "image/png"
    assert response.url == "http://example.invalid/signed"
    assert response.expires_in_seconds == 300

    signer.create_download_url.assert_called_once_with(
        bucket="markettwin-local",
        object_key=(
            "executions/example/steps/113/"
            "action-0001-navigate.png"
        ),
    )
