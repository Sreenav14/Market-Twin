"""Real-browser regression for a link blocked before navigation."""

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserPolicyError


async def test_outside_origin_link_raises_policy_error_before_click(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        '<a href="http://127.0.0.1:1/restricted">Open restricted destination</a>',
        encoding="utf-8",
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path)),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_port
    try:
        async with BrowserController(artifact_root=tmp_path / "artifacts") as controller:
            handle = await controller.create_session(
                execution_id=uuid4(), journey_id=uuid4(), network_policy="local_development",
                allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
            )
            await controller.navigate(
                session_id=handle.session_id, url=f"http://127.0.0.1:{port}/index.html",
            )
            with pytest.raises(BrowserPolicyError):
                await controller.click(
                    session_id=handle.session_id, role="link", name="Open restricted destination",
                )
            state = await controller.get_state(session_id=handle.session_id)
            assert state.observation.url == f"http://127.0.0.1:{port}/index.html"
    finally:
        server.shutdown()
        server.server_close()
