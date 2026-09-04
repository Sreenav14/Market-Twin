"""Deterministic URL/origin policy for MarketTwin browser execution."""

import ipaddress
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

from markettwin_execution_orchestrator.browser.contracts import (
    AllowedOrigin,
    NetworkPolicy,
)
from markettwin_execution_orchestrator.browser.errors import TargetUrlValidationError


@dataclass(frozen=True, slots=True)
class ValidatedUrl:
    """Normalized HTTP(S) URL that passed MarketTwin target policy."""

    href: str
    scheme: str
    hostname: str
    port: int | None
    origin: str


_DEFAULT_PORTS: dict[str, int] = {"http": 80, "https": 443}


def normalize_hostname(hostname: str) -> str:
    """Normalize hostnames for exact and subdomain-boundary comparisons."""

    candidate = hostname.strip().rstrip(".")
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    if not candidate:
        raise TargetUrlValidationError("Target URL must include a hostname.")

    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        try:
            return candidate.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise TargetUrlValidationError("Target hostname is not valid IDNA.") from exc
    return address.compressed.lower()


def normalize_port(scheme: str, port: int | None) -> int | None:
    """Represent default HTTP(S) ports as None, matching stored origins."""

    if port is None or _DEFAULT_PORTS.get(scheme) == port:
        return None
    return port


def _parsed_port(parsed: SplitResult) -> int | None:
    try:
        return parsed.port
    except ValueError as exc:
        raise TargetUrlValidationError("Target URL contains an invalid port.") from exc


def _origin_text(scheme: str, hostname: str, port: int | None) -> str:
    host = f"[{hostname}]" if ":" in hostname else hostname
    return f"{scheme}://{host}" if port is None else f"{scheme}://{host}:{port}"


def _matches_allowed_origin(
    *,
    scheme: str,
    hostname: str,
    port: int | None,
    origin: AllowedOrigin,
) -> bool:
    allowed_scheme = origin.scheme.lower()
    allowed_hostname = normalize_hostname(origin.hostname)
    allowed_port = normalize_port(allowed_scheme, origin.port)
    hostname_matches = hostname == allowed_hostname
    if origin.include_subdomains:
        hostname_matches = hostname_matches or hostname.endswith(f".{allowed_hostname}")
    return scheme == allowed_scheme and hostname_matches and port == allowed_port


def _validate_direct_network_location(
    hostname: str,
    network_policy: NetworkPolicy,
) -> None:
    """Reject unsafe directly-entered IPs and loopback hostnames."""

    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname == "localhost.localdomain"
    ):
        if network_policy == "local_development":
            return
        raise TargetUrlValidationError(
            "Loopback targets are only allowed in local development mode."
        )

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return

    if address.version == 6 and not address.is_loopback:
        raise TargetUrlValidationError("Direct IPv6 targets are not allowed.")
    if address.is_loopback:
        if network_policy == "local_development":
            return
        raise TargetUrlValidationError(
            "Loopback targets are only allowed in local development mode."
        )
    if not address.is_global:
        raise TargetUrlValidationError(
            "Private, link-local, reserved, and other non-global IP targets are not allowed."
        )


def validate_target_url(
    raw_url: str,
    allowed_origins: tuple[AllowedOrigin, ...] | list[AllowedOrigin],
    network_policy: NetworkPolicy,
) -> ValidatedUrl:
    """Validate and normalize one URL against MarketTwin runtime policy."""

    try:
        parsed = urlsplit(raw_url)
    except ValueError as exc:
        raise TargetUrlValidationError("Target URL must be a valid URL.") from exc

    scheme = parsed.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise TargetUrlValidationError("Only HTTP and HTTPS URLs are supported.")
    if parsed.username is not None or parsed.password is not None:
        raise TargetUrlValidationError("Credentials cannot be embedded in the URL.")
    if not parsed.hostname:
        raise TargetUrlValidationError("Target URL must include a hostname.")
    if not allowed_origins:
        raise TargetUrlValidationError("At least one allowed origin is required.")

    hostname = normalize_hostname(parsed.hostname)
    port = normalize_port(scheme, _parsed_port(parsed))
    if not any(
        _matches_allowed_origin(
            scheme=scheme,
            hostname=hostname,
            port=port,
            origin=origin,
        )
        for origin in allowed_origins
    ):
        raise TargetUrlValidationError(
            f'Target origin "{_origin_text(scheme, hostname, port)}" is not allowed.'
        )

    _validate_direct_network_location(hostname, network_policy)
    host_for_url = f"[{hostname}]" if ":" in hostname else hostname
    netloc = host_for_url if port is None else f"{host_for_url}:{port}"
    href = urlunsplit((scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    return ValidatedUrl(
        href=href,
        scheme=scheme,
        hostname=hostname,
        port=port,
        origin=_origin_text(scheme, hostname, port),
    )


def validate_websocket_url(
    raw_url: str,
    allowed_origins: tuple[AllowedOrigin, ...] | list[AllowedOrigin],
    network_policy: NetworkPolicy,
) -> ValidatedUrl:
    """Validate WS/WSS against the corresponding HTTP(S) allowed origin."""

    try:
        parsed = urlsplit(raw_url)
    except ValueError as exc:
        raise TargetUrlValidationError("WebSocket URL must be valid.") from exc

    mapped_scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme.lower())
    if mapped_scheme is None:
        raise TargetUrlValidationError("Only WS and WSS WebSocket URLs are supported.")
    mapped = urlunsplit(
        (mapped_scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment)
    )
    return validate_target_url(mapped, allowed_origins, network_policy)
