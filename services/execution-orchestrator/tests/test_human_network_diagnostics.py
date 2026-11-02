"""Synthetic failures expose fixed categories, without credential-bearing payloads."""

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.browser.contracts import AllowedOrigin, ResolvedAddress
from markettwin_execution_orchestrator.browser.egress import PinnedEgressProxy
from markettwin_execution_orchestrator.browser.errors import (
    HostResolutionError,
    TargetUrlValidationError,
    UnsafeDestinationAddressError,
)
from markettwin_execution_orchestrator.browser.network_diagnostics import HumanNetworkDiagnostics
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession
from playwright.async_api import Request, Route, WebSocketRoute


def test_counters_are_bounded_expiring_fixed_labels() -> None:
    now = [0.0]
    buffer = HumanNetworkDiagnostics(clock=lambda: now[0])
    for _ in range(300):
        buffer.record("captcha_resource_denied", "known_provider")
    assert buffer.snapshot() == ({
        "reason": "captcha_resource_denied", "destination": "known_provider", "count": 128,
    },)
    now[0] = 120
    assert buffer.snapshot() == ()
    buffer.record("dns_resolution_failed", "authorized_target")
    buffer.clear()
    assert buffer.snapshot() == ()


@pytest.mark.parametrize(("error", "url", "reason", "destination"), [
    (HostResolutionError("SECRET dns host"), "https://target.invalid/login?password=SECRET",
     "dns_resolution_failed", "authorized_target"),
    (UnsafeDestinationAddressError("SECRET address"), "https://target.invalid/login",
     "unsafe_destination_ip", "authorized_target"),
    (TargetUrlValidationError("SECRET path"), "https://www.google.com/private?token=SECRET",
     "captcha_resource_denied", "known_provider"),
    (TargetUrlValidationError("SECRET origin"), "https://third.invalid/private?token=SECRET",
     "target_origin_denied", "unknown_third_party"),
    (RuntimeError("SECRET transport"), "https://target.invalid/login",
     "browser_transport_failed", "authorized_target"),
])
def test_session_counters_strip_all_error_and_url_material(
    error: Exception, url: str, reason: str, destination: str,
) -> None:
    session = cast(JourneyBrowserSession, SimpleNamespace(
        control_mode="human", network_policy="public_only",
        allowed_origins=(AllowedOrigin("https", "target.invalid", None),),
        human_network_diagnostics=HumanNetworkDiagnostics(),
    ))
    BrowserController._record_network_failure(session, error, url)
    assert session.human_network_diagnostics.snapshot() == ({
        "reason": reason, "destination": destination, "count": 1,
    },)
    session.control_mode = "agent"
    BrowserController._record_network_failure(session, error, url)
    assert session.human_network_diagnostics.snapshot()[0]["count"] == 1


@pytest.mark.parametrize("category", [
    "unsafe_destination_ip", "dns_resolution_failed", "upstream_connection_failed",
])
async def test_actual_proxy_failure_stage_has_sanitized_reason(
    monkeypatch: pytest.MonkeyPatch, category: str,
) -> None:
    original_connect = asyncio.open_connection
    resolver = AsyncMock(return_value=(ResolvedAddress("8.8.8.8", 4),))
    if category == "unsafe_destination_ip":
        resolver.side_effect = UnsafeDestinationAddressError("SECRET address")
    elif category == "dns_resolution_failed":
        resolver.side_effect = HostResolutionError("SECRET resolver")
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.browser.egress.resolve_and_validate_host", resolver,
    )
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.browser.egress.asyncio.open_connection",
        AsyncMock(side_effect=ConnectionRefusedError("SECRET upstream")),
    )
    failures: list[str] = []
    proxy = PinnedEgressProxy("public_only", on_failure=lambda reason, *_: failures.append(reason))
    address = await proxy.start()
    port = int(address.rsplit(":", 1)[1])
    writer = None
    try:
        reader, writer = await original_connect("127.0.0.1", port)
        writer.write(b"CONNECT target.invalid:443 HTTP/1.1\r\n\r\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 2)
        assert b"502 Bad Gateway" in response
        assert b"SECRET" not in response
        assert failures == [category]
    finally:
        if writer is not None:
            writer.close()
            await writer.wait_closed()
        await proxy.close()


def test_proxy_diagnostics_reject_other_session_ownership() -> None:
    from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
    from markettwin_execution_orchestrator.browser.errors import BrowserSessionOwnershipError

    controller = BrowserController()
    session_id, execution_id, journey_id = uuid4(), uuid4(), uuid4()
    controller._sessions[session_id] = cast(JourneyBrowserSession, SimpleNamespace(
        session_id=session_id, execution_id=execution_id, journey_id=journey_id,
        state="open", control_mode="human", human_network_diagnostics=HumanNetworkDiagnostics(),
    ))
    with pytest.raises(BrowserSessionOwnershipError):
        controller.human_network_diagnostics(handle=BrowserSessionHandle(
            session_id, uuid4(), journey_id,
        ))


@pytest.mark.parametrize("socket", [False, True])
async def test_actual_route_denial_counts_without_restoring_capture(socket: bool) -> None:
    session = cast(JourneyBrowserSession, SimpleNamespace(
        control_mode="human", network_policy="public_only", capture_enabled=False,
        authenticated_session=True,
        allowed_origins=(AllowedOrigin("https", "target.invalid", None),),
        human_network_diagnostics=HumanNetworkDiagnostics(),
        event_buffer=SimpleNamespace(record_failed_request=AsyncMock()),
    ))
    controller = BrowserController()
    request = cast(Request, SimpleNamespace(
        url="https://third.invalid/private?credential=SECRET",
        is_navigation_request=lambda: False,
    ))
    abort, close = AsyncMock(), AsyncMock()
    if socket:
        await controller._route_web_socket(session, cast(WebSocketRoute, SimpleNamespace(
            url="wss://third.invalid/private?credential=SECRET", close=close,
        )))
        close.assert_awaited_once()
    else:
        await controller._route_request(session, cast(Route, SimpleNamespace(
            request=request, abort=abort,
        )))
        abort.assert_awaited_once_with("blockedbyclient")
    assert session.human_network_diagnostics.snapshot() == ({
        "reason": "target_origin_denied", "destination": "unknown_third_party", "count": 1,
    },)
    assert not session.capture_enabled
