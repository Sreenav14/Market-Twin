"""Executable in-memory handoff specification, NOT a production security layer.

No browser transport, database, auth tokens, or model calls. Server-side callers
must supply authenticated identities, trusted time, and verified postconditions.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


class Rejected(RuntimeError):
    pass


@dataclass(frozen=True)
class Lease:
    owner: str
    epoch: int
    expires: float


class Handoff:
    def __init__(self, context: str, authorized_users: frozenset[str]):
        self.context = context
        self.authorized_users = authorized_users
        self.state = "agent"
        self.epoch = 0
        self.capture = True
        self.pause_requested = False
        self.lease: Lease | None = None
        self.lock = asyncio.Lock()
        self.audit: list[str] = []

    def require_context(self, context: str) -> None:
        if context != self.context:
            raise Rejected("Wrong browser context")

    async def agent_action(
        self, epoch: int, context: str, operation: Callable[[], Awaitable[object]],
    ) -> object:
        # Check at execution time INSIDE the same lock as ownership transitions.
        async with self.lock:
            self.require_context(context)
            if self.state != "agent" or self.pause_requested or epoch != self.epoch:
                raise Rejected("Agent action no longer authorized")
            return await operation()

    async def request_handoff(self, context: str) -> None:
        self.require_context(context)
        self.pause_requested = True  # Stop new admissions while the current action drains.
        async with self.lock:
            if self.state != "agent":
                raise Rejected("Already paused or terminal")
            self.epoch += 1
            self.capture = False
            self.state = "waiting"
            self.audit.append("waiting_for_human")

    async def claim(self, owner: str, context: str, now: float, ttl: float) -> Lease:
        async with self.lock:
            self.require_context(context)
            if owner not in self.authorized_users or ttl <= 0:
                raise Rejected("Invalid claimant or lease duration")
            if self.state != "waiting":
                raise Rejected("No claimable request")
            self.epoch += 1
            self.lease = Lease(owner, self.epoch, now + ttl)
            self.state = "human"
            self.audit.append("human_control_acquired")
            return self.lease

    def require_lease(self, lease: Lease, context: str, now: float) -> None:
        self.require_context(context)
        if self.state != "human" or self.lease != lease or now >= lease.expires:
            raise Rejected("Expired, stale, or inactive lease")

    async def human_action(
        self, lease: Lease, context: str, now: float,
        operation: Callable[[], Awaitable[object]],
    ) -> object:
        async with self.lock:
            self.require_lease(lease, context, now)
            return await operation()

    async def done(self, lease: Lease, context: str, now: float) -> None:
        async with self.lock:
            self.require_lease(lease, context, now)
            self.lease = None  # Revoke input before verification.
            self.epoch += 1
            self.state = "verifying"
            self.audit.append("human_submitted_done")

    async def verify(self, context: str, *, postcondition: bool, capture_safe: bool) -> bool:
        """Internal verifier result; neither flag may come directly from a UI claim."""
        async with self.lock:
            self.require_context(context)
            if self.state != "verifying":
                raise Rejected("No pending verification")
            self.epoch += 1
            if not postcondition or not capture_safe:
                self.state = "waiting"
                self.audit.append("verification_failed")
                return False
            self.state = "agent"
            self.pause_requested = False
            self.capture = True
            self.audit.append("verified_resume")
            return True

    async def expire(self, now: float) -> None:
        async with self.lock:
            if self.state == "human" and self.lease and now >= self.lease.expires:
                self.lease = None
                self.epoch += 1
                self.state = "waiting"
                self.audit.append("lease_expired")

    async def context_lost(self) -> None:
        async with self.lock:
            self.state = "context_lost"
            self.epoch += 1
            self.lease = None
            self.capture = False
            self.pause_requested = True
            self.audit.append("context_lost")

    def record_page_event(self, event: str) -> None:
        # This illustrates suppression only. Production also needs sanitization.
        if self.capture and self.state == "agent" and not self.pause_requested:
            self.audit.append(event)


def escalation(*, forbidden: bool = False, secret_step: bool = False,
               missing_user_fact: bool = False, missing_observation: bool = False,
               recovery_exhausted: bool = False) -> str:
    """Transparent first-version rules; not a calibrated learned uncertainty model."""
    if forbidden:
        return "stop_policy_blocked"
    if secret_step:
        return "request_private_handoff"
    if missing_observation:
        return "expand_evidence"
    if missing_user_fact:
        return "ask_targeted_question"
    if recovery_exhausted:
        return "request_assistance_or_finish_unresolved"
    return "continue_within_scope"
