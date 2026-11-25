"""Attach durable run-wide browsing supervision to a run's browser controller."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_database.models import RunEvent
from markettwin_execution_orchestrator.browser.offsite import OffsiteBrowsing
from markettwin_execution_orchestrator.models import ask
from markettwin_execution_orchestrator.persistence.run_event_repository import RunEventRepository


async def configure_offsite(controller, run, session: AsyncSession) -> None:
    # Supervised freedom is the default for every run (owner decision,
    # 2026-11-13): the agent may roam the public web, and every outside
    # navigation is Lead-reviewed with durable records. The mechanical
    # guardrails live in the browser policy, not in an opt-in switch.
    async def review(source: str, destination: str, goal: str) -> tuple[str, str]:
        return await ask.review_offsite_navigation(source=source, destination=destination, goal=goal)

    async def save(kind, payload, journey_id, execution_id) -> None:
        # Route callbacks can run while the caller's session is recording a
        # step. Never concurrently use that SQLAlchemy session or its transaction.
        async with AsyncSession(bind=session.bind, expire_on_commit=False) as events:
            await RunEventRepository(events).create(
                test_run_id=run.id, event_type=kind, payload=payload,
                journey_id=journey_id, execution_id=execution_id,
            )
            await events.commit()

    latest = await session.scalar(select(RunEvent).where(
        RunEvent.test_run_id == run.id,
        RunEvent.event_type.in_(("offsite.continue", "offsite.stop", "offsite.domain_changed")),
    ).order_by(RunEvent.id.desc()).limit(1))
    policy = OffsiteBrowsing(goal=str(run.configuration_snapshot.get("study_brief", "")),
                            review=review, save=save)
    state = latest.payload.get("state") if latest is not None else None
    if isinstance(state, dict):
        policy.pages = dict(state.get("pages") or {})
        policy.approved = set(state.get("approved") or [])
        policy.stopped = dict(state.get("stopped") or {})
        policy.deadline = state.get("deadline")
    controller.offsite = policy
