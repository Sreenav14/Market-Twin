"""Synthetic checks for explicit, read-only authenticated role verification."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from markettwin_execution_orchestrator.browser.auth_verifier import (
    AuthVerificationPolicy,
    verify_authenticated_role,
)
from playwright.async_api import async_playwright


def fixture_server(body: str) -> tuple[ThreadingHTTPServer, Thread, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            encoded = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, f"http://{host}:{port}"

@pytest.mark.asyncio
async def test_only_exact_approved_origin_and_role_marker_verifies() -> None:
    server, thread, origin = fixture_server(
        '<main><p id="identity">Signed in as user</p></main>',
    )
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            page.set_default_timeout(2000)
            await page.goto(f"{origin}/dashboard")
            policy = AuthVerificationPolicy(
                origin=origin,
                marker_selector="#identity",
                expected_marker="Signed in as user",
                role="user",
                account_reference="fixture-user",
            )
            assert page.url == f"{origin}/dashboard"
            assert await page.locator("#identity").inner_text() == "Signed in as user"
            principal = await verify_authenticated_role(
                page=page,
                policy=policy,
                allowed_origins=frozenset({origin}),
            )
            assert principal is not None
            assert principal.role == "user"
            assert principal.account_reference == "fixture-user"
            assert await verify_authenticated_role(
                page=page,
                policy=policy,
                allowed_origins=frozenset({"http://other.test"}),
            ) is None
        finally:
            await browser.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        '<p id="identity">Signed in as admin</p>',
        '<p id="identity">Signed in as user</p><p id="identity">Signed in as user</p>',
        '<p id="identity">Signed in as user</p><input type="password">',
        '<p id="identity">Signed in as user</p><input autocomplete="one-time-code">',
    ],
)
async def test_wrong_or_ambiguous_identity_marker_fails_closed(body: str) -> None:
    server, thread, origin = fixture_server(body)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            page.set_default_timeout(2000)
            await page.goto(f"{origin}/dashboard")
            policy = AuthVerificationPolicy(
                origin=origin,
                marker_selector="#identity",
                expected_marker="Signed in as user",
                role="user",
                account_reference="fixture-user",
            )
            assert await verify_authenticated_role(
                page=page,
                policy=policy,
                allowed_origins=frozenset({origin}),
            ) is None
        finally:
            await browser.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
