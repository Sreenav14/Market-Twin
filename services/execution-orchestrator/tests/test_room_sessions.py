"""U-P2: the Room — one browser per run, borrowed by items, proof
contexts inside the same Chromium (real browser, local fixture)."""

import threading
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest

from markettwin_execution_orchestrator.browser import (
    AllowedOrigin,
    BrowserController,
)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def fixture_origin() -> Iterator[tuple[str, int]]:
    directory = Path(__file__).parent / "fixtures/hitl_app"
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(directory))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


async def test_room_is_shared_rebound_and_proof_is_a_fresh_context(
    fixture_origin: tuple[str, int], tmp_path: Path,
) -> None:
    origin, port = fixture_origin
    run_id = uuid4()
    async with BrowserController(artifact_root=tmp_path / "artifacts") as controller:
        room = await controller.open_room_session(
            run_id=run_id,
            execution_id=uuid4(), journey_id=uuid4(),
            network_policy="local_development",
            allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
            authenticated_session=True,
        )
        await controller.navigate(session_id=room.session_id, url=f"{origin}/")
        room_session = controller._sessions[room.session_id]
        await room_session.context.add_cookies([{
            "name": "mt_room_cookie", "value": "1",
            "url": f"{origin}/",
        }])

        # Borrow: rebind to an item execution; ownership follows.
        item_execution, item_journey = uuid4(), uuid4()
        borrowed = await controller.rebind_session(
            session_id=room.session_id,
            execution_id=item_execution, journey_id=item_journey,
        )
        assert borrowed.session_id == room.session_id
        assert controller._sessions[room.session_id].execution_id == item_execution
        state = await controller.get_state(
            session_id=room.session_id,
            execution_id=item_execution, journey_id=item_journey,
        )
        assert state is not None

        # Proof: fresh context, SAME Chromium, seeded storage state.
        proof = await controller.create_proof_session(
            room_session_id=room.session_id,
            execution_id=uuid4(), journey_id=uuid4(),
        )
        proof_session = controller._sessions[proof.session_id]
        assert proof_session.browser is room_session.browser
        assert proof_session.context is not room_session.context
        cookie_names = {
            c["name"] for c in await proof_session.context.cookies()
        }
        assert "mt_room_cookie" in cookie_names

        # Closing the proof context leaves the Room fully usable.
        await controller.close_session(session_id=proof.session_id)
        assert proof.session_id not in controller._sessions
        await controller.navigate(
            session_id=room.session_id, url=f"{origin}/",
            execution_id=item_execution, journey_id=item_journey,
        )

        assert controller.room_handle(run_id) is not None
        await controller.close_room(run_id=run_id)
        assert controller.room_handle(run_id) is None
        assert room.session_id not in controller._sessions
