"""Viewer target annotation preserves frame size, evidence and control boundaries."""

import asyncio
import base64
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from time import monotonic
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.live_pointer import (
    LiveClickTarget,
    annotate_live_target,
)
from markettwin_execution_orchestrator.browser.owner import ControllerBrowserOwner
from PIL import Image

URL = "https://example.test/"


def frame():
    output = BytesIO()
    Image.new("RGB", (320, 240), "white").save(output, format="JPEG")
    return output.getvalue()


def test_target_scales_to_screencast_without_resizing_it():
    original = frame()
    target = LiveClickTarget(160, 180, 640, 480, URL, monotonic())
    marked = annotate_live_target(original, target, URL)
    with Image.open(BytesIO(marked)) as image:
        assert image.size == (320, 240)
        red, green, blue = image.getpixel((85, 100))
        assert red > green + 60 and red > blue + 40
    assert marked != original


@pytest.mark.parametrize("target", [
    None,
    LiveClickTarget(-10, 90, 320, 240, URL, monotonic()),
    LiveClickTarget(80, 90, 0, 240, URL, monotonic()),
])
def test_missing_or_invalid_target_returns_original_frame(target):
    original = frame()
    assert annotate_live_target(original, target, URL) == original


@pytest.mark.parametrize("target", [
    LiveClickTarget(80, 90, 320, 240, "https://other.test/", monotonic()),
    LiveClickTarget(80, 90, 320, 240, URL, monotonic() - 5),
])
def test_cursor_persists_after_navigation_and_between_actions(target):
    with Image.open(BytesIO(annotate_live_target(frame(), target, URL))) as image:
        red, green, blue = image.getpixel((85, 100))
        assert red > green + 60 and red > blue + 40


@pytest.mark.parametrize("mode", ["agent", "human_pending", "human"])
async def test_stream_keeps_original_jpeg_and_sends_agent_pointer_separately(mode):
    handle = BrowserSessionHandle(uuid4(), uuid4(), uuid4())
    original = frame()
    source = SimpleNamespace(generation=0, stopped=False, latest_frame=original,
                             frame_event=asyncio.Event())
    source.frame_event.set()
    session = SimpleNamespace(control_mode=mode, page=SimpleNamespace(url=URL),
                              live_click_target=LiveClickTarget(
                                  80, 90, 320, 240, URL, monotonic()))
    owner = ControllerBrowserOwner(SimpleNamespace(_get_session=lambda **_: session))
    owner._screencasts[handle.session_id] = source
    owner._screencast_allowed = Mock()
    shown = await owner.next_screencast_frame(handle, generation=0)
    assert shown is original
    assert source.latest_frame == original
    assert owner._screencast_allowed.call_count == 2
    latest, metadata = owner.current_observer_frame(handle, generation=0)
    assert latest is original
    assert metadata == {"type": "agent_pointer", "pointer":
                        {"x": 0.25, "y": 0.375} if mode == "agent" else None}


async def test_still_page_repeats_last_frame_instead_of_closing(monkeypatch):
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.browser.owner.SCREENCAST_FRAME_SECONDS", 0.01,
    )
    handle = BrowserSessionHandle(uuid4(), uuid4(), uuid4())
    original = frame()
    source = SimpleNamespace(generation=0, stopped=False, latest_frame=original,
                             frame_event=asyncio.Event())
    session = SimpleNamespace(control_mode="human_pending", page=SimpleNamespace(url=URL),
                              live_click_target=None)
    owner = ControllerBrowserOwner(SimpleNamespace(_get_session=lambda **_: session))
    owner._screencasts[handle.session_id] = source
    owner._screencast_allowed = Mock()
    assert await owner.next_screencast_frame(handle, generation=0) == original


async def test_pointer_change_wakes_still_page_without_repaint():
    handle = BrowserSessionHandle(uuid4(), uuid4(), uuid4())
    changed = asyncio.Event()
    original = frame()
    source = SimpleNamespace(generation=0, stopped=False, latest_frame=original,
                             frame_event=changed)
    session = SimpleNamespace(control_mode="agent", live_click_target=None,
                              control_generation=0,
                              live_view_changed=changed,
                              page=SimpleNamespace(
                                  mouse=SimpleNamespace(move=AsyncMock()),
                                  url=URL, viewport_size={"width": 320, "height": 240}))
    owner = ControllerBrowserOwner(SimpleNamespace(_get_session=lambda **_: session))
    owner._screencasts[handle.session_id] = source
    owner._screencast_allowed = Mock()
    waiter = asyncio.create_task(owner.next_screencast_frame(handle, generation=0))
    await asyncio.sleep(0)
    assert not waiter.done()
    locator = SimpleNamespace(bounding_box=AsyncMock(
        return_value={"x": 40, "y": 60, "width": 80, "height": 60}),
        scroll_into_view_if_needed=AsyncMock())
    await BrowserController._track_pointer(session, locator)
    positions = [call.args for call in session.page.mouse.move.await_args_list]
    assert len(positions) == 8
    assert positions[0] == (10, 11.25)
    assert positions[-1] == (80, 90)
    assert await asyncio.wait_for(waiter, timeout=0.2) is original
    _, metadata = owner.current_observer_frame(handle, generation=0)
    assert metadata["pointer"] == {"x": 0.25, "y": 0.375}
    session.page.url = "https://example.test/next"
    assert owner.current_observer_frame(handle, generation=0)[1]["pointer"] == {
        "x": 0.25, "y": 0.375}
    session.control_mode = "human_pending"
    assert owner.current_observer_frame(handle, generation=0)[1]["pointer"] is None


async def test_invalid_screencast_frame_is_still_acknowledged():
    handle = BrowserSessionHandle(uuid4(), uuid4(), uuid4())
    callbacks = {}
    channel = SimpleNamespace(send=AsyncMock(), detach=AsyncMock(),
                              on=lambda name, callback: callbacks.update({name: callback}))
    session = SimpleNamespace(live_view_changed=asyncio.Event(), page=object(),
                              context=SimpleNamespace(new_cdp_session=AsyncMock(return_value=channel)))
    owner = ControllerBrowserOwner(SimpleNamespace(_get_session=lambda **_: session))
    owner._screencast_allowed = Mock()
    await owner.start_screencast(handle, generation=0)
    callbacks["Page.screencastFrame"]({"sessionId": 42, "data": "not base64!"})
    await asyncio.sleep(0)
    channel.send.assert_any_await("Page.screencastFrameAck", {"sessionId": 42})
    assert owner._screencasts[handle.session_id].latest_frame is None
    assert owner.screencast_stats(handle.session_id)["decode_failures"] == 1
    source = owner._screencasts[handle.session_id]
    channel.send.side_effect = RuntimeError("transport unavailable")
    await owner._ack_screencast_frame(source, 43)
    assert owner.screencast_stats(handle.session_id)["ack_failures"] == 1


@pytest.mark.parametrize("revoke", [False, True])
async def test_static_page_initial_frame_is_seeded_with_permission_recheck(revoke):
    handle = BrowserSessionHandle(uuid4(), uuid4(), uuid4())
    original = frame()
    channel = SimpleNamespace(send=AsyncMock(return_value={
        "data": base64.b64encode(original).decode("ascii")}), detach=AsyncMock(), on=Mock())
    session = SimpleNamespace(live_view_changed=asyncio.Event(), page=object(),
        context=SimpleNamespace(new_cdp_session=AsyncMock(return_value=channel)))
    owner = ControllerBrowserOwner(SimpleNamespace(_get_session=lambda **_: session))
    from markettwin_execution_orchestrator.browser.owner import ViewerRejectedError
    owner._screencast_allowed = Mock(side_effect=[None, ViewerRejectedError("Revoked")]
                                    if revoke else None)
    if revoke:
        with pytest.raises(ViewerRejectedError):
            await owner.start_screencast(handle, generation=0)
        assert handle.session_id not in owner._screencasts
    else:
        await owner.start_screencast(handle, generation=0)
        assert await asyncio.wait_for(owner.next_screencast_frame(handle, generation=0), 0.1) == original
        assert [call.args[0] for call in channel.send.await_args_list] == [
            "Page.startScreencast", "Page.captureScreenshot"]


@pytest.mark.parametrize("stage", ["scroll", "box", "move"])
async def test_pointer_stops_when_control_is_revoked_during_move(stage):
    from markettwin_execution_orchestrator.browser.errors import HumanControlActiveError
    session = SimpleNamespace(control_mode="agent", control_generation=0,
        live_click_target=None, live_view_changed=asyncio.Event(),
        page=SimpleNamespace(url=URL, viewport_size={"width": 320, "height": 240}))

    async def revoke(*args, **kwargs):
        session.control_generation += 1
        session.control_mode = "human"

    session.page.mouse = SimpleNamespace(move=AsyncMock(
        side_effect=revoke if stage == "move" else None))
    locator = SimpleNamespace(scroll_into_view_if_needed=AsyncMock(
        side_effect=revoke if stage == "scroll" else None),
        bounding_box=AsyncMock(side_effect=revoke if stage == "box" else None,
            return_value={"x": 40, "y": 60, "width": 80, "height": 60}))
    with pytest.raises(HumanControlActiveError):
        await BrowserController._track_pointer(session, locator)
    assert session.page.mouse.move.await_count == (1 if stage == "move" else 0)
    assert session.live_click_target is None
    assert not session.live_view_changed.is_set()


@pytest.fixture
def fixture_page(tmp_path):
    (tmp_path / "index.html").write_text(
        '<button style="position:absolute;left:40px;top:60px;width:160px;height:40px" '
        'onclick="this.textContent=\'Details shown\'">Show details</button>', encoding="utf-8",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0),
                                partial(SimpleHTTPRequestHandler, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


async def test_screencast_starts_while_agent_action_holds_browser_lock(tmp_path, fixture_page):
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", fixture_page),),
        )
        session = controller._sessions[handle.session_id]
        await controller.navigate(
            session_id=handle.session_id, url=f"http://127.0.0.1:{fixture_page}/index.html",
        )
        owner = ControllerBrowserOwner(controller)
        async with session.lock:
            await owner.start_screencast(handle, generation=session.control_generation)
            shown = await owner.next_screencast_frame(
                handle, generation=session.control_generation,
            )
        assert shown.startswith(b"\xff\xd8")
        await owner.stop_screencast(handle)


async def test_real_click_moves_cursor_to_resolved_control_and_it_persists(tmp_path, fixture_page):
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", fixture_page),),
        )
        session = controller._sessions[handle.session_id]
        await controller.navigate(
            session_id=handle.session_id, url=f"http://127.0.0.1:{fixture_page}/index.html",
        )
        await controller.click(session_id=handle.session_id, role="button", name="Show details")
        target = session.live_click_target
        assert target is not None
        assert (target.x, target.y) == (120, 80)
        assert await session.page.get_by_role("button", name="Details shown").count() == 1
        await controller.get_state(session_id=handle.session_id)
        assert session.live_click_target == target
