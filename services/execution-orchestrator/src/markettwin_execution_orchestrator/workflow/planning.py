"""Meta Agent planning workflow for MarketTwin test runs."""

import json
from dataclasses import dataclass
from typing import Final
from uuid import UUID, uuid4

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from markettwin_shared.observability import (
    use_observability_correlation,
)
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.agents.meta_agent import (
    build_meta_runtime_snapshot_payload,
    create_meta_agent,
)
from markettwin_execution_orchestrator.agents.schemas.plan import MetaAgentPlan
from markettwin_execution_orchestrator.persistence import (
    AgentRuntimeSnapshotRepository,
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
    *,
    request: MetaPlanningRequest,
    session: AsyncSession,
) -> MetaAgentPlan:
    """Run the Meta Agent and return its validated structured plan."""
    
    agent = create_meta_agent()
    
    runtime_prompt = build_planning_prompt(request)
    
    snapshot_payload = (
        build_meta_runtime_snapshot_payload(
            agent=agent,
            runtime_prompt=runtime_prompt,
        )
    )
    
    snapshot_repository = (
        AgentRuntimeSnapshotRepository(session)
    )
    
    snapshot_id = uuid4()
    
    await snapshot_repository.create(
        snapshot_id=snapshot_id,
        test_run_id=request.test_run_id,
        payload=snapshot_payload,
    )
    
    await session.commit()
    
    session_service = InMemorySessionService()
    
    user_id = f"test_run_{request.test_run_id.hex}"
    session_id = f"planning_{request.test_run_id.hex}"
    
    await session_service.create_session(
        app_name = PLANNING_APP_NAME,
        user_id = user_id,
        session_id = session_id,
    )
    
    runner = Runner(
        agent = agent,
        app_name = PLANNING_APP_NAME,
        session_service = session_service,
    )
    
    user_context = types.Content(
        role = "user",
        parts = [
            types.Part(
                text = runtime_prompt,
            )
        ],
    )
    
    final_response: str | None = None
    
    try:
        with use_observability_correlation(
            test_run_id=request.test_run_id,
            agent_snapshot_id=snapshot_id,
            agent_role="meta",
        ):
            async for event in runner.run_async(
                user_id = user_id,
                session_id = session_id,
                new_message = user_context,
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