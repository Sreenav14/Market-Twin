"""Real-browser ground truth for controlled benchmark destination pages."""

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController


@pytest.mark.parametrize("link,heading", [
    ("Open help guide", "Help guide"),
    ("Open billing settings", "Profile settings"),
])
async def test_benchmark_navigation_renders_actual_destination(
    tmp_path: Path, link: str, heading: str,
) -> None:
    fixture = Path(__file__).parent / "fixtures/v1_benchmark"
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(fixture)),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        async with BrowserController(artifact_root=tmp_path) as controller:
            handle = await controller.create_session(
                execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
                allowed_origins=(AllowedOrigin("http", "127.0.0.1", server.server_port),),
            )
            await controller.navigate(
                session_id=handle.session_id,
                url=f"http://127.0.0.1:{server.server_port}/index.html",
            )
            result = await controller.click(session_id=handle.session_id, role="link", name=link)
            visible_headings = [item.name for item in result.observation.visible_elements
                                if item.role == "heading"]
            assert visible_headings == [heading]
            capture = await controller.capture_element(
                session_id=handle.session_id, role="heading", name=heading,
            )
            assert capture.observation.focused_screenshot_path is not None
    finally:
        server.shutdown()
        server.server_close()
