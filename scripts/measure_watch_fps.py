"""Measure the live Watch stream's real frames per second (U-P3-04).

Stands up the whole observer path in-process — a real Chromium on an
animated page, the CDP screencast owner, the viewer gateway behind a
local uvicorn, a real observer ticket and a real WebSocket client —
and counts binary frames for N seconds (default 30).

Gate: sustained >= 10 fps while the page is animating.

Run: .venv/bin/python scripts/measure_watch_fps.py [--seconds 30]
Exit code 0 when the gate passes, 1 otherwise.
"""

import argparse
import asyncio
import json
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/execution-orchestrator/src"))

import uvicorn
from fastapi import FastAPI
from websockets.asyncio.client import connect

from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.browser.owner import ControllerBrowserOwner
from markettwin_execution_orchestrator.browser.viewer_gateway import (
    ObserverLease,
    ViewerGateway,
)

ANIMATED_PAGE = """<!doctype html>
<title>fps fixture</title>
<div id="box" style="width:60px;height:60px;background:#0E7490;position:absolute"></div>
<div id="n">0</div>
<script>
let x = 0;
function tick() {
  x = (x + 3) % 600;
  document.getElementById('box').style.transform = `translate(${x}px, ${x % 200}px)`;
  document.getElementById('n').textContent = String(x);
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
</script>
"""


class PermissiveAuthority:
    def __init__(self, actor_id: UUID) -> None:
        self._actor_id = actor_id

    async def actor(self, session_cookie: str) -> UUID | None:
        return self._actor_id if session_cookie == "measure" else None

    async def observer_permitted(self, actor_id: UUID, handle: BrowserSessionHandle, generation: int) -> bool:
        return actor_id == self._actor_id


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=30.0)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "index.html").write_text(ANIMATED_PAGE)
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=tmp))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        actor_id = uuid4()
        try:
            async with BrowserController(artifact_root=root / "artifacts") as controller:
                handle = await controller.create_session(
                    execution_id=uuid4(), journey_id=uuid4(),
                    network_policy="local_development",
                    allowed_origins=(AllowedOrigin("http", "127.0.0.1", server.server_port),),
                )
                await controller.navigate(session_id=handle.session_id, url=f"{origin}/index.html")
                gateway = ViewerGateway(
                    ControllerBrowserOwner(controller),
                    PermissiveAuthority(actor_id),
                    allowed_origins=frozenset({"http://127.0.0.1"}),
                    allow_local_ws=True,
                )
                app = FastAPI()
                app.include_router(gateway.router)
                config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
                uvicorn_server = uvicorn.Server(config)
                server_task = asyncio.create_task(uvicorn_server.serve())
                while not uvicorn_server.started:
                    await asyncio.sleep(0.05)
                port = uvicorn_server.servers[0].sockets[0].getsockname()[1]
                lease = ObserverLease(
                    handle=handle, actor_id=actor_id, generation=0,
                    expires_at=datetime.now(UTC) + timedelta(minutes=5),
                )
                ticket = await gateway.issue_observer_ticket(actor_id, lease)
                frames = 0
                started = time.monotonic()
                async with connect(
                    f"ws://127.0.0.1:{port}/api/v1/hitl-viewer",
                    origin="http://127.0.0.1",
                    additional_headers={"Cookie": "markettwin_session=measure"},
                ) as websocket:
                    await websocket.send(json.dumps({"ticket": ticket}))
                    deadline = started + args.seconds
                    while time.monotonic() < deadline:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=2)
                        except TimeoutError:
                            break
                        if isinstance(message, bytes):
                            frames += 1
                elapsed = time.monotonic() - started
                uvicorn_server.should_exit = True
                await asyncio.wait_for(server_task, timeout=10)
        finally:
            server.shutdown()
    fps = frames / max(elapsed, 0.001)
    stats = gateway.observer_stats() if 'gateway' in locals() else {}
    print(f"frames={frames} seconds={elapsed:.1f} fps={fps:.2f} gateway_stats={stats}")
    if fps >= 10:
        print("WATCH FPS GATE: PASS (>= 10 fps sustained)")
        return 0
    print("WATCH FPS GATE: FAIL (< 10 fps)")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
