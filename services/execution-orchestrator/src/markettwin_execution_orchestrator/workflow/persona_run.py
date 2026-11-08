"""Persona run executor (U-P5-04): condition-true walks, anchored quotes.

Each enabled persona definition walks the app's journeys in its OWN
browser session, created with the definition's canonical conditions
as real browser settings (viewport, locale, CDP network throttling,
keyboard-only input). The walk measures; impressions are published
as persona.impression events carrying the measured signal and a
first-person quote anchored to the exact page. There are no scores
anywhere in this path, and nothing here can touch a verdict: the
events are a separate stream the evaluation worker renders as a
quotes report with no verdict field.
"""

import time
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_database.models import TestRun
from markettwin_shared.persona_definitions import PersonaDefinition

from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.models import ask
from markettwin_execution_orchestrator.persistence import ExecutionRepository
from markettwin_execution_orchestrator.persistence.persona_definition_repository import (
    PersonaDefinitionRepository,
)
from markettwin_execution_orchestrator.persistence.run_event_repository import (
    RunEventRepository,
)
from markettwin_execution_orchestrator.personas.factory import generate_definitions
from markettwin_execution_orchestrator.workflow.harness_state import load_harness_state

if TYPE_CHECKING:
    from markettwin_execution_orchestrator.workflow.run_executor import (
        MarketTwinRunRequest,
    )

_MAX_IMPRESSIONS_PER_PERSONA = 20
_INTERACTIVE_ROLES = {"button", "link", "textbox", "checkbox", "radio", "combobox"}


def _quote(
    definition: PersonaDefinition, *, kind: str, page: str, signal: dict,
) -> str:
    """First-person wording for one measured signal. Template v1: the
    words are generated from the measurement, never invented numbers."""

    if kind == "slow_load":
        seconds = signal["load_ms"] / 1000
        return (
            f"I waited {seconds:.1f} seconds for {page} to load. "
            "On a slow connection I would have given up."
            if definition.type == "impatient_mobile"
            else f"I waited {seconds:.1f} seconds for {page} to load. That felt slow."
        )
    if kind == "page_errors":
        return (
            f"Something on {page} broke while I was looking at it — "
            f"{signal['error_count']} error(s) appeared."
        )
    if kind == "small_targets":
        return (
            f"{signal['small_targets']} things I might tap on {page} are "
            "smaller than my fingertip. I would mis-tap them."
        )
    if kind == "no_keyboard_focus":
        return (
            f"I pressed Tab on {page} and nothing took focus. "
            "I cannot use this page at all."
        )
    if kind == "fast_and_clean":
        return f"{page} loaded fast and nothing broke. That felt easy."
    return f"I visited {page}."


async def _latest_board_state_urls(
    session: AsyncSession, *, application_id: UUID, exclude_run_id: UUID,
) -> list[str]:
    """State URLs from the application's most recent Board, if any."""

    rows = await session.execute(
        select(TestRun)
        .where(
            TestRun.application_id == application_id,
            TestRun.id != exclude_run_id,
        )
        .order_by(TestRun.created_at.desc())
        .limit(10)
    )
    for run in rows.scalars():
        state = await load_harness_state(session, run.id)
        if state is not None and state.states:
            return [board_state.url for board_state in state.states.values()]
    return []


async def _ensure_definitions(
    *, session: AsyncSession, request: "MarketTwinRunRequest",
    run: TestRun,
) -> list[PersonaDefinition]:
    repository = PersonaDefinitionRepository(session)
    rows = await repository.list_for_application(application_id=run.application_id)
    enabled = [
        PersonaDefinition.model_validate(row.definition)
        for row in rows if row.enabled
    ]
    if enabled:
        return enabled
    state_urls = await _latest_board_state_urls(
        session, application_id=run.application_id, exclude_run_id=request.run_id,
    ) or [request.start_url]
    generated = generate_definitions(
        state_urls=state_urls,
        existing_persona_ids={row.persona_id for row in rows},
    )
    for definition in generated:
        await repository.upsert(
            application_id=run.application_id, definition=definition,
            source_run_id=None,
        )
    await session.commit()
    return list(generated)


async def _walk_persona(
    *, session: AsyncSession, request: "MarketTwinRunRequest",
    controller: BrowserController, definition: PersonaDefinition,
) -> int:
    executions = ExecutionRepository(session)
    events = RunEventRepository(session)
    execution_id = uuid4()
    journey_id = uuid4()
    await executions.create_agent_execution(
        execution_id=execution_id, journey_id=journey_id,
        runtime_name="persona_walk_v1",
    )
    await session.commit()
    conditions = definition.conditions
    handle = await controller.create_session(
        execution_id=execution_id, journey_id=journey_id,
        allowed_origins=request.allowed_origins,
        network_policy=request.network_policy,
        viewport_size=(conditions.viewport_width, conditions.viewport_height),
        locale=conditions.locale,
    )
    impressions = 0
    walk_failed = False
    try:
        await executions.create_browser_session(
            browser_session_id=handle.session_id, execution_id=execution_id,
            test_run_id=request.run_id, session_role="persona",
        )
        await session.commit()
        if conditions.network is not None:
            await controller.emulate_network(
                session_id=handle.session_id,
                latency_ms=conditions.network.latency_ms,
                download_bps=conditions.network.download_bps,
                upload_bps=conditions.network.upload_bps,
            )
        journeys = definition.journeys or (request.start_url,)
        for url in journeys:
            if impressions >= _MAX_IMPRESSIONS_PER_PERSONA:
                break
            started = time.monotonic()
            result = await controller.navigate(
                session_id=handle.session_id, url=url,
            )
            load_ms = int((time.monotonic() - started) * 1000)
            observation = result.observation
            page = observation.title or url
            found: list[tuple[str, dict]] = []
            error_count = len(observation.console_errors_since_last_action) + len(
                observation.page_errors_since_last_action
            )
            if error_count:
                found.append(("page_errors", {"error_count": error_count}))
            slow_threshold = 1500 if conditions.network is not None else 3000
            if load_ms > slow_threshold:
                found.append(("slow_load", {"load_ms": load_ms}))
            small_targets = sum(
                1 for element in observation.visible_elements
                if element.role in _INTERACTIVE_ROLES
                and (element.bounding_box.width < 24 or element.bounding_box.height < 24)
            )
            if small_targets and conditions.input in {"touch", "pointer"}:
                found.append(("small_targets", {"small_targets": small_targets}))
            if conditions.input == "keyboard":
                focus_result = None
                try:
                    focus_result = await controller.focus_next(
                        session_id=handle.session_id,
                        execution_id=execution_id, journey_id=journey_id,
                    )
                except Exception:
                    # A controller failure is not evidence about the
                    # page; it must never become a "no focus" quote.
                    focus_result = None
                if (
                    focus_result is not None
                    and focus_result.observation.aria_snapshot
                    == observation.aria_snapshot
                ):
                    found.append(("no_keyboard_focus", {}))
            if not found and load_ms < 800 and error_count == 0:
                found.append(("fast_and_clean", {"load_ms": load_ms}))
            for kind, signal in found:
                if impressions >= _MAX_IMPRESSIONS_PER_PERSONA:
                    break
                # Kind + wording pass through the ask door (U-P7):
                # classification is deterministic-first; narration is
                # Model-written when available, template otherwise.
                # The door never raises into the walk.
                kind = await ask.classify_impression(
                    kind_hint=kind, signal=signal,
                )
                quote = await ask.narrate_impression(
                    persona_name=definition.name,
                    persona_type=definition.type,
                    kind=kind, signal=signal, page_title=page,
                    fallback=_quote(
                        definition, kind=kind, page=page, signal=signal,
                    ),
                )
                await events.create(
                    test_run_id=request.run_id,
                    event_type="persona.impression",
                    journey_id=journey_id,
                    execution_id=execution_id,
                    payload={
                        "persona_id": definition.persona_id,
                        "persona_name": definition.name,
                        "persona_type": definition.type,
                        "journey_url": url,
                        "page_title": page,
                        "kind": kind,
                        "quote": quote,
                        "signal": signal,
                    },
                )
                impressions += 1
            await session.commit()
    except BaseException:
        walk_failed = True
        raise
    finally:
        await controller.close_session(session_id=handle.session_id)
        await executions.mark_browser_session_closed(
            browser_session_id=handle.session_id,
        )
        await executions.finish_agent_execution(
            execution_id=execution_id,
            status="failed" if walk_failed else "completed",
            outcome=None,
        )
        await session.commit()
    return impressions


async def execute_persona_run(
    *, request: "MarketTwinRunRequest", session: AsyncSession,
) -> None:
    """Run every enabled persona for the run's application."""

    from markettwin_execution_orchestrator.persistence.run_state_repository import (
        RunStateRepository,
    )

    run = await session.get(TestRun, request.run_id)
    if run is None:
        raise ValueError("Persona run requires a persisted test run.")
    definitions = await _ensure_definitions(
        session=session, request=request, run=run,
    )
    await RunStateRepository(session).mark_running(test_run_id=request.run_id)
    await session.commit()
    async with BrowserController() as controller:
        for definition in definitions:
            await _walk_persona(
                session=session, request=request, controller=controller,
                definition=definition,
            )
    # Reached only when every walk finished: like the Board engine,
    # the executor owns the run's terminal state. Without this the
    # run stays "running" forever and a Kafka redelivery would mark
    # the finished run failed.
    await RunStateRepository(session).mark_completed(test_run_id=request.run_id)
    await session.commit()
