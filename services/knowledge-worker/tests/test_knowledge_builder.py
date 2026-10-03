"""The Knowledge Builder is the single semantic boundary for source evidence."""

import json
from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import pytest
from litellm.types.utils import ModelResponse  # pyright: ignore[reportMissingTypeStubs]
from markettwin_knowledge_worker import knowledge_builder
from markettwin_knowledge_worker.extraction.contracts import ExtractedEvidence, ExtractionResult
from markettwin_knowledge_worker.knowledge_builder import KnowledgeBuilder


def _completion(payload: dict[str, object]) -> ModelResponse:
    return ModelResponse(
        choices=[
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(payload)},
            }
        ]
    )


def _result(*, ordinal: int = 1) -> dict[str, object]:
    return {
        "application_knowledge": [
            {
                "name": "Resume processing",
                "content": "Accepted resumes are prepared for analysis.",
                "evidence_ordinals": [ordinal],
                "grounding_confidence": "high",
            }
        ],
        "artifacts": [
            {
                "name": "Resume lifecycle",
                "kind": "procedure",
                "content": "Upload then analysis.",
                "steps": ["Upload a supported resume", "Resume is ready for analysis"],
                "evidence_ordinals": [ordinal],
                "grounding_confidence": "high",
            }
        ],
        "skills": [
            {
                "name": "Upload Resume",
                "definition": {
                    "intent": "Upload a supported resume for analysis",
                    "expected_outcomes": ["Accepted resume is ready for analysis"],
                },
                "evidence_ordinals": [ordinal],
                "grounding_confidence": "high",
            }
        ],
    }


async def test_builder_returns_all_grounded_knowledge_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extraction = ExtractionResult(
        source_path=tmp_path / "requirements.txt",
        units=(
            ExtractedEvidence(
                evidence_type="text",
                content_text="Users upload supported resumes before analysis.",
                content_json=None,
                source_locator={"chunk": 1},
                extractor_name="text",
                extractor_version="1",
                ordinal=1,
            ),
        ),
        issues=(),
        source_item_count=1,
        processed_item_count=1,
    )
    mock = AsyncMock(return_value=_completion(_result()))
    monkeypatch.setattr(knowledge_builder, "acompletion", mock)

    result = await KnowledgeBuilder().build(extraction)

    assert result.application_knowledge[0].evidence_ordinals == (1,)
    assert result.artifacts[0].steps == (
        "Upload a supported resume",
        "Resume is ready for analysis",
    )
    assert result.skills[0].name == "Upload Resume"
    request = cast(dict[str, object], mock.call_args.kwargs)
    assert request["response_format"] is type(result)
    prompt = json.dumps(request["messages"])
    assert "Evidence 1" in prompt
    assert "Users upload supported resumes" in prompt


async def test_builder_sends_original_image_to_the_semantic_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_path = tmp_path / "screen.png"
    image_path.write_bytes(b"PNG bytes")
    extraction = ExtractionResult(
        source_path=image_path,
        units=(
            ExtractedEvidence(
                evidence_type="image",
                content_text=None,
                content_json={"media_type": "image/png"},
                source_locator={"image": 1},
                extractor_name="image-source-adapter",
                extractor_version="1",
                ordinal=1,
                media_path=image_path,
            ),
        ),
        issues=(),
        source_item_count=1,
        processed_item_count=1,
    )
    mock = AsyncMock(return_value=_completion(_result()))
    monkeypatch.setattr(knowledge_builder, "acompletion", mock)
    monkeypatch.setenv("IMAGE_MODEL_NAME", "openai/test-vision")

    await KnowledgeBuilder().build(extraction)

    request = cast(dict[str, object], mock.call_args.kwargs)
    messages = cast(list[dict[str, object]], request["messages"])
    content = cast(list[dict[str, object]], messages[1]["content"])
    image_part = next(part for part in content if part["type"] == "image_url")
    image_url = cast(dict[str, str], image_part["image_url"])
    assert image_url["url"].startswith("data:image/png;base64,")
    assert "observations" not in json.dumps(request["messages"])


async def test_builder_rejects_unknown_ordinal_before_consolidation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extraction = ExtractionResult(
        source_path=tmp_path / "source.txt",
        units=(
            ExtractedEvidence(
                evidence_type="text",
                content_text="Documented product behavior.",
                content_json=None,
                source_locator={"chunk": 1},
                extractor_name="text",
                extractor_version="1",
                ordinal=1,
            ),
        ),
        issues=(),
        source_item_count=1,
        processed_item_count=1,
    )
    mock = AsyncMock(return_value=_completion(_result(ordinal=2)))
    monkeypatch.setattr(knowledge_builder, "acompletion", mock)

    with pytest.raises(ValueError, match="unknown evidence ordinals"):
        await KnowledgeBuilder().build(extraction)
    mock.assert_awaited_once()


@pytest.mark.parametrize("fails", [False, True])
async def test_video_uses_actual_clips_and_cleans_only_temporary_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fails: bool
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original-video")
    clips_root = tmp_path / "clips"
    clips_root.mkdir()
    clip = clips_root / "clip.mp4"
    clip.write_bytes(b"trimmed-video")
    extraction = ExtractionResult(
        source_path=source,
        units=(
            ExtractedEvidence(
                evidence_type="video_segment",
                content_text=None,
                content_json={"media_type": "video/mp4"},
                source_locator={"start_seconds": 85.0, "end_seconds": 120.0},
                extractor_name="video-source-adapter",
                extractor_version="1",
                ordinal=1,
                media_path=clip,
            ),
        ),
        issues=(),
        source_item_count=1,
        processed_item_count=1,
        cleanup_paths=(clips_root,),
    )
    mock = AsyncMock(
        side_effect=RuntimeError("provider failed") if fails else None,
        return_value=_completion(_result()),
    )
    monkeypatch.setattr(knowledge_builder, "acompletion", mock)
    monkeypatch.setenv("VIDEO_MODEL_NAME", "openai/test-video")
    monkeypatch.setenv("VIDEO_INPUT_FORMAT", "video_url")
    if fails:
        with pytest.raises(RuntimeError, match="provider failed"):
            await KnowledgeBuilder().build(extraction)
    else:
        await KnowledgeBuilder().build(extraction)
    request = cast(dict[str, object], mock.call_args.kwargs)
    messages = cast(list[dict[str, object]], request["messages"])
    content = cast(list[dict[str, object]], messages[1]["content"])
    video_part = next(part for part in content if part["type"] == "video_url")
    video_url = cast(dict[str, str], video_part["video_url"])
    assert video_url["url"] == "data:video/mp4;base64,dHJpbW1lZC12aWRlbw=="
    assert "85.0" in json.dumps(messages)
    assert source.read_bytes() == b"original-video"
    assert not clips_root.exists()


async def test_consolidation_cannot_cite_unused_source_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KNOWLEDGE_SOURCE_CHUNK_MAX_CHARS", "50")
    monkeypatch.setenv("KNOWLEDGE_SKILL_BATCH_MAX_CHARS", "60")
    first = ExtractedEvidence(
        evidence_type="text",
        content_text="a" * 40,
        content_json=None,
        source_locator={"chunk": 1},
        extractor_name="text",
        extractor_version="1",
        ordinal=1,
    )
    extraction = ExtractionResult(
        source_path=tmp_path / "large.txt",
        units=(first, replace(first, ordinal=2)),
        issues=(),
        source_item_count=2,
        processed_item_count=2,
    )
    mock = AsyncMock(
        side_effect=[
            _completion(_result()),
            _completion({"application_knowledge": [], "artifacts": [], "skills": []}),
            _completion(_result(ordinal=2)),
        ]
    )
    monkeypatch.setattr(knowledge_builder, "acompletion", mock)
    with pytest.raises(ValueError, match="unknown evidence ordinals"):
        await KnowledgeBuilder().build(extraction)
    assert mock.await_count == 3
