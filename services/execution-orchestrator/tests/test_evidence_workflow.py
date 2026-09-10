"""Regression coverage for final Journey events and session evidence."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.agents.meta_agent_factory import MetaAgentFactory
from markettwin_execution_orchestrator.agents.schemas.mission import TestMissionSpec as MissionSpec
from markettwin_execution_orchestrator.agents.schemas.persona import PersonaSpec
from markettwin_execution_orchestrator.agents.schemas.plan import MetaAgentPlan
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.contracts import (
    BrowserSessionArtifacts,
    BrowserSessionHandle,
)
from markettwin_execution_orchestrator.persistence import (
    ExecutionRepository,
    RunEventRepository,
    S3ArtifactStorage,
    SessionArtifactRecorder,
)
from markettwin_execution_orchestrator.persistence.models import RunEvent
from markettwin_execution_orchestrator.workflow import journey_executor, multi_persona_executor
from markettwin_execution_orchestrator.workflow.journey_planner import build_persona_journeys
from markettwin_execution_orchestrator.workflow.persona_result import (
    JourneyExecutionStatus,
    JourneyOutcome,
    PersonaJourneyResult,
)
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def plan() -> MetaAgentPlan:
    return MetaAgentPlan(
        mission_summary="Check checkout.",
        personas=tuple(
            PersonaSpec(
                persona_id=name,
                name=name,
                perspective="A careful shopper.",
                behavior_traits=("careful",),
                priorities=("clarity",),
            )
            for name in ("alice", "bob", "carol")
        ),
        missions=(
            MissionSpec(
                mission_id="checkout",
                name="Checkout",
                objective="Complete checkout.",
                success_criteria=("Order confirmed",),
            ),
        ),
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (None, None),
        ("", None),
        ("/relative/path", None),
        ("https://", None),
        ("https://example.com:bad/path", None),
        ("https://example.com:99999/path", None),
        ("https://[broken/path", None),
        (
            "https://user:secret@example.com:8443/cart?token=secret#private",
            "https://example.com:8443/cart",
        ),
        (
            "https://user:secret@[2001:db8::1]:8443/cart?token=secret#private",
            "https://[2001:db8::1]:8443/cart",
        ),
        ("https://example.com/cart", "https://example.com/cart"),
    ],
)
def test_safe_final_url(url: str | None, expected: str | None) -> None:
    # Exercise malformed inputs directly at the internal sanitization boundary.
    assert multi_persona_executor._safe_final_url(url) == expected  # pyright: ignore[reportPrivateUsage]


async def test_run_event_repository_flushes_without_committing() -> None:
    session = MagicMock(spec=AsyncSession)

    def assign_id(event: RunEvent) -> None:
        event.id = 42

    session.add.side_effect = assign_id
    event_id = await RunEventRepository(session).create(
        test_run_id=uuid4(),
        journey_id=None,
        execution_id=None,
        event_type="journey.result",
        payload={"status": "completed"},
    )

    assert event_id == 42
    session.flush.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "status", [JourneyExecutionStatus.COMPLETED, JourneyExecutionStatus.TIMED_OUT]
)
async def test_result_event_shares_final_execution_commit(
    plan: MetaAgentPlan,
    status: JourneyExecutionStatus,
) -> None:
    journeys = build_persona_journeys(plan)
    request = multi_persona_executor.MultiPersonaExecutionRequest(
        run_id=uuid4(),
        plan=plan,
        journey_ids_by_key={journey.journey_key: uuid4() for journey in journeys},
        start_url="https://example.com",
        allowed_origins=(AllowedOrigin("https", "example.com"),),
    )
    session = MagicMock(spec=AsyncSession)
    repository = MagicMock(spec=ExecutionRepository)
    calls = MagicMock()
    calls.attach_mock(session.commit, "commit")
    calls.attach_mock(repository.finish_agent_execution, "finish")
    calls.attach_mock(session.flush, "flush")
    outcome = JourneyOutcome.PASSED if status == JourneyExecutionStatus.COMPLETED else None
    results = [
        PersonaJourneyResult(
            journey=journey,
            status=status,
            outcome=outcome,
            summary="Checkout observed.",
            actions=("Clicked checkout",),
            observations=("Saw confirmation",),
            friction_points=("Slow page",),
            blockers=("Example blocker",),
            satisfied_criteria=("Order confirmed",),
            unsatisfied_criteria=("Fast response",),
            final_url="https://user:secret@example.com/cart?token=private#secret",
        )
        for journey in journeys
    ]
    with (
        patch.object(multi_persona_executor, "ExecutionRepository", return_value=repository),
        patch.object(
            multi_persona_executor, "execute_persona_journey", new=AsyncMock(side_effect=results)
        ),
    ):
        actual = await multi_persona_executor.execute_multi_persona_plan(
            request=request,
            browser_controller=MagicMock(spec=BrowserController),
            session=session,
            factory=MagicMock(spec=MetaAgentFactory),
        )

    assert actual.journeys == tuple(results)
    assert [call[0] for call in calls.mock_calls] == ["commit", "finish", "flush", "commit"] * 3
    for index, call in enumerate(session.add.call_args_list):
        event = call.args[0]
        assert isinstance(event, RunEvent)
        assert event.test_run_id == request.run_id
        assert event.journey_id == request.journey_ids_by_key[journeys[index].journey_key]
        assert (
            event.execution_id
            == repository.finish_agent_execution.call_args_list[index].kwargs["execution_id"]
        )
        assert event.event_type == "journey.result"
        assert event.payload == {
            "journey_key": journeys[index].journey_key,
            "status": status.value,
            "outcome": outcome.value if outcome is not None else None,
            "summary": "Checkout observed.",
            "actions": ["Clicked checkout"],
            "observations": ["Saw confirmation"],
            "friction_points": ["Slow page"],
            "blockers": ["Example blocker"],
            "satisfied_criteria": ["Order confirmed"],
            "unsatisfied_criteria": ["Fast response"],
            "final_url": "https://example.com/cart",
        }


@pytest.mark.parametrize(
    "failure", [None, "completed", "storage", "close", "persist_and_close", "upload"]
)
async def test_session_artifacts_after_browser_close(
    plan: MetaAgentPlan,
    failure: str | None,
) -> None:
    request = journey_executor.PersonaJourneyExecutionRequest(
        execution_id=uuid4(),
        journey_id=uuid4(),
        journey=build_persona_journeys(plan)[0],
        start_url="https://example.com",
        allowed_origins=(AllowedOrigin("https", "example.com"),),
    )
    handle = BrowserSessionHandle(uuid4(), request.execution_id, request.journey_id)
    artifacts = BrowserSessionArtifacts(trace_paths=(Path("trace-001.zip"),))
    controller = MagicMock(spec=BrowserController)
    controller.create_session.return_value = handle
    controller.close_session.return_value = artifacts
    session = MagicMock(spec=AsyncSession)
    repository = MagicMock(spec=ExecutionRepository)
    storage = MagicMock(spec=S3ArtifactStorage)
    recorder = MagicMock(spec=SessionArtifactRecorder)
    factory = MagicMock(spec=MetaAgentFactory)
    runner = MagicMock()
    runner.close = AsyncMock()
    runner.session_service.create_session = AsyncMock()

    async def final_events() -> AsyncIterator[MagicMock]:
        event = MagicMock()
        event.is_final_response.return_value = True
        event.content.parts = [MagicMock(text='{"outcome":"passed","summary":"Order confirmed"}')]
        yield event

    runner.run_async.return_value = final_events()
    # Even a failed Journey must upload evidence once its browser closes successfully.
    if failure != "completed":
        factory.create_persona_runtime.side_effect = RuntimeError("Agent failed")
    calls = MagicMock()
    calls.attach_mock(controller.close_session, "close")
    calls.attach_mock(repository.mark_browser_session_closed, "mark_closed")
    calls.attach_mock(session.commit, "commit")
    calls.attach_mock(recorder.record, "record")
    if failure in {"close", "persist_and_close"}:
        controller.close_session.side_effect = RuntimeError("Close failed")
    if failure == "persist_and_close":
        repository.create_browser_session.side_effect = RuntimeError("Persistence failed")
    if failure == "upload":
        recorder.record.side_effect = RuntimeError("Upload failed")

    with (
        patch.object(journey_executor, "ExecutionRepository", return_value=repository),
        patch.object(journey_executor, "InMemoryRunner", return_value=runner),
        patch.object(
            journey_executor, "SessionArtifactRecorder", return_value=recorder
        ) as recorder_class,
        patch.object(S3ArtifactStorage, "from_environment", return_value=storage) as from_env,
    ):
        if failure == "storage":
            from_env.side_effect = RuntimeError("S3_BUCKET must be configured.")
        if failure in {"close", "persist_and_close", "upload"}:
            with pytest.raises(RuntimeError, match="Close failed|Upload failed"):
                await journey_executor.execute_persona_journey(
                    request=request,
                    browser_controller=controller,
                    session=session,
                    factory=factory,
                )
        else:
            result = await journey_executor.execute_persona_journey(
                request=request,
                browser_controller=controller,
                session=session,
                factory=factory,
            )
            assert result.status == (
                JourneyExecutionStatus.COMPLETED
                if failure == "completed"
                else JourneyExecutionStatus.FAILED
            )

    controller.close_session.assert_awaited_once_with(
        session_id=handle.session_id,
        execution_id=request.execution_id,
        journey_id=request.journey_id,
    )
    if failure in {None, "completed", "upload"}:
        recorder_class.assert_called_once_with(
            session=session,
            execution_id=request.execution_id,
            storage=storage,
        )
        recorder.record.assert_awaited_once_with(artifacts)
        assert [call[0] for call in calls.mock_calls][-4:] == [
            "close",
            "mark_closed",
            "commit",
            "record",
        ]
    else:
        recorder_class.assert_not_called()
    if failure == "close":
        session.rollback.assert_awaited_once()
        repository.mark_browser_session_failed.assert_awaited_once_with(
            browser_session_id=handle.session_id,
        )
    elif failure == "persist_and_close":
        repository.mark_browser_session_failed.assert_not_awaited()
