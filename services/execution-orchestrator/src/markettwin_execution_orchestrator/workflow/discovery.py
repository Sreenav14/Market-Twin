"""Bounded discovery with durable browser evidence and no product verdicts."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from functools import wraps
from typing import TYPE_CHECKING, Literal, cast
from urllib.parse import urlsplit
from uuid import uuid4

from google.adk.agents.run_config import RunConfig
from google.adk.runners import InMemoryRunner
from google.genai import types
from markettwin_database.models import ExecutionStep, TestRun
from markettwin_shared.discovery_contract import (
    BlockedReason,
    DiscoveredFeature,
    DiscoveredJourney,
    DiscoveredStep,
    DiscoveryAction,
    DiscoveryMap,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.agents.discovery_agent import create_discovery_agent
from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserPolicyError
from markettwin_execution_orchestrator.browser.tools import BrowserTool, create_browser_tools
from markettwin_execution_orchestrator.persistence import (
    ExecutionRepository,
    ExecutionStepRecorder,
    PlanRepository,
    S3ArtifactStorage,
    SessionArtifactRecorder,
)
from markettwin_execution_orchestrator.persistence.run_event_repository import RunEventRepository
from markettwin_execution_orchestrator.persistence.run_state_repository import RunStateRepository
from markettwin_execution_orchestrator.workflow.deep_run import default_scope

if TYPE_CHECKING:
    from markettwin_execution_orchestrator.workflow.run_executor import MarketTwinRunRequest

ACT_TOOLS = frozenset({
    "browser_navigate", "browser_click", "browser_fill", "browser_select", "browser_check",
    "browser_uncheck", "browser_go_back", "browser_fill_safe", "browser_select_safe",
})


@dataclass
class DiscoveryProgressTracker:
    calls: int = 0
    consecutive_observations: int = 0
    scrolls_by_url: Counter[str] = field(default_factory=Counter[str])
    failed_locators: Counter[str] = field(default_factory=Counter[str])

    def reset_journey(self) -> None:
        self.consecutive_observations = 0
        self.scrolls_by_url.clear()
        self.failed_locators.clear()

    def before_call(self, name: str, url: str) -> BlockedReason | None:
        self.calls += 1
        if self.calls > 60:
            return "step_budget"
        if name in ACT_TOOLS:
            self.consecutive_observations = 0
            self.scrolls_by_url.clear()
        elif name not in {"browser_begin_journey", "browser_end_journey"}:
            self.consecutive_observations += 1
            if name == "browser_scroll":
                self.scrolls_by_url[url] += 1
            if self.consecutive_observations >= 5 or self.scrolls_by_url[url] >= 4:
                return "observation_loop"
        return None

    def failed_locator(self, arguments: dict[str, object]) -> BlockedReason | None:
        signature = json.dumps({key: arguments.get(key) for key in
                                ("role", "name", "label", "text", "scope_role", "scope_name")},
                               sort_keys=True)
        self.failed_locators[signature] += 1
        return "target_not_found" if self.failed_locators[signature] >= 2 else None

    @property
    def reminder(self) -> str | None:
        if self.consecutive_observations >= 3:
            return ("You have observed 3 times without acting. Either perform a concrete action "
                    "toward a journey now, or end this journey attempt with a blocked_reason.")
        return None


class AuthenticationRequired(BrowserPolicyError):
    """Discovery must stop at login instead of requesting credentials."""


def journey_key(steps: tuple[DiscoveredStep, ...], title: str) -> str:
    payload = [s.model_dump(exclude={"execution_step_id", "ordinal"}) for s in steps]
    digest = hashlib.sha256(json.dumps(payload or title, sort_keys=True).encode()).hexdigest()[:20]
    return f"journey_{digest}"


@dataclass
class DiscoveryJournal:
    origin: str
    tracker: DiscoveryProgressTracker = field(default_factory=DiscoveryProgressTracker)
    journeys: list[DiscoveredJourney] = field(default_factory=list[DiscoveredJourney])
    notes: list[str] = field(default_factory=list[str])
    title: str | None = None
    feature_key: str = "application"
    steps: list[DiscoveredStep] = field(default_factory=list[DiscoveredStep])
    indexed_paths: set[str] = field(default_factory=set[str])
    indexed_controls: dict[str, list[dict[str, object]]] = field(
        default_factory=dict[str, list[dict[str, object]]],
    )
    current_path: str = "/"
    current_page: str = "/"
    observation: dict[str, object] = field(default_factory=dict[str, object])

    def locator_observation(self) -> dict[str, object]:
        return {**self.observation, "visible_elements": [
            *self.indexed_controls.get(self.current_page, []),
            *cast(list[dict[str, object]], self.observation.get("visible_elements", [])),
        ]}

    def end(self, completed: bool, reason: BlockedReason | None = None) -> None:
        if self.title is None:
            return
        if not any(s.action in {"click", "fill", "select", "check", "uncheck"} for s in self.steps):
            completed, reason = False, reason or "target_not_found"
        if self.current_page not in self.indexed_paths and reason == "target_not_found":
            completed = False
            self.notes.append(f"{self.title}: full-page controls were not indexed.")
        steps = tuple(self.steps)
        journey = DiscoveredJourney(
            journey_key=journey_key(steps, self.title), title=self.title,
            feature_key=self.feature_key, completed=completed,
            blocked_reason=None if completed else reason or "unknown", steps=steps,
        )
        if journey.journey_key not in {j.journey_key for j in self.journeys}:
            self.journeys.append(journey)
        if journey.blocked_reason:
            self.notes.append(f"{journey.title}: {journey.blocked_reason}.")
        self.title, self.steps = None, []

    def unused_indexed_controls(self) -> tuple[dict[str, object], ...]:
        used = {
            (s.target_role, s.target_name)
            for journey in self.journeys
            for s in journey.steps
            if s.target_role and s.target_name
        }
        used.update(
            (s.target_role, s.target_name)
            for s in self.steps
            if s.target_role and s.target_name
        )
        unused: list[dict[str, object]] = []
        seen: set[tuple[object, object]] = set()
        for controls in self.indexed_controls.values():
            for control in controls:
                key = (control.get("role"), control.get("name"))
                if key[0] and key[1] and key not in used and key not in seen:
                    seen.add(key)
                    unused.append({"role": key[0], "name": key[1]})
        return tuple(unused[:20])

    def snapshot(self, owned_steps: set[int]) -> DiscoveryMap:
        validated: list[DiscoveredJourney] = []
        for journey in self.journeys:
            steps = tuple(s.model_copy(update={"ordinal": i + 1}) for i, s in enumerate(
                s for s in journey.steps if s.execution_step_id in owned_steps
            ))
            dropped = len(steps) != len(journey.steps)
            validated.append(journey.model_copy(update={
                "steps": steps, "completed": journey.completed and not dropped,
                "blocked_reason": "unknown" if dropped else journey.blocked_reason,
            }))
        features = tuple(DiscoveredFeature(
            feature_key=key, title=key.replace("_", " ").capitalize(),
            entry_url_path=next((s.navigation_url_path for j in validated if j.feature_key == key
                                 for s in j.steps if s.navigation_url_path), "/"),
            journey_keys=tuple(j.journey_key for j in validated if j.feature_key == key),
        ) for key in dict.fromkeys(j.feature_key for j in validated))
        return DiscoveryMap(target_origin=self.origin, features=features,
                            journeys=tuple(validated), coverage_notes=tuple(self.notes[:100]))


async def execute_discovery_run(
    *, request: MarketTwinRunRequest, session: AsyncSession,
) -> DiscoveryMap:
    """Explore once, close the browser, and release the worker while awaiting approval."""
    parsed = urlsplit(request.start_url)
    journal = DiscoveryJournal(origin=f"{parsed.scheme}://{parsed.netloc}")
    run = await session.get(TestRun, request.run_id)
    if run is None:
        raise ValueError("Discovery run does not exist.")
    if run.configuration_snapshot.get("discovery_map") is not None:
        return DiscoveryMap.model_validate(run.configuration_snapshot["discovery_map"])
    record = await PlanRepository(session).create_auth_bootstrap(
        test_run_id=request.run_id, requires_identity_verification=False,
    )
    execution_id = uuid4()
    executions = ExecutionRepository(session)
    await executions.create_agent_execution(execution_id=execution_id, journey_id=record.journey_id,
                                            runtime_name="discovery_contract_v1")
    await RunStateRepository(session).mark_running(test_run_id=request.run_id)
    run.configuration_snapshot = {**run.configuration_snapshot, "discovery_stage": "discovering"}
    await session.commit()
    storage = await asyncio.to_thread(S3ArtifactStorage.from_environment)
    recorder = ExecutionStepRecorder(session=session, execution_id=execution_id, storage=storage)
    safe_data = {v.key: v.value for v in default_scope(request).safe_test_data}
    async with BrowserController() as controller:
        handle = await controller.create_session(
            execution_id=execution_id, journey_id=record.journey_id,
            allowed_origins=request.allowed_origins, network_policy=request.network_policy,
            fixture_action_rules=request.fixture_action_rules,
        )
        await executions.create_browser_session(browser_session_id=handle.session_id,
                                                execution_id=execution_id)
        await session.commit()

        async def stop_at_login() -> None:
            raise AuthenticationRequired("Discovery excludes authenticated journeys.")

        controller.bind_authentication_handler(handle, stop_at_login)
        base = {tool.__name__: tool for tool in create_browser_tools(
            controller=controller, handle=handle, step_recorder=recorder, discovery=True,
        )}
        lock = asyncio.Lock()

        async def browser_begin_journey(title: str, feature_key: str) -> dict[str, object]:
            """Start a concrete journey; feature_key is a lowercase underscore slug."""
            # Validate labels with the same contract constraints before mutating the journal.
            DiscoveredJourney(journey_key="validation", title=title, feature_key=feature_key,
                              completed=False, blocked_reason="unknown")
            journal.end(False, "unknown")
            journal.title, journal.feature_key = title, feature_key
            journal.tracker.reset_journey()
            result = await base["browser_navigate"](url=request.start_url)
            observation = result.get("observation")
            if isinstance(observation, dict):
                journal.observation = cast(dict[str, object], observation)
                journal.current_path = urlsplit(str(journal.observation.get("url", ""))).path or "/"
                journal.current_page = hashlib.sha256(str(
                    journal.observation.get("url", ""),
                ).encode()).hexdigest()
            return {**result, "status": "started", "returned_to_start": True}

        async def browser_end_journey(
            completed: bool, blocked_reason: BlockedReason | None = None,
        ) -> dict[str, object]:
            """Save the actions actually recorded; state a blocker when incomplete."""
            journal.end(completed, blocked_reason)
            return {"status": "saved"}

        async def browser_fill_safe(label: str, input_key: str) -> dict[str, object]:
            """Fill a labeled field using a provided safe data key only."""
            return await base["browser_fill"](label=label, value=safe_data[input_key])

        async def browser_select_safe(label: str, input_key: str) -> dict[str, object]:
            """Select an option using a provided safe data key only."""
            return await base["browser_select"](label=label, value=safe_data[input_key])

        def tracked(tool: BrowserTool) -> BrowserTool:
            @wraps(tool)
            async def invoke(**arguments: object) -> dict[str, object]:
                async with lock:
                    name = tool.__name__
                    reason = journal.tracker.before_call(name, journal.current_path)
                    if reason:
                        journal.end(False, reason)
                        return {"status": "blocked", "blocked_reason": reason}
                    if journal.title is None and name not in {
                        "browser_begin_journey", "browser_end_journey",
                    }:
                        return {"status": "blocked", "message": "Begin a journey first."}
                    previous = journal.locator_observation()
                    try:
                        result = await tool(**arguments)
                    except AuthenticationRequired:
                        journal.end(False, "authentication_required")
                        return {"status": "blocked", "blocked_reason": "authentication_required"}
                    except BrowserPolicyError:
                        journal.end(False, "policy_blocked")
                        return {"status": "blocked", "blocked_reason": "policy_blocked"}
                    except (KeyError, ValidationError):
                        return {"status": "failed", "message": "Use valid labels and safe keys."}
                    if result.get("status") == "failed":
                        if result.get("error_code") == "ambiguous_target":
                            journal.end(False, "ambiguous_target")
                        elif result.get("error_code") == "absent_target":
                            reason = journal.tracker.failed_locator(arguments)
                            if reason:
                                journal.end(False, reason)
                        return result
                    observation = result.get("observation")
                    if isinstance(observation, dict):
                        journal.observation = cast(dict[str, object], observation)
                        journal.current_path = urlsplit(
                            str(journal.observation.get("url", "")),
                        ).path or "/"
                        journal.current_page = hashlib.sha256(str(
                            journal.observation.get("url", ""),
                        ).encode()).hexdigest()
                        if name == "browser_get_page_index":
                            journal.indexed_paths.add(journal.current_page)
                            controls = cast(list[dict[str, object]], result.get("page_index", []))
                            if arguments.get("cursor", 0) == 0:
                                journal.indexed_controls[journal.current_page] = []
                            journal.indexed_controls.setdefault(journal.current_page, []).extend(
                                controls,
                            )
                        if name in ACT_TOOLS and type(result.get("step_id")) is int:
                            record_discovered_step(journal, name, arguments, result, previous)
                    if journal.tracker.reminder:
                        result["discovery_reminder"] = journal.tracker.reminder
                    return result
            return invoke

        tools = [tracked(tool) for name, tool in base.items()
                 if name not in {"browser_fill", "browser_select"}]
        tools.extend(tracked(tool) for tool in (
            browser_begin_journey, browser_end_journey, browser_fill_safe, browser_select_safe,
        ))
        runner = InMemoryRunner(agent=create_discovery_agent(tools), app_name="discovery")
        try:
            await runner.session_service.create_session(app_name="discovery", user_id="mapper",
                                                        session_id=str(execution_id))
            async with asyncio.timeout(420):
                async for _event in runner.run_async(
                    user_id="mapper", session_id=str(execution_id),
                    new_message=types.Content(role="user", parts=[types.Part(text=(
                        f"Explore {request.start_url}. App brief: {request.study_brief}\n"
                        f"Safe input keys: {', '.join(safe_data)}. Maximum 60 tool calls."
                    ))]), run_config=RunConfig(max_llm_calls=48),
                ):
                    if journal.tracker.calls >= 60:
                        journal.end(False, "step_budget")
                        break
                leftover = journal.unused_indexed_controls()
                if leftover and journal.tracker.calls < 55:
                    listed = "; ".join(f"{c['role']} '{c['name']}'" for c in leftover)
                    async for _event in runner.run_async(
                        user_id="mapper", session_id=str(execution_id),
                        new_message=types.Content(role="user", parts=[types.Part(text=(
                            "These indexed controls were never used in a recorded journey: "
                            f"{listed}. Begin a separate journey for each remaining control "
                            "or finish with a coverage note. Do not invent observations."
                        ))]), run_config=RunConfig(max_llm_calls=12),
                    ):
                        if journal.tracker.calls >= 60:
                            journal.end(False, "step_budget")
                            break
                leftover = journal.unused_indexed_controls()
                if leftover:
                    journal.notes.append(
                        "Unattempted indexed controls: "
                        + "; ".join(f"{c['role']} '{c['name']}'" for c in leftover) + "."
                    )
            journal.end(False, "unknown")
        except TimeoutError:
            journal.end(False, "time_budget")
            journal.notes.append("Discovery stopped at its wall-clock budget.")
        except Exception:
            journal.end(False, "provider_error")
            journal.notes.append("Discovery stopped because its agent was unavailable.")
        finally:
            await runner.close()
            artifacts = await controller.close_session(session_id=handle.session_id)
            await SessionArtifactRecorder(session=session, execution_id=execution_id,
                                          storage=storage).record(artifacts)
            await executions.mark_browser_session_closed(browser_session_id=handle.session_id)
    owned = set((await session.scalars(select(ExecutionStep.id).where(
        ExecutionStep.execution_id == execution_id, ExecutionStep.status == "completed",
    ))).all())
    result = journal.snapshot(owned)
    run = await session.get(TestRun, request.run_id, populate_existing=True)
    assert run is not None
    run.configuration_snapshot = {**run.configuration_snapshot,
                                  "discovery_map": result.model_dump(mode="json"),
                                  "discovery_stage": "awaiting_approval"}
    # Existing awaiting_human state releases the worker; the snapshot gives the precise stage.
    run.status = "awaiting_human"
    await executions.finish_agent_execution(execution_id=execution_id, status="completed",
                                             outcome=None)
    await RunEventRepository(session).create(
        test_run_id=request.run_id, journey_id=record.journey_id, execution_id=execution_id,
        event_type="discovery.completed", payload={
            "features": len(result.features),
            "journeys_completed": sum(j.completed for j in result.journeys),
            "blocked_by_reason": dict(Counter(
                j.blocked_reason for j in result.journeys if j.blocked_reason
            )),
        },
    )
    await session.commit()
    return result


def record_discovered_step(
    journal: DiscoveryJournal, name: str, arguments: dict[str, object],
    result: dict[str, object], previous: dict[str, object],
) -> None:
    """Build facts from tool results, never from model-provided observations."""
    action = name.removeprefix("browser_").removesuffix("_safe")
    observation = journal.observation
    elements = cast(list[dict[str, object]], previous.get("visible_elements", []))
    matching = next((e for e in elements if e.get("role") == arguments.get("role")
                     and e.get("name") == arguments.get("name")), dict[str, object]())
    markers = _new_behavioral_markers(previous, observation, action)
    try:
        step = DiscoveredStep(
            ordinal=len(journal.steps) + 1, action=cast(DiscoveryAction, action),
            target_role=cast(str | None, arguments.get("role")),
            target_name=cast(str | None, arguments.get("name")),
            target_label=cast(str | None, arguments.get("label")),
            target_text=cast(str | None, arguments.get("text")),
            scope_role=cast(str | None, arguments.get("scope_role")),
            scope_name=cast(str | None, arguments.get("scope_name")),
            input_key=cast(str | None, arguments.get("input_key")),
            locator_strategy=cast(str | None, result.get("locator_strategy")),
            navigation_url_path=(urlsplit(str(arguments["url"])).path or "/")
                if action == "navigate" else None,
            resulting_url_path=journal.current_path,
            resulting_page_title=str(observation.get("title", ""))[:500] or None,
            observed_text_markers=markers, execution_step_id=cast(int, result["step_id"]),
            name_source=cast(Literal["playwright", "approximate", "unavailable"],
                             matching.get("name_source", "unavailable")),
        )
    except ValidationError:
        journal.notes.append("An action lacked a safely replayable locator and was omitted.")
        journal.end(False, "target_not_found")
        return
    journal.steps.append(step)


def _new_behavioral_markers(
    previous: dict[str, object], observation: dict[str, object], action: str,
) -> tuple[str, ...]:
    """Keep outcome text while ignoring section headings exposed only by scrolling."""
    previous_elements = cast(list[dict[str, object]], previous.get("visible_elements", []))
    previous_markers = {
        (e.get("role"), e.get("name")) for e in previous_elements
        if e.get("role") in {"heading", "status", "alert"}
    }
    previous_url = previous.get("url")
    current_url = observation.get("url")
    navigated = action in {"navigate", "go_back"} or (
        isinstance(previous_url, str) and isinstance(current_url, str)
        and previous_url != current_url
    )
    markers: list[str] = []
    for element in cast(list[dict[str, object]], observation.get("visible_elements", [])):
        role, name = element.get("role"), element.get("name")
        if role not in {"heading", "status", "alert"} or not name:
            continue
        if (role, name) in previous_markers:
            continue
        if role == "heading" and element.get("level") != 1 and not navigated:
            continue
        marker = str(name)[:160]
        if marker not in markers:
            markers.append(marker)
        if len(markers) == 8:
            break
    return tuple(markers)
