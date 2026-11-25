"""U-P5-04: persona walks publish anchored impressions, never scores."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from markettwin_execution_orchestrator.browser.contracts import (
    BrowserObservation,
    ElementBoundingBox,
    VisibleElement,
)
from markettwin_execution_orchestrator.workflow import persona_run


@pytest.fixture(autouse=True)
def isolate_task_model(monkeypatch):
    monkeypatch.setattr(persona_run, "review_checkpoint", AsyncMock(return_value={"decision": "continue", "reason": "Fixture"}))
    # These tests exercise measurement; the task runner has its own tests.
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.workflow.persona_goal.attempt_goal",
        AsyncMock(return_value={"status": "attempted", "account": "Fixture", "verified_completion": False}),
    )


class _FakeController:
    def __init__(self, observation: BrowserObservation) -> None:
        self.observation = observation
        self.sessions: list[dict] = []
        self.network: list[dict] = []

    async def create_session(self, **kwargs):
        self.sessions.append(kwargs)
        return SimpleNamespace(session_id=uuid4())

    async def emulate_network(self, **kwargs):
        self.network.append(kwargs)

    async def navigate(self, **kwargs):
        return SimpleNamespace(observation=self.observation)

    async def focus_next(self, **kwargs):
        return SimpleNamespace(observation=self.observation)

    async def close_session(self, **kwargs):
        return None


def _observation(**overrides) -> BrowserObservation:
    base = dict(
        url="https://app.example.test/home", title="Home",
        aria_snapshot="<main>Welcome</main>", viewport_width=320,
        viewport_height=800, scroll_y=0, document_height=900,
        visible_elements=(
            VisibleElement(
                role="button", name="Buy", tag="button", enabled=True,
                bounding_box=ElementBoundingBox(x=0, y=0, width=16, height=16),
            ),
        ),
    )
    base.update(overrides)
    return BrowserObservation(**base)


@pytest.mark.asyncio
async def test_walk_publishes_anchored_impressions_with_signals(monkeypatch) -> None:
    # Hermetic door: deterministic classification + template quotes.
    monkeypatch.setenv("ASK_BACKEND_NARRATE_IMPRESSION", "deterministic")
    events: list[dict] = []

    class _Events:
        def __init__(self, session):
            pass

        async def create(self, **kwargs):
            if kwargs["event_type"] == "persona.impression":
                events.append(kwargs["payload"])

    monkeypatch.setattr(persona_run, "RunEventRepository", _Events)
    monkeypatch.setattr(
        persona_run, "ExecutionRepository",
        lambda _: Mock(
            create_agent_execution=AsyncMock(),
            create_browser_session=AsyncMock(),
            mark_browser_session_closed=AsyncMock(),
            finish_agent_execution=AsyncMock(),
        ),
    )
    definitions = persona_run.generate_definitions(
        state_urls=["https://app.example.test/home"], existing_persona_ids=set(),
    )
    mobile = next(d for d in definitions if d.type == "impatient_mobile")
    controller = _FakeController(_observation(
        console_errors_since_last_action=("TypeError: boom",),
    ))
    session = Mock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    request = SimpleNamespace(
        run_id=uuid4(), start_url="https://app.example.test/home",
        study_brief="Find pricing", max_duration_seconds_per_journey=180,
        knowledge_context=({"id": "approved-context"},),
        allowed_origins=(), network_policy="local_development",
    )
    result = await persona_run._walk_persona(
        session=session, request=request, controller=controller,
        definition=mobile,
    )
    kinds = {event["kind"] for event in events}
    assert kinds == {"page_errors", "small_targets"}
    assert result["impressions"] == 2
    assert result["stop"] is None
    assert all(event["persona_id"] == "impatient_mobile-1" for event in events)
    assert all("score" not in event for event in events)
    # The mobile session got the canonical viewport + Slow 4G applied.
    assert controller.sessions[0]["viewport_size"] == (320, 800)
    journey = session.add.call_args.args[0]
    assert controller.sessions[0]["journey_id"] == journey.id
    assert journey.test_run_id == request.run_id
    assert controller.network[0]["latency_ms"] == 150
    assert controller.network[0]["download_bps"] == 200_000
    quote = next(e["quote"] for e in events if e["kind"] == "small_targets")
    assert "Home" in quote and "1 things" in quote


@pytest.mark.asyncio
@pytest.mark.parametrize("stopped", [False, True])
async def test_persona_run_marks_the_run_completed(monkeypatch, stopped) -> None:
    """Audit fix (D1): the executor owns the run's terminal state —
    a finished persona run must not stay "running" forever."""

    states_calls: list[str] = []

    class _States:
        def __init__(self, session):
            pass

        async def mark_running(self, **kwargs):
            states_calls.append("running")

        async def mark_completed(self, **kwargs):
            states_calls.append("completed")

        async def mark_failed(self, **kwargs):
            states_calls.append("failed")

    monkeypatch.setattr(
        "markettwin_execution_orchestrator.persistence."
        "run_state_repository.RunStateRepository",
        _States,
    )

    class _Controller:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(persona_run, "BrowserController", _Controller)
    definitions = persona_run.generate_definitions(
        state_urls=["https://app.example.test/home"], existing_persona_ids=set(),
    )

    async def _ensure(**kwargs):
        return definitions[:2]

    monkeypatch.setattr(persona_run, "_ensure_definitions", _ensure)
    walked: list[str] = []
    ordinals: list[int] = []

    async def _walk(**kwargs):
        walked.append(kwargs["definition"].persona_id)
        ordinals.append(kwargs["ordinal"])
        if stopped and kwargs["ordinal"] == 1:
            return {"impressions": 0,
                    "stop": {"stop_kind": "safety", "reason": "Fixture stop"}}
        return {"impressions": 0, "stop": None}

    monkeypatch.setattr(persona_run, "_walk_persona", _walk)
    session = Mock()
    session.get = AsyncMock(
        return_value=SimpleNamespace(
            id=uuid4(), application_id=uuid4(), status="planning",
            configuration_snapshot={
                "selected_persona_ids": [
                    d.persona_id for d in definitions[:2]]}),
    )
    session.commit = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    event_repository = SimpleNamespace(create=AsyncMock())
    monkeypatch.setattr(persona_run, "RunEventRepository", lambda _: event_repository)
    request = SimpleNamespace(run_id=uuid4(), study_brief="Find pricing", testing_depth="high")
    await persona_run.execute_persona_run(request=request, session=session)
    # Stop locality (doc 24 section 3.2): the stop ends only the first
    # persona's walk — both personas walk, the run completes, and no
    # run.failed is ever emitted for a Lead stop.
    assert walked == [definition.persona_id for definition in definitions[:2]]
    assert ordinals == [1, 2]
    assert states_calls == ["running", "completed"]
    assert not any(call.kwargs["event_type"] == "run.failed"
                   for call in event_repository.create.call_args_list)
    collections = [call.kwargs["payload"]
                   for call in event_repository.create.call_args_list
                   if call.kwargs["event_type"] == "run.collection"]
    assert len(collections) == 1
    if stopped:
        assert collections[0]["partial"] is True
        assert collections[0]["stopped_personas"] == [
            {"persona_id": definitions[0].persona_id, "stop_kind": "safety"},
        ]
    else:
        assert collections[0]["partial"] is False
        assert collections[0]["stopped_personas"] == []


@pytest.mark.asyncio
async def test_failed_walk_finishes_its_execution_as_failed(monkeypatch) -> None:
    """Audit fix (D4): a walk that raises must not record its agent
    execution as "completed"."""

    finishes: list[dict] = []

    class _Executions:
        def __init__(self, session):
            pass

        async def create_agent_execution(self, **kwargs):
            return None

        async def create_browser_session(self, **kwargs):
            return None

        async def mark_browser_session_closed(self, **kwargs):
            return None

        async def finish_agent_execution(self, **kwargs):
            finishes.append(kwargs)

    monkeypatch.setattr(persona_run, "ExecutionRepository", _Executions)
    definitions = persona_run.generate_definitions(
        state_urls=["https://app.example.test/home"], existing_persona_ids=set(),
    )
    first_time = next(d for d in definitions if d.type == "first_time")
    controller = _FakeController(_observation())
    controller.navigate = AsyncMock(side_effect=RuntimeError("browser died"))
    session = Mock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    request = SimpleNamespace(
        run_id=uuid4(), start_url="https://app.example.test/home",
        study_brief="Find pricing", max_duration_seconds_per_journey=180,
        allowed_origins=(), network_policy="local_development",
    )
    with pytest.raises(RuntimeError, match="browser died"):
        await persona_run._walk_persona(
            session=session, request=request, controller=controller,
            definition=first_time,
        )
    assert [finish["status"] for finish in finishes] == ["failed"]


class _KeyboardController:
    """Persona-walk controller double with scripted focus behaviour."""

    def __init__(self, observation, *, focused_states, baseline=None):
        self.observation = observation
        self.focused_states = list(focused_states)
        self.baseline = baseline or {}
        self.sessions: list[dict] = []
        self.tabs = 0
        self.keyboard_only = False

    async def create_session(self, **kwargs):
        self.sessions.append(kwargs)
        return SimpleNamespace(session_id=uuid4())

    def set_keyboard_only(self, handle):
        self.keyboard_only = True

    async def emulate_network(self, **kwargs):
        return None

    async def navigate(self, **kwargs):
        return SimpleNamespace(observation=self.observation)

    async def focus_next(self, **kwargs):
        self.tabs += 1
        return SimpleNamespace(observation=self.observation)

    async def focusable_style_baseline(self, **kwargs):
        return self.baseline

    async def focused_element_state(self, **kwargs):
        if not self.focused_states:
            return None
        state = self.focused_states[min(self.tabs - 1, len(self.focused_states) - 1)]
        if isinstance(state, Exception):
            raise state
        return state

    async def close_session(self, **kwargs):
        return None


def _keyboard_definition():
    definitions = persona_run.generate_definitions(
        state_urls=["https://app.example.test/home"], existing_persona_ids=set(),
    )
    return next(d for d in definitions if d.conditions.input == "keyboard")


def _walk_session():
    session = Mock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _walk_request():
    return SimpleNamespace(
        run_id=uuid4(), start_url="https://app.example.test/home",
        study_brief="Find pricing", max_duration_seconds_per_journey=180,
        knowledge_context=(), allowed_origins=(),
        network_policy="local_development",
    )


def _patch_walk_repositories(monkeypatch, events):
    class _Events:
        def __init__(self, session):
            pass

        async def create(self, **kwargs):
            events.append(kwargs)

    monkeypatch.setattr(persona_run, "RunEventRepository", _Events)
    monkeypatch.setattr(
        persona_run, "ExecutionRepository",
        lambda _: Mock(
            create_agent_execution=AsyncMock(),
            create_browser_session=AsyncMock(),
            mark_browser_session_closed=AsyncMock(),
            finish_agent_execution=AsyncMock(),
        ),
    )


@pytest.mark.asyncio
async def test_keyboard_walk_with_no_focus_anywhere_claims_no_keyboard_focus(monkeypatch) -> None:
    """T-P5-P1: zero focus events across the full 12-tab walk is the
    only shape that earns the no_keyboard_focus impression."""
    monkeypatch.setenv("ASK_BACKEND_NARRATE_IMPRESSION", "deterministic")
    events: list[dict] = []
    _patch_walk_repositories(monkeypatch, events)
    controller = _KeyboardController(_observation(), focused_states=[None])
    result = await persona_run._walk_persona(
        session=_walk_session(), request=_walk_request(),
        controller=controller, definition=_keyboard_definition(),
    )
    assert controller.tabs == persona_run.KEYBOARD_WALK_TABS == 12
    impressions = [e["payload"] for e in events if e["event_type"] == "persona.impression"]
    assert {e["kind"] for e in impressions} == {"no_keyboard_focus"}
    walks = [e["payload"] for e in events if e["event_type"] == "persona.keyboard_walk"]
    assert len(walks) == 1 and walks[0]["tabs"] == 12
    assert result["stop"] is None and result["impressions"] == 1


@pytest.mark.asyncio
async def test_keyboard_walk_with_visible_indicator_makes_no_keyboard_impression(monkeypatch) -> None:
    """T-P5-P2: focus lands and shows a real outline — no impression,
    and the raw walk record still lands in evidence."""
    monkeypatch.setenv("ASK_BACKEND_NARRATE_IMPRESSION", "deterministic")
    events: list[dict] = []
    _patch_walk_repositories(monkeypatch, events)
    state = {
        "role": "button", "name": "Buy", "ordinal": 0,
        "outline_style": "solid", "outline_width": "2px",
        "box_shadow": "none", "background": "rgb(255, 255, 255)",
        "border_width": "1px", "border_color": "rgb(0, 0, 0)",
    }
    controller = _KeyboardController(_observation(), focused_states=[state])
    await persona_run._walk_persona(
        session=_walk_session(), request=_walk_request(),
        controller=controller, definition=_keyboard_definition(),
    )
    kinds = {e["payload"]["kind"] for e in events if e["event_type"] == "persona.impression"}
    assert "no_keyboard_focus" not in kinds
    assert "focus_indicator_invisible" not in kinds
    walks = [e["payload"] for e in events if e["event_type"] == "persona.keyboard_walk"]
    assert walks and walks[0]["steps"][0]["indicator_visible"] is True


@pytest.mark.asyncio
async def test_keyboard_walk_with_invisible_indicator_names_the_element(monkeypatch) -> None:
    """T-P5-P3: focus lands but nothing about the element changes —
    the focus_indicator_invisible impression names the element."""
    monkeypatch.setenv("ASK_BACKEND_NARRATE_IMPRESSION", "deterministic")
    events: list[dict] = []
    _patch_walk_repositories(monkeypatch, events)
    base = {
        "outline_style": "none", "outline_width": "0px",
        "box_shadow": "none", "background": "rgb(255, 255, 255)",
        "border_width": "1px", "border_color": "rgb(0, 0, 0)",
    }
    state = {"role": "button", "name": "Buy", "ordinal": 0, **base}
    controller = _KeyboardController(
        _observation(), focused_states=[state], baseline={"0": base},
    )
    await persona_run._walk_persona(
        session=_walk_session(), request=_walk_request(),
        controller=controller, definition=_keyboard_definition(),
    )
    impressions = [e["payload"] for e in events if e["event_type"] == "persona.impression"]
    invisible = [e for e in impressions if e["kind"] == "focus_indicator_invisible"]
    assert len(invisible) == 1
    assert "Buy" in invisible[0]["signal"]["element"]
    assert "Buy" in invisible[0]["quote"]


@pytest.mark.asyncio
async def test_keyboard_walk_controller_failure_is_named_not_quoted(monkeypatch) -> None:
    """T-P5-P4: a controller failure mid-walk yields no impression —
    the walk record names the failure instead."""
    monkeypatch.setenv("ASK_BACKEND_NARRATE_IMPRESSION", "deterministic")
    events: list[dict] = []
    _patch_walk_repositories(monkeypatch, events)
    controller = _KeyboardController(
        _observation(), focused_states=[RuntimeError("probe died")],
    )
    result = await persona_run._walk_persona(
        session=_walk_session(), request=_walk_request(),
        controller=controller, definition=_keyboard_definition(),
    )
    kinds = {e["payload"]["kind"] for e in events if e["event_type"] == "persona.impression"}
    assert "no_keyboard_focus" not in kinds
    assert "focus_indicator_invisible" not in kinds
    walks = [e["payload"] for e in events if e["event_type"] == "persona.keyboard_walk"]
    assert walks and walks[0]["failure"] == "RuntimeError"
    assert result["stop"] is None


@pytest.mark.asyncio
async def test_lead_stop_ends_only_this_personas_walk(monkeypatch) -> None:
    """T-P5-P5: a Lead stop records stopped_at_checkpoint with the
    typed stop_kind on the persona's own task result, and the walk
    returns the stop instead of walking journeys."""
    monkeypatch.setenv("ASK_BACKEND_NARRATE_IMPRESSION", "deterministic")
    monkeypatch.setattr(
        persona_run, "review_checkpoint",
        AsyncMock(return_value={
            "decision": "stop", "reason": "Unsafe page",
            "stop_kind": "safety", "source": "lead",
        }),
    )
    events: list[dict] = []
    _patch_walk_repositories(monkeypatch, events)
    controller = _KeyboardController(_observation(), focused_states=[None])
    result = await persona_run._walk_persona(
        session=_walk_session(), request=_walk_request(),
        controller=controller, definition=_keyboard_definition(),
    )
    assert result["stop"] == {"stop_kind": "safety", "reason": "Unsafe page"}
    stopped = [e["payload"] for e in events
               if e["event_type"] == "persona.task.result"
               and e["payload"].get("status") == "stopped_at_checkpoint"]
    assert len(stopped) == 1
    assert stopped[0]["stop_kind"] == "safety"
    assert stopped[0]["reason"] == "Unsafe page"
    # No journey pages were walked after the stop (only the entry
    # navigation happened, inside the task phase's own doubles).
    assert not any(e["event_type"] == "persona.impression" for e in events)
def _a2_executions(monkeypatch, *, mark_closed=None):
    """ExecutionRepository double recording finishes; mark_closed may
    be an async callable taking the session (cleanup failure shapes)."""
    finishes: list[dict] = []

    class _Executions:
        def __init__(self, session):
            self.session = session

        async def create_agent_execution(self, **kwargs):
            return None

        async def create_browser_session(self, **kwargs):
            return None

        async def mark_browser_session_closed(self, **kwargs):
            if mark_closed is not None:
                await mark_closed(self.session)

        async def finish_agent_execution(self, **kwargs):
            finishes.append(kwargs)

    monkeypatch.setattr(persona_run, "ExecutionRepository", _Executions)
    return finishes


def _a2_definition():
    definitions = persona_run.generate_definitions(
        state_urls=["https://app.example.test/home"], existing_persona_ids=set(),
    )
    return next(d for d in definitions if d.type == "first_time")


@pytest.mark.asyncio
async def test_a2_browser_creation_failure_still_finishes_execution(monkeypatch) -> None:
    """Astra A2 (creation): browser creation used to sit BEFORE the
    walk's cleanup try, so a launch failure left the already-persisted
    AgentExecution "running" forever — nothing ever finished it."""
    events: list[dict] = []
    _patch_walk_repositories(monkeypatch, events)
    finishes = _a2_executions(monkeypatch)
    controller = _FakeController(_observation())

    async def _no_browser(**kwargs):
        raise RuntimeError("browser launch failed")

    controller.create_session = _no_browser
    with pytest.raises(RuntimeError, match="browser launch failed"):
        await persona_run._walk_persona(
            session=_walk_session(), request=_walk_request(),
            controller=controller, definition=_a2_definition(),
        )
    assert [finish["status"] for finish in finishes] == ["failed"]


@pytest.mark.asyncio
async def test_a2_poisoned_session_cleanup_preserves_original_error(monkeypatch) -> None:
    """Astra A2 (poisoned session): the walk died mid-flush, leaving
    the session poisoned; cleanup's first write then raised
    PendingRollbackError, which replaced the walk's real error and
    skipped finish_agent_execution entirely."""
    from sqlalchemy.exc import PendingRollbackError

    async def _mark_closed(session):
        if getattr(session, "poisoned", False):
            raise PendingRollbackError("session is poisoned")

    events: list[dict] = []
    _patch_walk_repositories(monkeypatch, events)
    finishes = _a2_executions(monkeypatch, mark_closed=_mark_closed)
    session = _walk_session()
    session.poisoned = True

    async def _rollback():
        session.poisoned = False

    session.rollback = AsyncMock(side_effect=_rollback)
    controller = _FakeController(_observation())
    controller.navigate = AsyncMock(side_effect=RuntimeError("browser died"))
    with pytest.raises(RuntimeError, match="browser died"):
        await persona_run._walk_persona(
            session=session, request=_walk_request(),
            controller=controller, definition=_a2_definition(),
        )
    assert [finish["status"] for finish in finishes] == ["failed"]


@pytest.mark.asyncio
async def test_a2_cleanup_failure_never_replaces_walk_error(monkeypatch) -> None:
    """Astra A2 (cleanup failure): when marking the browser session
    closed itself fails, the execution must already be finished and
    the walk's own error — not the cleanup error — must propagate."""
    async def _mark_closed(session):
        raise RuntimeError("cleanup broke")

    events: list[dict] = []
    _patch_walk_repositories(monkeypatch, events)
    finishes = _a2_executions(monkeypatch, mark_closed=_mark_closed)
    controller = _FakeController(_observation())
    controller.navigate = AsyncMock(side_effect=RuntimeError("browser died"))
    with pytest.raises(RuntimeError, match="browser died"):
        await persona_run._walk_persona(
            session=_walk_session(), request=_walk_request(),
            controller=controller, definition=_a2_definition(),
        )
    assert [finish["status"] for finish in finishes] == ["failed"]


@pytest.mark.asyncio
async def test_a3_redelivered_running_persona_run_reaches_browser_creation(monkeypatch) -> None:
    """Astra A3: the worker's recoverable-redelivery path redispatches
    a persona run whose row is already "running" (no browser rows).
    The entry called mark_running unconditionally, and the repository
    rejects running -> running — recovery deterministically failed
    the run it meant to recover. This drives the REAL
    execute_persona_run with the REAL RunStateRepository against a
    run row already in "running": it must reach browser creation and
    complete."""
    monkeypatch.setenv("ASK_BACKEND_NARRATE_IMPRESSION", "deterministic")
    events: list[dict] = []
    _patch_walk_repositories(monkeypatch, events)
    definitions = persona_run.generate_definitions(
        state_urls=["https://app.example.test/home"], existing_persona_ids=set(),
    )
    definition = next(d for d in definitions if d.type == "first_time")
    run = SimpleNamespace(
        id=uuid4(), application_id=uuid4(), status="running",
        started_at=None, completed_at=None,
        configuration_snapshot={
            "persona_definitions_snapshot": [
                definition.model_dump(mode="json"),
            ],
            "selected_persona_ids": [definition.persona_id],
        },
    )
    session = Mock()
    session.get = AsyncMock(return_value=run)
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    controller = _FakeController(_observation())

    class _Controller:
        async def __aenter__(self):
            return controller

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(persona_run, "BrowserController", _Controller)
    request = SimpleNamespace(
        run_id=run.id, start_url="https://app.example.test/home",
        study_brief="Find pricing", testing_depth="medium",
        max_duration_seconds_per_journey=180, knowledge_context=(),
        allowed_origins=(), network_policy="local_development",
    )
    await persona_run.execute_persona_run(request=request, session=session)
    assert controller.sessions, "browser creation was never reached"
    assert run.status == "completed"
    collections = [e for e in events if e["event_type"] == "run.collection"]
    assert len(collections) == 1
    assert collections[0]["payload"]["run_kind"] == "persona"


@pytest.mark.asyncio
async def test_call_limit_exhausted_ends_the_walk_without_a_tour(monkeypatch) -> None:
    """FIX-3: a persona whose goal attempt ends call_limit_exhausted
    stops there -- objectives break, the diagnostic tour is skipped, and
    the walk returns cleanly instead of the error failing the run
    (live run MT-000163)."""
    events: list[dict] = []
    _patch_walk_repositories(monkeypatch, events)
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.workflow.persona_goal.attempt_goal",
        AsyncMock(return_value={
            "status": "call_limit_exhausted",
            "account": "Task stopped: the model-call limit for this attempt was exhausted.",
            "blocker": {"error_type": "LlmCallsLimitExceededError",
                        "reason": "Max number of llm calls limit of `16` exceeded."},
            "verified_completion": False,
        }),
    )

    class _CountingController(_FakeController):
        def __init__(self, observation):
            super().__init__(observation)
            self.navigations: list[dict] = []

        async def navigate(self, **kwargs):
            self.navigations.append(kwargs)
            return await super().navigate(**kwargs)

    controller = _CountingController(_observation())
    result = await persona_run._walk_persona(
        session=_walk_session(), request=_walk_request(),
        controller=controller, definition=_a2_definition(),
    )
    assert result["impressions"] == 0 and result["stop"] is None
    assert len(controller.navigations) == 1  # entry navigation only; no tour
    task_results = [e["payload"] for e in events if e["event_type"] == "persona.task.result"]
    assert len(task_results) == 1
    assert task_results[0]["status"] == "call_limit_exhausted"
    assert task_results[0]["blocker"]["error_type"] == "LlmCallsLimitExceededError"


@pytest.mark.asyncio
async def test_persona_run_owner_stop_cancels_at_the_next_persona(
    monkeypatch,
) -> None:
    """Owner stop (the Stop run button): the flag ctl records in the
    run's configuration snapshot ends the run at the next persona
    boundary — the persona in flight finishes, the rest never walk,
    and the run closes cancelled, never completed."""

    states_calls: list[str] = []

    class _States:
        def __init__(self, session):
            pass

        async def mark_running(self, **kwargs):
            states_calls.append("running")

        async def mark_completed(self, **kwargs):
            states_calls.append("completed")

        async def mark_cancelled(self, **kwargs):
            states_calls.append("cancelled")

        async def mark_failed(self, **kwargs):
            states_calls.append("failed")

    monkeypatch.setattr(
        "markettwin_execution_orchestrator.persistence."
        "run_state_repository.RunStateRepository",
        _States,
    )

    class _Controller:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(persona_run, "BrowserController", _Controller)
    definitions = persona_run.generate_definitions(
        state_urls=["https://app.example.test/home"], existing_persona_ids=set(),
    )

    async def _ensure(**kwargs):
        return definitions[:2]

    monkeypatch.setattr(persona_run, "_ensure_definitions", _ensure)
    run_row = SimpleNamespace(
        id=uuid4(), application_id=uuid4(), status="planning",
        configuration_snapshot={
            "selected_persona_ids": [
                d.persona_id for d in definitions[:2]]})
    walked: list[str] = []

    async def _walk(**kwargs):
        walked.append(kwargs["definition"].persona_id)
        # The ctl write landing while the first persona walks: the
        # snapshot the run fresh-reads at the next boundary now
        # carries the flag (the fixture session returns this row).
        run_row.configuration_snapshot = {
            **run_row.configuration_snapshot,
            "owner_stop": {"requested_at": "2026-11-18T20:34:00+00:00",
                           "requested_by": "owner"},
        }
        return {"impressions": 0, "stop": None}

    monkeypatch.setattr(persona_run, "_walk_persona", _walk)
    session = Mock()
    session.get = AsyncMock(return_value=run_row)
    session.commit = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    event_repository = SimpleNamespace(create=AsyncMock())
    monkeypatch.setattr(persona_run, "RunEventRepository", lambda _: event_repository)
    request = SimpleNamespace(
        run_id=uuid4(), study_brief="Find pricing", testing_depth="high")
    await persona_run.execute_persona_run(request=request, session=session)
    assert walked == [definitions[0].persona_id]
    assert states_calls == ["running", "cancelled"]
    event_types = [
        call.kwargs["event_type"]
        for call in event_repository.create.call_args_list
    ]
    assert "run.owner_stop" in event_types
    collections = [
        call.kwargs["payload"]
        for call in event_repository.create.call_args_list
        if call.kwargs["event_type"] == "run.collection"
    ]
    assert len(collections) == 1
    assert collections[0]["owner_stopped"] is True
    assert collections[0]["partial"] is True
    assert collections[0]["journey_count"] == 1
