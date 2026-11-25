"""Run-wide browse authority, separate from the target's interaction authority."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from uuid import UUID

from markettwin_execution_orchestrator.browser.contracts import AllowedOrigin
from markettwin_execution_orchestrator.browser.errors import BrowserPolicyError
from markettwin_execution_orchestrator.browser.network import resolve_and_validate_host
from markettwin_execution_orchestrator.browser.policy import (
    ValidatedUrl, normalize_hostname, validate_target_url,
)


class OffsiteJourneyStopped(BrowserPolicyError):
    """A durable stop fences all later actions in this journey."""


def is_handoff_provider(url: str) -> bool:
    parsed = urlsplit(url)
    host = normalize_hostname(parsed.hostname or "")
    exact = {
        "accounts.google.com", "login.microsoftonline.com", "login.microsoft.com",
        "login.live.com", "appleid.apple.com", "account.apple.com",
        "challenges.cloudflare.com", "recaptcha.net", "www.recaptcha.net",
    }
    return (host in exact or any(
        host == suffix or host.endswith("." + suffix)
        for suffix in ("okta.com", "oktapreview.com", "auth0.com", "hcaptcha.com")
    ) or (host in {"www.google.com", "www.gstatic.com"}
          and (parsed.path or "/").startswith("/recaptcha/")))


def public_url(url: str) -> ValidatedUrl:
    parsed = urlsplit(url)
    # Reuse URL parsing, credential, protocol and direct-address checks, without
    # adding anything to the real allowlist.
    host = normalize_hostname(parsed.hostname or "")
    origin = AllowedOrigin(scheme=parsed.scheme, hostname=host, port=parsed.port)  # type: ignore[arg-type]
    return validate_target_url(url, (origin,), "public_only")


Review = Callable[[str, str, str], Awaitable[tuple[str, str]]]
Save = Callable[[str, dict[str, object], UUID, UUID], Awaitable[None]]


@dataclass
class OffsiteBrowsing:
    goal: str
    review: Review
    save: Save
    pages: dict[str, int] = field(default_factory=dict)
    approved: set[str] = field(default_factory=set)
    subresource_hosts: set[str] = field(default_factory=set)
    stopped: dict[str, str] = field(default_factory=dict)
    deadline: float | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def ensure_journey(self, journey_id: UUID) -> None:
        if reason := self.stopped.get(str(journey_id)):
            raise OffsiteJourneyStopped(reason)

    async def checkpoint(self, source: str, journey_id: UUID, execution_id: UUID) -> None:
        self.ensure_journey(journey_id)
        if self.deadline is not None and time.time() >= self.deadline:
            await self.stop("Off-site browsing reached its 20-minute limit.",
                            source, source, journey_id, execution_id)

    def validate(self, url: str, journey_id: UUID) -> ValidatedUrl:
        self.ensure_journey(journey_id)
        result = public_url(url)
        if self.deadline is not None and time.time() >= self.deadline:
            raise OffsiteJourneyStopped("Off-site browsing reached its 20-minute limit.")
        if is_handoff_provider(url) or result.hostname not in self.approved:
            raise BrowserPolicyError("Outside address has no browsing authority.")
        return result

    async def record(
        self, kind: str, payload: dict[str, object], journey_id: UUID, execution_id: UUID,
    ) -> None:
        await self.save(kind, {**payload, "state": {
            "pages": dict(self.pages), "approved": sorted(self.approved),
            "stopped": dict(self.stopped),
            "deadline": self.deadline,
        }}, journey_id, execution_id)

    async def stop(
        self, reason: str, source: str, destination: str,
        journey_id: UUID, execution_id: UUID,
    ) -> None:
        self.stopped[str(journey_id)] = reason
        await self.record("offsite.stop", {
            "decision": "stop", "reason": reason,
            "from": safe_address(source), "to": safe_address(destination),
        }, journey_id, execution_id)
        raise OffsiteJourneyStopped(reason)

    async def navigate(
        self, url: str, source: str, journey_id: UUID, execution_id: UUID,
    ) -> ValidatedUrl:
        async with self.lock:
            self.ensure_journey(journey_id)
            await self.checkpoint(source, journey_id, execution_id)
            if self.deadline is None:
                self.deadline = time.time() + 20 * 60
            try:
                destination = public_url(url)
                await resolve_and_validate_host(destination.hostname, "public_only")
            except Exception:
                await self.stop("Outside destination is not a public HTTP(S) address.",
                                source, url, journey_id, execution_id)
                raise AssertionError("stop always raises")
            host = destination.hostname
            if is_handoff_provider(url):
                raise BrowserPolicyError("Sign-in and CAPTCHA require human control.")
            if host not in self.pages and len(self.pages) >= 3:
                await self.stop("Outside domain limit reached (3 per run).",
                                source, destination.origin, journey_id, execution_id)
            # Review every outside navigation, even on an already visited host.
            # URLs are data; the reviewer never receives page instructions.
            try:
                async with asyncio.timeout(20):
                    decision, reason = await self.review(
                        safe_address(source), safe_address(destination.href),
                        f"{self.goal}\nOutside visits so far: {self.pages}. "
                        f"Time remaining: {max(0, int(self.deadline - time.time()))} seconds.",
                    )
                if decision not in {"continue", "stop"} or not reason:
                    raise ValueError("Invalid lead decision")
            except Exception:
                decision, reason = "stop", "Lead check failed or timed out."
            if decision != "continue":
                await self.stop(reason, source, destination.origin, journey_id, execution_id)
            self.pages[host] = self.pages.get(host, 0) + 1
            self.approved.add(host)
            await self.record("offsite.continue", {
                "decision": "continue", "reason": reason,
                "from": safe_address(source), "to": destination.origin,
                "page_count": self.pages[host],
            }, journey_id, execution_id)
            return destination


def safe_address(url: str) -> str:
    """Decision records never retain query parameters, fragments or credentials."""
    try:
        parsed = urlsplit(url)
        if not parsed.hostname:
            return "unavailable"
        return f"{parsed.scheme}://{parsed.hostname}{parsed.path}"[:500]
    except ValueError:
        return "unavailable"


def validate_browsing_url(session, url: str) -> ValidatedUrl:
    """Single synchronous rule used by page reads and the live viewer."""
    if session.offsite is not None:
        session.offsite.ensure_journey(session.journey_id)
    try:
        return validate_target_url(url, session.allowed_origins, session.network_policy)
    except BrowserPolicyError:
        if session.offsite is None:
            raise
        return session.offsite.validate(url, session.journey_id)


def validate_human_url(session, url: str) -> ValidatedUrl:
    """Human leases may reach public sign-in providers; this grants no agent access."""
    try:
        return validate_target_url(url, session.allowed_origins, session.network_policy)
    except BrowserPolicyError:
        if session.offsite is None or not is_handoff_provider(url):
            raise
        return public_url(url)
