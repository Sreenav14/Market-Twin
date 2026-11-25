from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import controller as controller_module
from markettwin_execution_orchestrator.browser.contracts import AllowedOrigin
from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.errors import TargetUrlValidationError
from markettwin_execution_orchestrator.browser.policy import (
    validate_captcha_subresource,
    validate_target_url,
    validate_websocket_url,
)

EXACT = (
    AllowedOrigin(
        scheme="https",
        hostname="example.com",
        port=None,
        include_subdomains=False,
    ),
)


def test_allows_exact_approved_origin() -> None:
    result = validate_target_url("https://example.com/path", EXACT, "public_only")
    assert result.hostname == "example.com"
    assert result.href == "https://example.com/path"


def test_blocks_subdomain_when_disabled() -> None:
    with pytest.raises(TargetUrlValidationError):
        validate_target_url("https://www.example.com", EXACT, "public_only")


def test_allows_subdomain_when_enabled() -> None:
    result = validate_target_url(
        "https://www.example.com",
        (
            AllowedOrigin(
                scheme="https",
                hostname="example.com",
                include_subdomains=True,
            ),
        ),
        "public_only",
    )
    assert result.hostname == "www.example.com"


def test_blocks_domain_suffix_attack() -> None:
    with pytest.raises(TargetUrlValidationError):
        validate_target_url(
            "https://evil-example.com",
            (AllowedOrigin("https", "example.com", None, True),),
            "public_only",
        )


def test_blocks_different_scheme() -> None:
    with pytest.raises(TargetUrlValidationError, match="not allowed"):
        validate_target_url("http://example.com", EXACT, "public_only")


def test_blocks_unapproved_port() -> None:
    with pytest.raises(TargetUrlValidationError, match="not allowed"):
        validate_target_url("https://example.com:8443", EXACT, "public_only")


def test_allows_approved_non_default_port() -> None:
    result = validate_target_url(
        "https://example.com:8443",
        (AllowedOrigin("https", "example.com", 8443, False),),
        "public_only",
    )
    assert result.port == 8443


def test_normalizes_default_port() -> None:
    result = validate_target_url("https://example.com:443/x", EXACT, "public_only")
    assert result.port is None
    assert result.href == "https://example.com/x"


def test_blocks_outside_domain() -> None:
    with pytest.raises(TargetUrlValidationError):
        validate_target_url("https://example.org", EXACT, "public_only")


def test_blocks_unsupported_protocol() -> None:
    with pytest.raises(TargetUrlValidationError, match="HTTP and HTTPS"):
        validate_target_url("file:///secret.txt", EXACT, "public_only")


def test_blocks_embedded_credentials() -> None:
    with pytest.raises(TargetUrlValidationError, match="Credentials"):
        validate_target_url("https://user:password@example.com", EXACT, "public_only")


def test_blocks_localhost_public() -> None:
    origins = (AllowedOrigin("http", "localhost", 3000, False),)
    with pytest.raises(TargetUrlValidationError, match="local development"):
        validate_target_url("http://localhost:3000", origins, "public_only")


def test_allows_localhost_local_development() -> None:
    origins = (AllowedOrigin("http", "localhost", 3000, False),)
    result = validate_target_url("http://localhost:3000", origins, "local_development")
    assert result.hostname == "localhost"


def test_blocks_private_ipv4_even_local_development() -> None:
    origins = (AllowedOrigin("http", "192.168.1.5", None, False),)
    with pytest.raises(TargetUrlValidationError, match="non-global"):
        validate_target_url("http://192.168.1.5", origins, "local_development")


def test_blocks_cloud_metadata_address() -> None:
    origins = (AllowedOrigin("http", "169.254.169.254", None, False),)
    with pytest.raises(TargetUrlValidationError):
        validate_target_url(
            "http://169.254.169.254/latest/meta-data",
            origins,
            "local_development",
        )


def test_allows_ipv6_loopback_only_local_development() -> None:
    origins = (AllowedOrigin("http", "::1", 8000, False),)
    result = validate_target_url("http://[::1]:8000", origins, "local_development")
    assert result.hostname == "::1"


def test_blocks_direct_public_ipv6() -> None:
    origins = (AllowedOrigin("https", "2606:4700:4700::1111", None, False),)
    with pytest.raises(TargetUrlValidationError, match="Direct IPv6"):
        validate_target_url(
            "https://[2606:4700:4700::1111]",
            origins,
            "public_only",
        )


def test_idna_and_trailing_dot_are_normalized() -> None:
    result = validate_target_url("https://EXAMPLE.com./path", EXACT, "public_only")
    assert result.hostname == "example.com"


def test_websocket_uses_corresponding_https_origin() -> None:
    result = validate_websocket_url("wss://example.com/socket", EXACT, "public_only")
    assert result.hostname == "example.com"
    assert result.scheme == "https"


def test_websocket_outside_allowlist_is_blocked() -> None:
    with pytest.raises(TargetUrlValidationError):
        validate_websocket_url("wss://evil.example/socket", EXACT, "public_only")


def test_allows_recaptcha_widget_assets() -> None:
    script = validate_captcha_subresource("https://www.google.com/recaptcha/api.js")
    frame = validate_captcha_subresource(
        "https://www.google.com/recaptcha/api2/anchor?k=site"
    )
    asset = validate_captcha_subresource(
        "https://www.gstatic.com/recaptcha/releases/abc/recaptcha__en.js"
    )
    assert script.hostname == "www.google.com"
    assert frame.origin == "https://www.google.com"
    assert asset.hostname == "www.gstatic.com"


def test_blocks_captcha_host_outside_the_widget_path() -> None:
    with pytest.raises(TargetUrlValidationError, match="not a captcha provider"):
        validate_captcha_subresource("https://www.google.com/")
    with pytest.raises(TargetUrlValidationError, match="not a captcha provider"):
        validate_captcha_subresource("https://www.google.com/search?q=klaviyo")
    with pytest.raises(TargetUrlValidationError, match="HTTPS"):
        validate_captcha_subresource("http://www.google.com/recaptcha/api.js")
    with pytest.raises(TargetUrlValidationError, match="not a captcha provider"):
        validate_captcha_subresource("https://www.google.com.evil.test/recaptcha/api.js")
    with pytest.raises(TargetUrlValidationError, match="standard HTTPS port"):
        validate_captcha_subresource("https://www.google.com:8443/recaptcha/api.js")


def test_allows_other_public_captcha_widgets() -> None:
    hcaptcha = validate_captcha_subresource("https://js.hcaptcha.com/1/api.js")
    turnstile = validate_captcha_subresource(
        "https://challenges.cloudflare.com/turnstile/v0/api.js"
    )
    challenge = validate_captcha_subresource(
        "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/flexible"
    )
    assert hcaptcha.hostname == "js.hcaptcha.com"
    assert turnstile.hostname == "challenges.cloudflare.com"
    assert challenge.hostname == "challenges.cloudflare.com"
    with pytest.raises(TargetUrlValidationError):
        validate_captcha_subresource("https://challenges.cloudflare.com/cdn-cgi/trace")


class _Frame:
    def __init__(self, parent: _Frame | None) -> None:
        self.parent_frame = parent


class _Request:
    def __init__(
        self, url: str, *, navigation: bool = False, main: bool = True,
        method: str = "GET", post_data: str | None = None,
    ) -> None:
        self.url = url
        self.method = method
        self.post_data = post_data
        self._navigation = navigation
        self.frame = _Frame(None if main else _Frame(None))

    def is_navigation_request(self) -> bool:
        return self._navigation


class _Route:
    def __init__(self, request: _Request) -> None:
        self.request = request
        self.continued = False
        self.aborted: str | None = None

    async def continue_(self) -> None:
        self.continued = True

    async def abort(self, error_code: str) -> None:
        self.aborted = error_code


def _session() -> SimpleNamespace:
    return SimpleNamespace(
        control_mode="agent",
        allowed_origins=(AllowedOrigin("https", "www.klaviyo.com"),),
        network_policy="public_only",
        session_id=uuid4(),
        offsite=None,
        is_auth_only_url=lambda _url: False,
    )


async def test_page_can_load_recaptcha_inside_the_target(monkeypatch: pytest.MonkeyPatch) -> None:
    resolved: list[str] = []

    async def allow(hostname: str, _policy: str) -> tuple[()]:
        resolved.append(hostname)
        return ()

    monkeypatch.setattr(controller_module, "resolve_and_validate_host", allow)
    route = _Route(_Request(
        "https://www.google.com/recaptcha/api2/anchor?k=site",
        navigation=True,
        main=False,
    ))
    await BrowserController()._route_request(_session(), route)  # type: ignore[arg-type]
    assert route.continued
    assert route.aborted is None
    assert resolved == ["www.google.com"]


async def test_main_frame_cannot_open_the_captcha_host(monkeypatch: pytest.MonkeyPatch) -> None:
    resolved: list[str] = []

    async def allow(hostname: str, _policy: str) -> tuple[()]:
        resolved.append(hostname)
        return ()

    monkeypatch.setattr(controller_module, "resolve_and_validate_host", allow)
    route = _Route(_Request(
        "https://www.google.com/recaptcha/api.js",
        navigation=True,
        main=True,
    ))
    await BrowserController()._route_request(_session(), route)  # type: ignore[arg-type]
    assert route.aborted == "blockedbyclient"
    assert not route.continued
    assert resolved == []


def _route_session() -> SimpleNamespace:
    """A session with no offsite policy installed (the default route path)."""
    return SimpleNamespace(
        control_mode="agent",
        allowed_origins=(AllowedOrigin("https", "www.klaviyo.com"),),
        network_policy="public_only",
        session_id=uuid4(),
        offsite=None,
        page=SimpleNamespace(url="https://www.klaviyo.com/"),
        journey_id=uuid4(),
        execution_id=uuid4(),
        is_auth_only_url=lambda _url: False,
    )


def _recording_resolver(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    resolved: list[tuple[str, str]] = []

    async def allow(hostname: str, policy: str) -> tuple[()]:
        resolved.append((hostname, policy))
        return ()

    monkeypatch.setattr(controller_module, "resolve_and_validate_host", allow)
    return resolved


async def test_third_party_assets_load_freely(monkeypatch: pytest.MonkeyPatch) -> None:
    # Guarded freedom (owner decision, 2026-11-13): a page may load its
    # design files, scripts and images from any public host, so the test
    # browser renders what an end user sees.
    resolved = _recording_resolver(monkeypatch)
    route = _Route(_Request("https://cdn.evil.test/widget.js"))
    await BrowserController()._route_request(_route_session(), route)  # type: ignore[arg-type]
    assert route.continued
    assert route.aborted is None
    assert resolved == [("cdn.evil.test", "public_only")]


async def test_third_party_submissions_without_sensitive_data_continue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Owner rule (2026-11-24): a cross-origin submission is free unless
    # it carries sensitive data off the target's origin. This replaces
    # the earlier blanket "outside submissions stay blocked" rule.
    resolved = _recording_resolver(monkeypatch)
    route = _Route(_Request(
        "https://api.other.test/collect", method="POST",
        post_data="event=page_view&count=3",
    ))
    await BrowserController()._route_request(_route_session(), route)  # type: ignore[arg-type]
    assert route.continued
    assert route.aborted is None
    assert resolved == [("api.other.test", "public_only")]


async def test_recaptcha_token_posts_can_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    # The widget's token calls are POSTs (api2/reload fetches the
    # challenge, api2/userverify verifies the response). The old method
    # gate aborted both, so no page could ever produce a token.
    resolved = _recording_resolver(monkeypatch)
    controller = BrowserController()
    session = _route_session()
    reload_route = _Route(_Request(
        "https://www.google.com/recaptcha/api2/reload?k=site", method="POST",
        post_data="v=abc&k=site&c=token&reason=q",
    ))
    await controller._route_request(session, reload_route)  # type: ignore[arg-type]
    assert reload_route.continued
    assert reload_route.aborted is None
    verify_route = _Route(_Request(
        "https://www.google.com/recaptcha/api2/userverify?k=site", method="POST",
        post_data="response=token",
    ))
    await controller._route_request(session, verify_route)  # type: ignore[arg-type]
    assert verify_route.continued
    assert verify_route.aborted is None
    assert resolved == [("www.google.com", "public_only")] * 2


async def test_cross_origin_post_with_password_field_is_blocked_and_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A send carrying a credential field off the target's origin is the
    # suspicious case: blocked, and the block lands on the Lead-review
    # surface with its reason (the class only, never the value).
    from unittest.mock import AsyncMock

    resolved = _recording_resolver(monkeypatch)
    record = AsyncMock()
    session = _route_session()
    session.offsite = SimpleNamespace(
        checkpoint=AsyncMock(), record=record, subresource_hosts=set(),
    )
    route = _Route(_Request(
        "https://api.other.test/collect", method="POST",
        post_data="user=a&password=hunter2",
    ))
    await BrowserController()._route_request(session, route)  # type: ignore[arg-type]
    assert route.aborted == "blockedbyclient"
    assert not route.continued
    assert resolved == []
    blocked = [
        call for call in record.await_args_list
        if call.args[0] == "browser.egress_blocked"
    ]
    assert len(blocked) == 1
    payload = blocked[0].args[1]
    assert payload["decision"] == "blocked"
    assert payload["reason"] == "sensitive_field:password"
    assert "hunter2" not in str(payload)


async def test_cross_origin_post_with_card_value_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = _recording_resolver(monkeypatch)
    route = _Route(_Request(
        "https://api.other.test/collect", method="POST",
        post_data="note=thanks&card=4242 4242 4242 4242",
    ))
    await BrowserController()._route_request(_route_session(), route)  # type: ignore[arg-type]
    assert route.aborted == "blockedbyclient"
    assert not route.continued
    assert resolved == []


async def test_private_address_submissions_stay_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # G1 has no exceptions: a send toward an internal address is refused
    # by the location rules before any submission scan runs.
    resolved = _recording_resolver(monkeypatch)
    route = _Route(_Request(
        "https://192.168.1.10/collect", method="POST", post_data="event=x",
    ))
    await BrowserController()._route_request(_route_session(), route)  # type: ignore[arg-type]
    assert route.aborted == "blockedbyclient"
    assert not route.continued
    assert resolved == []


async def test_third_party_domains_are_recorded_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Every newly-seen third-party host a page talks to lands on the
    # Lead-review surface exactly once per run.
    from unittest.mock import AsyncMock

    _recording_resolver(monkeypatch)
    record = AsyncMock()
    session = _route_session()
    session.offsite = SimpleNamespace(
        checkpoint=AsyncMock(), record=record, subresource_hosts=set(),
    )
    controller = BrowserController()
    for url in (
        "https://cdn.evil.test/widget.js",
        "https://cdn.evil.test/other.js",
        "https://www.google.com/recaptcha/api.js",
    ):
        route = _Route(_Request(url))
        await controller._route_request(session, route)  # type: ignore[arg-type]
        assert route.continued
    domains = [
        call.args[1]["host"] for call in record.await_args_list
        if call.args[0] == "browser.third_party_domain"
    ]
    assert domains == ["cdn.evil.test", "www.google.com"]


@pytest.mark.parametrize(("method", "kind", "navigation", "host", "allowed"), [
    ("GET", "script", False, "cdn.example.com", True),
    ("GET", "font", False, "cdn.example.com", True),
    ("GET", "stylesheet", False, "cdn.example.com", True),
    ("GET", "document", True, "cdn.example.com", False),
    ("POST", "fetch", False, "cdn.example.com", False),
    ("GET", "script", False, "127.0.0.1", False),
])
async def test_human_target_page_can_load_public_ui_dependencies(
    monkeypatch: pytest.MonkeyPatch, method: str, kind: str, navigation: bool,
    host: str, allowed: bool,
) -> None:
    from markettwin_execution_orchestrator.browser.network_diagnostics import HumanNetworkDiagnostics

    _recording_resolver(monkeypatch)
    session = _route_session()
    session.control_mode = "human"
    session.offsite = SimpleNamespace()
    session.human_network_diagnostics = HumanNetworkDiagnostics()
    request = _Request(f"https://{host}/asset", method=method, navigation=navigation)
    request.resource_type = kind
    route = _Route(request)
    await BrowserController()._route_request(session, route)  # type: ignore[arg-type]
    assert route.continued is allowed


async def test_private_address_assets_stay_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    # A public-looking page may never pull the browser toward an internal
    # address; the location rules approve no private or loopback host.
    resolved = _recording_resolver(monkeypatch)
    route = _Route(_Request("https://192.168.1.10/x.js"))
    await BrowserController()._route_request(_route_session(), route)  # type: ignore[arg-type]
    assert route.aborted == "blockedbyclient"
    assert not route.continued
    assert resolved == []


async def test_provider_assets_stay_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    # Sign-in/CAPTCHA provider hosts serve the human handoff, never the
    # agent's page loads (captcha widget assets keep their own exception).
    resolved = _recording_resolver(monkeypatch)
    route = _Route(_Request("https://accounts.google.com/x.png"))
    await BrowserController()._route_request(_route_session(), route)  # type: ignore[arg-type]
    assert route.aborted == "blockedbyclient"
    assert not route.continued
    assert resolved == []


async def test_target_origin_posts_still_work(monkeypatch: pytest.MonkeyPatch) -> None:
    # The target's own forms are the product working, not data leaving it:
    # same-origin submissions keep today's strict validation and pass.
    resolved = _recording_resolver(monkeypatch)
    route = _Route(_Request("https://www.klaviyo.com/submit", method="POST"))
    await BrowserController()._route_request(_route_session(), route)  # type: ignore[arg-type]
    assert route.continued
    assert route.aborted is None
    assert resolved == [("www.klaviyo.com", "public_only")]


def test_blocks_localhost_localdomain_public() -> None:
    origins = (AllowedOrigin("http", "localhost.localdomain", 3000, False),)
    with pytest.raises(TargetUrlValidationError, match="local development"):
        validate_target_url(
            "http://localhost.localdomain:3000",
            origins,
            "public_only",
        )
