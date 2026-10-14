"""Real Chromium regressions for scoped observation and minimal safe interactions."""

import asyncio
import json
import threading
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.contracts import BrowserActionResult
from markettwin_execution_orchestrator.browser.errors import (
    BrowserActionError,
    BrowserSessionOwnershipError,
    HumanControlActiveError,
)
from markettwin_execution_orchestrator.browser.tools import (
    BrowserStepRecorder,
    create_browser_tools,
)


@pytest.fixture
def scoped_fixture(tmp_path: Path) -> Iterator[tuple[str, int]]:
    fields = ''.join(f'<label>Field {index}<input required></label>' for index in range(42))
    (tmp_path / "index.html").write_text(
        '<form aria-label="Registration"><label>Name<input value="PRIVATE-TEXT"></label>'
        '<label>Password<input type="password" value="SECRET-TEXT"></label>'
        '<label>Team<select><option>Research</option>'
        '<option selected>Viewer</option></select></label>'
        '<label>Show tips<input type="checkbox"></label>'
        '<button type="button" onclick="document.title=\'Registration saved\'">Save</button></form>'
        '<section aria-label="Draft"><button onclick="document.title=\'Draft saved\'">Save</button>'
        '</section><form aria-label="Long form">' + fields + '</form>'
        '<button onclick="document.title=\'DESTRUCTIVE\'">Delete account</button>'
        '<nav aria-label="Site"><a href="#pricing" onclick="document.title=\'Pricing destination\'">Pricing</a></nav>'
        '<footer><a href="#footer">Pricing</a></footer>',
        encoding="utf-8",
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/index.html", server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


async def test_named_navigation_resolves_duplicate_public_link(
    scoped_fixture: tuple[str, int], tmp_path: Path,
) -> None:
    url, port = scoped_fixture
    async with BrowserController(artifact_root=tmp_path / "evidence") as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(),
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
            network_policy="local_development",
        )
        await controller.navigate(session_id=handle.session_id, url=url)
        with pytest.raises(BrowserActionError):
            await controller.click(session_id=handle.session_id, role="link", name="Pricing")
        result = await controller.click(
            session_id=handle.session_id, role="link", name="Pricing",
            scope_role="navigation", scope_name="Site",
        )
        assert result.observation.title == "Pricing destination"


class Recorder:
    def __init__(self) -> None:
        self.evidence: list[tuple[int, BrowserActionResult]] = []
        self.finished: list[tuple[int, str]] = []
        self.count = 0

    async def start_step(self, *, action_type: str, action_summary: str) -> int:
        self.count += 1
        return self.count

    async def finish_step(
        self, *, step_id: int, status: Literal["completed", "failed", "policy_blocked"],
        observation_summary: str | None = None,
    ) -> None:
        self.finished.append((step_id, status))

    async def record_evidence(self, *, step_id: int, result: BrowserActionResult) -> None:
        self.evidence.append((step_id, result))

    async def record_failure_evidence(self, *, step_id: int, result: BrowserActionResult) -> None:
        self.evidence.append((step_id, result))


async def test_scoped_duplicate_inspection_and_recording(
    scoped_fixture: tuple[str, int], tmp_path: Path,
) -> None:
    url, port = scoped_fixture
    async with BrowserController(artifact_root=tmp_path / "artifacts") as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        await controller.navigate(session_id=handle.session_id, url=url)
        with pytest.raises(BrowserActionError, match="observed 2"):
            await controller.click(session_id=handle.session_id, role="button", name="Save")
        with pytest.raises(BrowserActionError, match="Scope"):
            await controller.click(
                session_id=handle.session_id, role="button", name="Save",
                scope_role="form", scope_name="Missing",
            )
        recorder = Recorder()
        tools = {tool.__name__: tool for tool in create_browser_tools(
            controller=controller, handle=handle, step_recorder=cast(BrowserStepRecorder, recorder),
        )}
        result = await tools["browser_click"](
            role="button", name="Save", scope_role="form", scope_name="Registration",
        )
        assert result["step_id"] == 1
        assert recorder.finished == [(1, "completed")]
        assert recorder.evidence[0][1].observation.title == "Registration saved"
        await tools["browser_get_form_state"](scope_role="form", scope_name="Registration")
        observation = recorder.evidence[-1][1].observation
        assert len(observation.form_fields) == 4
        assert observation.form_fields[2].selected_options == (1,)
        assert not observation.more_available
        assert observation.form_fields[3].checked is False
        await tools["browser_check"](
            label="Show tips", scope_role="form", scope_name="Registration",
        )
        checked = await controller.get_form_state(
            session_id=handle.session_id, scope_role="form", scope_name="Registration",
        )
        assert checked.observation.form_fields[3].checked is True
        await tools["browser_uncheck"](
            label="Show tips", scope_role="form", scope_name="Registration",
        )
        unchecked = await controller.get_form_state(
            session_id=handle.session_id, scope_role="form", scope_name="Registration",
        )
        assert unchecked.observation.form_fields[3].checked is False
        with pytest.raises(BrowserActionError):
            await controller.set_checked(session_id=handle.session_id, label="Name", checked=True)
        assert "PRIVATE-TEXT" not in observation.aria_snapshot
        assert "SECRET-TEXT" not in observation.aria_snapshot
        assert "PRIVATE-TEXT" not in json.dumps(observation.to_dict())
        assert observation.accessibility_snapshot_path is not None
        snapshot = await asyncio.to_thread(Path(observation.accessibility_snapshot_path).read_text)
        assert "SECRET-TEXT" not in snapshot
        long_form = await controller.get_form_state(
            session_id=handle.session_id, scope_role="form", scope_name="Long form",
        )
        assert len(long_form.observation.form_fields) == 40
        assert long_form.observation.more_available
        assert long_form.observation.truncated
        assert all(field.required for field in long_form.observation.form_fields)


async def test_focus_and_viewport_guards(
    scoped_fixture: tuple[str, int], tmp_path: Path,
) -> None:
    url, port = scoped_fixture
    async with BrowserController(artifact_root=tmp_path / "artifacts") as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        await controller.navigate(session_id=handle.session_id, url=url)
        # Tab/Shift+Tab can visit destructive buttons but never activate them.
        for _ in range(52):
            result = await controller.focus_next(session_id=handle.session_id)
            assert result.observation.title != "DESTRUCTIVE"
        result = await controller.focus_next(session_id=handle.session_id, reverse=True)
        assert result.observation.title != "DESTRUCTIVE"
        mobile = await controller.set_viewport(session_id=handle.session_id, preset="mobile320")
        assert mobile.observation.viewport_width == 320
        with pytest.raises(BrowserSessionOwnershipError):
            await controller.get_form_state(
                session_id=handle.session_id, execution_id=uuid4(),
                scope_role="form", scope_name="Registration",
            )
        await controller.begin_human_control(session_id=handle.session_id)
        with pytest.raises(HumanControlActiveError):
            await controller.focus_next(session_id=handle.session_id)
        with pytest.raises(HumanControlActiveError):
            await controller.set_viewport(session_id=handle.session_id, preset="desktop1280")
        with pytest.raises(HumanControlActiveError):
            await controller.get_form_state(
                session_id=handle.session_id, scope_role="form", scope_name="Registration",
            )
