"""Tests for ADK model telemetry hooks without replacing the agent loop."""

from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from markettwin_execution_orchestrator.models import telemetry
from markettwin_execution_orchestrator.models.model_factory import (
    ModelRuntimeConfig,
)
from markettwin_shared.observability import ModelTokenUsage
from sqlalchemy.ext.asyncio import AsyncSession


class FakeRepository:
    def __init__(self, _session: object) -> None:
        self.started: list[dict[str, object]] = []
        self.finished: list[dict[str, object]] = []

    async def start_model_invocation(
        self,
        **kwargs: object,
    ) -> UUID:
        self.started.append(dict(kwargs))
        return cast(UUID, kwargs["invocation_id"])

    async def finish_model_invocation(
        self,
        **kwargs: object,
    ) -> None:
        self.finished.append(dict(kwargs))


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0

    async def commit(self) -> None:
        self.commit_count += 1


@pytest.mark.asyncio
async def test_adk_observer_records_one_completed_model_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repositories: list[FakeRepository] = []

    def repository_factory(session: object) -> FakeRepository:
        repository = FakeRepository(session)
        repositories.append(repository)
        return repository

    monkeypatch.setattr(
        telemetry,
        "ObservabilityRepository",
        repository_factory,
    )

    session = FakeSession()
    observer = telemetry.AdkModelInvocationObserver(
        session=cast(AsyncSession, session),
        test_run_id=uuid4(),
        agent_snapshot_id=uuid4(),
        agent_role="persona",
        runtime_agent_name="markettwin_test",
        model_config=ModelRuntimeConfig(
            provider="openai",
            model_name="openai/gpt-4o-mini",
            max_tokens=512,
            num_retries=2,
        ),
    )

    context = cast(
        CallbackContext,
        SimpleNamespace(invocation_id="adk-invocation-1"),
    )
    request = cast(LlmRequest, object())

    await observer.before_model_callback(
        context,
        request,
    )
    await observer.after_model_callback(
        context,
        LlmResponse(
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=100,
                candidates_token_count=20,
                total_token_count=120,
            ),
            model_version="gpt-4o-mini-test",
        ),
    )

    repository = repositories[0]
    assert len(repository.started) == 1
    assert len(repository.finished) == 1
    assert repository.started[0]["agent_role"] == "persona"

    usage = cast(
        ModelTokenUsage,
        repository.finished[0]["usage"],
    )
    assert usage.input_tokens == 100
    assert usage.output_tokens == 20
    assert usage.total_tokens == 120
    assert repository.finished[0]["status"] == "completed"
    assert session.commit_count == 2
