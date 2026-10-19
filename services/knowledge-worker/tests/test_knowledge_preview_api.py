"""The private preview adapter owns upload limits and temporary source files."""

import asyncio
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from litellm.exceptions import APIError
from litellm.exceptions import Timeout as ModelTimeout
from markettwin_knowledge_worker.config import KnowledgeWorkerSettings
from markettwin_knowledge_worker.extraction import ExtractionResult
from markettwin_knowledge_worker.knowledge_builder import (
    KnowledgeBuilder,
    KnowledgeOutputLimitError,
)
from markettwin_knowledge_worker.main import create_app
from markettwin_knowledge_worker.services.knowledge_preview_service import KnowledgePreviewService
from markettwin_shared.knowledge import KnowledgeBuildResult


def _client(builder: AsyncMock) -> TestClient:
    app = create_app()
    app.state.preview_service = KnowledgePreviewService(cast(KnowledgeBuilder, builder))
    return TestClient(app)


def _empty_result() -> KnowledgeBuildResult:
    return KnowledgeBuildResult(application_knowledge=(), artifacts=(), skills=())


@pytest.mark.asyncio
async def test_preview_refuses_excess_requests_before_multipart_parsing() -> None:
    started, release = asyncio.Event(), asyncio.Event()
    builder = AsyncMock(spec=KnowledgeBuilder)

    async def build(_: ExtractionResult) -> KnowledgeBuildResult:
        started.set()
        await release.wait()
        return _empty_result()

    builder.build.side_effect = build
    app = create_app(KnowledgeWorkerSettings(preview_max_concurrency=1))
    app.state.preview_service = KnowledgePreviewService(cast(KnowledgeBuilder, builder))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = asyncio.create_task(client.post(
            "/internal/v1/knowledge/preview",
            files={"file": ("screen.png", b"image bytes", "image/png")},
        ))
        await asyncio.wait_for(started.wait(), timeout=5)
        busy = await client.post("/internal/v1/knowledge/preview", content=b"invalid multipart")
        assert busy.status_code == 503
        assert busy.headers["retry-after"] == "5"
        release.set()
        assert (await first).status_code == 200
        assert (await client.post("/internal/v1/knowledge/preview")).status_code == 422


@pytest.mark.asyncio
async def test_preview_total_deadline_cancels_generation(tmp_path: Path) -> None:
    source = tmp_path / "image.png"
    source.write_bytes(b"image")
    cancelled = asyncio.Event()
    builder = AsyncMock(spec=KnowledgeBuilder)

    async def build(_: ExtractionResult) -> KnowledgeBuildResult:
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.set()
        return _empty_result()

    builder.build.side_effect = build
    service = KnowledgePreviewService(cast(KnowledgeBuilder, builder), timeout_seconds=0.1)
    with pytest.raises(TimeoutError):
        await service.preview(source)
    assert cancelled.is_set()


def test_preview_uses_existing_extractor_and_cleans_uploaded_image() -> None:
    paths: list[Path] = []

    async def build(extraction: ExtractionResult) -> KnowledgeBuildResult:
        units = extraction.units
        assert len(units) == 1
        assert units[0].source_locator == {"image": 1}
        assert units[0].media_path is not None
        assert units[0].media_path.read_bytes() == b"image bytes"
        paths.append(units[0].media_path)
        return _empty_result()

    builder = AsyncMock(spec=KnowledgeBuilder)
    builder.build.side_effect = build
    with _client(builder) as client:
        response = client.post(
            "/internal/v1/knowledge/preview",
            files={"file": ("screen.png", b"image bytes", "image/png")},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == {
        "name": "screen.png",
        "original_url": None,
        "source_item_count": 1,
        "processed_item_count": 1,
    }
    assert payload["evidence"][0]["source_locator"] == {"image": 1}
    assert payload["application_knowledge"] == []
    assert payload["artifacts"] == []
    assert payload["skills"] == []
    assert "media_path" not in response.text
    assert "base64" not in response.text
    assert not paths[0].exists()


def test_preview_rejects_unsupported_format_and_excess_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = AsyncMock(spec=KnowledgeBuilder)
    with _client(builder) as client:
        unsupported = client.post(
            "/internal/v1/knowledge/preview",
            files={"file": ("source.bin", b"abc", "application/octet-stream")},
        )
        monkeypatch.setenv("KNOWLEDGE_PREVIEW_MAX_BYTES", "2")
        oversized = client.post(
            "/internal/v1/knowledge/preview",
            files={"file": ("source.txt", b"abc", "text/plain")},
        )
    assert unsupported.status_code == 415
    assert oversized.status_code == 413
    builder.build.assert_not_awaited()


def test_preview_maps_unreadable_source_and_model_failure() -> None:
    builder = AsyncMock(spec=KnowledgeBuilder)
    with _client(builder) as client:
        blank = client.post(
            "/internal/v1/knowledge/preview",
            files={"file": ("source.txt", b"   ", "text/plain")},
        )
        builder.build.side_effect = RuntimeError("private provider detail")
        failed = client.post(
            "/internal/v1/knowledge/preview",
            files={"file": ("source.txt", b"A documented feature.", "text/plain")},
        )
    assert blank.status_code == 422
    assert failed.status_code == 502
    assert "private provider detail" not in failed.text


@pytest.mark.parametrize("filename", ["../source.txt", "C:source.txt", "source.txt:stream",
                                      "CON.txt", "NUL", "source.txt.", "source.txt ",
                                      "a" * 256 + ".txt"])
def test_preview_rejects_path_like_filenames(filename: str) -> None:
    with _client(AsyncMock(spec=KnowledgeBuilder)) as client:
        response = client.post(
            "/internal/v1/knowledge/preview",
            files={"file": (filename, b"abc", "text/plain")},
        )
    assert response.status_code == 422


def test_preview_explains_truncated_model_output() -> None:
    builder = AsyncMock(spec=KnowledgeBuilder)
    builder.build.side_effect = KnowledgeOutputLimitError("private provider detail")
    with _client(builder) as client:
        response = client.post(
            "/internal/v1/knowledge/preview",
            files={"file": ("source.txt", b"A documented feature.", "text/plain")},
        )
    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Knowledge generation reached its output limit. "
        "Try a smaller source or a model with a larger output limit."
    )
    assert "private" not in response.text


@pytest.mark.parametrize(
    "error,status",
    [
        (APIError(500, "private provider detail", "test", "test"), 502),
        (ModelTimeout("private timeout detail", "test", "test"), 504),
    ],
)
def test_preview_maps_provider_errors_without_leaking_details(error, status):
    builder = AsyncMock(spec=KnowledgeBuilder)
    builder.build.side_effect = error
    with _client(builder) as client:
        response = client.post(
            "/internal/v1/knowledge/preview",
            files={"file": ("source.txt", b"A documented feature.", "text/plain")},
        )
    assert response.status_code == status
    assert "private" not in response.text


@pytest.mark.parametrize("authorization", [None, "Bearer wrong-secret"])
def test_preview_authentication_precedes_multipart_parsing(authorization: str | None) -> None:
    settings = KnowledgeWorkerSettings(
        app_env="production", knowledge_internal_secret="a" * 32,
    )
    app = create_app(settings)
    preview = AsyncMock()
    app.state.preview_service = preview
    headers = {"content-type": "multipart/form-data"}
    if authorization is not None:
        headers["authorization"] = authorization
    with TestClient(app) as client:
        response = client.post(
            "/internal/v1/knowledge/preview", content=b"invalid", headers=headers,
        )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    preview.preview.assert_not_awaited()


def test_preview_accepts_matching_internal_secret() -> None:
    settings = KnowledgeWorkerSettings(
        app_env="production", knowledge_internal_secret="a" * 32,
    )
    app = create_app(settings)
    builder = AsyncMock(spec=KnowledgeBuilder)
    builder.build.return_value = _empty_result()
    app.state.preview_service = KnowledgePreviewService(cast(KnowledgeBuilder, builder))
    with TestClient(app) as client:
        response = client.post(
            "/internal/v1/knowledge/preview", headers={"authorization": "Bearer " + "a" * 32},
            files={"file": ("source.txt", b"Documented source facts.", "text/plain")},
        )
    assert response.status_code == 200
    builder.build.assert_awaited_once()


@pytest.mark.parametrize("environment", ["development", "production"])
def test_worker_nonlocal_requires_internal_secret(monkeypatch, environment):
    from pydantic import ValidationError

    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.delenv("KNOWLEDGE_INTERNAL_SECRET", raising=False)
    with pytest.raises(ValidationError, match="required outside local/test"):
        KnowledgeWorkerSettings.from_env()


@pytest.mark.parametrize("environment", ["local", "test", "production"])
def test_worker_rejects_short_configured_secret(environment):
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="at least 32 characters"):
        KnowledgeWorkerSettings.model_validate({
            "app_env": environment, "knowledge_internal_secret": "short",
        })


@pytest.mark.parametrize("secret", [" " * 32, "short"])
def test_worker_rejects_blank_internal_secret(secret: str) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="at least 32 characters"):
        KnowledgeWorkerSettings.model_validate({"knowledge_internal_secret": secret})


def test_preview_failure_logs_omit_provider_payload(caplog: pytest.LogCaptureFixture) -> None:
    builder = AsyncMock(spec=KnowledgeBuilder)
    builder.build.side_effect = RuntimeError("secret-provider-payload-123")
    with _client(builder) as client:
        response = client.post(
            "/internal/v1/knowledge/preview",
            files={"file": ("source.txt", b"Documented feature.", "text/plain")},
        )
    assert response.status_code == 502
    assert "secret-provider-payload-123" not in caplog.text
    assert "RuntimeError" in caplog.text
