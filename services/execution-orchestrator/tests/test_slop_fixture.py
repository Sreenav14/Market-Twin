"""U-P6 gate: a seeded slop+JS app and a clean control page, driven
through the real slop executor with a real browser.

The slop page must be caught: placeholder text + broken media as
slop, and each of the three JS error kinds exactly once (deduped).
The clean page must be acquitted in every family.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from markettwin_database.models import TestRun
from markettwin_execution_orchestrator.browser.contracts import AllowedOrigin
from markettwin_execution_orchestrator.workflow import slop_run

SLOP_PAGE = """
<!doctype html><html lang="en"><head><title>Sloppy</title></head>
<body>
  <h1>Welcome to our platform — unlock the power of seamless experience</h1>
  <p>Lorem ipsum dolor sit amet, this text goes here.</p>
  <img src="/missing-badge.png" alt="Trust badge" width="120" height="24">
  <a href="/clean">See the clean page</a>
  <button>Get started</button>
  <script>
    console.error('Chunk load failed for settings');
    setTimeout(() => { throw new Error('Kaboom uncaught'); }, 50);
    setTimeout(() => { Promise.reject(new Error('async went wrong')); }, 80);
  </script>
</body></html>
"""

CLEAN_WORDS = " ".join(
    f"Detail{i} explains exactly what this setting does and when to use it."
    for i in range(12)
)

CLEAN_PAGE = f"""
<!doctype html><html lang="en"><head><title>Clean settings</title></head>
<body>
  <h1>Notification settings</h1>
  <p>{CLEAN_WORDS}</p>
  <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8Xw8AAwMCAO+ip1sAAAAASUVORK5CYII=" alt="Status dot" width="8" height="8">
  <button>Save notification settings</button>
</body></html>
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = CLEAN_PAGE if self.path.startswith("/clean") else SLOP_PAGE
        payload = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.mark.asyncio
async def test_seeded_slop_and_js_fixture(monkeypatch) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    published: list[dict] = []

    class _Events:
        def __init__(self, session):
            pass

        async def create(self, **kwargs):
            published.append(kwargs["payload"])

    completed: list[bool] = []

    class _States:
        def __init__(self, session):
            pass

        async def mark_running(self, **kwargs):
            return None

        async def mark_completed(self, **kwargs):
            completed.append(True)

    monkeypatch.setattr(slop_run, "RunEventRepository", _Events)
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.persistence.run_state_repository.RunStateRepository",
        _States,
    )
    monkeypatch.setattr(
        slop_run, "ExecutionRepository",
        lambda _: Mock(
            create_agent_execution=AsyncMock(),
            create_browser_session=AsyncMock(),
            mark_browser_session_closed=AsyncMock(),
            finish_agent_execution=AsyncMock(),
        ),
    )
    run_id = uuid4()
    run = TestRun(id=run_id)
    session = Mock()
    session.get = AsyncMock(return_value=run)
    session.commit = AsyncMock()
    request = SimpleNamespace(
        run_id=run_id,
        start_url=f"http://127.0.0.1:{port}/",
        allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        network_policy="local_development",
    )
    try:
        await slop_run.execute_slop_run(request=request, session=session)
    finally:
        server.shutdown()
    # Audit fix (D1): the executor marks its own run completed.
    assert completed == [True]
    by_url = {state["url"]: state for state in published}
    slop_state = by_url[f"http://127.0.0.1:{port}/"]
    clean_state = by_url[f"http://127.0.0.1:{port}/clean"]

    # Each JS kind caught exactly once (console error reproduces on
    # the executor's re-visit, so it is serious there).
    js_rules = {e["rule_id"]: e for e in slop_state["js_errors"]}
    assert set(js_rules) == {
        "DEF_JS_UNCAUGHT", "DEF_JS_CONSOLE_ERROR", "DEF_JS_UNHANDLED_REJECTION",
    }
    assert js_rules["DEF_JS_UNCAUGHT"]["count"] == 1
    assert js_rules["DEF_JS_UNHANDLED_REJECTION"]["count"] == 1
    assert js_rules["DEF_JS_CONSOLE_ERROR"]["severity"] == "serious"
    # Slop verdicts on the slop page: placeholder + broken media.
    fired = {
        rule["rule_id"]
        for element in slop_state["elements"]
        for rule in element["rules_fired"]
    }
    assert "SLOP_PLACEHOLDER_TEXT" in fired
    assert "SLOP_BROKEN_MEDIA" in fired
    assert any(e["verdict"] == "slop" for e in slop_state["elements"])
    # The clean control is acquitted everywhere.
    assert clean_state["js_errors"] == []
    assert all(e["verdict"] == "clean" for e in clean_state["elements"])
    assert clean_state["page_signals"] == []
