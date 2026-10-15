"""Read-only authenticated identity and role checks for approved targets."""

from typing import NamedTuple
from urllib.parse import urlsplit

from markettwin_shared.auth_verification import AuthVerificationPolicy
from playwright.async_api import Page


class VerifiedPrincipal(NamedTuple):
    role: str
    account_reference: str
    origin: str


__all__ = [
    "AuthVerificationPolicy",
    "VerifiedPrincipal",
    "verify_authenticated_role",
]


def _origin(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        return None
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    default_port = 443 if parsed.scheme == "https" else 80
    port = f":{parsed.port}" if parsed.port and parsed.port != default_port else ""
    return f"{parsed.scheme}://{host}{port}"


async def verify_authenticated_role(
    *,
    page: Page,
    policy: AuthVerificationPolicy,
    allowed_origins: frozenset[str],
) -> VerifiedPrincipal | None:
    """Return a principal only when the exact approved origin and marker match.

    Marker content remains inside the verifier and is never returned, persisted,
    logged, or passed to the agent. Missing, ambiguous, or changed markers fail closed.
    """
    if policy.origin not in allowed_origins or _origin(page.url) != policy.origin:
        return None
    try:
        challenges = page.locator(
            'input[type="password"]:visible, input[autocomplete="one-time-code"]:visible, '
            'input[name*="otp" i]:visible, input[name*="captcha" i]:visible, '
            'iframe[title*="captcha" i]:visible, [data-captcha]:visible'
        )
        if await challenges.count():
            return None
        locator = page.locator(policy.marker_selector)
        if await locator.count() != 1 or not await locator.is_visible():
            return None
        marker = (await locator.inner_text(timeout=1500)).strip()
    except Exception:
        return None
    if marker != policy.expected_marker:
        return None
    return VerifiedPrincipal(
        role=policy.role,
        account_reference=policy.account_reference,
        origin=policy.origin,
    )
