"""Read-only authenticated identity and role checks for approved targets."""

from typing import NamedTuple
from urllib.parse import urlsplit

from markettwin_shared.auth_verification import AuthVerificationPolicy
from playwright.async_api import Page

from markettwin_execution_orchestrator.browser.policy import validate_captcha_subresource


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


def _anchor_location(url: str) -> tuple[str, str] | None:
    resource = validate_captcha_subresource(url)
    source = urlsplit(resource.href)
    if (source.hostname not in {"www.google.com", "www.recaptcha.net"}
            or source.path not in {"/recaptcha/api2/anchor", "/recaptcha/enterprise/anchor"}):
        return None
    return source.hostname, source.path


async def has_active_sensitive_challenge(page: Page) -> bool:
    """Inspect visible challenge UI only, never challenge tokens or credentials.

    A persistent provider anchor is cleared only by its checked checkbox. Missing,
    unreadable or ambiguous widget state remains an active challenge.
    """
    if await page.locator(
        'input[type="password"]:visible, input[autocomplete="one-time-code"]:visible, '
        'input[autocomplete="username"]:visible, input[name*="otp" i]:visible, '
        'input[name*="captcha" i]:visible, [data-captcha]:visible'
    ).count():
        return True
    widgets = page.locator(
        'iframe[title*="captcha" i]:visible, '
        'iframe[title*="Cloudflare security challenge" i]:visible'
    )
    for index in range(await widgets.count()):
        widget = widgets.nth(index)
        try:
            element = await widget.element_handle()
            frame = await element.content_frame()
            # The src attribute can remain an anchor URL after an in-frame redirect.
            # Use the live document's host/path; never read challenge token fields.
            location = _anchor_location(frame.url) if frame is not None else None
            if frame is None or location is None:
                return True
            document = await frame.locator("html").element_handle()
            checkboxes = frame.get_by_role("checkbox")
            if await checkboxes.count() != 1 or not await checkboxes.is_visible():
                return True
            solved = await checkboxes.get_attribute("aria-checked") == "true"
            if not solved and await checkboxes.get_attribute("type") == "checkbox":
                solved = await checkboxes.is_checked()
            if (not solved or frame.is_detached() or _anchor_location(frame.url) != location
                    or not await document.is_visible()
                    or not await element.is_visible()
                    or await element.content_frame() is not frame):
                return True
        except Exception:
            return True
    return False


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
        if await has_active_sensitive_challenge(page):
            return None
        locator = page.locator(policy.marker_selector)
        if await locator.count() != 1 or not await locator.is_visible():
            return None
        marker = (await locator.inner_text(timeout=1500)).strip()
    except Exception:
        return None
    if marker != policy.expected_marker:
        return None
    if _origin(page.url) != policy.origin:
        return None
    return VerifiedPrincipal(
        role=policy.role,
        account_reference=policy.account_reference,
        origin=policy.origin,
    )
