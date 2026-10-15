"""Live Journey-scoped Playwright session state."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from playwright.async_api import Browser, BrowserContext, Page

from markettwin_execution_orchestrator.browser.contracts import (
    AllowedOrigin,
    BrowserControlMode,
    BrowserEventBuffer,
    BrowserSessionState,
    NetworkPolicy,
)


@dataclass(slots=True)
class JourneyBrowserSession:
    """All mutable browser resources owned by one Journey execution."""

    session_id: UUID
    execution_id: UUID
    journey_id: UUID
    allowed_origins: tuple[AllowedOrigin, ...]
    network_policy: NetworkPolicy
    timeout_ms: int
    browser: Browser
    context: BrowserContext
    page: Page
    artifact_directory: Path
    state: BrowserSessionState = "starting"
    control_mode: BrowserControlMode = "agent"
    control_generation: int = 0
    action_number: int = 0
    trace_segment: int = 0
    tracing_active: bool = False
    capture_enabled: bool = True
    auth_only_origins: tuple[str, ...] = ()
    authenticated_session: bool = False
    event_buffer: BrowserEventBuffer = field(default_factory=BrowserEventBuffer)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def next_action_number(self) -> int:
        """Advance and return the monotonically increasing action number."""

        self.action_number += 1
        return self.action_number

    def is_auth_only_url(self, url: str) -> bool:
        parsed = urlsplit(url)
        host = (
            f"[{parsed.hostname}]"
            if parsed.hostname and ":" in parsed.hostname else parsed.hostname
        )
        default_port = 443 if parsed.scheme == "https" else 80
        origin = f"{parsed.scheme}://{host}" + (
            f":{parsed.port}" if parsed.port and parsed.port != default_port else ""
        )
        return origin in self.auth_only_origins
