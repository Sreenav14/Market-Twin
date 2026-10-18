"""Execute one complete MarketTwin Persona Journey."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass, replace
from typing import Literal, cast
from uuid import UUID, uuid4

from google.adk.runners import InMemoryRunner
from google.genai import types
from markettwin_shared.auth_verification import AuthVerificationPolicy
from markettwin_shared.observability import (
    use_observability_correlation,
)
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.agents.configuration import configure_agent
from markettwin_execution_orchestrator.agents.meta_agent_factory import (
    MetaAgentFactory,
)
from markettwin_execution_orchestrator.agents.persona_agents import (
    build_persona_runtime_snapshot_payload,
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
from markettwin_execution_orchestrator.browser.auth_session_broker import (
    AuthSessionReuseRejected,
    AuthSessionScope,
)
from markettwin_execution_orchestrator.browser.contracts import NetworkPolicy
from markettwin_execution_orchestrator.browser.errors import (
    BrowserPolicyError,
    HumanAssistanceSkipped,
)
from markettwin_execution_orchestrator.browser.mcp_tools import connect_controlled_browser_tools
from markettwin_execution_orchestrator.persistence import (
    AgentRuntimeSnapshotRepository,
    ExecutionRepository,
    ExecutionStepRecorder,
    S3ArtifactStorage,
    SessionArtifactRecorder,
)
from markettwin_execution_orchestrator.workflow.persona_result import (
    JourneyExecutionStatus,
    JourneyOutcome,
    PersonaJourneyResult,
)
from markettwin_execution_orchestrator.workflow.report_validation import validate_execution_report

JOURNEY_APP_NAME = "markettwin_persona_journey"


@dataclass(frozen=True, slots=True)
class PersonaJourneyExecutionRequest:
    """Everything required to execute one already-planned Journey."""

    test_run_id: UUID
    execution_id: UUID
    journey_id: UUID
    persona_id: UUID
    mission_id: UUID

    journey: PersonaJourneySpec

    start_url: str
    allowed_origins: tuple[AllowedOrigin, ...]

    auth_verification: AuthVerificationPolicy | None = None
    auth_session_scope: AuthSessionScope | None = None
    auth_mode: Literal["required", "optional"] = "required"
    runtime_human_assistance: bool = False
    runtime_target_id: UUID | None = None
    network_policy: NetworkPolicy = "public_only"
    max_duration_seconds: int = 180
    prompt_override: dict[str, str] | None = None
    agent_number: int = 2


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
    snapshot_repository = AgentRuntimeSnapshotRepository(session)
    browser_session_persisted = False

    browser_session = None
    runner: InMemoryRunner | None = None
    artifact_storage: S3ArtifactStorage | None = None
    mcp_resources = AsyncExitStack()
    persona_timer: asyncio.Timeout | None = None

    try:
        auth_snapshot = None
        if request.auth_session_scope is not None:
            try:
                auth_snapshot = browser_controller.take_auth_session_snapshot(
                    scope=request.auth_session_scope, case_id=request.journey.journey_key,
                )
            except AuthSessionReuseRejected:
                pass
        elif request.runtime_human_assistance and request.runtime_target_id is not None:
            try:
                auth_snapshot = browser_controller.take_human_session_snapshot(
                    run_id=request.test_run_id, target_id=request.runtime_target_id,
                    case_id=request.journey.journey_key,
                )
            except AuthSessionReuseRejected:
                pass
        browser_session = await browser_controller.create_session(
            execution_id=request.execution_id,
            journey_id=request.journey_id,
            allowed_origins=request.allowed_origins,
            network_policy=request.network_policy,
            auth_snapshot=auth_snapshot,
            auth_only_origins=(request.auth_verification.auth_only_origins
                               if request.auth_verification else ()),
            authenticated_session=(request.auth_verification is not None
                                   or request.runtime_human_assistance),
        )

        await execution_repository.create_browser_session(
            browser_session_id=browser_session.session_id,
            execution_id=request.execution_id,
        )

        await session.commit()

        browser_session_persisted = True
        if request.auth_verification is not None:
            from markettwin_execution_orchestrator.workflow.case_execution import (
                MAX_HUMAN_LOGIN_WAIT_SECONDS,
                pause_case_deadline,
                verify_or_request_login,
            )
            policy, auth_scope, handle = (
                request.auth_verification, request.auth_session_scope, browser_session,
            )
            if auth_scope is None:
                raise BrowserPolicyError("The approved authentication scope is unavailable.")

            async def verify_login() -> None:
                await verify_or_request_login(
                    request=request, controller=browser_controller, handle=handle,
                    policy=policy, auth_scope=auth_scope, session=session,
                    max_wait_seconds=MAX_HUMAN_LOGIN_WAIT_SECONDS,
                )

            async def request_login() -> None:
                if persona_timer is None:
                    await verify_login()
                else:
                    async with pause_case_deadline(
                        persona_timer, allowance_seconds=MAX_HUMAN_LOGIN_WAIT_SECONDS,
                    ):
                        await verify_login()

            browser_controller.bind_authentication_handler(handle, request_login)
            # Navigate once before the persona starts. Human login is a bounded
            # prerequisite outside the agent's model execution deadline.
            await browser_controller.navigate(session_id=handle.session_id, url=request.start_url)
            if request.auth_mode == "required" or auth_snapshot is not None:
                verified = await browser_controller.verify_authenticated_role(
                    handle=handle, policy=policy,
                )
                if verified is None:
                    browser_controller.revoke_auth_session_snapshot(scope=auth_scope)
                await request_login()
        elif request.runtime_human_assistance:
            from markettwin_execution_orchestrator.workflow.case_execution import (
                MAX_HUMAN_LOGIN_WAIT_SECONDS,
                pause_case_deadline,
                request_runtime_assistance,
            )
            handle = browser_session

            async def request_runtime_help() -> None:
                if persona_timer is None:
                    await request_runtime_assistance(
                        request=request, controller=browser_controller, handle=handle,
                        session=session,
                    )
                else:
                    async with pause_case_deadline(
                        persona_timer, allowance_seconds=MAX_HUMAN_LOGIN_WAIT_SECONDS,
                    ):
                        await request_runtime_assistance(
                            request=request, controller=browser_controller, handle=handle,
                            session=session,
                        )

            browser_controller.bind_authentication_handler(handle, request_runtime_help)

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
        snapshot_id = uuid4()
        # MCP background handlers inherit context when their tasks are created.
        with use_observability_correlation(
            test_run_id=request.test_run_id,
            journey_id=request.journey_id,
            execution_id=request.execution_id,
            agent_snapshot_id=snapshot_id,
            persona_id=request.persona_id,
            mission_id=request.mission_id,
            agent_role="persona",
        ):
            async with asyncio.timeout(10):
                mcp_tools = await mcp_resources.enter_async_context(
                    connect_controlled_browser_tools(runtime.browser_tools)
                )
        runtime.agent.tools = list(mcp_tools)
        
        if request.prompt_override is not None:
            runtime.agent.instruction = request.prompt_override["instruction"]
        runtime_prompt = (
            request.prompt_override["runtime_prompt"]
            if request.prompt_override is not None
            else _build_journey_prompt(request)
        )
        
        root_agent, structure, primary_configuration = configure_agent(
            runtime.agent, request.prompt_override,
            name=f"Agent_{request.agent_number}", max_tokens=2048, browser_allowed=True,
        )
        snapshot_payload = (
            build_persona_runtime_snapshot_payload(
                journey=request.journey,
                agent=runtime.agent,
                browser_tools=runtime.browser_tools,
                runtime_prompt=runtime_prompt,
            )
        )
        snapshot_payload = replace(
            snapshot_payload,
            runtime_agent_name=root_agent.name,
            model_configuration=cast(
                dict[str, object], primary_configuration["model_configuration"],
            ),
            tools=tuple(cast(list[str], primary_configuration["tools"])),
            metadata={**snapshot_payload.metadata, "browser_tool_transport": "mcp_memory",
                      "agent_structure": structure},
        )
        
        await snapshot_repository.create(
            snapshot_id=snapshot_id,
            test_run_id=request.test_run_id,
            journey_id=request.journey_id,
            execution_id=request.execution_id,
            payload=snapshot_payload,
        )

        await session.commit()

        runner = InMemoryRunner(
            agent=root_agent,
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

        with use_observability_correlation(
            test_run_id=request.test_run_id,
            journey_id=request.journey_id,
            execution_id=request.execution_id,
            agent_snapshot_id=snapshot_id,
            persona_id=request.persona_id,
            mission_id=request.mission_id,
            agent_role="persona",
        ):
            async with asyncio.timeout(
                request.max_duration_seconds
            ) as persona_timer:
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=message,
                ):
                    if (
                        event.is_final_response()
                        and event.author == runtime.agent.name
                        and event.content
                        and event.content.parts
                    ):
                        final_response_parts.extend(
                            part.text
                            for part in event.content.parts
                            if part.text
                        )

        if not final_response_parts:
            raise RuntimeError("Persona Agent returned no final Journey response.")

        reported = _parse_persona_report("\n".join(final_response_parts))
        validation = await validate_execution_report(
            report=reported, success_criteria=request.journey.mission.success_criteria,
            execution_id=request.execution_id, session=session,
        )
        report = validation.report

        return PersonaJourneyResult(
            journey=request.journey,
            status=(JourneyExecutionStatus.POLICY_BLOCKED if validation.policy_blocked
                    else JourneyExecutionStatus.COMPLETED),
            outcome=None if validation.policy_blocked else JourneyOutcome(report.outcome),
            reported_outcome=JourneyOutcome(reported.outcome),
            reported_criterion_evidence=reported.criterion_evidence,
            reported_unsatisfied_criteria=reported.unsatisfied_criteria,
            report_validation_issues=validation.issues,
            summary=("Journey blocked by browser policy; the reported outcome was not accepted."
                     if validation.policy_blocked else report.summary),
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

    except HumanAssistanceSkipped:
        return PersonaJourneyResult(
            journey=request.journey, status=JourneyExecutionStatus.SKIPPED,
            summary="Not tested—human assistance skipped.",
        )
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
        try:
            try:
                if runner is not None:
                    await runner.close()
            finally:
                await mcp_resources.aclose()
        finally:
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
