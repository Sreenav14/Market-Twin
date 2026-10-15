"""Real Chromium regressions for scoped observation and minimal safe interactions."""

import asyncio
import json
import threading
import zipfile
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.contracts import BrowserActionResult
from markettwin_execution_orchestrator.browser.errors import (
    BrowserActionError,
    BrowserActionBlockedError,
    BrowserSessionOwnershipError,
    BrowserSessionStateError,
    HumanControlActiveError,
)
from markettwin_execution_orchestrator.browser.evidence import write_event_logs
from markettwin_execution_orchestrator.browser.observations import build_observation
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


async def test_approval_rejects_changed_page_state_and_requires_exact_fingerprint(
    scoped_fixture: tuple[str, int], tmp_path: Path,
) -> None:
    url, port = scoped_fixture
    async with BrowserController(artifact_root=tmp_path / "approval") as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(),
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
            network_policy="local_development",
        )
        await controller.navigate(session_id=handle.session_id, url=url)
        args = dict(session_id=handle.session_id, role="button", name="Save",
                    scope_role="region", scope_name="Draft")
        intent = await controller.inspect_click_approval(**args)
        assert intent is not None
        with pytest.raises(BrowserActionBlockedError):
            await controller.click(**args)
        await controller.navigate(session_id=handle.session_id, url=url + "?record=changed")
        with pytest.raises(BrowserActionBlockedError, match="does not match"):
            await controller.click(**args, approval_fingerprint=intent.fingerprint)
        fresh = await controller.inspect_click_approval(**args)
        assert fresh is not None
        result = await controller.click(**args, approval_fingerprint=fresh.fingerprint)
        assert result.observation.title == "Draft saved"


async def test_authentication_only_origin_is_accessible_only_during_human_control(
    scoped_fixture: tuple[str, int], tmp_path: Path,
) -> None:
    url, port = scoped_fixture
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    idp = f"http://127.0.0.1:{server.server_port}"
    try:
        async with BrowserController(artifact_root=tmp_path / "sso") as controller:
            handle = await controller.create_session(
                execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
                allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),
                                 AllowedOrigin("http", "127.0.0.1", server.server_port)),
                auth_only_origins=(idp,),
            )
            await controller.navigate(session_id=handle.session_id, url=url)
            with pytest.raises(BrowserActionError):
                await controller.navigate(session_id=handle.session_id, url=idp + "/index.html")
            await controller.begin_human_control(session_id=handle.session_id)
            live = controller._get_session(session_id=handle.session_id)  # pyright: ignore[reportPrivateUsage]
            await live.page.goto(idp + "/index.html")
            assert live.page.url.startswith(idp)
            with pytest.raises(HumanControlActiveError):
                await controller.get_state(session_id=handle.session_id)
            await live.page.goto(url)
            await controller.end_human_control(
                session_id=handle.session_id, verified=True, safe_to_capture=True,
            )
            assert (await controller.get_state(session_id=handle.session_id)).observation.url == url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


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
        with pytest.raises(BrowserActionBlockedError, match="Sensitive forms"):
            await tools["browser_click"](
                role="button", name="Save", scope_role="form", scope_name="Registration",
            )
        assert recorder.finished == [(1, "policy_blocked")]
        assert not recorder.evidence
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


async def test_human_control_quiesces_agent_tools_and_suppresses_canary_capture(
    scoped_fixture: tuple[str, int], tmp_path: Path,
) -> None:
    url, port = scoped_fixture
    artifact_root = tmp_path / "artifacts"
    async with BrowserController(artifact_root=artifact_root) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        await controller.navigate(session_id=handle.session_id, url=url)
        session = cast(Any, controller)._get_session(session_id=handle.session_id)
        session.event_buffer.record_console_error("pre-handoff diagnostic")
        await controller.begin_human_control(session_id=handle.session_id)
        assert session.control_mode == "human"
        assert session.tracing_active is False
        assert session.event_buffer.all_console_errors == []

        canary = "CANARY_PASSWORD_" + "HITL_SYNTHETIC_42"
        await session.page.evaluate(
            """(canary) => {
              console.error(`sensitive console ${canary}`);
              setTimeout(() => { throw new Error(`sensitive page error ${canary}`); }, 0);
            }""",
            canary,
        )
        await session.page.evaluate(
            """async (url) => { try { await fetch(url); } catch {} }""",
            f"http://127.0.0.1:1/failure?otp={canary}",
        )
        await asyncio.sleep(0.05)
        assert session.event_buffer.all_console_errors == []
        assert session.event_buffer.all_page_errors == []
        assert session.event_buffer.all_failed_requests == []
        with pytest.raises(HumanControlActiveError):
            await controller.get_state(session_id=handle.session_id)
        with pytest.raises(BrowserSessionStateError):
            await controller.end_human_control(session_id=handle.session_id)

        artifacts = await controller.close_session(session_id=handle.session_id)
        assert artifacts.console_log_path is None
        assert artifacts.page_log_path is None
        assert artifacts.network_log_path is None
        assert artifacts.trace_paths
        for trace_path in artifacts.trace_paths:
            with zipfile.ZipFile(trace_path) as trace:
                leaked_members = [
                    name for name in trace.namelist() if canary.encode() in trace.read(name)
                ]
                assert not leaked_members, f"Canary appeared in trace entries: {leaked_members}"
        assert all(
            canary.encode() not in path.read_bytes()
            for path in artifact_root.rglob("*")
            if path.is_file()
        )


async def test_agent_action_rechecks_authority_after_waiting_for_session_lock(
    scoped_fixture: tuple[str, int], tmp_path: Path,
) -> None:
    url, port = scoped_fixture
    async with BrowserController(artifact_root=tmp_path / "artifacts") as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        await controller.navigate(session_id=handle.session_id, url=url)
        session = cast(Any, controller)._get_session(session_id=handle.session_id)
        await session.lock.acquire()
        action = asyncio.create_task(controller.get_state(session_id=handle.session_id))
        await asyncio.sleep(0)
        session.control_mode = "human"
        session.lock.release()
        with pytest.raises(HumanControlActiveError):
            await action


@pytest.mark.parametrize("outcome", ["resume", "unverified", "cancel", "timeout"])
async def test_sensitive_sinks_and_cleanup_paths(
    scoped_fixture: tuple[str, int], tmp_path: Path, outcome: str,
) -> None:
    url, port = scoped_fixture
    root = tmp_path / "evidence"
    async with BrowserController(artifact_root=root) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        await controller.navigate(session_id=handle.session_id, url=url)
        session = cast(Any, controller)._get_session(session_id=handle.session_id)
        await controller.begin_human_control(session_id=handle.session_id)
        recorder = Recorder()
        tools = {tool.__name__: tool for tool in create_browser_tools(
            controller=controller, handle=handle,
            step_recorder=cast(BrowserStepRecorder, recorder),
        )}
        canary = "CANARY_" + uuid4().hex
        await session.page.evaluate("""secret => {
            document.body.insertAdjacentHTML('beforeend', '<p id="secret"></p>');
            document.querySelector('#secret').textContent = secret;
            console.error(secret);
            alert(secret);
            setTimeout(() => { throw new Error(secret); }, 0);
        }""", canary)
        await session.page.evaluate(
            "async secret => {try {await fetch('http://127.0.0.1:1/?otp='+secret)}catch{}}",
            canary,
        )
        with pytest.raises(HumanControlActiveError):
            await tools["browser_click"](role="button", name=canary)
        with pytest.raises(HumanControlActiveError):
            await tools["browser_get_state"]()
        assert recorder.count == 0
        assert recorder.evidence == []
        with pytest.raises(HumanControlActiveError):
            await build_observation(session)
        with pytest.raises(HumanControlActiveError):
            await write_event_logs(session)
        await asyncio.sleep(0.05)
        assert session.event_buffer.all_console_errors == []
        assert session.event_buffer.all_page_errors == []
        assert session.event_buffer.all_failed_requests == []

        if outcome == "resume":
            # The trusted verifier must move to a reviewed safe page before
            # resuming. Human-phase DOM and form values are never snapshotted.
            await session.page.goto(url)
            await controller.end_human_control(
                session_id=handle.session_id, verified=True, safe_to_capture=True,
            )
            result = await tools["browser_get_state"]()
            assert canary not in json.dumps(result)
        elif outcome == "unverified":
            with pytest.raises(BrowserSessionStateError):
                await controller.end_human_control(session_id=handle.session_id)
        elif outcome == "timeout":
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.01):
                    await asyncio.sleep(1)
        artifacts = await controller.close_session(session_id=handle.session_id)
        assert len(artifacts.trace_paths) == 1
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            assert canary.encode() not in path.read_bytes()
            if path.suffix == ".zip":
                with zipfile.ZipFile(path) as trace:
                    assert all(canary.encode() not in trace.read(n) for n in trace.namelist())


async def test_close_after_pending_handoff_revoke_skips_browser_logs(
    scoped_fixture: tuple[str, int], tmp_path: Path,
) -> None:
    url, port = scoped_fixture
    async with BrowserController(artifact_root=tmp_path / "pending-revoke") as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
            authenticated_session=True,
        )
        await controller.navigate(session_id=handle.session_id, url=url)
        session = cast(Any, controller)._get_session(session_id=handle.session_id)
        # A cancellation/revoke before viewer attach fences agent writes while
        # the context remains capture-enabled; shutdown must still be safe.
        session.control_mode = "verifying"

        artifacts = await controller.close_session(session_id=handle.session_id)

        assert artifacts.console_log_path is None
        assert artifacts.page_log_path is None
        assert artifacts.network_log_path is None
