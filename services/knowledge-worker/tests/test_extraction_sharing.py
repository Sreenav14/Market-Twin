"""One extraction per source across the preview and markdown calls (SKR step 3).

The control plane calls preview and markdown back to back with the same
source bytes; the document parse must run once, both outputs must cite the
same evidence ordinals, and over-limit media must be refused with its named
reason at every layer.
"""

from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from markettwin_knowledge_worker.extraction import dispatcher
from markettwin_knowledge_worker.extraction.contracts import (
    ExtractedEvidence,
    ExtractionResult,
)
from markettwin_knowledge_worker.extraction.video import (
    VideoExtractionError,
    VideoExtractor,
)
from markettwin_knowledge_worker.knowledge_builder import KnowledgeBuilder
from markettwin_knowledge_worker.main import create_app
from markettwin_knowledge_worker.markdown_builder import MarkdownBuilder
from markettwin_knowledge_worker.services import (
    knowledge_markdown_service,
    knowledge_preview_service,
)
from markettwin_knowledge_worker.services.knowledge_markdown_service import (
    KnowledgeMarkdownService,
)
from markettwin_knowledge_worker.services.knowledge_preview_service import (
    InvalidPreviewSourceError,
    KnowledgePreviewService,
)
from markettwin_shared.knowledge import KnowledgeBuildResult
from markettwin_shared.knowledge_markdown import (
    KnowledgeMarkdownUsage,
    UnderstandResult,
    UnderstoodFile,
    UnderstoodSection,
)


def _extraction(path: Path, ordinals: tuple[int, ...] = (1, 2)) -> ExtractionResult:
    return ExtractionResult(
        source_path=path,
        units=tuple(
            ExtractedEvidence(
                evidence_type="text",
                content_text=f"unit {ordinal}",
                content_json=None,
                source_locator={"item": ordinal},
                extractor_name="stub",
                extractor_version="1",
                ordinal=ordinal,
            )
            for ordinal in ordinals
        ),
        issues=(),
        source_item_count=len(ordinals),
        processed_item_count=len(ordinals),
    )


@pytest.mark.asyncio
async def test_document_extraction_runs_once_for_identical_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []

    async def fake_extract_document(path: Path) -> ExtractionResult:
        calls.append(path)
        return _extraction(path)

    monkeypatch.setattr(dispatcher, "extract_document", fake_extract_document)
    dispatcher.clear_extraction_cache()
    first = tmp_path / "a" / "source.txt"
    second = tmp_path / "b" / "source.txt"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"same source bytes")
    second.write_bytes(b"same source bytes")

    one = await dispatcher.extract_source(first)
    two = await dispatcher.extract_source(second)
    assert len(calls) == 1
    assert two.source_path == second
    assert [unit.ordinal for unit in two.units] == [unit.ordinal for unit in one.units]

    third = tmp_path / "b" / "other.txt"
    third.write_bytes(b"different bytes")
    await dispatcher.extract_source(third)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_preview_and_markdown_share_one_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def fake_extract_document(path: Path) -> ExtractionResult:
        nonlocal calls
        calls += 1
        return _extraction(path, ordinals=(1, 2, 3))

    monkeypatch.setattr(dispatcher, "extract_document", fake_extract_document)
    dispatcher.clear_extraction_cache()
    seen: dict[str, ExtractionResult] = {}

    preview_builder = AsyncMock(spec=KnowledgeBuilder)

    async def preview_build(extraction: ExtractionResult) -> KnowledgeBuildResult:
        seen["preview"] = extraction
        return KnowledgeBuildResult(application_knowledge=(), artifacts=(), skills=())

    preview_builder.build.side_effect = preview_build

    markdown_builder = AsyncMock(spec=MarkdownBuilder)

    async def markdown_build(
        extraction: ExtractionResult,
    ) -> tuple[UnderstandResult, KnowledgeMarkdownUsage]:
        seen["markdown"] = extraction
        return (
            UnderstandResult(
                files=(
                    UnderstoodFile(
                        slug="topic",
                        title="Topic",
                        description="About the source.",
                        sections=(
                            UnderstoodSection(
                                heading="All",
                                body_md="Body.",
                                evidence_ordinals=(1, 2, 3),
                            ),
                        ),
                    ),
                )
            ),
            KnowledgeMarkdownUsage(
                model="test", calls=0, prompt_tokens=0, completion_tokens=0, total_tokens=0
            ),
        )

    markdown_builder.build.side_effect = markdown_build

    source = tmp_path / "source.txt"
    source.write_bytes(b"shared bytes")
    preview = await KnowledgePreviewService(
        cast(KnowledgeBuilder, preview_builder)
    ).preview(source)
    markdown = await KnowledgeMarkdownService(
        cast(MarkdownBuilder, markdown_builder)
    ).markdown(source, entry_id=uuid4(), workspace_id=uuid4())

    assert calls == 1
    assert [unit.ordinal for unit in seen["preview"].units] == [1, 2, 3]
    assert [unit.ordinal for unit in seen["markdown"].units] == [1, 2, 3]
    assert [unit.ordinal for unit in preview.extraction.units] == [
        unit.ordinal for unit in markdown.extraction.units
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("service_kind", ["preview", "markdown"])
async def test_over_limit_video_reason_survives_the_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, service_kind: str
) -> None:
    async def refuse(path: Path) -> ExtractionResult:
        raise VideoExtractionError("video_limit_exceeded", "Video requires too many clips.")

    monkeypatch.setattr(knowledge_preview_service, "extract_source", refuse)
    monkeypatch.setattr(knowledge_markdown_service, "extract_source", refuse)
    source = tmp_path / "long.mp4"
    source.write_bytes(b"video")
    with pytest.raises(InvalidPreviewSourceError, match="Video requires too many clips."):
        if service_kind == "preview":
            await KnowledgePreviewService(
                cast(KnowledgeBuilder, AsyncMock(spec=KnowledgeBuilder))
            ).preview(source)
        else:
            await KnowledgeMarkdownService(
                cast(MarkdownBuilder, AsyncMock(spec=MarkdownBuilder))
            ).markdown(source, entry_id=uuid4(), workspace_id=uuid4())


@pytest.mark.asyncio
async def test_video_beyond_clip_limit_is_refused_with_a_named_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def duration(path: Path) -> float:
        return 6000.0

    monkeypatch.setattr(VideoExtractor, "_duration_seconds", staticmethod(duration))
    source = tmp_path / "long.mp4"
    source.write_bytes(b"video")
    with pytest.raises(VideoExtractionError) as caught:
        await VideoExtractor().extract(source)
    assert caught.value.code == "video_limit_exceeded"
    assert "too many clips" in str(caught.value)


def test_preview_api_returns_the_named_media_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def refuse(path: Path) -> ExtractionResult:
        raise VideoExtractionError("video_limit_exceeded", "Video requires too many clips.")

    monkeypatch.setattr(knowledge_preview_service, "extract_source", refuse)
    app = create_app()
    app.state.preview_service = KnowledgePreviewService(
        cast(KnowledgeBuilder, AsyncMock(spec=KnowledgeBuilder))
    )
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/internal/v1/knowledge/preview",
        files={"file": ("long.mp4", b"video", "video/mp4")},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Video requires too many clips."
