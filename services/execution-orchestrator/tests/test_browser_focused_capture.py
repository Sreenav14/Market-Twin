"""Real-browser regression for focused evidence below the viewport."""

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserActionError
from PIL import Image


async def test_focused_capture_scrolls_to_rendered_element(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        '<div style="height:2000px">Top of page</div>'
        '<h2 style="background:rgb(0,255,0)">Profile destination</h2>'
        '<h2 hidden>Hidden destination</h2>',
        encoding="utf-8",
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path)),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        async with BrowserController(artifact_root=tmp_path / "artifacts") as controller:
            handle = await controller.create_session(
                execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
                allowed_origins=(AllowedOrigin("http", "127.0.0.1", server.server_port),),
            )
            await controller.navigate(
                session_id=handle.session_id,
                url=f"http://127.0.0.1:{server.server_port}/index.html",
            )
            result = await controller.capture_element(
                session_id=handle.session_id, role="heading", name="Profile destination",
            )
            assert result.observation.scroll_y > 0
            assert result.observation.screenshot_path is not None
            assert result.observation.focused_screenshot_path is not None
            with Image.open(result.observation.screenshot_path) as viewport:
                assert viewport.height == result.observation.viewport_height
            with Image.open(result.observation.focused_screenshot_path) as crop:
                assert any(color == (0, 255, 0) for _, color in crop.convert("RGB").getcolors(
                    maxcolors=crop.width * crop.height,
                ) or [])
            with pytest.raises(BrowserActionError):
                await controller.capture_element(
                    session_id=handle.session_id, text="Hidden destination",
                )
    finally:
        server.shutdown()
        server.server_close()
