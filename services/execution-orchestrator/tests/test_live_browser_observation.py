"""Read-only live observation: real Chromium, no control state change, bounded waits."""

import threading
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser import owner as owner_module
from markettwin_execution_orchestrator.browser.owner import (
    ControllerBrowserOwner,
    ViewerRejectedError,
)
from markettwin_execution_orchestrator.browser.owner_registry import browser_owner_registry


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def fixture_origin() -> Iterator[tuple[str, int]]:
    directory = Path(__file__).parent / "fixtures/hitl_app"
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(directory)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


async def test_agent_observation_returns_jpeg_without_changing_control_state(
    fixture_origin: tuple[str, int], tmp_path: Path,
) -> None:
    origin, port = fixture_origin
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        await controller.navigate(session_id=handle.session_id, url=origin + "/index.html")
        session = cast(Any, controller)._get_session(session_id=handle.session_id)
        before = (
            session.control_generation, session.control_mode,
            session.capture_enabled, session.tracing_active,
        )
        owner = ControllerBrowserOwner(controller)

        image = await owner.observe(handle, generation=before[0])

        assert image.startswith(b"\xff\xd8")
        assert (
            session.control_generation, session.control_mode,
            session.capture_enabled, session.tracing_active,
        ) == before
        assert session.page.url.startswith(origin)
        await controller.close_session(session_id=handle.session_id)


async def test_observation_is_rejected_for_human_control_and_stale_generation(
    fixture_origin: tuple[str, int], tmp_path: Path,
) -> None:
    origin, port = fixture_origin
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        await controller.navigate(session_id=handle.session_id, url=origin + "/index.html")
        session = cast(Any, controller)._get_session(session_id=handle.session_id)
        owner = ControllerBrowserOwner(controller)
        generation = session.control_generation

        with pytest.raises(ViewerRejectedError):
            await owner.observe(handle, generation=generation + 1)

        await controller.begin_human_control(session_id=handle.session_id)
        assert session.control_mode == "human"
        with pytest.raises(ViewerRejectedError):
            await owner.observe(handle, generation=session.control_generation)
        await controller.close_session(session_id=handle.session_id)


async def test_pending_assistance_is_observable_but_not_mutated(
    fixture_origin: tuple[str, int], tmp_path: Path,
) -> None:
    origin, port = fixture_origin
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        await controller.navigate(session_id=handle.session_id, url=origin + "/index.html")
        session = cast(Any, controller)._get_session(session_id=handle.session_id)
        generation = session.control_generation
        session.control_mode = "human_pending"
        owner = ControllerBrowserOwner(controller)

        assert (await owner.observe(handle, generation=generation)).startswith(b"\xff\xd8")
        assert session.control_mode == "human_pending"
        assert session.control_generation == generation
        assert session.capture_enabled
        session.control_mode = "agent"
        await controller.close_session(session_id=handle.session_id)


async def test_observation_lock_wait_is_bounded(
    fixture_origin: tuple[str, int], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin, port = fixture_origin
    monkeypatch.setattr(owner_module, "OBSERVATION_LOCK_SECONDS", 0.05)
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        await controller.navigate(session_id=handle.session_id, url=origin + "/index.html")
        session = cast(Any, controller)._get_session(session_id=handle.session_id)
        owner = ControllerBrowserOwner(controller)

        async with session.lock:
            with pytest.raises(ViewerRejectedError):
                await owner.observe(handle, generation=session.control_generation)
        # The lock must be released after the failed wait, so a later observation works.
        assert (await owner.observe(handle, generation=session.control_generation)).startswith(
            b"\xff\xd8"
        )
        await controller.close_session(session_id=handle.session_id)


async def test_registry_observation_requires_the_exact_live_handle(
    fixture_origin: tuple[str, int], tmp_path: Path,
) -> None:
    origin, port = fixture_origin
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        await controller.navigate(session_id=handle.session_id, url=origin + "/index.html")
        session = cast(Any, controller)._get_session(session_id=handle.session_id)
        generation = session.control_generation
        wrong_execution = type(handle)(handle.session_id, uuid4(), handle.journey_id)

        with pytest.raises(ViewerRejectedError):
            await browser_owner_registry.observe(wrong_execution, generation=generation)
        assert (
            await browser_owner_registry.observe(handle, generation=generation)
        ).startswith(b"\xff\xd8")
        await controller.close_session(session_id=handle.session_id)
