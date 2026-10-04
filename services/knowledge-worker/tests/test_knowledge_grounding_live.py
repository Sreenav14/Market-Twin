"""Opt-in semantic regressions using the configured model, rather than mocked answers."""

import json
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from litellm.litellm_core_utils.logging_worker import (  # pyright: ignore[reportMissingTypeStubs]
    GLOBAL_LOGGING_WORKER,
)
from litellm.llms.custom_httpx.async_client_cleanup import (  # pyright: ignore[reportMissingTypeStubs]
    close_litellm_async_clients,
)
from markettwin_knowledge_worker.extraction import extract_source
from markettwin_knowledge_worker.knowledge_builder import KnowledgeBuilder

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("MARKETTWIN_TEST_GROUNDING") != "1",
        reason="Opt-in model calls on synthetic sources; set MARKETTWIN_TEST_GROUNDING=1.",
    ),
    pytest.mark.asyncio(loop_scope="module"),
]


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def clean_model_clients() -> AsyncIterator[None]:
    """Drain SDK callbacks before closing the shared loop used by these live checks."""
    try:
        yield
    finally:
        await GLOBAL_LOGGING_WORKER.flush()
        await GLOBAL_LOGGING_WORKER.stop()
        await close_litellm_async_clients()


async def test_context_labels_do_not_invent_capabilities(tmp_path: Path) -> None:
    source = tmp_path / "context.txt"
    source.write_text("Components: Ravo, Teli, Nimo. Ravo connects to Teli.", encoding="utf-8")
    result = await KnowledgeBuilder().build(await extract_source(source))
    assert len(result.application_knowledge) == 1
    assert not result.skills
    assert not result.artifacts
    content = result.application_knowledge[0].content.casefold()
    assert all(name in content for name in ("ravo", "teli", "nimo"))
    assert all(word not in content for word in ("cache", "retry", "timeout", "authentication"))


@pytest.mark.parametrize("explicit_failure", [False, True])
async def test_documented_capability_keeps_only_documented_failures(
    tmp_path: Path, explicit_failure: bool
) -> None:
    source = tmp_path / "behavior.txt"
    text = "Selecting Publish makes the release appear in the releases list."
    if explicit_failure:
        text += " If the title is blank, show 'Title required' and do not publish."
    source.write_text(text, encoding="utf-8")
    result = await KnowledgeBuilder().build(await extract_source(source))
    assert len(result.skills) == 1
    skill = result.skills[0]
    assert "publish" in f"{skill.name} {skill.definition.intent}".casefold()
    assert "release" in " ".join(skill.definition.expected_outcomes).casefold()
    failures = " ".join(skill.definition.failure_signals).casefold()
    if explicit_failure:
        assert "title required" in failures
    else:
        assert not skill.definition.failure_signals
        assert not skill.definition.constraints
    assert "timeout" not in failures
    assert "unavailable" not in failures


@pytest.mark.skipif(
    not os.environ.get("MARKETTWIN_GROUNDING_CONTEXT_IMAGE"),
    reason="Requires an explicitly authorized context-only diagram fixture.",
)
async def test_native_context_diagram_does_not_force_artifacts_or_skills() -> None:
    source = Path(os.environ["MARKETTWIN_GROUNDING_CONTEXT_IMAGE"])
    result = await KnowledgeBuilder().build(await extract_source(source))
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    assert len(result.application_knowledge) == 1
    assert not result.artifacts
    assert not result.skills
    assert result.application_knowledge[0].evidence_ordinals == (1,)


@pytest.mark.skipif(
    os.environ.get("MARKETTWIN_TEST_RELATIONSHIPS") != "1"
    or not os.environ.get("MARKETTWIN_GROUNDING_CONTEXT_IMAGE"),
    reason="Known model limitation; opt in to the relationship eval when changing the model.",
)
async def test_native_diagram_preserves_directed_relationships() -> None:
    source = Path(os.environ["MARKETTWIN_GROUNDING_CONTEXT_IMAGE"])
    result = await KnowledgeBuilder().build(await extract_source(source))
    content = "\n".join(item.content for item in result.application_knowledge).casefold()
    # These visible edges must survive summarization; a component inventory is insufficient.
    for origin, destination in (("queue", "transcoder"), ("chukwa", "s3"), ("s3", "emr")):
        assert re.search(
            rf"{origin}[^.!?\n]{{0,100}}(?:to|into|→|->|feeds|sends)[^.!?\n]{{0,60}}"
            rf"{destination}",
            content,
        ), f"Missing directed relationship: {origin} -> {destination}"


async def test_pdf_keeps_documented_formats_limits_and_failure(requirements_pdf: Path) -> None:
    result = await KnowledgeBuilder().build(await extract_source(requirements_pdf))
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    uploads = [
        skill
        for skill in result.skills
        if "upload" in f"{skill.name} {skill.definition.intent}".casefold()
    ]
    assert uploads, "The PDF's documented upload capability must be retained."
    upload = uploads[0]
    assert "pdf" in " ".join(upload.definition.inputs).casefold()
    assert "docx" in " ".join(upload.definition.inputs).casefold()
    assert "10" in " ".join(upload.definition.constraints)
    assert any(
        "parsing" in " ".join(skill.definition.failure_signals).casefold()
        or "processing error" in " ".join(skill.definition.failure_signals).casefold()
        for skill in result.skills
    )
