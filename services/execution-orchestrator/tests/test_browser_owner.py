"""Real same-context restricted viewer proof; synthetic identities only."""

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import zipfile
from collections.abc import AsyncGenerator, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.errors import (
    BrowserSessionStateError,
    HumanControlActiveError,
)
from markettwin_execution_orchestrator.browser.owner import (
    ControllerBrowserOwner,
    OwnerLease,
    ViewerInput,
    ViewerRejectedError,
)
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession
from playwright.async_api import Locator, expect
from pydantic import ValidationError


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


@pytest.mark.parametrize("trial", [1, 2, 3])
async def test_owner_same_context_login_fencing_and_volatile_frames(
    fixture_origin: tuple[str, int], tmp_path: Path, trial: int,
) -> None:
    origin, port = fixture_origin
    root = tmp_path / "artifacts"
    latencies: list[float] = []
    frame_sizes: list[int] = []
    async with BrowserController(artifact_root=root) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        await controller.navigate(
            session_id=handle.session_id, url=origin + "/index.html?view=login"
        )
        session = cast(Any, controller)._get_session(session_id=handle.session_id)
        context = session.context
        browser_channel = await session.browser.new_browser_cdp_session()
        process_info = await browser_channel.send("SystemInfo.getProcessInfo")
        pids = [int(item["id"]) for item in process_info["processInfo"]]
        working_set_bytes: int | None = None
        if sys.platform == "win32":
            command = "Get-Process -Id " + ",".join(str(pid) for pid in pids)
            command += (
                " | Measure-Object -Property WorkingSet64 -Sum | Select-Object -ExpandProperty Sum"
            )
            output = await asyncio.to_thread(subprocess.check_output,
                ["powershell.exe", "-NoProfile", "-Command", command], text=True,
            )
            working_set_bytes = int(output.strip())
        cpu_before = sum(float(item["cpuTime"]) for item in process_info["processInfo"])
        owner = ControllerBrowserOwner(controller)
        lease = OwnerLease(handle, uuid4(), uuid4(), 1, datetime.now(UTC) + timedelta(minutes=1))
        with pytest.raises(ViewerRejectedError):
            await owner.attach(lease)
        await controller.begin_human_control(session_id=handle.session_id)
        await owner.attach(lease)
        with pytest.raises(ViewerRejectedError):
            await owner.attach(lease)
        with pytest.raises(HumanControlActiveError):
            await controller.get_state(session_id=handle.session_id)

        sequence = 0

        async def send(**payload: object) -> None:
            nonlocal sequence
            sequence += 1
            event = ViewerInput.model_validate({"sequence": sequence, **payload})
            started = time.perf_counter()
            await owner.input(lease, event)
            latencies.append((time.perf_counter() - started) * 1000)

        async def click(locator: Any) -> None:
            box = await locator.bounding_box()
            assert box is not None
            await send(event="click", x=int(box["x"] + box["width"] / 2),
                       y=int(box["y"] + box["height"] / 2))

        await click(session.page.get_by_label("Username"))
        await send(event="text", text="fixture-user")
        await send(event="key", key="Tab")
        await send(event="text", text="synthetic-password")
        frame = await owner.frame(lease)
        assert frame.startswith(b"\xff\xd8")
        frame_sizes.append(len(frame))
        await send(event="key", key="Tab")
        await send(event="key", key="Enter")
        await expect(cast(Locator, session.page.get_by_label("One-time code"))).to_be_visible()
        await click(session.page.get_by_label("One-time code"))
        await send(event="text", text="246810")
        await click(session.page.get_by_role("button", name="Verify"))
        await expect(cast(Locator, session.page.get_by_text(
            "Signed in as user", exact=True,
        ))).to_be_visible()
        assert session.context is context
        assert session.session_id == handle.session_id
        for _ in range(5):
            started = time.perf_counter()
            frame_sizes.append(len(await owner.frame(lease)))
            latencies.append((time.perf_counter() - started) * 1000)
        with pytest.raises(ViewerRejectedError):
            await owner.input(lease, ViewerInput(sequence=sequence, event="click", x=1, y=1))
        with pytest.raises(ViewerRejectedError):
            await owner.frame(replace(lease, actor_id=uuid4()))
        with pytest.raises(ViewerRejectedError):
            await owner.input(lease, ViewerInput(sequence=sequence+1, event="key", key="Control+l"))
        await send(event="resize", width=640, height=480)
        await send(event="scroll", delta=200)
        canary = "VIEWER_" + uuid4().hex
        await session.page.evaluate("""value => {
            console.error(value);
            document.body.insertAdjacentHTML('beforeend', '<p id="canary"></p>');
            document.querySelector('#canary').textContent = value;
        }""", canary)
        sensitive_frame = await owner.frame(lease)
        assert sensitive_frame.startswith(b"\xff\xd8")
        await session.page.reload()
        with pytest.raises(ViewerRejectedError):
            await owner.input(lease, ViewerInput(sequence=sequence+1, event="click", x=900, y=800))
        await owner.revoke(handle, 2)
        with pytest.raises(ViewerRejectedError):
            await owner.input(lease, ViewerInput(sequence=sequence+1, event="text", text="stale"))
        with pytest.raises(ViewerRejectedError):
            await owner.frame(lease)
        assert not session.capture_enabled
        await controller.end_human_control(
            session_id=handle.session_id, verified=True, safe_to_capture=True,
        )
        assert (await controller.get_state(session_id=handle.session_id)).observation.title
        process_info = await browser_channel.send("SystemInfo.getProcessInfo")
        cpu_after = sum(float(item["cpuTime"]) for item in process_info["processInfo"])
        await browser_channel.detach()
        await controller.close_session(session_id=handle.session_id)

    # Sensitive phase text and frame bytes may exist only in volatile memory.
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        data = path.read_bytes()
        assert frame not in data
        assert sensitive_frame not in data
        assert canary.encode() not in data
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                assert all(canary.encode() not in archive.read(n) for n in archive.namelist())
                records = [archive.read(n) for n in archive.namelist() if n.endswith(".trace")]
                assert all(b'"text":"synthetic-password"' not in data for data in records)
                assert all(b'"text":"246810"' not in data for data in records)
    metrics = {
        "transport": "private_cdp_viewport", "same_context": True,
        "samples_ms": latencies, "frame_bytes": frame_sizes,
        "network_latency": "not_measured", "working_set_bytes_at_start": working_set_bytes,
        "browser_processes": len(pids), "cpu_seconds_delta": cpu_after - cpu_before,
        "trial": trial,
    }
    (tmp_path / "viewer-metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    if metrics_directory := os.environ.get("MARKETTWIN_HITL_METRICS_DIR"):
        directory = Path(metrics_directory)
        await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
        (directory / f"owner-trial-{trial}.json").write_text(json.dumps(metrics), encoding="utf-8")


async def test_owner_rejects_expiry_browser_loss_and_raw_protocol(
    fixture_origin: tuple[str, int], tmp_path: Path,
) -> None:
    origin, port = fixture_origin
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        await controller.navigate(session_id=handle.session_id, url=origin + "/index.html")
        await controller.begin_human_control(session_id=handle.session_id)
        owner = ControllerBrowserOwner(controller)
        lease = OwnerLease(handle, uuid4(), uuid4(), 1, datetime.now(UTC) + timedelta(minutes=1))
        with pytest.raises(ViewerRejectedError):
            await owner.attach(replace(lease, expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        await owner.attach(lease)
        with pytest.raises(ValidationError):
            ViewerInput.model_validate({"sequence": 1, "event": "Runtime.evaluate", "text": "bad"})
        with pytest.raises(ValidationError):
            ViewerInput.model_validate({"sequence": 1, "event": "text", "text": "x" * 2049})
        session = cast(Any, controller)._get_session(session_id=handle.session_id)
        await session.browser.close()
        with pytest.raises(ViewerRejectedError):
            await owner.input(lease, ViewerInput(sequence=1, event="key", key="Tab"))


async def test_popup_remains_in_owned_context_and_expired_input_is_rejected(
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
        context = session.context
        await controller.begin_human_control(session_id=handle.session_id)
        owner = ControllerBrowserOwner(controller)
        lease = OwnerLease(handle, uuid4(), uuid4(), 1, datetime.now(UTC) + timedelta(minutes=1))
        await owner.attach(lease)
        async with context.expect_page() as popup:
            await session.page.evaluate(
                "url => window.open(url)", origin + "/index.html?view=login"
            )
        page = await popup.value
        await page.wait_for_load_state()
        await asyncio.sleep(0.05)
        assert session.page is page
        assert session.context is context
        assert await owner.frame(lease)
        with patch("markettwin_execution_orchestrator.browser.owner.datetime") as clock:
            clock.now.return_value = lease.expires_at + timedelta(seconds=1)
            with pytest.raises(ViewerRejectedError):
                await owner.input(lease, ViewerInput(sequence=1, event="key", key="Tab"))
            with pytest.raises(ViewerRejectedError):
                await owner.frame(lease)
        await owner.revoke(handle, 2)


async def test_transport_reconnect_preserves_generation_and_strict_revoke_validation(
    fixture_origin: tuple[str, int], tmp_path: Path,
) -> None:
    origin, port = fixture_origin
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        await controller.navigate(session_id=handle.session_id, url=origin + "/index.html")
        await controller.begin_human_control(session_id=handle.session_id)
        owner = ControllerBrowserOwner(controller)
        lease = OwnerLease(handle, uuid4(), uuid4(), 1, datetime.now(UTC) + timedelta(seconds=30))
        await owner.attach(lease)
        await owner.detach(lease)
        live = controller._get_session(  # pyright: ignore[reportPrivateUsage]
            session_id=handle.session_id,
        )
        assert live.control_generation == 1 and live.control_mode == "human"
        with pytest.raises(ViewerRejectedError):
            await owner.input(lease, ViewerInput(sequence=1, event="key", key="Tab"))
        with pytest.raises(ViewerRejectedError):
            await owner.attach(replace(lease, actor_id=uuid4()))
        with pytest.raises(ViewerRejectedError):
            await owner.attach(replace(lease, expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        await owner.attach(lease)
        with pytest.raises(ViewerRejectedError):
            await owner.attach(lease)
        with pytest.raises(BrowserSessionStateError):
            await owner.revoke(handle, 1)
        await owner.revoke(handle, 2)
        await owner.revoke(handle, 2)  # exact duplicate of an already applied revoke
        with pytest.raises(BrowserSessionStateError):
            await owner.revoke(handle, 1)
        assert live.control_mode == "verifying" and live.control_generation == 2
        assert not live.capture_enabled and not live.tracing_active


@pytest.fixture
async def pointer_owner(
    fixture_origin: tuple[str, int], tmp_path: Path,
) -> AsyncGenerator[tuple[ControllerBrowserOwner, OwnerLease, JourneyBrowserSession]]:
    origin, port = fixture_origin
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        )
        await controller.navigate(session_id=handle.session_id, url=origin + "/index.html")
        await controller.begin_human_control(session_id=handle.session_id)
        session = controller._get_session(  # pyright: ignore[reportPrivateUsage]
            session_id=handle.session_id,
        )
        await session.page.set_content("""<button id="tile">Tile</button>
            <input id="slider" type="range" min="0" max="100" value="0"
                style="position:absolute;left:80px;top:100px;width:240px;height:40px">
            <script>window.pointerEvents = [];
            for (const type of ['pointerdown', 'pointermove', 'pointerup']) {
              document.addEventListener(type, event => window.pointerEvents.push({
                type, buttons: event.buttons
              }));
            }
            document.querySelector('#tile').onclick = () => {
              document.querySelector('#tile').textContent = 'Selected';
            };</script>""")
        owner = ControllerBrowserOwner(controller)
        lease = OwnerLease(handle, uuid4(), uuid4(), 1, datetime.now(UTC) + timedelta(minutes=1))
        await owner.attach(lease)
        yield owner, lease, session


async def test_real_pointer_drag_and_click_are_distinct_gestures(
    pointer_owner: tuple[ControllerBrowserOwner, OwnerLease, JourneyBrowserSession],
) -> None:
    owner, lease, session = pointer_owner
    await owner.input(lease, ViewerInput(sequence=1, event="click", x=25, y=18))
    await expect(session.page.locator("#tile")).to_have_text("Selected")
    await session.page.evaluate("window.pointerEvents = []")
    await owner.input(lease, ViewerInput(sequence=2, event="pointer_down", x=90, y=120))
    await owner.input(lease, ViewerInput(sequence=3, event="pointer_move", x=180, y=120))
    await owner.input(lease, ViewerInput(sequence=4, event="pointer_up", x=310, y=120))
    assert int(await session.page.locator("#slider").input_value()) > 90
    events = cast(list[dict[str, object]], await session.page.evaluate("window.pointerEvents"))
    assert sum(event["type"] == "pointerdown" for event in events) == 1
    assert sum(event["type"] == "pointerup" for event in events) == 1
    assert any(event["type"] == "pointermove" and event["buttons"] == 1 for event in events)


@pytest.mark.parametrize("event", ["pointer_move", "pointer_up", "pointer_cancel"])
async def test_pointer_requires_matching_down(
    pointer_owner: tuple[ControllerBrowserOwner, OwnerLease, JourneyBrowserSession], event: str,
) -> None:
    owner, lease, session = pointer_owner
    with pytest.raises(ViewerRejectedError, match="transition"):
        await owner.input(lease, ViewerInput.model_validate({
            "sequence": 1, "event": event, "x": 30, "y": 20,
        }))
    assert await session.page.evaluate("window.pointerEvents.length") == 0


@pytest.mark.parametrize("event", ["pointer_down", "pointer_move", "pointer_up", "pointer_cancel"])
async def test_all_pointer_events_check_actual_viewport_bounds(
    pointer_owner: tuple[ControllerBrowserOwner, OwnerLease, JourneyBrowserSession], event: str,
) -> None:
    owner, lease, session = pointer_owner
    await owner.input(lease, ViewerInput(sequence=1, event="resize", width=640, height=480))
    if event != "pointer_down":
        await owner.input(lease, ViewerInput(sequence=2, event="pointer_down", x=90, y=120))
    with pytest.raises(ViewerRejectedError):
        await owner.input(lease, ViewerInput.model_validate({
            "sequence": 3, "event": event, "x": 640, "y": 120,
        }))
    # Invalid events cannot leave a button held or dispatch an out-of-bounds move.
    await session.page.mouse.move(30, 25)
    events = cast(list[dict[str, object]], await session.page.evaluate("window.pointerEvents"))
    assert events[-1]["buttons"] == 0


async def test_detach_releases_drag_and_stale_actor_cannot_release_new_lease(
    pointer_owner: tuple[ControllerBrowserOwner, OwnerLease, JourneyBrowserSession],
) -> None:
    owner, lease, session = pointer_owner
    await owner.input(lease, ViewerInput(sequence=1, event="pointer_down", x=90, y=120))
    await owner.detach(lease)
    await session.page.mouse.move(30, 25)
    assert await session.page.evaluate("window.pointerEvents.at(-1).buttons") == 0
    await owner.attach(lease)
    await owner.input(lease, ViewerInput(sequence=1, event="pointer_down", x=90, y=120))
    with pytest.raises(ViewerRejectedError):
        await owner.input(replace(lease, actor_id=uuid4()), ViewerInput(
            sequence=2, event="pointer_cancel", x=90, y=120,
        ))
    await owner.detach(replace(lease, actor_id=uuid4()))
    await owner.input(lease, ViewerInput(sequence=2, event="pointer_move", x=150, y=120))
    assert await session.page.evaluate("window.pointerEvents.at(-1).buttons") == 1
    await owner.revoke(lease.handle, 2)
    await session.page.mouse.move(30, 25)
    assert await session.page.evaluate("window.pointerEvents.at(-1).buttons") == 0
    with pytest.raises(ViewerRejectedError):
        await owner.input(lease, ViewerInput(sequence=3, event="pointer_move", x=150, y=120))


@pytest.mark.parametrize("failure", ["expired", "sequence", "duplicate_down", "browser_loss"])
async def test_failed_authority_or_transition_fences_held_pointer(
    pointer_owner: tuple[ControllerBrowserOwner, OwnerLease, JourneyBrowserSession], failure: str,
) -> None:
    owner, lease, session = pointer_owner
    await owner.input(lease, ViewerInput(sequence=1, event="pointer_down", x=90, y=120))
    if failure == "expired":
        with patch("markettwin_execution_orchestrator.browser.owner.datetime") as clock:
            clock.now.return_value = lease.expires_at + timedelta(seconds=1)
            with pytest.raises(ViewerRejectedError):
                await owner.frame(lease)
    elif failure == "browser_loss":
        await session.browser.close()
        with pytest.raises(ViewerRejectedError):
            await owner.input(lease, ViewerInput(sequence=2, event="pointer_up", x=90, y=120))
        return
    else:
        with pytest.raises(ViewerRejectedError):
            await owner.input(lease, ViewerInput(
                sequence=1 if failure == "sequence" else 2,
                event="pointer_move" if failure == "sequence" else "pointer_down", x=90, y=120,
            ))
    await session.page.mouse.move(30, 25)
    assert await session.page.evaluate("window.pointerEvents.at(-1).buttons") == 0
    assert session.control_mode == "none"
    with pytest.raises(ViewerRejectedError):
        await owner.input(lease, ViewerInput(sequence=3, event="pointer_move", x=150, y=120))


async def test_pointer_cancel_releases_without_an_extra_move(
    pointer_owner: tuple[ControllerBrowserOwner, OwnerLease, JourneyBrowserSession],
) -> None:
    owner, lease, session = pointer_owner
    await owner.input(lease, ViewerInput(sequence=1, event="pointer_down", x=90, y=120))
    await session.page.evaluate("window.pointerEvents = []")
    await owner.input(lease, ViewerInput(sequence=2, event="pointer_cancel", x=310, y=120))
    events = cast(list[dict[str, object]], await session.page.evaluate("window.pointerEvents"))
    assert [event["type"] for event in events] == ["pointerup"]
    assert events[0]["buttons"] == 0
    await owner.input(lease, ViewerInput(sequence=3, event="click", x=25, y=18))
    await expect(session.page.locator("#tile")).to_have_text("Selected")


async def test_pointer_dispatch_timeout_releases_and_fences_without_replay(
    pointer_owner: tuple[ControllerBrowserOwner, OwnerLease, JourneyBrowserSession],
) -> None:
    owner, lease, session = pointer_owner
    await owner.input(lease, ViewerInput(sequence=1, event="pointer_down", x=90, y=120))

    async def hang(*args: object) -> None:
        await asyncio.sleep(60)

    with patch("markettwin_execution_orchestrator.browser.owner.VIEWER_OPERATION_SECONDS", 0.05):
        with patch.object(session.page.mouse, "move", AsyncMock(side_effect=hang)):
            with pytest.raises(ViewerRejectedError):
                await asyncio.wait_for(owner.input(
                    lease, ViewerInput(sequence=2, event="pointer_move", x=150, y=120),
                ), timeout=1)
    assert session.control_mode == "none"
    await session.page.mouse.move(30, 25)
    assert await session.page.evaluate("window.pointerEvents.at(-1).buttons") == 0
    with pytest.raises(ViewerRejectedError):
        await owner.input(lease, ViewerInput(sequence=2, event="pointer_move", x=150, y=120))


@pytest.mark.parametrize("event", ["click", "pointer_down"])
async def test_revocation_during_move_cannot_press_after_authority_fence(
    pointer_owner: tuple[ControllerBrowserOwner, OwnerLease, JourneyBrowserSession], event: str,
) -> None:
    owner, lease, session = pointer_owner
    started, finish_move = asyncio.Event(), asyncio.Event()

    async def delayed_move(*args: object) -> None:
        started.set()
        await finish_move.wait()

    with patch.object(session.page.mouse, "move", AsyncMock(side_effect=delayed_move)):
        pending = asyncio.create_task(owner.input(lease, ViewerInput.model_validate({
            "sequence": 1, "event": event, "x": 90, "y": 120,
        })))
        await started.wait()
        revoke = asyncio.create_task(owner.revoke(lease.handle, 2))
        await asyncio.sleep(0)
        finish_move.set()
        with pytest.raises(ViewerRejectedError):
            await pending
        await revoke
    assert await session.page.evaluate("window.pointerEvents.length") == 0
    assert session.control_generation == 2 and session.control_mode == "verifying"


async def test_pointer_moves_share_the_existing_thirty_event_budget(
    pointer_owner: tuple[ControllerBrowserOwner, OwnerLease, JourneyBrowserSession],
) -> None:
    owner, lease, session = pointer_owner
    now = datetime.now(UTC)
    with patch("markettwin_execution_orchestrator.browser.owner.datetime") as clock:
        clock.now.return_value = now
        await owner.input(lease, ViewerInput(sequence=1, event="pointer_down", x=90, y=120))
        for sequence in range(2, 31):
            await owner.input(lease, ViewerInput(
                sequence=sequence, event="pointer_move", x=150, y=120,
            ))
        with pytest.raises(ViewerRejectedError):
            await owner.input(lease, ViewerInput(sequence=31, event="pointer_move", x=180, y=120))
    await session.page.mouse.move(30, 25)
    assert await session.page.evaluate("window.pointerEvents.at(-1).buttons") == 0


async def test_uncertain_pointer_release_cannot_be_reused_by_another_lease(
    pointer_owner: tuple[ControllerBrowserOwner, OwnerLease, JourneyBrowserSession],
) -> None:
    owner, lease, session = pointer_owner
    await owner.input(lease, ViewerInput(sequence=1, event="pointer_down", x=90, y=120))
    with patch.object(
        session.page.mouse, "up", AsyncMock(side_effect=RuntimeError("private payload")),
    ):
        await owner.detach(lease)
    assert session.state == "failed" and session.control_mode == "none"
    with pytest.raises(ViewerRejectedError):
        await owner.attach(replace(lease, lease_id=uuid4(), generation=2))
    with pytest.raises(ViewerRejectedError) as error:
        await owner.input(lease, ViewerInput(sequence=2, event="pointer_move", x=150, y=120))
    assert "private payload" not in str(error.value)


@pytest.mark.parametrize("operation", ["input", "frame", "detach", "revoke"])
async def test_stalled_owner_lock_fails_closed_without_outside_lock_mouse_input(
    pointer_owner: tuple[ControllerBrowserOwner, OwnerLease, JourneyBrowserSession], operation: str,
) -> None:
    owner, lease, session = pointer_owner
    await owner.input(lease, ViewerInput(sequence=1, event="pointer_down", x=90, y=120))
    with patch("markettwin_execution_orchestrator.browser.owner.VIEWER_OPERATION_SECONDS", 0.05):
        with patch.object(session.page.mouse, "up", AsyncMock()) as release:
            async with session.lock:
                with pytest.raises(ViewerRejectedError):
                    if operation == "input":
                        await owner.input(lease, ViewerInput(
                            sequence=2, event="pointer_move", x=150, y=120,
                        ))
                    elif operation == "frame":
                        await owner.frame(lease)
                    elif operation == "detach":
                        await owner.detach(lease)
                    else:
                        await owner.revoke(lease.handle, 2)
                release.assert_not_called()
    assert session.state == "failed" and session.control_mode == "none"
    with pytest.raises(ViewerRejectedError):
        await owner.attach(replace(lease, lease_id=uuid4(), generation=3))


async def test_stale_actor_lock_timeout_cannot_fence_current_pointer_lease(
    pointer_owner: tuple[ControllerBrowserOwner, OwnerLease, JourneyBrowserSession],
) -> None:
    owner, lease, session = pointer_owner
    await owner.input(lease, ViewerInput(sequence=1, event="pointer_down", x=90, y=120))
    with patch("markettwin_execution_orchestrator.browser.owner.VIEWER_OPERATION_SECONDS", 0.05):
        async with session.lock:
            with pytest.raises(ViewerRejectedError):
                await owner.input(replace(lease, actor_id=uuid4()), ViewerInput(
                    sequence=2, event="pointer_cancel", x=90, y=120,
                ))
    assert session.state == "open" and session.control_mode == "human"
    await owner.input(lease, ViewerInput(sequence=2, event="pointer_move", x=150, y=120))
    assert await session.page.evaluate("window.pointerEvents.at(-1).buttons") == 1
    await owner.input(lease, ViewerInput(sequence=3, event="pointer_cancel", x=150, y=120))
