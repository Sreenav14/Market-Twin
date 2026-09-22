"""Execute one complete MarketTwin Persona Journey."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.agents.meta_agent_factory import (
    MetaAgentFactory,
)
from markettwin_execution_orchestrator.agents.runtime_snapshot import (
    build_persona_runtime_snapshot,
)
from markettwin_execution_orchestrator.agents.schemas.journey import (
    PersonaJourneySpec,
)
from markettwin_execution_orchestrator.agents.schemas.persona_report import (
    PersonaAgentReport,
)
from markettwin_execution_orchestrator.browser import (
    AllowedOrigin,
    BrowserController,
)
from markettwin_execution_orchestrator.browser.contracts import NetworkPolicy
from markettwin_execution_orchestrator.browser.errors import (
    BrowserPolicyError,
)
from markettwin_execution_orchestrator.models.model_factory import (
    resolve_model_runtime_config,
)
from markettwin_execution_orchestrator.models.telemetry import (
    AdkModelInvocationObserver,
)
from markettwin_execution_orchestrator.persistence import (
    ExecutionRepository,
    ExecutionStepRecorder,
    ObservabilityRepository,
    S3ArtifactStorage,
    SessionArtifactRecorder,
)
from markettwin_execution_orchestrator.workflow.persona_result import (
    JourneyExecutionStatus,
    JourneyOutcome,
    PersonaJourneyResult,
)

JOURNEY_APP_NAME = "markettwin_persona_journey"


@dataclass(frozen=True, slots=True)
class PersonaJourneyExecutionRequest:
    """Everything required to execute one already-planned Journey."""

    test_run_id: UUID
    execution_id: UUID
    journey_id: UUID

    journey: PersonaJourneySpec

    start_url: str
    allowed_origins: tuple[AllowedOrigin, ...]

    network_policy: NetworkPolicy = "public_only"
    max_duration_seconds: int = 180


def _build_journey_prompt(
    request: PersonaJourneyExecutionRequest,
) -> str:
    """Build the runtime instruction supplied to the Persona Agent."""

    return f"""
Execute your assigned MarketTwin Journey.

Authorized starting URL:
{request.start_url}

Start by navigating to the authorized starting URL.

Complete the mission according to your persona, the mission objective,
and its success criteria.

Use only the MarketTwin browser tools available to you.

When the Journey is complete, impossible, or blocked, stop using tools
and return the required JSON final response.
""".strip()


def _parse_persona_report(raw_response: str) -> PersonaAgentReport:
    """Validate the Persona Agent's final response."""

    candidate = raw_response.strip()

    if candidate.startswith("```json"):
        candidate = candidate.removeprefix("```json").strip()

    if candidate.startswith("```"):
        candidate = candidate.removeprefix("```").strip()

    if candidate.endswith("```"):
        candidate = candidate.removesuffix("```").strip()

    return PersonaAgentReport.model_validate_json(candidate)


async def execute_persona_journey(
    *,
    request: PersonaJourneyExecutionRequest,
    browser_controller: BrowserController,
    session: AsyncSession,
    factory: MetaAgentFactory | None = None,
) -> PersonaJourneyResult:
    """Execute one Persona Journey from browser creation through cleanup."""

    if request.max_duration_seconds <= 0:
        raise ValueError("max_duration_seconds must be positive")

    runtime_factory = factory or MetaAgentFactory()
    execution_repository = ExecutionRepository(session)
    browser_session_persisted = False

    browser_session = None
    runner: InMemoryRunner | None = None
    artifact_storage: S3ArtifactStorage | None = None

    try:
        browser_session = await browser_controller.create_session(
            execution_id=request.execution_id,
            journey_id=request.journey_id,
            allowed_origins=request.allowed_origins,
            network_policy=request.network_policy,
        )

        await execution_repository.create_browser_session(
            browser_session_id=browser_session.session_id,
            execution_id=request.execution_id,
        )

        await session.commit()

        browser_session_persisted = True

        artifact_storage = await asyncio.to_thread(S3ArtifactStorage.from_environment)

        step_recorder = ExecutionStepRecorder(
            session=session,
            execution_id=request.execution_id,
            storage=artifact_storage,
        )

        runtime = runtime_factory.create_persona_runtime(
            journey=request.journey,
            browser_controller=browser_controller,
            browser_session=browser_session,
            step_recorder=step_recorder,
        )

        model_config = resolve_model_runtime_config()
        runtime_prompt = _build_journey_prompt(request)
        snapshot_id = uuid4()

        snapshot = build_persona_runtime_snapshot(
            test_run_id=request.test_run_id,
            journey_id=request.journey_id,
            execution_id=request.execution_id,
            journey=request.journey,
            runtime_agent_name=runtime.agent.name,
            model_config=model_config,
            effective_instruction=str(runtime.agent.instruction),
            runtime_prompt=runtime_prompt,
            # ADK leaves callable return types unspecified; snapshots only read tool names.
            tools=cast(
                Sequence[object],
                runtime.agent.tools,  # pyright: ignore[reportUnknownMemberType]
            ),
        )

        observability_repository = ObservabilityRepository(
            session
        )
        await observability_repository.create_agent_snapshot(
            snapshot_id=snapshot_id,
            snapshot=snapshot,
        )
        await session.commit()

        observer = AdkModelInvocationObserver(
            session=session,
            test_run_id=request.test_run_id,
            journey_id=request.journey_id,
            execution_id=request.execution_id,
            agent_snapshot_id=snapshot_id,
            agent_role="persona",
            runtime_agent_name=runtime.agent.name,
            model_config=model_config,
        )
        runtime.agent.before_model_callback = (
            observer.before_model_callback
        )
        runtime.agent.after_model_callback = (
            observer.after_model_callback
        )
        runtime.agent.on_model_error_callback = (
            observer.on_model_error_callback
        )

        runner = InMemoryRunner(
            agent=runtime.agent,
            app_name=JOURNEY_APP_NAME,
        )

        user_id = f"execution_{request.execution_id.hex}"
        session_id = f"journey_{request.journey_id.hex}_{uuid4().hex}"

        await runner.session_service.create_session(
            app_name=JOURNEY_APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )

        message = types.Content(
            role="user",
            parts=[
                types.Part(
                    text=runtime_prompt,
                )
            ],
        )

        final_response_parts: list[str] = []

        async with asyncio.timeout(request.max_duration_seconds):
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message,
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    final_response_parts.extend(
                        part.text for part in event.content.parts if part.text
                    )

        if not final_response_parts:
            raise RuntimeError("Persona Agent returned no final Journey response.")

        report = _parse_persona_report("\n".join(final_response_parts))

        return PersonaJourneyResult(
            journey=request.journey,
            status=JourneyExecutionStatus.COMPLETED,
            outcome=JourneyOutcome(report.outcome),
            summary=report.summary,
            actions=report.actions,
            observations=report.observations,
            friction_points=report.friction_points,
            blockers=report.blockers,
            satisfied_criteria=report.satisfied_criteria,
            criterion_evidence=report.criterion_evidence,
            unsatisfied_criteria=report.unsatisfied_criteria,
            final_url=report.final_url,
        )

    except SQLAlchemyError:
        await session.rollback()
        raise

    except BrowserPolicyError as exc:
        return PersonaJourneyResult(
            journey=request.journey,
            status=JourneyExecutionStatus.POLICY_BLOCKED,
            summary=str(exc),
            blockers=(str(exc),),
        )

    except TimeoutError:
        return PersonaJourneyResult(
            journey=request.journey,
            status=JourneyExecutionStatus.TIMED_OUT,
            summary=("Persona Journey exceeded the configured execution time."),
            blockers=("Journey execution timed out.",),
        )

    except ValidationError as exc:
        return PersonaJourneyResult(
            journey=request.journey,
            status=JourneyExecutionStatus.FAILED,
            summary="Persona Agent returned an invalid structured result.",
            blockers=(str(exc),),
        )

    except Exception as exc:
        return PersonaJourneyResult(
            journey=request.journey,
            status=JourneyExecutionStatus.FAILED,
            summary="Persona Journey execution failed.",
            blockers=(str(exc),),
        )

    finally:
        if runner is not None:
            await runner.close()

        if browser_session is not None:
            try:
                session_artifacts = await browser_controller.close_session(
                    session_id=browser_session.session_id,
                    execution_id=request.execution_id,
                    journey_id=request.journey_id,
                )

            except Exception:
                if browser_session_persisted:
                    await session.rollback()

                    await execution_repository.mark_browser_session_failed(
                        browser_session_id=browser_session.session_id,
                    )

                    await session.commit()
                raise

            else:
                if browser_session_persisted:
                    await execution_repository.mark_browser_session_closed(
                        browser_session_id=browser_session.session_id,
                    )

                    await session.commit()

                if artifact_storage is not None:
                    session_artifact_recorder = SessionArtifactRecorder(
                        session=session,
                        execution_id=request.execution_id,
                        storage=artifact_storage,
                    )
                    await session_artifact_recorder.record(session_artifacts)
