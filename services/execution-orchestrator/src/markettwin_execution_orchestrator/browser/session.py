"""Live Journey-scoped Playwright session state."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from markettwin_shared.action_approval import SensitiveActionRule
from playwright.async_api import Browser, BrowserContext, Page

from markettwin_execution_orchestrator.browser.contracts import (
    AllowedOrigin,
    BrowserControlMode,
    BrowserEventBuffer,
    BrowserSessionState,
    NetworkPolicy,
)
from markettwin_execution_orchestrator.browser.live_pointer import LiveClickTarget
from markettwin_execution_orchestrator.browser.offsite import OffsiteBrowsing
from markettwin_execution_orchestrator.browser.network_diagnostics import HumanNetworkDiagnostics


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
    # Unified Room (U-P2): a room session is the run's shared browser,
    # rebound to one item execution at a time; a proof session is a
    # fresh context inside the room's browser (shares_browser) whose
    # close must not close the shared Chromium.
    is_room: bool = False
    shares_browser: bool = False
    # JS capture enrichment (U-P6-03): slop sessions capture structured
    # JS errors (message + stack + URL only) even on authenticated
    # pages, and install the unhandled-rejection init hook.
    js_capture: bool = False
    rejections_harvested: int = 0
    rejections_document: str = ""
    # Rejection items dropped at harvest because neither the item nor
    # its document carried a URL to attribute them to (doc 24 §4.1):
    # counted, never silently lost and never guessed onto a page.
    rejections_dropped: int = 0
    rejection_harvest_failures: int = 0
    last_rejection_harvest_failed: bool = False
    # Set when a bounded sensitive-challenge inspection could not
    # answer within its bound (MT-000237, Fix C); drained onto the
    # page state by the inspecting workflow, never raised.
    challenge_check_timed_out: bool = False
    page_setup_failures: int = 0
    fixture_action_rules: tuple[SensitiveActionRule, ...] = ()
    event_buffer: BrowserEventBuffer = field(default_factory=BrowserEventBuffer)
    human_network_diagnostics: HumanNetworkDiagnostics = field(
        default_factory=HumanNetworkDiagnostics,
    )
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    live_click_target: LiveClickTarget | None = None
    keyboard_only: bool = False
    live_view_changed: asyncio.Event = field(default_factory=asyncio.Event)
    offsite: OffsiteBrowsing | None = None
    provider_handoff_url: str | None = None

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
