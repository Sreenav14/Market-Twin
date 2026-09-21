"""Meta Agent planning workflow for MarketTwin test runs."""

import json
from dataclasses import dataclass
from typing import Final
from uuid import UUID, uuid4

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.agents.meta_agent import (
    META_AGENT_MAX_TOKENS,
    create_meta_agent,
)
from markettwin_execution_orchestrator.agents.runtime_snapshot import (
    build_meta_runtime_snapshot,
)
from markettwin_execution_orchestrator.agents.schemas.plan import MetaAgentPlan
from markettwin_execution_orchestrator.models.model_factory import (
    resolve_model_runtime_config,
)
from markettwin_execution_orchestrator.models.telemetry import (
    AdkModelInvocationObserver,
)
from markettwin_execution_orchestrator.persistence import (
    ObservabilityRepository,
)

PLANNING_APP_NAME: Final[str] = "markettwin_planning"


@dataclass(frozen=True, slots=True)
class MetaPlanningRequest:
    """Immutable input used to plan one persisted Test Run."""

    test_run_id: UUID
    study_brief: str
    target_snapshot: dict[str, object]


def build_planning_prompt(
    request: MetaPlanningRequest,
) -> str:
    """Build the bounded input supplied to the Meta Agent."""

    context = {
        "study_brief": request.study_brief,
        "target": request.target_snapshot,
    }

    return (
        "Create the MarketTwin testing plan for the following "
        "authorized application target and study goal.\n\n"
        f"{json.dumps(context, indent=2, sort_keys=True)}"
    )


async def generate_meta_agent_plan(
    request: MetaPlanningRequest,
    *,
    session: AsyncSession | None = None,
) -> MetaAgentPlan:
    """Run the Meta Agent and return its validated structured plan."""

    agent = create_meta_agent()
    planning_prompt = build_planning_prompt(request)

    if session is not None:
        model_config = resolve_model_runtime_config(
            max_tokens=META_AGENT_MAX_TOKENS,
        )
        snapshot_id = uuid4()
        snapshot = build_meta_runtime_snapshot(
            test_run_id=request.test_run_id,
            runtime_agent_name=agent.name,
            model_config=model_config,
            effective_instruction=str(agent.instruction),
            runtime_prompt=planning_prompt,
        )

        repository = ObservabilityRepository(session)
        await repository.create_agent_snapshot(
            snapshot_id=snapshot_id,
            snapshot=snapshot,
        )
        await session.commit()

        observer = AdkModelInvocationObserver(
            session=session,
            test_run_id=request.test_run_id,
            agent_snapshot_id=snapshot_id,
            agent_role="meta",
            runtime_agent_name=agent.name,
            model_config=model_config,
        )
        agent.before_model_callback = (
            observer.before_model_callback
        )
        agent.after_model_callback = (
            observer.after_model_callback
        )
        agent.on_model_error_callback = (
            observer.on_model_error_callback
        )

    session_service = InMemorySessionService()

    user_id = f"test_run_{request.test_run_id.hex}"
    session_id = f"planning_{request.test_run_id.hex}"

    await session_service.create_session(
        app_name=PLANNING_APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    runner = Runner(
        agent=agent,
        app_name=PLANNING_APP_NAME,
        session_service=session_service,
    )

    user_context = types.Content(
        role="user",
        parts=[
            types.Part(
                text=planning_prompt
            )
        ],
    )

    final_response: str | None = None

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_context,
        ):
            if (
                event.is_final_response()
                and event.content
                and event.content.parts
            ):
                response_parts = [
                    part.text
                    for part in event.content.parts
                    if part.text
                ]
                if response_parts:
                    final_response = "\n".join(response_parts)
    finally:
        await runner.close()

    if not final_response:
        raise RuntimeError("Meta Agent returned no final planning response")

    return MetaAgentPlan.model_validate_json(final_response)
