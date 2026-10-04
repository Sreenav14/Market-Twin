"""The private preview adapter owns upload limits and temporary source files."""

from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from litellm.exceptions import APIError
from litellm.exceptions import Timeout as ModelTimeout
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


def test_preview_rejects_path_like_filenames() -> None:
    with _client(AsyncMock(spec=KnowledgeBuilder)) as client:
        response = client.post(
            "/internal/v1/knowledge/preview",
            files={"file": ("../source.txt", b"abc", "text/plain")},
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
