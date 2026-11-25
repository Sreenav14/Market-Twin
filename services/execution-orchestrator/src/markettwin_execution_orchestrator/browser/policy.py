"""Deterministic URL/origin policy for MarketTwin browser execution."""

import ipaddress
import json
import re
from dataclasses import dataclass
from urllib.parse import SplitResult, parse_qsl, urlsplit, urlunsplit

from markettwin_execution_orchestrator.browser.action_policy import (
    _SENSITIVE_AUTOCOMPLETE_VALUES,
    _SENSITIVE_LABEL_PHRASES,
)
from markettwin_execution_orchestrator.browser.contracts import (
    AllowedOrigin,
    NetworkPolicy,
)
from markettwin_execution_orchestrator.browser.errors import (
    SuspiciousEgressError,
    TargetUrlValidationError,
)


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


@dataclass(frozen=True, slots=True)
class _CaptchaProvider:
    hostname: str
    path_prefix: str
    include_subdomains: bool = False


# Widget assets only. These hosts are not approved navigation targets.
_CAPTCHA_PROVIDERS: tuple[_CaptchaProvider, ...] = (
    _CaptchaProvider("www.google.com", "/recaptcha/"),
    _CaptchaProvider("www.recaptcha.net", "/recaptcha/"),
    _CaptchaProvider("www.gstatic.com", "/recaptcha/"),
    _CaptchaProvider("hcaptcha.com", "/", include_subdomains=True),
    _CaptchaProvider("challenges.cloudflare.com", "/turnstile/"),
    _CaptchaProvider("challenges.cloudflare.com", "/cdn-cgi/challenge-platform/"),
)


def _matches_captcha_provider(
    hostname: str,
    path: str,
    provider: _CaptchaProvider,
) -> bool:
    allowed = normalize_hostname(provider.hostname)
    host_matches = hostname == allowed
    if provider.include_subdomains:
        host_matches = host_matches or hostname.endswith(f".{allowed}")
    return host_matches and path.startswith(provider.path_prefix)


def is_known_captcha_host(hostname: str) -> bool:
    """Classify a host for sanitized diagnostics, without granting request authority."""
    normalized = normalize_hostname(hostname)
    return any(
        normalized == provider.hostname
        or (provider.include_subdomains and normalized.endswith(f".{provider.hostname}"))
        for provider in _CAPTCHA_PROVIDERS
    )


def validate_captcha_subresource(raw_url: str) -> ValidatedUrl:
    """Allow one public captcha widget asset. Main-frame navigation stays blocked."""

    try:
        parsed = urlsplit(raw_url)
    except ValueError as exc:
        raise TargetUrlValidationError("Captcha URL must be a valid URL.") from exc

    scheme = parsed.scheme.lower()
    if scheme != "https":
        raise TargetUrlValidationError("Captcha providers must use HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise TargetUrlValidationError("Credentials cannot be embedded in the URL.")
    if not parsed.hostname:
        raise TargetUrlValidationError("Captcha URL must include a hostname.")

    hostname = normalize_hostname(parsed.hostname)
    port = normalize_port(scheme, _parsed_port(parsed))
    if port is not None:
        raise TargetUrlValidationError("Captcha providers must use the standard HTTPS port.")
    path = parsed.path or "/"
    if not any(
        _matches_captcha_provider(hostname, path, provider)
        for provider in _CAPTCHA_PROVIDERS
    ):
        raise TargetUrlValidationError("URL is not a captcha provider asset.")

    _validate_direct_network_location(hostname, "public_only")
    href = urlunsplit((scheme, hostname, parsed.path, parsed.query, ""))
    return ValidatedUrl(
        href=href,
        scheme=scheme,
        hostname=hostname,
        port=None,
        origin=_origin_text(scheme, hostname, None),
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
# --- Cross-origin submissions (owner rule, 2026-11-24) -------------------
#
# A page under test may send requests to public third parties (its own
# analytics, embeds, captcha token calls). A send is suspicious — blocked,
# with the block recorded — only when it carries sensitive data off the
# page's own origin: a field named like the browser policy's sensitive
# classification (password / passcode / OTP / payment card ...), or a
# payment-card value. The classifier returns a named reason — the
# sensitive class only, never a field value or body content — or None
# when the send is clean.

_SUBMISSION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _normalized_field_key(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())


# The scan reuses the interaction policy's sensitive classification, minus
# "captcha": a captcha-named field is the widget's own token field, not a
# credential. The agent still may not type into captcha fields — that
# interaction guard lives in action_policy and is untouched by this scan.
_SENSITIVE_FIELD_KEYS: tuple[str, ...] = tuple(
    dict.fromkeys(
        normalized
        for normalized in (
            _normalized_field_key(phrase)
            for phrase in (*_SENSITIVE_LABEL_PHRASES, *_SENSITIVE_AUTOCOMPLETE_VALUES)
        )
        if normalized and normalized != "captcha"
    )
)


def _body_pairs(post_data: str) -> list[tuple[str | None, str]]:
    """(field name, value) pairs from one request body.

    Form and JSON bodies give named fields; any other body comes back as
    one nameless value so it is still value-scanned.
    """

    text = post_data.strip()
    if not text:
        return []
    if text[0] in "{[":
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if parsed is not None:
            pairs: list[tuple[str | None, str]] = []

            def walk(node: object, key: str | None) -> None:
                if isinstance(node, dict):
                    for name, item in node.items():
                        walk(item, str(name))
                elif isinstance(node, list):
                    for item in node:
                        walk(item, key)
                elif node is not None:
                    pairs.append((key, str(node)))

            walk(parsed, None)
            return pairs
    if "=" in text:
        return parse_qsl(text, keep_blank_values=True)
    return [(None, text)]


def _luhn_valid(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        digit = int(char)
        if index % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _carries_card_number(value: str) -> bool:
    for run in re.findall(r"\d[\d -]{11,}\d", value):
        candidate = run.replace(" ", "").replace("-", "")
        if 13 <= len(candidate) <= 19 and _luhn_valid(candidate):
            return True
    return False


def cross_origin_submission_reason(
    method: str,
    post_data: str | None,
) -> str | None:
    """Name why one cross-origin submission is suspicious, or return None.

    Only submissions (POST/PUT/PATCH/DELETE) are classified; loads stay
    free. A bodyless submission carries nothing and is always clean.
    """

    if method.upper() not in _SUBMISSION_METHODS or not post_data:
        return None
    for name, value in _body_pairs(post_data):
        if name is not None:
            key = _normalized_field_key(name)
            for phrase in _SENSITIVE_FIELD_KEYS:
                if phrase in key:
                    return f"sensitive_field:{phrase}"
        if _carries_card_number(value):
            return "payment_card_value"
    return None


def ensure_unsuspicious_submission(method: str, post_data: str | None) -> None:
    """Raise SuspiciousEgressError when a cross-origin submission is suspicious."""

    reason = cross_origin_submission_reason(method, post_data)
    if reason is not None:
        raise SuspiciousEgressError(
            "Cross-origin submission carries sensitive data off the target origin.",
            reason=reason,
        )
