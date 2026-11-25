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

import asyncio
import time
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_database.models import TestRun
from markettwin_shared.persona_definitions import PersonaDefinition

from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.workflow.offsite_browsing import configure_offsite
from markettwin_execution_orchestrator.workflow.lead_review import review_checkpoint
from markettwin_execution_orchestrator.models import ask
from markettwin_execution_orchestrator.persistence import ExecutionRepository, PlanRepository
from markettwin_execution_orchestrator.persistence.persona_definition_repository import (
    PersonaDefinitionRepository,
)
from markettwin_execution_orchestrator.persistence.run_event_repository import (
    RunEventRepository,
)
from markettwin_execution_orchestrator.personas.factory import generate_definitions
from markettwin_execution_orchestrator.workflow.case_execution import (
    MAX_HUMAN_LOGIN_WAIT_SECONDS,
    BrowserHandoffExecution,
    pause_case_deadline,
    request_browser_handoff,
)
from markettwin_execution_orchestrator.workflow.cooperative_pause import cooperative_pause_checkpoint
from markettwin_execution_orchestrator.workflow.harness_state import load_harness_state

if TYPE_CHECKING:
    from markettwin_execution_orchestrator.workflow.run_executor import (
        MarketTwinRunRequest,
    )

# Browser teardown bound (F5): closing a session whose browser died
# with the host (sleep/crash) can await a dead driver forever. The
# close is best-effort; the run's terminal bookkeeping in the same
# finally is not, so the close gets a hard bound (MT-000151).
TEARDOWN_TIMEOUT_SECONDS = 30
_MAX_IMPRESSIONS_PER_PERSONA = 20
# Tab presses per page in the keyboard walk (doc 24 section 3.1):
# enough to cross a header nav and land in page content, few
# enough that a focus trap cannot hold the walk hostage.
KEYBOARD_WALK_TABS = 12
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
    if kind == "focus_indicator_invisible":
        return (
            f"I tabbed to {signal['element']} on {page} and could not "
            "see where I was — nothing about it changed to show focus."
        )
    if kind == "fast_and_clean":
        return f"{page} loaded fast and nothing broke. That felt easy."
    return f"I visited {page}."


def _indicator_visible(state: dict, baseline: dict) -> bool:
    """A visible focus indicator: a real outline, or a box-shadow /
    border / background change against the element's pre-focus style.
    A missing baseline entry gives the page the benefit of the doubt —
    an unbaselined element is never accused."""

    outline = str(state.get("outline_style") or "none")
    width = str(state.get("outline_width") or "0px")
    if outline != "none" and width not in {"0px", "0"}:
        return True
    return any(
        state.get(key) != baseline.get(key)
        for key in ("box_shadow", "background", "border_width", "border_color")
    )


async def _keyboard_walk(
    *, controller, handle, execution_id, journey_id,
) -> tuple[list[tuple[str, dict]], dict]:
    """Up to KEYBOARD_WALK_TABS Tab presses, reading focus after each.

    Returns (impressions, walk_record). no_keyboard_focus is claimed
    only when the full walk completes with zero focus events; a
    focused element with no visible indicator is the
    focus_indicator_invisible impression; a visible indicator produces
    no impression. A controller failure mid-walk produces no
    impression either — the record names the failure instead, because
    a broken controller is not evidence about the page.
    """

    try:
        baseline = await controller.focusable_style_baseline(
            session_id=handle.session_id,
            execution_id=execution_id, journey_id=journey_id,
        )
        steps: list[dict] = []
        invisible: dict | None = None
        for tab in range(1, KEYBOARD_WALK_TABS + 1):
            await controller.focus_next(
                session_id=handle.session_id,
                execution_id=execution_id, journey_id=journey_id,
                observe=False,
            )
            state = await controller.focused_element_state(
                session_id=handle.session_id,
                execution_id=execution_id, journey_id=journey_id,
            )
            if state is None:
                steps.append({"tab": tab, "focused": None})
                continue
            indicator = _indicator_visible(
                state, baseline.get(str(state["ordinal"]), {}),
            )
            steps.append({
                "tab": tab, "role": state["role"], "name": state["name"],
                "indicator_visible": indicator,
            })
            if not indicator and invisible is None:
                invisible = {
                    "element": f"{state['name'] or state['role']} ({state['role']})",
                    "tab": tab,
                }
        record = {"tabs": len(steps), "steps": steps}
        if not any(step.get("role") for step in steps):
            return [("no_keyboard_focus", {"tabs": len(steps)})], record
        if invisible is not None:
            return [("focus_indicator_invisible", invisible)], record
        return [], record
    except Exception as exc:
        return [], {"tabs": 0, "steps": [], "failure": type(exc).__name__}


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
    snapshot = dict(run.configuration_snapshot or {})
    if "persona_definitions_snapshot" in snapshot:
        return [PersonaDefinition.model_validate(value)
                for value in snapshot["persona_definitions_snapshot"]]
    repository = PersonaDefinitionRepository(session)
    rows = await repository.list_for_application(application_id=run.application_id)
    enabled = [
        PersonaDefinition.model_validate(row.definition)
        for row in rows if row.enabled
    ]
    if rows:
        snapshot["persona_definitions_snapshot"] = [definition.model_dump(mode="json") for definition in enabled]
        run.configuration_snapshot = snapshot
        await session.commit()
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
    snapshot["persona_definitions_snapshot"] = [definition.model_dump(mode="json") for definition in generated]
    run.configuration_snapshot = snapshot
    await session.commit()
    return list(generated)


def persona_objectives(request: "MarketTwinRunRequest") -> list[str]:
    """Goal-based persona tasks from the pinned map (doc 21 section 12).

    One objective per recorded journey, phrased from the journey's
    intent -- a goal, never step ids: personas do not step-replay the
    tested walk. Without map journeys the single objective is the
    study brief, exactly as before this wiring existed.
    """
    app_map = getattr(request, "app_map", None)
    journeys = app_map.get("journeys") if isinstance(app_map, dict) else None
    if not isinstance(journeys, list):
        return [request.study_brief]
    objectives: list[str] = []
    for journey in journeys:
        if not isinstance(journey, dict):
            continue
        intent = journey.get("intent") or journey.get("name")
        if not isinstance(intent, str) or not intent.strip():
            continue
        objective = intent.strip()
        terminal = journey.get("terminal_url")
        if isinstance(terminal, str) and terminal:
            objective += f" (The goal is reached at {terminal}.)"
        objectives.append(objective)
    return objectives or [request.study_brief]


async def _walk_persona(
    *, session: AsyncSession, request: "MarketTwinRunRequest",
    controller: BrowserController, definition: PersonaDefinition, ordinal: int = 1,
) -> dict:
    from markettwin_execution_orchestrator.workflow.persona_goal import (
        attempt_goal,
        persona_task_deadline,
    )

    executions = ExecutionRepository(session)
    events = RunEventRepository(session)
    execution_id = uuid4()
    journey = await PlanRepository(session).create_browser_journey(
        test_run_id=request.run_id, ordinal=ordinal, name=definition.name,
        objective=definition.voice.focus,
        attributes={"persona_id": definition.persona_id, "persona_type": definition.type},
    )
    journey_id = journey.journey_id
    await executions.create_agent_execution(
        execution_id=execution_id, journey_id=journey_id,
        runtime_name="persona_walk_v1",
    )
    await session.commit()
    conditions = definition.conditions
    impressions = 0
    walk_failed = False
    handle = None
    try:
        handle = await controller.create_session(
            execution_id=execution_id, journey_id=journey_id,
            allowed_origins=request.allowed_origins,
            network_policy=request.network_policy,
            viewport_size=(conditions.viewport_width, conditions.viewport_height),
            locale=conditions.locale,
        )
        if conditions.input == "keyboard":
            controller.set_keyboard_only(handle)
        await executions.create_browser_session(
            browser_session_id=handle.session_id, execution_id=execution_id,
            test_run_id=request.run_id, session_role="persona",
        )
        await session.commit()
        handoff_seconds = 0.0
        if getattr(request, "runtime_human_assistance", False):
            handoff = BrowserHandoffExecution(
                request.run_id, execution_id, journey_id, request.allowed_origins,
            )

            async def request_help() -> None:
                nonlocal handoff_seconds
                started = time.monotonic()
                try:
                    async def hand_off() -> None:
                        await request_browser_handoff(
                            request=handoff, controller=controller, handle=handle, session=session,
                        )

                    deadline = persona_task_deadline.get()
                    if deadline is None:
                        await hand_off()
                    else:
                        async with pause_case_deadline(
                            deadline, allowance_seconds=MAX_HUMAN_LOGIN_WAIT_SECONDS,
                        ):
                            await hand_off()
                finally:
                    handoff_seconds += time.monotonic() - started

            async def operator_pause() -> None:
                nonlocal handoff_seconds
                started = time.monotonic()
                try:
                    await cooperative_pause_checkpoint(
                        request=handoff, controller=controller, handle=handle, session=session,
                        case_timeout=persona_task_deadline.get(),
                    )
                finally:
                    handoff_seconds += time.monotonic() - started

            controller.bind_authentication_handler(handle, request_help)
            controller.bind_cooperative_pause_handler(handle, operator_pause)
        if conditions.network is not None:
            await controller.emulate_network(
                session_id=handle.session_id,
                latency_ms=conditions.network.latency_ms,
                download_bps=conditions.network.download_bps,
                upload_bps=conditions.network.upload_bps,
            )
        # Start from the same entry page in this persona's isolated session.
        # The task runs before any diagnostic tour can reveal the navigation.
        await controller.navigate(session_id=handle.session_id, url=request.start_url)
        # Persona tasks derive from the graph's journeys (doc 21
        # section 12): one goal-based attempt per recorded journey,
        # stopping early when a task is blocked.
        task: dict = {}
        for objective in persona_objectives(request):
            task = await attempt_goal(
                controller=controller, handle=handle, definition=definition,
                objective=objective,
                seconds=request.max_duration_seconds_per_journey,
            )
            await events.create(
                test_run_id=request.run_id, event_type="persona.task.result",
                journey_id=journey_id, execution_id=execution_id,
                payload={"persona_id": definition.persona_id, "persona_name": definition.name, **task},
            )
            await session.commit()
            if task["status"] in ("blocked", "call_limit_exhausted"):
                break
        review = await review_checkpoint(objective=request.study_brief, evidence={
            "persona": definition.name, "task": task,
        })
        await events.create(test_run_id=request.run_id, event_type="lead.checkpoint",
            journey_id=journey_id, execution_id=execution_id, payload=review)
        await session.commit()
        stop: dict | None = None
        if review["decision"] == "stop":
            # A Lead stop is this persona's alone (doc 24 section
            # 3.2): its own task record names the stop, impressions
            # gathered before it stand, and the walk ends here.
            stop = {
                "stop_kind": review.get("stop_kind"),
                "reason": str(review.get("reason") or ""),
            }
            await events.create(
                test_run_id=request.run_id, event_type="persona.task.result",
                journey_id=journey_id, execution_id=execution_id,
                payload={
                    "persona_id": definition.persona_id,
                    "persona_name": definition.name,
                    "persona_type": definition.type,
                    "status": "stopped_at_checkpoint",
                    "stop_kind": stop["stop_kind"],
                    "reason": stop["reason"],
                    "source": "lead_stop",
                    "impressions": impressions,
                },
            )
            await session.commit()
        journeys = () if task["status"] in ("blocked", "call_limit_exhausted") or review["decision"] == "stop" else definition.journeys or (request.start_url,)
        for url in journeys:
            if impressions >= _MAX_IMPRESSIONS_PER_PERSONA:
                break
            started = time.monotonic()
            handoff_before_navigation = handoff_seconds
            result = await controller.navigate(
                session_id=handle.session_id, url=url,
            )
            assisted_time = handoff_seconds - handoff_before_navigation
            load_ms = max(0, int((time.monotonic() - started - assisted_time) * 1000))
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
                walk_found, walk_record = await _keyboard_walk(
                    controller=controller, handle=handle,
                    execution_id=execution_id, journey_id=journey_id,
                )
                found.extend(walk_found)
                await events.create(
                    test_run_id=request.run_id,
                    event_type="persona.keyboard_walk",
                    journey_id=journey_id, execution_id=execution_id,
                    payload={
                        "persona_id": definition.persona_id,
                        "journey_url": url,
                        **walk_record,
                    },
                )
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
        # Bounded, best-effort teardown (F5): if the browser died with
        # the host, close_session can await a dead driver forever and
        # hold the run open (MT-000151). The bookkeeping below is what
        # closes the run; it must always be reached.
        if handle is not None:
            try:
                async with asyncio.timeout(TEARDOWN_TIMEOUT_SECONDS):
                    await controller.close_session(session_id=handle.session_id)
            except Exception:
                pass
        try:
            # Roll back first: a walk that died mid-flush leaves the
            # session poisoned, and a cleanup write on a poisoned
            # session raises PendingRollbackError — replacing the
            # walk's real error and skipping terminalization entirely.
            # The execution is finished and committed BEFORE the
            # browser row is marked closed, so a failure there can
            # never leave the execution "running"; a leftover open
            # browser row is closed by the worker's startup reaper.
            await session.rollback()
            await executions.finish_agent_execution(
                execution_id=execution_id,
                status="failed" if walk_failed else "completed",
                outcome=None,
            )
            await session.commit()
            if handle is not None:
                await executions.mark_browser_session_closed(
                    browser_session_id=handle.session_id,
                )
                await session.commit()
        except Exception:
            await session.rollback()
            if not walk_failed:
                raise
    return {"impressions": impressions, "stop": stop}


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
    # Redelivery (Astra A3): the worker's recoverable-redelivery
    # path redispatches a run whose row is already "running"
    # (no browser rows yet), and mark_running rejects
    # running -> running. Capture the loaded status now and
    # skip the transition on re-entry -- the guard slop_run
    # already uses.
    already_running = run.status == "running"
    definitions = await _ensure_definitions(
        session=session, request=request, run=run,
    )
    if not definitions:
        raise ValueError("Enable at least one persona before running a persona test.")
    snapshot = dict(run.configuration_snapshot or {})
    if "selected_persona_ids" in snapshot:
        selected = set(snapshot["selected_persona_ids"])
        definitions = [definition for definition in definitions if definition.persona_id in selected]
    else:
        from markettwin_execution_orchestrator.personas.selection import select_personas

        definitions, reason = await select_personas(definitions, objective=request.study_brief, depth=request.testing_depth)
        run.configuration_snapshot = {**snapshot,
            "selected_persona_ids": [definition.persona_id for definition in definitions],
            "persona_selection_reason": reason}
        await session.commit()
    if not already_running:
        await RunStateRepository(session).mark_running(test_run_id=request.run_id)
    await session.commit()
    stopped_personas: list[dict] = []
    walks = 0
    owner_stopped = False
    async with BrowserController() as controller:
        await configure_offsite(controller, run, session)
        for ordinal, definition in enumerate(definitions, start=1):
            # Owner stop (the Stop run button): ctl records the
            # request in the run's configuration snapshot; the run
            # honours it at the next persona boundary — the current
            # walk finishes, the remaining personas never start.
            fresh = await session.get(
                TestRun, request.run_id, populate_existing=True)
            if fresh is not None and isinstance(
                (fresh.configuration_snapshot or {}).get("owner_stop"), dict
            ):
                owner_stopped = True
                await RunEventRepository(session).create(
                    test_run_id=request.run_id, event_type="run.owner_stop",
                    journey_id=None, execution_id=None, payload={})
                await session.commit()
                break
            result = await _walk_persona(
                session=session, request=request, controller=controller,
                definition=definition, ordinal=ordinal,
            )
            walks += 1
            # Stop locality (doc 24 section 3.2): a Lead stop ends
            # only that persona's walk. The remaining personas walk
            # normally and the run completes — a Lead stop of any
            # kind, safety included, never fails the run.
            if result["stop"] is not None:
                stopped_personas.append({
                    "persona_id": definition.persona_id,
                    "stop_kind": result["stop"]["stop_kind"],
                })
    await RunEventRepository(session).create(test_run_id=request.run_id,
        event_type="run.collection", journey_id=None, execution_id=None,
        payload={"run_kind": "persona", "journey_count": walks,
                 "personas_selected": len(definitions),
                 "partial": bool(stopped_personas) or owner_stopped,
                 "owner_stopped": owner_stopped,
                 "stopped_personas": stopped_personas})
    if owner_stopped:
        await RunStateRepository(session).mark_cancelled(
            test_run_id=request.run_id)
    else:
        await RunStateRepository(session).mark_completed(
            test_run_id=request.run_id)
    await session.commit()
