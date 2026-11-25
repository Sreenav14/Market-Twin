"""Synthetic checks for explicit, read-only authenticated role verification."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import asyncio
from typing import cast

import pytest
from markettwin_execution_orchestrator.browser.auth_verifier import (
    AuthVerificationPolicy,
    has_active_sensitive_challenge,
    inspect_sensitive_challenge,
    verify_authenticated_role,
)
from playwright.async_api import Page, async_playwright


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


class _HangingLocator:
    """A locator whose count() send-wait never returns (MT-000169)."""

    async def count(self) -> int:
        await asyncio.Event().wait()
        return 0


class _HangingPage:
    def locator(self, _selector: str) -> _HangingLocator:
        return _HangingLocator()


class _QuietLocator:
    async def count(self) -> int:
        return 0


class _QuietPage:
    def locator(self, _selector: str) -> _QuietLocator:
        return _QuietLocator()


@pytest.mark.asyncio
async def test_sensitive_challenge_inspection_times_out_as_no_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MT-000169 kept the bound; MT-000237 changed the answer. The
    inspection sat on a locator.count() send-wait that never returned,
    and the stall watchdog killed the run. The inspection must still
    give up within its bound — but a check that cannot complete is
    not a challenge, so it now answers False instead of raising
    BrowserTimeoutError into the navigation that would leave the
    page. The outer wait_for only bounds a regression to hanging."""
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.browser.auth_verifier"
        ".SENSITIVE_CHALLENGE_TIMEOUT_SECONDS",
        0.2,
        raising=False,
    )
    assert await asyncio.wait_for(
        has_active_sensitive_challenge(cast(Page, _HangingPage())),
        timeout=10,
    ) is False


@pytest.mark.asyncio
async def test_sensitive_challenge_inspection_reports_its_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The timeout stays observable on this channel: the checkpoint
    caller records the info signal (rule UI_STATE_UNASSESSED, detail
    "Challenge check timed out; treated as no challenge.") from
    timed_out, so a timed-out inspection must be distinguishable
    from a quiet page — and a quiet page is not a timeout."""
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.browser.auth_verifier"
        ".SENSITIVE_CHALLENGE_TIMEOUT_SECONDS",
        0.2,
        raising=False,
    )
    timed_out = await inspect_sensitive_challenge(cast(Page, _HangingPage()))
    assert timed_out.active is False
    assert timed_out.timed_out is True
    quiet = await inspect_sensitive_challenge(cast(Page, _QuietPage()))
    assert quiet.active is False
    assert quiet.timed_out is False


@pytest.mark.asyncio
async def test_sensitive_challenge_inspection_answers_false_on_a_quiet_page() -> None:
    assert await has_active_sensitive_challenge(cast(Page, _QuietPage())) is False


class _MarkerLocator:
    async def count(self) -> int:
        return 1

    async def is_visible(self) -> bool:
        return True

    async def inner_text(self, timeout: int | None = None) -> str:
        return "Signed in as user"


class _HangingChallengePage:
    """The identity marker is present and exact, but the challenge
    inspection hangs: verification must still fail closed."""

    url = "http://fixture.test/dashboard"

    def locator(self, selector: str) -> object:
        if "password" in selector:
            return _HangingLocator()
        return _MarkerLocator()


@pytest.mark.asyncio
async def test_verify_authenticated_role_fails_closed_when_challenge_check_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fix C preserves this caller's pre-change behaviour: before the
    fix, the timeout raised and the except in verify_authenticated_role
    returned None. A challenge state that could not be read never
    verifies an identity, even with an exact marker on the page."""
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.browser.auth_verifier"
        ".SENSITIVE_CHALLENGE_TIMEOUT_SECONDS",
        0.2,
        raising=False,
    )
    policy = AuthVerificationPolicy(
        origin="http://fixture.test",
        marker_selector="#identity",
        expected_marker="Signed in as user",
        role="user",
        account_reference="fixture-user",
    )
    assert await verify_authenticated_role(
        page=cast(Page, _HangingChallengePage()),
        policy=policy,
        allowed_origins=frozenset({"http://fixture.test"}),
    ) is None
