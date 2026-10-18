"""Real Chromium regression for shared persona/feature authentication boundaries.

The human callback is synthetic here; durable lease/request behavior is covered
by workflow and database handoff tests, not simulated as an integrated broker.
"""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserPolicyError
from markettwin_shared.auth_verification import AuthVerificationPolicy


@pytest.mark.parametrize("wrong_identity", [False, True])
async def test_optional_login_is_shared_and_does_not_replay_navigation(tmp_path, wrong_identity):
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            body = (
                '<h1>Public</h1><a href="/login">Log in</a>' if self.path == "/" else
                '<h1>Sign in</h1><input type="password" value="secret-canary">'
                if self.path == "/login" else
                '<p id="identity">' + ("wrong" if wrong_identity else "member") + '</p>'
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    policy = AuthVerificationPolicy(origin=origin, marker_selector="#identity",
                                    expected_marker="member", role="member",
                                    account_reference="synthetic-member")
    requests = []
    try:
        async with BrowserController(artifact_root=tmp_path) as controller:
            handle = await controller.create_session(
                execution_id=uuid4(), journey_id=uuid4(),
                allowed_origins=(AllowedOrigin(scheme="http", hostname="127.0.0.1",
                                               port=server.server_port),),
                network_policy="local_development", authenticated_session=True,
            )
            session = controller._sessions[handle.session_id]

            async def human_login():
                requests.append(handle.session_id)
                # Taking the owner/verifier lock must work: callback cannot hold it.
                await controller.begin_human_control(
                    session_id=handle.session_id,
                )
                await session.page.goto(origin + "/dashboard")
                session.control_mode = "verifying"
                principal = await controller.verify_authenticated_role(handle=handle, policy=policy)
                if principal is None:
                    session.control_mode = "none"
                    raise BrowserPolicyError("Identity verification failed.")
                await controller.end_human_control(
                    session_id=handle.session_id, verified=True, safe_to_capture=True,
                )

            controller.bind_authentication_handler(handle, human_login)
            await controller.navigate(session_id=handle.session_id, url=origin + "/")
            assert requests == []  # optional public browsing does not prompt
            if wrong_identity:
                with pytest.raises(BrowserPolicyError, match="Identity verification failed"):
                    await controller.click(session_id=handle.session_id, role="link", name="Log in")
                assert session.control_mode != "agent"
            else:
                result = await controller.click(
                    session_id=handle.session_id, role="link", name="Log in",
                )
                assert result.observation.url == origin + "/dashboard"
                assert session.control_mode == "agent"
            assert requests == [handle.session_id]
            assert hits.count("/login") == 1
            if wrong_identity:
                assert not list(tmp_path.rglob("*click.png"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


async def test_forced_handoff_serializes_concurrent_browser_tools(tmp_path):
    """No tool may dispatch while a forced IdP handoff is being persisted."""
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(),
            allowed_origins=(AllowedOrigin(scheme="http", hostname="127.0.0.1", port=5191),),
            network_policy="local_development", authenticated_session=True,
        )
        session = controller._sessions[handle.session_id]
        await session.page.route("http://127.0.0.1:5191/**", lambda route: route.fulfill(
            body=('<button type="button" onclick="this.textContent=\'Dispatched\'">'
                  'Inspect details</button>'),
        ))
        await session.page.goto("http://127.0.0.1:5191/")
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def human_login():
            calls.append(handle.session_id)
            entered.set()
            await release.wait()  # durable-request creation before taking browser control
            await controller.begin_human_control(session_id=handle.session_id)
            await controller.end_human_control(
                session_id=handle.session_id, verified=True, safe_to_capture=True,
            )

        controller.bind_authentication_handler(handle, human_login)

        async def forced_checkpoint():
            async with session.lock:
                await controller._authentication_checkpoint(session, lock_held=True, force=True)

        handoff = asyncio.create_task(forced_checkpoint())
        await asyncio.wait_for(entered.wait(), timeout=5)
        click = asyncio.create_task(controller.click(
            session_id=handle.session_id, role="button", name="Inspect details",
        ))
        try:
            await asyncio.sleep(0.1)
            assert not click.done()
            assert await session.page.get_by_role("button").inner_text() == "Inspect details"
            assert handle.session_id in controller._pending_authentication
        finally:
            release.set()
            await asyncio.wait_for(asyncio.gather(handoff, click), timeout=10)
        assert calls == [handle.session_id]
        assert await session.page.get_by_role("button").inner_text() == "Dispatched"

