"""Live Journey-scoped Playwright session state."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from playwright.async_api import Browser, BrowserContext, Page

from markettwin_execution_orchestrator.browser.contracts import (
    AllowedOrigin,
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
    action_number: int = 0
    trace_segment: int = 0
    tracing_active: bool = False
    capture_enabled: bool = True
    event_buffer: BrowserEventBuffer = field(default_factory=BrowserEventBuffer)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def next_action_number(self) -> int:
        """Advance and return the monotonically increasing action number."""

        self.action_number += 1
        return self.action_number
