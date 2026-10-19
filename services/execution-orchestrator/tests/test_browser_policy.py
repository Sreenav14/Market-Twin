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
    assert hcaptcha.hostname == "js.hcaptcha.com"
    assert turnstile.hostname == "challenges.cloudflare.com"
    with pytest.raises(TargetUrlValidationError):
        validate_captcha_subresource("https://challenges.cloudflare.com/cdn-cgi/trace")


class _Frame:
    def __init__(self, parent: _Frame | None) -> None:
        self.parent_frame = parent


class _Request:
    def __init__(self, url: str, *, navigation: bool = False, main: bool = True) -> None:
        self.url = url
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


async def test_other_third_parties_stay_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    resolved: list[str] = []

    async def allow(hostname: str, _policy: str) -> tuple[()]:
        resolved.append(hostname)
        return ()

    monkeypatch.setattr(controller_module, "resolve_and_validate_host", allow)
    route = _Route(_Request("https://cdn.evil.test/widget.js"))
    await BrowserController()._route_request(_session(), route)  # type: ignore[arg-type]
    assert route.aborted == "blockedbyclient"
    assert resolved == []


def test_blocks_localhost_localdomain_public() -> None:
    origins = (AllowedOrigin("http", "localhost.localdomain", 3000, False),)
    with pytest.raises(TargetUrlValidationError, match="local development"):
        validate_target_url(
            "http://localhost.localdomain:3000",
            origins,
            "public_only",
        )
