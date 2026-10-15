"""Real same-context restricted viewer proof; synthetic identities only."""

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import zipfile
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.errors import HumanControlActiveError
from markettwin_execution_orchestrator.browser.owner import (
    ControllerBrowserOwner,
    OwnerLease,
    ViewerInput,
    ViewerRejectedError,
)
from playwright.async_api import expect
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
        await controller.navigate(session_id=handle.session_id, url=origin + "/index.html?view=login")
        session = cast(Any, controller)._get_session(session_id=handle.session_id)
        context = session.context
        browser_channel = await session.browser.new_browser_cdp_session()
        process_info = await browser_channel.send("SystemInfo.getProcessInfo")
        pids = [int(item["id"]) for item in process_info["processInfo"]]
        working_set_bytes: int | None = None
        if sys.platform == "win32":
            command = "Get-Process -Id " + ",".join(str(pid) for pid in pids)
            command += " | Measure-Object -Property WorkingSet64 -Sum | Select-Object -ExpandProperty Sum"
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
        await expect(session.page.get_by_label("One-time code")).to_be_visible()
        await click(session.page.get_by_label("One-time code"))
        await send(event="text", text="246810")
        await click(session.page.get_by_role("button", name="Verify"))
        await expect(session.page.get_by_text("Signed in as user", exact=True)).to_be_visible()
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
        lease = OwnerLease(handle, uuid4(), uuid4(), 1, datetime.now(UTC) + timedelta(seconds=1))
        await owner.attach(lease)
        async with context.expect_page() as popup:
            await session.page.evaluate("url => window.open(url)", origin + "/index.html?view=login")
        page = await popup.value
        await page.wait_for_load_state()
        await asyncio.sleep(0.05)
        assert session.page is page
        assert session.context is context
        assert await owner.frame(lease)
        await asyncio.sleep(max(0, (lease.expires_at - datetime.now(UTC)).total_seconds()) + 0.02)
        with pytest.raises(ViewerRejectedError):
            await owner.input(lease, ViewerInput(sequence=1, event="key", key="Tab"))
        with pytest.raises(ViewerRejectedError):
            await owner.frame(lease)
        await owner.revoke(handle, 2)
