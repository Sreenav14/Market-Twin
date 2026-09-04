from __future__ import annotations

import pytest
from markettwin_execution_orchestrator.browser.contracts import AllowedOrigin
from markettwin_execution_orchestrator.browser.errors import TargetUrlValidationError
from markettwin_execution_orchestrator.browser.policy import (
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


def test_blocks_localhost_localdomain_public() -> None:
    origins = (AllowedOrigin("http", "localhost.localdomain", 3000, False),)
    with pytest.raises(TargetUrlValidationError, match="local development"):
        validate_target_url(
            "http://localhost.localdomain:3000",
            origins,
            "public_only",
        )
