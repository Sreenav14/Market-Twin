"""Structured generation validates PDF grounding without a database dependency."""

import json
import os
import re
from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import pytest
from litellm.types.utils import ModelResponse  # pyright: ignore[reportMissingTypeStubs]
from markettwin_knowledge_worker import knowledge_builder
from markettwin_knowledge_worker.extraction import PdfExtractor
from markettwin_knowledge_worker.extraction.contracts import ExtractedEvidence, ExtractionResult
from markettwin_knowledge_worker.knowledge_builder import KnowledgeOutputLimitError
from markettwin_knowledge_worker.skill_generator import GeneratedSkills, SkillGenerator
from markettwin_shared.knowledge import GeneratedSkillDraft
from pydantic import ValidationError

from .conftest import write_pdf

DRAFT: dict[str, object] = {
    "name": "Upload Resume",
    "definition": {
        "intent": "Upload a supported resume for analysis",
        "preconditions": ["User is signed in"],
        "inputs": ["PDF resume", "DOCX resume"],
        "constraints": ["Maximum upload size is 10 MB"],
        "expected_outcomes": ["Accepted resume is ready for analysis"],
        "failure_signals": ["Size error", "Format error"],
    },
    "evidence_ordinals": [1],
    "grounding_confidence": "high",
    "warnings": [],
}


def completion(content: str, *, finish_reason: str = "stop") -> ModelResponse:
    if content.startswith('{"skills":'):
        content = json.dumps({"application_knowledge": [], "artifacts": [], **json.loads(content)})
    return ModelResponse(
        choices=[
            {
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": content},
            }
        ]
    )


async def test_generator_uses_real_pdf_text_and_returns_grounded_drafts(
    requirements_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock = AsyncMock(return_value=completion(json.dumps({"skills": [DRAFT]})))
    monkeypatch.setattr(knowledge_builder.litellm, "acompletion", mock)
    monkeypatch.setenv("MODEL_NAME", "openai/gpt-4o-mini")
    drafts = await SkillGenerator().generate(PdfExtractor().extract(requirements_pdf))
    assert drafts[0].evidence_ordinals == (1,)
    assert drafts[0].definition.constraints == ("Maximum upload size is 10 MB",)
    request = cast(dict[str, object], mock.call_args.kwargs)
    assert request["response_format"] is GeneratedSkills
    prompt = json.dumps(request["messages"])
    assert "Maximum upload size is 10 MB" in prompt
    assert '"page_end": 3' in prompt.replace('\\"', '"')
    assert "evidence_unit_ids" not in prompt
    mock.assert_awaited_once()


@pytest.mark.parametrize("ordinals", [[], [0], [-1], [True], ["1"], [1.5]])
def test_draft_requires_positive_integer_ordinals(ordinals: list[object]) -> None:
    with pytest.raises(ValidationError):
        GeneratedSkillDraft.model_validate({**DRAFT, "evidence_ordinals": ordinals})


def test_draft_rejects_database_ids_and_missing_outcomes() -> None:
    with pytest.raises(ValidationError):
        GeneratedSkillDraft.model_validate({**DRAFT, "evidence_unit_ids": []})
    with pytest.raises(ValidationError):
        GeneratedSkillDraft.model_validate({**DRAFT, "definition": {"intent": "Upload resume"}})


async def test_generator_rejects_unknown_citations(
    requirements_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock = AsyncMock(
        return_value=completion(
            json.dumps(
                {
                    "skills": [{**DRAFT, "evidence_ordinals": [99]}],
                }
            )
        )
    )
    monkeypatch.setattr(knowledge_builder.litellm, "acompletion", mock)
    with pytest.raises(ValueError, match="unknown evidence ordinals"):
        await SkillGenerator().generate(PdfExtractor().extract(requirements_pdf))


@pytest.mark.parametrize("content", ["not JSON", "{}", '{"skills": [{"name": "Upload"}]}'])
async def test_generator_rejects_invalid_structured_output(
    content: str,
    requirements_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        knowledge_builder.litellm, "acompletion", AsyncMock(return_value=completion(content))
    )
    with pytest.raises(ValidationError):
        await SkillGenerator().generate(PdfExtractor().extract(requirements_pdf))


async def test_generator_rejects_truncated_response(
    requirements_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        knowledge_builder.litellm,
        "acompletion",
        AsyncMock(
            return_value=completion(
                '{"skills": []}',
                finish_reason="length",
            )
        ),
    )
    with pytest.raises(KnowledgeOutputLimitError, match="output limit"):
        await SkillGenerator().generate(PdfExtractor().extract(requirements_pdf))


async def test_generator_requires_content_and_unique_ordinals(
    requirements_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock = AsyncMock()
    monkeypatch.setattr(knowledge_builder.litellm, "acompletion", mock)
    extraction = PdfExtractor().extract(requirements_pdf)
    for invalid in (
        replace(extraction, units=()),
        replace(extraction, units=(extraction.units[0],) * 2),
    ):
        with pytest.raises(ValueError):
            await SkillGenerator().generate(invalid)
    mock.assert_not_awaited()


async def test_generator_surfaces_missing_visual_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "partly-scanned.pdf"
    write_pdf(
        path,
        ("Uploaded PDF or DOCX resumes up to 10 MB are ready for analysis.",),
        visual_page=True,
    )
    mock = AsyncMock(return_value=completion(json.dumps({"skills": [DRAFT]})))
    monkeypatch.setattr(knowledge_builder.litellm, "acompletion", mock)
    drafts = await SkillGenerator().generate(PdfExtractor().extract(path))
    assert any("needs_visual_fallback" in warning for warning in drafts[0].warnings)


async def test_generator_can_return_no_documented_skills(
    requirements_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        knowledge_builder.litellm, "acompletion",
        AsyncMock(return_value=completion('{"skills": []}')),
    )
    assert await SkillGenerator().generate(PdfExtractor().extract(requirements_pdf)) == ()


async def test_generator_batches_whole_evidence_then_consolidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KNOWLEDGE_SOURCE_CHUNK_MAX_CHARS", "50")
    monkeypatch.setenv("KNOWLEDGE_SKILL_BATCH_MAX_CHARS", "60")
    extraction = ExtractionResult(
        source_path=tmp_path / "large.txt",
        units=tuple(
            ExtractedEvidence(
                evidence_type="text",
                content_text=character * 40,
                content_json=None,
                source_locator={"line": ordinal},
                extractor_name="test",
                extractor_version="1",
                ordinal=ordinal,
            )
            for ordinal, character in ((1, "a"), (2, "b"))
        ),
        issues=(),
        source_item_count=2,
        processed_item_count=2,
    )
    second = {**DRAFT, "name": "Analyze Resume", "evidence_ordinals": [2]}
    consolidated = {**DRAFT, "evidence_ordinals": [1, 2]}
    mock = AsyncMock(
        side_effect=[
            completion(json.dumps({"skills": [DRAFT]})),
            completion(json.dumps({"skills": [second]})),
            completion(json.dumps({"skills": [consolidated]})),
        ]
    )
    monkeypatch.setattr(knowledge_builder.litellm, "acompletion", mock)

    drafts = await SkillGenerator().generate(extraction)

    assert drafts[0].evidence_ordinals == (1, 2)
    assert mock.await_count == 3
    final_prompt = json.dumps(mock.await_args_list[-1].kwargs["messages"])
    assert "candidate_results" in final_prompt
    assert "aaaaaaaa" not in final_prompt


@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_LLM") != "1",
    reason="Set MARKETTWIN_TEST_LLM=1 to run the real configured model (incurs API usage).",
)
async def test_live_pdf_produces_useful_grounded_skills(requirements_pdf: Path) -> None:
    """Prove the intelligence path, rather than only mocking its structured response."""
    extraction = PdfExtractor().extract(requirements_pdf)
    drafts = await SkillGenerator().generate(extraction)
    print(json.dumps({"skills": [draft.model_dump(mode="json") for draft in drafts]}, indent=2))
    assert len(drafts) >= 3
    for capability, ordinal in (("upload", 1), ("analy", 1), ("download", 1)):
        matching = [
            draft
            for draft in drafts
            if capability in f"{draft.name} {draft.definition.intent}".casefold()
        ]
        assert matching, f"Missing documented capability: {capability}"
        assert any(ordinal in draft.evidence_ordinals for draft in matching)
    upload = next(draft for draft in drafts if "upload" in draft.name.casefold())
    assert re.search(r"10\s*(MB|megabytes)", " ".join(upload.definition.constraints), re.IGNORECASE)
    inputs = " ".join(upload.definition.inputs).casefold()
    assert "pdf" in inputs and "docx" in inputs
    download = next(draft for draft in drafts if "download" in draft.name.casefold())
    assert "pdf" in download.definition.model_dump_json().casefold()
    assert "retry" in " ".join(draft.definition.model_dump_json() for draft in drafts).casefold()
