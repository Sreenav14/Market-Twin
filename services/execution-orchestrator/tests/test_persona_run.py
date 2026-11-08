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
    request = SimpleNamespace(
        run_id=uuid4(), start_url="https://app.example.test/home",
        allowed_origins=(), network_policy="local_development",
    )
    count = await persona_run._walk_persona(
        session=session, request=request, controller=controller,
        definition=mobile,
    )
    kinds = {event["kind"] for event in events}
    assert kinds == {"page_errors", "small_targets"}
    assert count == 2
    assert all(event["persona_id"] == "impatient_mobile-1" for event in events)
    assert all("score" not in event for event in events)
    # The mobile session got the canonical viewport + Slow 4G applied.
    assert controller.sessions[0]["viewport_size"] == (320, 800)
    assert controller.network[0]["latency_ms"] == 150
    assert controller.network[0]["download_bps"] == 200_000
    quote = next(e["quote"] for e in events if e["kind"] == "small_targets")
    assert "Home" in quote and "1 things" in quote


@pytest.mark.asyncio
async def test_persona_run_marks_the_run_completed(monkeypatch) -> None:
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
        return definitions[:1]

    monkeypatch.setattr(persona_run, "_ensure_definitions", _ensure)
    walked: list[str] = []

    async def _walk(**kwargs):
        walked.append(kwargs["definition"].persona_id)
        return 0

    monkeypatch.setattr(persona_run, "_walk_persona", _walk)
    session = Mock()
    session.get = AsyncMock(
        return_value=SimpleNamespace(application_id=uuid4()),
    )
    session.commit = AsyncMock()
    request = SimpleNamespace(run_id=uuid4())
    await persona_run.execute_persona_run(request=request, session=session)
    assert walked == [definitions[0].persona_id]
    assert states_calls == ["running", "completed"]


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
    request = SimpleNamespace(
        run_id=uuid4(), start_url="https://app.example.test/home",
        allowed_origins=(), network_policy="local_development",
    )
    with pytest.raises(RuntimeError, match="browser died"):
        await persona_run._walk_persona(
            session=session, request=request, controller=controller,
            definition=first_time,
        )
    assert [finish["status"] for finish in finishes] == ["failed"]
