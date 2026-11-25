"""Step 1 (doc 33): the understanding pass over the pricing fixture.

The model is stubbed at the litellm seam (the house pattern); the expected
file set is the hand-written fixture expectation, so the pipeline must
preserve exact values, the exception's placement, and the tax uncertainty.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import litellm
import pytest
from fastapi.testclient import TestClient
from litellm.types.utils import ModelResponse  # pyright: ignore[reportMissingTypeStubs]
from markettwin_knowledge_worker.config import KnowledgeConfigurationError
from markettwin_knowledge_worker.extraction.contracts import (
    ExtractedEvidence,
    ExtractionResult,
)
from markettwin_knowledge_worker.main import create_app
from markettwin_knowledge_worker.markdown_builder import (
    MarkdownBuilder,
    UnderstandingBudgetExceeded,
    understanding_budget,
)
from markettwin_knowledge_worker.services import knowledge_markdown_service as markdown_service_module
from markettwin_knowledge_worker.services.knowledge_markdown_service import (
    KnowledgeMarkdownService,
)
from markettwin_shared.knowledge_markdown import UnderstandResult

FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED = UnderstandResult.model_validate(
    json.loads((FIXTURES / "pricing-expected.json").read_text(encoding="utf-8"))
)


def _completion(payload: dict[str, object]) -> ModelResponse:
    return ModelResponse(
        choices=[
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(payload)},
            }
        ],
        usage={"prompt_tokens": 120, "completion_tokens": 240, "total_tokens": 360},
    )


def _extraction() -> ExtractionResult:
    text = (FIXTURES / "pricing-fixture.md").read_text(encoding="utf-8")
    unit = ExtractedEvidence(
        evidence_type="text",
        content_text=text,
        content_json=None,
        source_locator={"page": 1},
        extractor_name="text",
        extractor_version="1",
        ordinal=1,
    )
    return ExtractionResult(
        source_path=FIXTURES / "pricing-fixture.md",
        units=(unit,),
        issues=(),
        source_item_count=1,
        processed_item_count=1,
    )


async def test_fixture_understanding_matches_the_expected_file_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_NAME", "openai/test-model")
    completion = AsyncMock(return_value=_completion(EXPECTED.model_dump(mode="json")))
    monkeypatch.setattr(litellm, "acompletion", completion)

    async def fake_extract(_path: Path) -> ExtractionResult:
        return _extraction()

    monkeypatch.setattr(markdown_service_module, "extract_source", fake_extract)
    service = KnowledgeMarkdownService(MarkdownBuilder())
    markdown = await service.markdown(
        FIXTURES / "pricing-fixture.md", entry_id=uuid4(), workspace_id=uuid4()
    )
    assert markdown.result == EXPECTED
    file = markdown.result.files[0]
    assert file.slug == "pricing"
    bodies = {section.heading: section.body_md for section in file.sections}
    assert "$19" in bodies["Plans"] and "$49" in bodies["Plans"]
    assert "**Exception:**" in bodies["Annual billing"]
    assert "$470.40" in bodies["Worked example"]
    uncertainties = [
        record.text
        for section in file.sections
        for record in section.uncertainties
    ]
    assert any("tax" in text for text in uncertainties)
    assert markdown.usage.model == "openai/test-model"
    assert markdown.usage.calls == 1
    assert markdown.usage.prompt_tokens == 120
    assert markdown.usage.completion_tokens == 240


async def test_build_without_a_budget_context_never_calls_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_NAME", "openai/test-model")
    completion = AsyncMock(return_value=_completion(EXPECTED.model_dump(mode="json")))
    monkeypatch.setattr(litellm, "acompletion", completion)
    with pytest.raises(UnderstandingBudgetExceeded):
        await MarkdownBuilder().build(_extraction())
    completion.assert_not_awaited()


async def test_exhausted_budget_refuses_before_sending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_NAME", "openai/test-model")
    completion = AsyncMock(return_value=_completion(EXPECTED.model_dump(mode="json")))
    monkeypatch.setattr(litellm, "acompletion", completion)
    with understanding_budget(uuid4(), max_calls=1, max_tokens=10):
        with pytest.raises(UnderstandingBudgetExceeded):
            await MarkdownBuilder().build(_extraction())
    completion.assert_not_awaited()


async def test_missing_model_name_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("IMAGE_MODEL_NAME", raising=False)
    monkeypatch.delenv("VIDEO_MODEL_NAME", raising=False)
    service = KnowledgeMarkdownService(MarkdownBuilder())
    with pytest.raises(KnowledgeConfigurationError):
        await service.markdown(
            FIXTURES / "pricing-fixture.md", entry_id=uuid4(), workspace_id=uuid4()
        )


def test_markdown_endpoint_requires_ids_and_returns_the_file_set() -> None:
    from markettwin_knowledge_worker.services.knowledge_markdown_service import (
        KnowledgeMarkdown,
    )
    from markettwin_shared.knowledge_markdown import KnowledgeMarkdownUsage

    class FakeService:
        async def markdown(
            self, _path: Path, *, entry_id: object, workspace_id: object
        ) -> KnowledgeMarkdown:
            return KnowledgeMarkdown(
                extraction=_extraction(),
                result=EXPECTED,
                usage=KnowledgeMarkdownUsage(
                    model="openai/test-model", calls=1,
                    prompt_tokens=120, completion_tokens=240, total_tokens=360,
                ),
            )

    app = create_app()
    app.state.markdown_service = FakeService()
    client = TestClient(app)
    entry_id, workspace_id = uuid4(), uuid4()
    missing = client.post(
        "/internal/v1/knowledge/markdown",
        files={"file": ("pricing-fixture.md", b"# x", "text/markdown")},
    )
    assert missing.status_code == 422
    response = client.post(
        "/internal/v1/knowledge/markdown",
        files={
            "file": (
                "pricing-fixture.md",
                (FIXTURES / "pricing-fixture.md").read_bytes(),
                "text/markdown",
            )
        },
        data={"entry_id": str(entry_id), "workspace_id": str(workspace_id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["files"][0]["slug"] == "pricing"
    assert body["usage"]["calls"] == 1
    assert body["evidence"][0]["ordinal"] == 1
