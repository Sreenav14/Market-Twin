"""Python Playwright browser authority for MarketTwin Journey execution."""

from __future__ import annotations

import asyncio
import json
import re
import secrets
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from ipaddress import ip_address
from pathlib import Path
from time import monotonic
from typing import Any, Literal, cast
from urllib.parse import urljoin, urlsplit
from uuid import UUID, uuid4

from markettwin_shared.action_approval import SensitiveActionRule
from markettwin_shared.auth_verification import AuthVerificationPolicy
from playwright.async_api import (
    Browser,
    Dialog,
    Locator,
    Page,
    Playwright,
    Request,
    Route,
    WebSocketRoute,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from markettwin_execution_orchestrator.agents.schemas.test_case import (
    ExpectedAssertion,
    SemanticTarget,
)
from markettwin_execution_orchestrator.browser.action_policy import (
    ensure_low_risk_click_target,
    ensure_non_sensitive_fill,
)
from markettwin_execution_orchestrator.browser.actions import (
    require_unique,
    resolve_action_locator,
    scoped_root,
    semantic_locator,
)
from markettwin_execution_orchestrator.browser.assertions import (
    AssertionObservation,
    evaluate_assertion,
    repeat_read_only_assertion,
)
from markettwin_execution_orchestrator.browser.auth_session_broker import (
    AuthSessionBroker,
    AuthSessionScope,
    AuthSessionSnapshot,
    HumanSessionScope,
)
from markettwin_execution_orchestrator.browser.auth_verifier import (
    SENSITIVE_CHALLENGE_TIMEOUT_SECONDS,
    VerifiedPrincipal,
    has_active_sensitive_challenge,
    inspect_sensitive_challenge,
    verify_authenticated_role,
)
from markettwin_execution_orchestrator.browser.contracts import (
    AllowedOrigin,
    BrowserActionResult,
    BrowserSessionArtifacts,
    BrowserSessionHandle,
    ElementBoundingBox,
    FailedRequestRecord,
    JsErrorRecord,
    NetworkPolicy,
    ScopeRole,
)
from markettwin_execution_orchestrator.browser.discovery_checkpoint import is_discovery_checkpoint
from markettwin_execution_orchestrator.browser.egress import PinnedEgressProxy
from markettwin_execution_orchestrator.browser.errors import (
    BrowserActionBlockedError,
    BrowserActionError,
    BrowserNavigationError,
    BrowserPolicyError,
    BrowserSessionNotFoundError,
    BrowserSessionOwnershipError,
    BrowserSessionStateError,
    BrowserTimeoutError,
    HostResolutionError,
    HumanControlActiveError,
    SuspiciousEgressError,
    TargetUrlValidationError,
    UnsafeDestinationAddressError,
)
from markettwin_execution_orchestrator.browser.evidence import (
    bounding_box_intersects_viewport,
    capture_screenshot,
    crop_viewport_screenshot,
    start_trace,
    stop_trace,
    write_event_logs,
)
from markettwin_execution_orchestrator.browser.human_control import (
    begin_human_control,
    end_human_control,
)
from markettwin_execution_orchestrator.browser.live_pointer import LiveClickTarget
from markettwin_execution_orchestrator.browser.network import resolve_and_validate_host
from markettwin_execution_orchestrator.browser.offsite import (
    OffsiteBrowsing, is_handoff_provider, public_url, safe_address,
    validate_browsing_url, validate_human_url,
)
from markettwin_execution_orchestrator.browser.network_diagnostics import (
    NetworkDiagnosticDestination,
    NetworkDiagnosticReason,
)
from markettwin_execution_orchestrator.browser.observations import (
    build_observation,
    inspect_form_fields,
)
from markettwin_execution_orchestrator.browser.policy import (
    ValidatedUrl,
    ensure_unsuspicious_submission,
    is_known_captcha_host,
    normalize_hostname,
    validate_captcha_subresource,
    validate_target_url,
    validate_websocket_url,
)
from markettwin_execution_orchestrator.browser.sensitive_action_policy import (
    SensitiveActionIntent,
    classify_click_action,
)
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession


_AUTH_BUTTON_PATTERN = re.compile(
    r"^(sign\s*in|log\s*in|sign\s*up|register|create (?:an? )?account|continue(?: with .+)?)$",
    re.I,
)
_AUTH_HEADING_PATTERN = re.compile(
    r"^(sign\s*in|log\s*in|login|sign\s*up|register|create (?:an? )?account|"
    r"verify (?:your identity|your email|your phone number)|authorize .+|permissions requested)$",
    re.I,
    )
_AUTH_CONTINUE_PATTERN = re.compile(
    r"^(continue(?: with .+)?|sign\s*in.*|log\s*in.*|sign\s*up|register|"
    r"create (?:an? )?account|verify|allow|authorize)$", re.I,
    )
_ARIA_SNAPSHOT_ENTRY_PATTERN = re.compile(
    r'''^\s*- (?:')?(button|link|textbox|searchbox|combobox|checkbox|radio|'''
    r'''tab|menuitem)'''
    r'''(?: ("(?:[^"\\]|\\.)*"))?(?:\s|:|$)'''
    )


# Bound for the best-effort reset of a wedged resting page (see
# BrowserController._validate_resting_page).
_RESTING_PAGE_RESET_TIMEOUT_SECONDS = 5


# Unhandled-rejection init hook (U-P6-03; doc 24 section 4.1): ONE
# definition, installed by every context that can produce a slop or
# proof record — create_session with js_capture, proof siblings, and
# the harvest verification replay (which goes through create_session).
# Each item carries the URL of the document that produced it, read at
# event time; harvest stamps records from the item, never from
# whatever page is current when the harvest happens to run.
JS_REJECTION_HOOK_SCRIPT = """
window.__mt_rejections = [];
window.__mt_rejection_doc = Date.now().toString(36)
  + Math.random().toString(36).slice(2);
window.__mt_rejection_doc_url = location.href;
window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason;
  window.__mt_rejections.push({
    message: String(reason && reason.message ? reason.message : reason),
    stack: reason && reason.stack ? String(reason.stack) : null,
    url: location.href,
  });
});
"""


class BrowserController:
    """Sole MarketTwin owner of Playwright and Journey browser sessions."""

    def __init__(
        self,
        *,
        artifact_root: Path | str = "artifacts/runs",
        headless: bool = True,
        max_pages_per_session: int = 4,
    ) -> None:
        if max_pages_per_session < 1:
            raise ValueError("max_pages_per_session must be at least 1")

        self._artifact_root = Path(artifact_root)
        self._headless = headless
        self._max_pages_per_session = max_pages_per_session
        self._playwright: Playwright | None = None
        self._sessions: dict[UUID, JourneyBrowserSession] = {}
        self._session_purposes: dict[UUID, str] = {}
        self._rooms: dict[UUID, UUID] = {}
        self._egress_proxies: dict[UUID, PinnedEgressProxy] = {}
        self._auth_session_broker = AuthSessionBroker()
        self._authentication_handlers: dict[UUID, Callable[[], Awaitable[None]]] = {}
        self._authentication_locks: dict[UUID, asyncio.Lock] = {}
        self._pending_authentication: set[UUID] = set()
        self._cooperative_handlers: dict[UUID, Callable[[], Awaitable[None]]] = {}
        self._cooperative_locks: dict[UUID, asyncio.Lock] = {}
        self._start_lock = asyncio.Lock()
        self._approval_salt = secrets.token_hex(32)
        self.offsite: OffsiteBrowsing | None = None

    async def start(self) -> None:
        """Start the in-process Playwright driver once."""

        if self._playwright is not None:
            return
        async with self._start_lock:
            if self._playwright is None:
                self._playwright = await async_playwright().start()

    async def close(self) -> None:
        """Close every Journey browser and the shared Playwright driver."""

        for session_id in tuple(self._sessions):
            try:
                await self.close_session(session_id=session_id)
            except Exception:
                pass

        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        self._auth_session_broker.clear()

    async def __aenter__(self) -> BrowserController:
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def create_session(
        self,
        *,
        execution_id: UUID,
        journey_id: UUID,
        allowed_origins: tuple[AllowedOrigin, ...] | list[AllowedOrigin],
        network_policy: NetworkPolicy,
        auth_snapshot: AuthSessionSnapshot | None = None,
        auth_only_origins: tuple[str, ...] = (),
        authenticated_session: bool = False,
        timeout_ms: int = 30_000,
        viewport_preset: Literal["mobile320", "desktop1280"] = "desktop1280",
        fixture_action_rules: tuple[SensitiveActionRule, ...] = (),
        is_room: bool = False,
        viewport_size: tuple[int, int] | None = None,
        locale: str | None = None,
        js_capture: bool = False,
    ) -> BrowserSessionHandle:
        """Create one fresh Chromium + BrowserContext for one Journey."""

        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if not allowed_origins:
            raise ValueError("At least one allowed origin is required")
        for origin in auth_only_origins:
            validate_target_url(origin, allowed_origins, network_policy)
        if auth_snapshot is not None:
            validate_target_url(
                auth_snapshot.scope.origin,
                allowed_origins,
                network_policy,
            )

        await self.start()
        assert self._playwright is not None

        session_id = uuid4()
        artifact_directory = self._artifact_root / str(execution_id) / str(session_id)
        artifact_directory.mkdir(parents=True, exist_ok=True)

        browser: Browser | None = None
        def destination_policy(scheme: str, hostname: str, port: int) -> NetworkPolicy:
            if self.offsite is not None:
                host = f"[{hostname}]" if ":" in hostname else hostname
                try:
                    validate_target_url(f"{scheme}://{host}:{port}", allowed_origins, network_policy)
                except BrowserPolicyError:
                    return "public_only"
            return network_policy

        egress = PinnedEgressProxy(
            network_policy, on_failure=lambda reason, scheme, hostname, port:
            self._on_egress_failure(session_id, reason, scheme, hostname, port),
            destination_policy=destination_policy,
        )
        try:
            proxy_url = await egress.start()
            browser = await self._playwright.chromium.launch(
                headless=self._headless,
                proxy={"server": proxy_url, "bypass": "<-loopback>"},
                args=[
                    "--disable-quic",
                    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                ],
            )
            self._egress_proxies[session_id] = egress
            context_kwargs: dict[str, Any] = {}
            if locale is not None:
                context_kwargs["locale"] = locale
            context = await browser.new_context(
                viewport=(
                    {"width": viewport_size[0], "height": viewport_size[1]}
                    if viewport_size is not None
                    else {"width": 320 if viewport_preset == "mobile320" else 1280, "height": 900}
                ),
                device_scale_factor=1,
                accept_downloads=False,
                service_workers="block",
                **context_kwargs,
            )
            if auth_snapshot is not None:
                await AuthSessionBroker.install_snapshot(
                    snapshot=auth_snapshot,
                    context=cast(Any, context),
                )
            context.set_default_timeout(timeout_ms)
            context.set_default_navigation_timeout(timeout_ms)

            page = await context.new_page()
            session = JourneyBrowserSession(
                session_id=session_id,
                execution_id=execution_id,
                journey_id=journey_id,
                allowed_origins=tuple(allowed_origins),
                network_policy=network_policy,
                timeout_ms=timeout_ms,
                browser=browser,
                context=context,
                page=page,
                artifact_directory=artifact_directory,
                auth_only_origins=auth_only_origins,
                authenticated_session=authenticated_session or auth_snapshot is not None,
                fixture_action_rules=fixture_action_rules,
                is_room=is_room,
                js_capture=js_capture,
                offsite=self.offsite,
            )
            if js_capture:
                # Unhandled-rejection hook (U-P6-03): pageerror does
                # not fire for rejected promises, so the page itself
                # collects them for harvest_js_records().
                await context.add_init_script(JS_REJECTION_HOOK_SCRIPT)
            self._sessions[session_id] = session

            await context.route("**/*", lambda route: self._route_request(session, route))
            await context.route_web_socket(
                "**/*",
                lambda route: self._route_web_socket(session, route),
            )
            context.on("page", lambda new_page: self._schedule_page_setup(session, new_page))
            await self._configure_page(session, page)
            await start_trace(session)
            session.state = "open"
            handle = BrowserSessionHandle(
                session_id=session_id,
                execution_id=execution_id,
                journey_id=journey_id,
            )
            from markettwin_execution_orchestrator.browser.owner_registry import (
                browser_owner_registry,
            )

            browser_owner_registry.register(self, handle)
        except Exception:
            self._sessions.pop(session_id, None)
            try:
                if browser is not None:
                    await browser.close()
            finally:
                self._egress_proxies.pop(session_id, None)
                await egress.close()
            raise

        return handle

    async def open_room_session(
        self,
        *,
        run_id: UUID,
        execution_id: UUID,
        journey_id: UUID,
        allowed_origins: tuple[AllowedOrigin, ...] | list[AllowedOrigin],
        network_policy: NetworkPolicy,
        auth_snapshot: AuthSessionSnapshot | None = None,
        authenticated_session: bool = False,
        fixture_action_rules: tuple[SensitiveActionRule, ...] = (),
        js_capture: bool = False,
    ) -> BrowserSessionHandle:
        """Open the run's Room: ONE session shared by the whole run (U-P2).

        The Room is created exactly like a journey session, marked
        is_room, and registered under the run id. Workers borrow it via
        rebind_session; only close_room may close it.
        """

        handle = await self.create_session(
            execution_id=execution_id,
            journey_id=journey_id,
            allowed_origins=allowed_origins,
            network_policy=network_policy,
            auth_snapshot=auth_snapshot,
            authenticated_session=authenticated_session,
            fixture_action_rules=fixture_action_rules,
            is_room=True,
            js_capture=js_capture,
        )
        self._rooms[run_id] = handle.session_id
        return handle

    def room_handle(self, run_id: UUID) -> BrowserSessionHandle | None:
        session_id = self._rooms.get(run_id)
        if session_id is None:
            return None
        session = self._sessions.get(session_id)
        if session is None:
            return None
        return BrowserSessionHandle(
            session_id=session_id,
            execution_id=session.execution_id,
            journey_id=session.journey_id,
        )

    async def close_room(self, *, run_id: UUID) -> None:
        session_id = self._rooms.pop(run_id, None)
        if session_id is not None and session_id in self._sessions:
            await self.close_session(session_id=session_id)

    async def rebind_session(
        self,
        *,
        session_id: UUID,
        execution_id: UUID,
        journey_id: UUID,
    ) -> BrowserSessionHandle:
        """Bind a shared (Room) session to one item execution.

        Single-writer rule: the Room serves exactly one execution at a
        time, so rebinding re-keys its ownership (and its owner-
        registry handle) to the borrowing execution.
        """

        session = self._get_session(session_id=session_id)
        from markettwin_execution_orchestrator.browser.owner_registry import (
            browser_owner_registry,
        )

        browser_owner_registry.unregister(
            BrowserSessionHandle(
                session_id=session_id,
                execution_id=session.execution_id,
                journey_id=session.journey_id,
            )
        )
        session.execution_id = execution_id
        session.journey_id = journey_id
        self._authentication_handlers.pop(session_id, None)
        self._authentication_locks.pop(session_id, None)
        self._pending_authentication.discard(session_id)
        self._cooperative_handlers.pop(session_id, None)
        self._cooperative_locks.pop(session_id, None)
        handle = BrowserSessionHandle(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        browser_owner_registry.register(self, handle)
        return handle

    async def create_proof_session(
        self,
        *,
        room_session_id: UUID,
        execution_id: UUID,
        journey_id: UUID,
    ) -> BrowserSessionHandle:
        """Open a fresh context INSIDE the Room's browser (U-P2-03).

        Defect proof must not be polluted by working-session state:
        the proof context starts clean, seeded only with the Room's
        storage state (cookies/local storage) when the Room is
        authenticated — session storage and page state never carry.
        Closing a proof session closes only its context.
        """

        room = self._get_session(session_id=room_session_id)
        return await self._create_sibling_session(
            room, execution_id=execution_id, journey_id=journey_id,
            purpose="proof", js_capture=True,
        )

    async def create_worker_session(
        self,
        *,
        room_session_id: UUID,
        execution_id: UUID,
        journey_id: UUID,
        lane_index: int,
        js_capture: bool = False,
        reuse_room_auth: bool = True,
    ) -> BrowserSessionHandle:
        """Open a lane context INSIDE the Room's browser (doc 18 S1).

        A lane is a read-only window opened from the Room: seeded
        with the Room's storage state when the Room is authenticated
        (one login serves the run), born with the guardrail route
        handlers, and borrowable repeatedly - one lane session
        serves many pages sequentially. It never authenticates and
        never writes session state back to the Room. Closing it
        closes only its context. lane_index is the caller's lane
        number, recorded in the run's page records by the caller.
        js_capture is the caller's choice: slop lanes opt in (their
        per-page JS records feed the defect family); harness lanes
        leave it off.
        """

        room = self._get_session(session_id=room_session_id)
        return await self._create_sibling_session(
            room, execution_id=execution_id, journey_id=journey_id,
            purpose="worker", js_capture=js_capture, reuse_room_auth=reuse_room_auth,
        )

    async def _create_sibling_session(
        self,
        room: JourneyBrowserSession,
        *,
        execution_id: UUID,
        journey_id: UUID,
        purpose: str,
        js_capture: bool = False,
        reuse_room_auth: bool = True,
    ) -> BrowserSessionHandle:
        session_id = uuid4()
        artifact_directory = self._artifact_root / str(execution_id) / str(session_id)
        artifact_directory.mkdir(parents=True, exist_ok=True)
        storage_state = None
        authenticated_session = room.authenticated_session and reuse_room_auth
        if authenticated_session:
            storage_state = await room.context.storage_state()
        context = await room.browser.new_context(
            viewport={"width": 1280, "height": 900},
            device_scale_factor=1,
            accept_downloads=False,
            service_workers="block",
            storage_state=storage_state,  # type: ignore[arg-type]
        )
        context.set_default_timeout(room.timeout_ms)
        context.set_default_navigation_timeout(room.timeout_ms)
        page = await context.new_page()
        session = JourneyBrowserSession(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
            allowed_origins=room.allowed_origins,
            network_policy=room.network_policy,
            timeout_ms=room.timeout_ms,
            browser=room.browser,
            context=context,
            page=page,
            artifact_directory=artifact_directory,
            auth_only_origins=room.auth_only_origins,
            authenticated_session=authenticated_session,
            fixture_action_rules=room.fixture_action_rules,
            shares_browser=True,
            js_capture=js_capture,
            offsite=self.offsite,
        )
        if js_capture:
            # Capture parity (doc 24 section 4.2): a context whose
            # JS records are harvested installs the same rejection
            # hook as a capture session — proof contexts for
            # attribution parity, slop lane contexts because the
            # JS defect family is harvested per lane session.
            await context.add_init_script(JS_REJECTION_HOOK_SCRIPT)
        self._sessions[session_id] = session
        self._session_purposes[session_id] = purpose
        await context.route("**/*", lambda route: self._route_request(session, route))
        await context.route_web_socket(
            "**/*",
            lambda route: self._route_web_socket(session, route),
        )
        context.on("page", lambda new_page: self._schedule_page_setup(session, new_page))
        await self._configure_page(session, page)
        await start_trace(session)
        session.state = "open"
        handle = BrowserSessionHandle(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        from markettwin_execution_orchestrator.browser.owner_registry import (
            browser_owner_registry,
        )

        browser_owner_registry.register(self, handle)
        return handle

    def _get_session(
        self,
        *,
        session_id: UUID,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
    ) -> JourneyBrowserSession:
        try:
            session = self._sessions[session_id]
        except KeyError as exc:
            raise BrowserSessionNotFoundError(
                f"Browser session {session_id} does not exist."
            ) from exc

        if execution_id is not None and session.execution_id != execution_id:
            raise BrowserSessionOwnershipError("Browser session does not belong to this execution.")
        if journey_id is not None and session.journey_id != journey_id:
            raise BrowserSessionOwnershipError("Browser session does not belong to this Journey.")
        return session

    def bind_authentication_handler(
        self, handle: BrowserSessionHandle, handler: Callable[[], Awaitable[None]],
    ) -> None:
        """Bind a frozen identity verifier to this owned session only."""
        self._get_session(session_id=handle.session_id, execution_id=handle.execution_id,
                          journey_id=handle.journey_id)
        self._authentication_handlers[handle.session_id] = handler
        self._authentication_locks[handle.session_id] = asyncio.Lock()

    def bind_cooperative_pause_handler(
        self, handle: BrowserSessionHandle, handler: Callable[[], Awaitable[None]],
    ) -> None:
        self._get_session(session_id=handle.session_id, execution_id=handle.execution_id,
                          journey_id=handle.journey_id)
        self._cooperative_handlers[handle.session_id] = handler
        self._cooperative_locks[handle.session_id] = asyncio.Lock()

    async def cooperative_checkpoint(self, handle: BrowserSessionHandle) -> None:
        handler = self._cooperative_handlers.get(handle.session_id)
        if handler is not None:
            async with self._cooperative_locks[handle.session_id]:
                await handler()

    async def cooperative_pause_ready(self, handle: BrowserSessionHandle) -> bool:
        """Safe boundary probe; never recursively invokes action/pause handlers."""
        session = self._get_session(session_id=handle.session_id,
                                    execution_id=handle.execution_id, journey_id=handle.journey_id)
        async with session.lock:
            if session.state != "open" or session.control_mode != "agent":
                return False
            try:
                validate_browsing_url(session, session.page.url)
            except BrowserPolicyError:
                return False
            return not await self._has_authentication_challenge(session)

    async def has_authentication_challenge(
        self, handle: BrowserSessionHandle, *, include_pending: bool = True,
    ) -> bool:
        """Read challenge presence only; never inspect credentials or assume identity."""
        session = self._get_session(session_id=handle.session_id,
                                    execution_id=handle.execution_id,
                                    journey_id=handle.journey_id)
        return await self._has_authentication_challenge(session, include_pending=include_pending)

    async def _has_authentication_challenge(
        self, session: JourneyBrowserSession, *, include_pending: bool = True,
    ) -> bool:
        if ((include_pending and session.session_id in self._pending_authentication)
                or session.is_auth_only_url(session.page.url)):
            return True
        if session.page.url == "about:blank":
            return False
        inspection = await inspect_sensitive_challenge(session.page)
        if inspection.timed_out:
            # A check that cannot complete is not a challenge (Fix C):
            # record it on the session so the inspecting workflow can
            # drain it onto the page state; never raise it here.
            session.challenge_check_timed_out = True
        if inspection.active:
            return True
        # Email-only login and SSO chooser screens need an actual auth form;
        # ordinary navigation links and newsletter fields are not challenges.
        if await session.page.locator("form:visible").filter(
            has=session.page.locator('input[type="email"]:visible, input[name="username"]:visible'),
        ).filter(has=session.page.get_by_role(
            "button", name=_AUTH_BUTTON_PATTERN,
        )).count():
            return True
        if await session.page.get_by_role(
            "heading", name=_AUTH_HEADING_PATTERN,
        ).count() and await session.page.get_by_role(
            "button", name=_AUTH_CONTINUE_PATTERN,
        ).count():
            return True
        try:
            async with asyncio.timeout(SENSITIVE_CHALLENGE_TIMEOUT_SECONDS):
                signals = await self.discovery_page_signals(session_id=session.session_id)
        except TimeoutError:
            raise BrowserTimeoutError("Timed out inspecting the page for a checkpoint.") from None
        return is_discovery_checkpoint(**signals)

    async def human_continuation_ready(self, handle: BrowserSessionHandle) -> bool:
        """Validate safe continuation, without claiming an authenticated identity."""
        session = self._get_session(session_id=handle.session_id,
                                    execution_id=handle.execution_id, journey_id=handle.journey_id)
        validate_target_url(session.page.url, session.allowed_origins, session.network_policy)
        return (session.state == "open" and session.control_mode == "verifying"
                and not await self._has_authentication_challenge(session, include_pending=False))

    async def verify_handoff_destination(
        self, handle: BrowserSessionHandle, *, expected_url: str,
    ) -> bool:
        """Confirm a frozen audit route on the same session before reopening capture."""
        session = self._get_session(session_id=handle.session_id,
                                    execution_id=handle.execution_id, journey_id=handle.journey_id)
        async with session.lock:
            try:
                expected = validate_target_url(
                    expected_url, session.allowed_origins, session.network_policy,
                )
                if not await self.human_continuation_ready(handle):
                    return False

                def route_identity(value: str) -> tuple[str, str, str, str]:
                    checked = validate_target_url(
                        value, session.allowed_origins, session.network_policy,
                    )
                    parsed = urlsplit(checked.href)
                    fragment = parsed.fragment if parsed.fragment.startswith(("/", "!/")) else ""
                    return checked.origin, parsed.path.rstrip("/"), parsed.query, fragment

                if route_identity(session.page.url) == route_identity(expected.href):
                    return True
                # The operator can land on a post-login page. Read the original
                # audit route again before attributing any observations to it.
                await resolve_and_validate_host(expected.hostname, session.network_policy)
                response = await session.page.goto(
                    expected.href, wait_until="domcontentloaded", timeout=session.timeout_ms,
                )
                return (
                    response is not None and response.ok
                    and route_identity(session.page.url) == route_identity(expected.href)
                    and await self.human_continuation_ready(handle)
                )
            except (BrowserActionError, BrowserPolicyError, PlaywrightError):
                return False

    def take_human_session_snapshot(
        self, *, run_id: UUID, target_id: UUID, case_id: str,
    ) -> AuthSessionSnapshot:
        return self._auth_session_broker.take_human_session(
            run_id=run_id, target_id=target_id, case_id=case_id,
        )

    def revoke_human_session_snapshots(self, *, run_id: UUID, target_id: UUID) -> None:
        self._auth_session_broker.revoke_human_sessions(run_id=run_id, target_id=target_id)

    async def capture_human_session(
        self, handle: BrowserSessionHandle, *, run_id: UUID, target_id: UUID,
    ) -> bool:
        """Capture only after released control and safe continuation, never a role claim."""
        session = self._get_session(session_id=handle.session_id,
                                    execution_id=handle.execution_id, journey_id=handle.journey_id)
        async with session.lock:
            if not await self.human_continuation_ready(handle):
                return False
            origin = validate_target_url(
                session.page.url, session.allowed_origins, session.network_policy,
            ).origin
            scope = HumanSessionScope(run_id=run_id, target_id=target_id, origin=origin)
            await self._auth_session_broker.capture_human_session(
                scope=scope,
                context=cast(Any, session.context), page=session.page,
            )
            self._auth_session_broker.retain_for_task_verification(scope)
            return True

    async def _authentication_checkpoint(
        self, session: JourneyBrowserSession, *, lock_held: bool = False, force: bool = False,
    ) -> None:
        handler = self._authentication_handlers.get(session.session_id)
        if handler is None or session.control_mode != "agent":
            return
        if not force and not await self._has_authentication_challenge(session):
            return
        # Publish the challenge before dropping the browser lock. Concurrent
        # tools must join this handoff rather than dispatch on the old page.
        self._pending_authentication.add(session.session_id)
        # The owner service and verifier take the browser lock themselves. No
        # action is dispatched while waiting; after a dispatched navigation/click
        # we continue from the resulting page and never replay that action.
        if lock_held:
            session.lock.release()
        try:
            async with self._authentication_locks[session.session_id]:
                if await self._has_authentication_challenge(session):
                    try:
                        await handler()
                    finally:
                        self._pending_authentication.discard(session.session_id)
        finally:
            if lock_held:
                await session.lock.acquire()
        self._ensure_agent_control(session)

    @staticmethod
    def _ensure_agent_control(session: JourneyBrowserSession) -> None:
        if session.offsite is not None:
            session.offsite.ensure_journey(session.journey_id)
        if session.control_mode != "agent":
            raise HumanControlActiveError(
                "Agent browser tools are disabled during human-control handoff."
            )
        if session.state != "open":
            raise BrowserSessionStateError(
                f"Browser session is not open; current state is {session.state}."
            )
        if session.is_auth_only_url(session.page.url):
            raise BrowserActionBlockedError("Authentication-only origins require human control.")

    def require_agent_control(self, handle: BrowserSessionHandle) -> None:
        """Reject sensitive-phase tool calls before their summaries are recorded."""
        self._ensure_agent_control(
            self._get_session(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
            )
        )

    @asynccontextmanager
    async def _agent_control_action(
        self, session: JourneyBrowserSession
    ) -> AsyncGenerator[None, None]:
        handle = BrowserSessionHandle(session.session_id, session.execution_id, session.journey_id)
        if session.offsite is not None:
            await session.offsite.checkpoint(session.page.url, session.journey_id, session.execution_id)
        await self.cooperative_checkpoint(handle)
        await self._authentication_checkpoint(session)
        async with session.lock:
            await self._authentication_checkpoint(session, lock_held=True)
            self._ensure_agent_control(session)
            if session.offsite is not None and session.page.url != "about:blank":
                await self._validate_resting_page(session)
            yield

    @staticmethod
    async def _validate_resting_page(session: JourneyBrowserSession) -> None:
        """Validate the page a session is resting on before an agent action.

        A resting page that is not a public URL at all (a browser error
        page, a blob:/data: page) can never become valid, and refusing
        here would also block the navigation that could rescue the lane,
        so park the page on about:blank and let the action proceed. A
        public page that is merely off-origin still refuses, unchanged.
        """
        try:
            validate_browsing_url(session, session.page.url)
        except TargetUrlValidationError as original_error:
            try:
                async with asyncio.timeout(_RESTING_PAGE_RESET_TIMEOUT_SECONDS):
                    await session.page.goto("about:blank")
            except Exception:
                pass
            if session.page.url == "about:blank":
                return
            try:
                validate_browsing_url(session, session.page.url)
            except TargetUrlValidationError:
                raise original_error from None

    @staticmethod
    async def _require_keyboard_focus(session: JourneyBrowserSession, locator: Locator) -> None:
        if session.keyboard_only and not await locator.evaluate(
            "element => element === element.ownerDocument.activeElement"
        ):
            raise BrowserActionError("Use Tab to focus this control before activating it.",
                                     reason_code="keyboard_focus_required")

    def set_keyboard_only(self, handle: BrowserSessionHandle) -> None:
        session = self._get_session(session_id=handle.session_id,
            execution_id=handle.execution_id, journey_id=handle.journey_id)
        self._ensure_agent_control(session)
        session.keyboard_only = True

    @staticmethod
    async def _track_pointer(session: JourneyBrowserSession, locator: Locator) -> None:
        """Move the actual pointer and publish each position before the semantic action."""
        if getattr(session, "keyboard_only", False):
            return
        generation = session.control_generation

        def ensure_control() -> None:
            if session.control_mode != "agent" or session.control_generation != generation:
                raise HumanControlActiveError("Agent pointer control was revoked.")

        ensure_control()
        try:
            await locator.scroll_into_view_if_needed(timeout=250)
            ensure_control()
            box = await locator.bounding_box(timeout=250)
        except PlaywrightError:
            return
        finally:
            ensure_control()
        viewport = session.page.viewport_size
        if box and viewport:
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            if not (0 <= x < viewport["width"] and 0 <= y < viewport["height"]):
                return
            previous = session.live_click_target
            start_x = previous.x if previous else 0.0
            start_y = previous.y if previous else 0.0
            for step in range(1, 9):
                ensure_control()
                px = start_x + (x - start_x) * step / 8
                py = start_y + (y - start_y) * step / 8
                await session.page.mouse.move(px, py)
                ensure_control()
                # Publish positions only after the browser accepted the movement.
                session.live_click_target = LiveClickTarget(
                    px, py, viewport["width"], viewport["height"],
                    session.page.url, monotonic(),
                )
                session.live_view_changed.set()
                if step < 8:
                    await asyncio.sleep(1 / 60)

    async def _route_request(
        self,
        session: JourneyBrowserSession,
        route: Route,
    ) -> None:
        try:
            request = route.request
            main = self._is_main_frame_request(request)
            if session.offsite is not None:
                if session.control_mode != "human":
                    await session.offsite.checkpoint(
                        session.page.url, session.journey_id, session.execution_id,
                    )
                if session.control_mode == "human":
                    try:
                        validated = validate_human_url(session, request.url)
                    except BrowserPolicyError:
                        if main:
                            raise
                        if is_handoff_provider(session.page.url):
                            validated = public_url(request.url)
                        elif (self._is_strict_target(session, session.page.url)
                              and request.method == "GET"
                              and request.resource_type in {"script", "stylesheet", "font"}):
                            # Target sign-in pages also load their UI from public CDNs.
                            validated = public_url(request.url)
                        else:
                            raise
                else:
                    if main and (is_handoff_provider(request.url)
                                 or session.is_auth_only_url(request.url)):
                        session.provider_handoff_url = public_url(request.url).href
                        self._pending_authentication.add(session.session_id)
                        raise BrowserActionBlockedError("Provider navigation requires human control.")
                    if (not self._is_strict_target(session, session.page.url)
                            and session.page.url != "about:blank"
                            and request.method not in {"GET", "HEAD"}):
                        raise BrowserActionBlockedError("Outside pages cannot submit requests.")
                    try:
                        validated = validate_target_url(request.url, session.allowed_origins, session.network_policy)
                    except BrowserPolicyError:
                        if main and is_handoff_provider(request.url):
                            session.provider_handoff_url = public_url(request.url).href
                            self._pending_authentication.add(session.session_id)
                            raise BrowserActionBlockedError("Provider navigation requires human control.")
                        if main:
                            if request.method != "GET":
                                raise BrowserActionBlockedError("Outside submissions are not allowed.")
                            validated = await session.offsite.navigate(
                                request.url, session.page.url, session.journey_id, session.execution_id,
                            )
                        else:
                            # Subresources follow the guarded-freedom rule
                            # (see _validated_subresource_url): public loads
                            # are free; submissions and provider assets are not.
                            validated = self._validated_subresource_url(session, request)
                    if main:
                        previous = urlsplit(session.page.url).hostname
                        # A journey's first load is its start, not a domain
                        # change; the run's own page events record it. Only a
                        # move between two real pages is recorded here, so a
                        # bookkeeping write never gates a run's first page.
                        if previous is not None and previous != validated.hostname:
                            await session.offsite.record("offsite.domain_changed", {
                                "from": previous or "start", "to": validated.hostname,
                                "decision": "continue", "reason": "Navigation passed browsing policy.",
                            }, session.journey_id, session.execution_id)
                await resolve_and_validate_host(validated.hostname, (
                    session.network_policy if self._is_strict_target(session, request.url)
                    else "public_only"
                ))
                await self._record_third_party_domain(session, request, validated)
                await route.continue_()
                return
            if session.control_mode != "human" and session.is_auth_only_url(route.request.url):
                if (route.request.is_navigation_request()
                        and route.request.frame.parent_frame is None):
                    self._pending_authentication.add(session.session_id)
                raise BrowserActionBlockedError("Authentication-only request blocked.")
            validated = self._validated_request_url(session, route.request)
            await resolve_and_validate_host(
                validated.hostname,
                session.network_policy if self._is_strict_target(session, route.request.url)
                else "public_only",
            )
            await route.continue_()
        except Exception as error:
            if isinstance(error, SuspiciousEgressError):
                await self._record_egress_block(session, error, route.request.url)
            self._record_network_failure(
                session, error, route.request.url,
                resource=not self._is_main_frame_request(route.request),
            )
            await route.abort("blockedbyclient")

    @staticmethod
    def _is_strict_target(session: JourneyBrowserSession, url: str) -> bool:
        try:
            validate_target_url(url, session.allowed_origins, session.network_policy)
            return True
        except BrowserPolicyError:
            return False

    async def _navigation_url(self, session: JourneyBrowserSession, url: str) -> ValidatedUrl:
        try:
            return validate_target_url(url, session.allowed_origins, session.network_policy)
        except BrowserPolicyError:
            if session.offsite is None:
                raise
            session.offsite.ensure_journey(session.journey_id)
            try:
                result = public_url(url)
                await resolve_and_validate_host(result.hostname, "public_only")
                return result
            except (BrowserPolicyError, ValueError):
                await session.offsite.stop(
                    "Outside destination is not a public HTTP(S) address.",
                    session.page.url, url, session.journey_id, session.execution_id,
                )
                raise

    @staticmethod
    def _network_destination(
        session: JourneyBrowserSession, url: str,
    ) -> NetworkDiagnosticDestination:
        try:
            mapped = url.replace("wss://", "https://", 1).replace("ws://", "http://", 1)
            validate_target_url(mapped, session.allowed_origins, session.network_policy)
            return "authorized_target"
        except (ValueError, BrowserPolicyError):
            try:
                hostname = urlsplit(url).hostname
                if hostname and is_known_captcha_host(hostname):
                    return "known_provider"
            except (ValueError, BrowserPolicyError):
                pass
        return "unknown_third_party"

    @classmethod
    def _record_network_failure(
        cls, session: JourneyBrowserSession, error: Exception, url: str, *, resource: bool = True,
    ) -> None:
        if session.control_mode != "human":
            return
        destination = cls._network_destination(session, url)
        reason: NetworkDiagnosticReason = "browser_transport_failed"
        if isinstance(error, UnsafeDestinationAddressError):
            reason = "unsafe_destination_ip"
        elif isinstance(error, HostResolutionError):
            reason = "dns_resolution_failed"
        elif isinstance(error, BrowserPolicyError):
            reason = "target_origin_denied"
            if resource and destination == "known_provider":
                try:
                    validate_captcha_subresource(url)
                except TargetUrlValidationError:
                    pass
                else:
                    reason = "captcha_resource_denied"
        session.human_network_diagnostics.record(reason, destination)

    def _on_egress_failure(
        self, session_id: UUID, reason: NetworkDiagnosticReason,
        scheme: str, hostname: str, port: int,
    ) -> None:
        session = self._sessions.get(session_id)
        if session is None or session.control_mode != "human":
            return
        host = f"[{hostname}]" if ":" in hostname else hostname
        destination = self._network_destination(session, f"{scheme}://{host}:{port}")
        session.human_network_diagnostics.record(reason, destination)

    def human_network_diagnostics(
        self, *, handle: BrowserSessionHandle,
    ) -> tuple[dict[str, str | int], ...]:
        """Return only volatile fixed labels; caller must enforce the active viewer lease."""
        session = self._get_session(
            session_id=handle.session_id, execution_id=handle.execution_id,
            journey_id=handle.journey_id,
        )
        if session.state != "open" or session.control_mode != "human":
            return ()
        return session.human_network_diagnostics.snapshot()

    @staticmethod
    def _is_main_frame_request(request: Request) -> bool:
        # Playwright has no frame yet for a popup's first navigation request.
        # Treat that request as a top-level navigation: it needs target authority.
        main_frame = request.is_navigation_request()
        if main_frame:
            try:
                main_frame = request.frame.parent_frame is None
            except PlaywrightError:
                main_frame = True
        return main_frame

    async def _record_egress_block(
        self,
        session: JourneyBrowserSession,
        error: SuspiciousEgressError,
        url: str,
    ) -> None:
        """Persist one suspicious-egress block on the Lead-review surface.

        The block itself is the enforcement; the record is audit only, so
        a failed record never changes the request's fate.
        """

        offsite = getattr(session, "offsite", None)
        record = getattr(offsite, "record", None)
        if record is None:
            return
        try:
            await record("browser.egress_blocked", {
                "decision": "blocked", "reason": error.reason,
                "from": safe_address(session.page.url), "to": safe_address(url),
            }, session.journey_id, session.execution_id)
        except Exception:
            pass

    async def _record_third_party_domain(
        self,
        session: JourneyBrowserSession,
        request: Request,
        validated: ValidatedUrl,
    ) -> None:
        """Record the first subresource load from each outside host.

        Navigations already reach the Lead through the offsite review;
        this covers the quieter half — the third parties a page itself
        talks to — once per host per run, on the same surface. Audit
        only: recording never gates the request.
        """

        offsite = getattr(session, "offsite", None)
        seen = getattr(offsite, "subresource_hosts", None)
        record = getattr(offsite, "record", None)
        if seen is None or record is None or self._is_main_frame_request(request):
            return
        if validated.hostname in seen:
            return
        try:
            target_hosts = {
                normalize_hostname(origin.hostname)
                for origin in session.allowed_origins
            }
        except TargetUrlValidationError:
            target_hosts = set()
        if validated.hostname in target_hosts:
            return
        seen.add(validated.hostname)
        try:
            await record("browser.third_party_domain", {
                "decision": "allow", "host": validated.hostname,
                "from": safe_address(session.page.url),
            }, session.journey_id, session.execution_id)
        except Exception:
            pass

    def _validated_request_url(
        self,
        session: JourneyBrowserSession,
        request: Request,
    ) -> ValidatedUrl:
        """Approve a navigation to the target origin, or any subresource
        the guarded-freedom rule allows (see _validated_subresource_url)."""
        if not self._is_main_frame_request(request):
            return self._validated_subresource_url(session, request)
        return validate_target_url(
            request.url,
            session.allowed_origins,
            session.network_policy,
        )

    def _validated_subresource_url(
        self,
        session: JourneyBrowserSession,
        request: Request,
    ) -> ValidatedUrl:
        """Approve one non-navigation request under the guarded-freedom rules.

        Order matters: captcha widgets keep their exception — including
        their token calls, which are POSTs, so the method is not gated;
        the submission scan is what guards them now. The target's own
        assets keep today's strict validation (including its form posts).
        Sign-in and CAPTCHA provider hosts never serve assets to the
        agent. Any other public load is free, and any other public
        submission is free unless it carries sensitive data off the
        target's origin (owner rule, 2026-11-24: allow by default, block
        the suspicious send and record it). Public still means the
        location rules apply: no private, loopback or link-local address
        is ever approved here.
        """
        try:
            captcha_url = validate_captcha_subresource(request.url)
        except TargetUrlValidationError:
            captcha_url = None
        if captcha_url is not None:
            ensure_unsuspicious_submission(
                request.method, getattr(request, "post_data", None),
            )
            return captcha_url
        if is_handoff_provider(request.url):
            raise BrowserPolicyError("Provider assets require human control.")
        try:
            return validate_target_url(
                request.url,
                session.allowed_origins,
                session.network_policy,
            )
        except BrowserPolicyError:
            pass
        if request.method in {"GET", "HEAD"}:
            return public_url(request.url)
        ensure_unsuspicious_submission(
            request.method, getattr(request, "post_data", None),
        )
        return public_url(request.url)

    async def _route_web_socket(
        self,
        session: JourneyBrowserSession,
        route: WebSocketRoute,
    ) -> None:
        try:
            http_url = route.url.replace("wss://", "https://", 1).replace("ws://", "http://", 1)
            if session.control_mode != "human" and session.is_auth_only_url(http_url):
                raise BrowserActionBlockedError("Authentication-only socket blocked.")
            try:
                validated = validate_captcha_subresource(http_url)
            except TargetUrlValidationError:
                validated = validate_websocket_url(
                    route.url,
                    session.allowed_origins,
                    session.network_policy,
                )
            await resolve_and_validate_host(
                validated.hostname,
                session.network_policy,
            )
            route.connect_to_server()
        except Exception as error:
            self._record_network_failure(session, error, route.url)
            await route.close(
                code=1008,
                reason="Blocked by MarketTwin network policy",
            )

    def _schedule_page_setup(
        self,
        session: JourneyBrowserSession,
        page: Page,
    ) -> None:
        task = asyncio.create_task(self._configure_page(session, page))

        def completed(task: asyncio.Task[None]) -> None:
            if not task.cancelled() and task.exception() is not None:
                session.page_setup_failures += 1
                self._record_page_error(session, "Popup page setup failed.")

        task.add_done_callback(completed)

    async def _configure_page(
        self,
        session: JourneyBrowserSession,
        page: Page,
    ) -> None:
        if len(session.context.pages) > self._max_pages_per_session:
            self._record_page_error(
                session, "Popup blocked: Journey exceeded the configured page limit."
            )
            await page.close()
            return

        session.page = page
        page.on(
            "console",
            lambda message: self._on_console(session, message.type, message.text),
        )
        page.on(
            "pageerror",
            lambda error: self._record_page_error(
                session, str(error),
                stack=getattr(error, "stack", None),
            ),
        )
        page.on("requestfailed", lambda request: self._on_request_failed(session, request))
        page.on("dialog", lambda dialog: self._dismiss_dialog(session, dialog))
        page.on(
            "download",
            lambda _download: self._record_page_error(
                session, "Download blocked by MarketTwin policy."
            ),
        )

    @staticmethod
    def _js_capture_active(session: JourneyBrowserSession) -> bool:
        """Structured JS capture (U-P6-03) runs in agent mode when
        capture is on; on authenticated sessions only for sessions
        that opted in (slop runs — message + stack + URL only)."""

        return bool(
            session.capture_enabled
            and session.control_mode == "agent"
            and (not session.authenticated_session or session.js_capture)
        )

    @staticmethod
    def _record_page_error(
        session: JourneyBrowserSession, message: str,
        stack: str | None = None,
    ) -> None:
        if (session.capture_enabled and session.control_mode == "agent"
                and not session.authenticated_session):
            session.event_buffer.record_page_error(message)
        if session.js_capture and BrowserController._js_capture_active(session):
            session.event_buffer.record_js(JsErrorRecord(
                kind="uncaught", message=message, stack=stack,
                url=session.page.url if session.page is not None else "",
            ))

    @staticmethod
    def _on_console(session: JourneyBrowserSession, kind: str, text: str) -> None:
        if (kind == "error" and session.capture_enabled and session.control_mode == "agent"
                and not session.authenticated_session):
            session.event_buffer.record_console_error(text)
        if (kind == "error" and session.js_capture
                and BrowserController._js_capture_active(session)):
            session.event_buffer.record_js(JsErrorRecord(
                kind="console_error", message=text, stack=None,
                url=session.page.url if session.page is not None else "",
            ))

    async def discovery_page_signals(self, *, session_id: UUID) -> dict[str, Any]:
        """Read bounded checkpoint signals; never send them to a model or logs."""
        session = self._get_session(session_id=session_id)
        return await session.page.evaluate("""() => ({
            text: (document.body?.innerText || '').slice(0, 8000),
            scripts: Array.from(document.scripts).slice(0, 100).map(s => s.src),
            controls: document.querySelectorAll('button,a[href],input:not([type=hidden]),select,textarea').length
        })""")

    async def probe_page(self, *, session_id: UUID) -> dict[str, Any]:
        """Run the slop probe (U-P6-04): raw measurements of the
        current page — elements, images, overflow, word count."""

        from markettwin_execution_orchestrator.slop.probe import PROBE_SCRIPT

        session = self._get_session(session_id=session_id)
        async with self._agent_control_action(session):
            return await session.page.evaluate(PROBE_SCRIPT)

    async def harvest_js_records(
        self, *, session_id: UUID,
    ) -> list[JsErrorRecord]:
        """Collect unhandled rejections the init hook gathered since
        the last harvest (U-P6-03) and return ALL structured records."""

        session = self._get_session(session_id=session_id)
        session.last_rejection_harvest_failed = False
        if session.js_capture:
            try:
                snapshot = await session.page.evaluate(
                    "() => ({ doc: window.__mt_rejection_doc || '',"
                    " doc_url: window.__mt_rejection_doc_url || '',"
                    " items: window.__mt_rejections || [] })"
                )
            except Exception:
                session.rejection_harvest_failures += 1
                session.last_rejection_harvest_failed = True
                snapshot = {"doc": "", "doc_url": "", "items": []}
            # The init hook resets the array on every new document,
            # so the watermark is only valid for the document that
            # produced it. Keying the watermark to the document id
            # keeps page B's first rejections from being sliced away
            # by page A's count.
            document = str(snapshot.get("doc", ""))
            if document != session.rejections_document:
                session.rejections_document = document
                session.rejections_harvested = 0
            collected = list(snapshot.get("items") or [])
            new_items = collected[session.rejections_harvested:]
            session.rejections_harvested = len(collected)
            doc_url = str(snapshot.get("doc_url", ""))
            for item in new_items:
                url = str(item.get("url") or "") or doc_url
                if not url:
                    session.rejections_dropped += 1
                    continue
                session.event_buffer.record_js(JsErrorRecord(
                    kind="unhandled_rejection",
                    message=str(item.get("message", "")),
                    stack=item.get("stack"),
                    url=url,
                ))
        return list(session.event_buffer.js_records)

    def js_capture_diagnostics(self, *, session_id: UUID) -> dict[str, int | bool]:
        session = self._get_session(session_id=session_id)
        return {
            "rejections_dropped": session.rejections_dropped,
            "rejection_harvest_failures": session.rejection_harvest_failures,
            "last_rejection_harvest_failed": session.last_rejection_harvest_failed,
            "page_setup_failures": session.page_setup_failures,
        }

    def take_challenge_check_timeout(self, *, session_id: UUID) -> bool:
        """Return and clear the challenge-check timeout recorded since
        the last take (Fix C): a bounded challenge inspection that
        could not answer is surfaced on the page state by the caller,
        never raised into the crawl."""
        session = self._get_session(session_id=session_id)
        timed_out = session.challenge_check_timed_out
        session.challenge_check_timed_out = False
        return timed_out

    @staticmethod
    def _on_request_failed(session: JourneyBrowserSession, request: Request) -> None:
        if session.control_mode == "human":
            session.human_network_diagnostics.record(
                "browser_transport_failed", BrowserController._network_destination(
                    session, request.url,
                ),
            )
        if (session.capture_enabled and session.control_mode == "agent"
                and not session.authenticated_session):
            session.event_buffer.record_failed_request(
                FailedRequestRecord(
                    url=f"{urlsplit(request.url).scheme}://"
                    f"{urlsplit(request.url).netloc.rsplit('@', 1)[-1]}",
                    method=request.method,
                    resource_type=request.resource_type,
                    error_text="Network request failed",
                )
            )

    @staticmethod
    def _dismiss_dialog(session: JourneyBrowserSession, dialog: Dialog) -> None:
        BrowserController._record_page_error(
            session, f'Unexpected browser dialog dismissed: "{dialog.message}"'
        )
        asyncio.create_task(dialog.dismiss())

    async def get_state(
        self,
        *,
        session_id: UUID,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
        observe: bool = True,
    ) -> BrowserActionResult:
        """Return the current compact browser observation."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            session.next_action_number()
            if not observe:
                return BrowserActionResult(action="get_state", observation=None)
            screenshot = await capture_screenshot(
                session,
                label="state",
            )
            return BrowserActionResult(
                action="get_state",
                observation=await build_observation(session, screenshot_path=screenshot),
            )

    async def get_form_state(
        self,
        *,
        session_id: UUID,
        scope_role: ScopeRole,
        scope_name: str,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
        observe: bool = True,
    ) -> BrowserActionResult:
        """Inspect bounded form metadata without returning entered values."""
        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            validate_browsing_url(session, session.page.url)
            root = await scoped_root(session.page, scope_role=scope_role, scope_name=scope_name)
            # A named scope was required above, so this is a Locator.
            assert isinstance(root, Locator)
            fields, more_available = await inspect_form_fields(root)
            session.next_action_number()
            if not observe:
                return BrowserActionResult(action="get_form_state", observation=None)
            screenshot = await capture_screenshot(session, label="form-state")
            snapshot = json.dumps([asdict(field) for field in fields])
            return BrowserActionResult(
                action="get_form_state",
                observation=await build_observation(
                    session,
                    screenshot_path=screenshot,
                    aria_snapshot_override=snapshot,
                    form_fields=fields,
                    more_available=more_available,
                ),
            )

    async def read_assertion(
        self,
        *,
        session_id: UUID,
        assertion: ExpectedAssertion,
        timeout_ms: int = 1500,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
        observe: bool = True,
        approved_values: tuple[str, ...] = (),
        run_mode: str | None = None,
    ) -> tuple[BrowserActionResult, AssertionObservation]:
        """Read an assertion under the same origin, ownership and control guards."""
        if timeout_ms < 1 or timeout_ms > 5000:
            raise BrowserActionError("Assertion timeout must be between 1 and 5000 milliseconds.")
        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            validate_browsing_url(session, session.page.url)
            session.next_action_number()
            if assertion.target is not None:
                target = assertion.target
                root = await scoped_root(
                    session.page,
                    scope_role=target.scope_role,
                    scope_name=target.scope_name,
                )
                locator = semantic_locator(
                    root,
                    role=target.role,
                    name=target.name,
                    label=target.label,
                    text=target.text,
                )
                if await locator.count() == 1 and await locator.is_visible():
                    await locator.scroll_into_view_if_needed()
                elif isinstance(root, Locator) and await root.is_visible():
                    await root.scroll_into_view_if_needed()
            if assertion.origin == "user_approved" and assertion.oracle in {
                "visible_text", "visible", "enabled", "url_path_v1", "title",
            }:
                started = asyncio.get_running_loop().time()
                first, second = await repeat_read_only_assertion(
                    session.page, assertion, timeout_ms=min(timeout_ms, 2000),
                    minimum_interval_ms=500,
                    approved_values=approved_values, run_mode=run_mode,
                )
                stable = (first.status, first.observed_value, first.reason) == (
                    second.status, second.observed_value, second.reason,
                )
                outcome = AssertionObservation(
                    status=second.status if stable else "unverified",
                    observed_value=second.observed_value if stable else None,
                    elapsed_ms=int((asyncio.get_running_loop().time() - started) * 1000),
                    reason=second.reason if stable else "inspection_failed",
                )
            else:
                outcome = await evaluate_assertion(
                    session.page, assertion, timeout_ms=timeout_ms,
                    approved_values=approved_values, run_mode=run_mode,
                )
            if not observe:
                return (
                    BrowserActionResult(action="assertion", observation=None),
                    outcome,
                )
            screenshot = await capture_screenshot(session, label="assertion")
            result = BrowserActionResult(
                action="assertion",
                observation=await build_observation(
                    session,
                    screenshot_path=screenshot,
                ),
            )
            return result, outcome

    async def focus_next(
        self,
        *,
        session_id: UUID,
        reverse: bool = False,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
        observe: bool = True,
    ) -> BrowserActionResult:
        """Move keyboard focus one stop; no activation keys are accepted."""
        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            validate_target_url(session.page.url, session.allowed_origins, session.network_policy)
            session.next_action_number()
            await session.page.keyboard.press("Shift+Tab" if reverse else "Tab")
            if not observe:
                return BrowserActionResult(action="focus_next", observation=None)
            screenshot = await capture_screenshot(session, label="focus-next")
            return BrowserActionResult(
                action="focus_next",
                observation=await build_observation(session, screenshot_path=screenshot),
            )

    async def focused_element_state(
        self,
        *,
        session_id: UUID,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
    ) -> dict[str, Any] | None:
        """The focused element's identity + indicator style (read-only).

        For the persona keyboard walk (doc 24 section 3.1): which
        element holds focus — role, accessible name, and its ordinal
        among focusable elements, the same ordinal the style baseline
        is keyed by — plus the style facts an indicator judgement
        diffs against that baseline. None when nothing holds focus.
        """

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        return await session.page.evaluate(
            """() => {
              const focusable = 'a[href], button:not([disabled]),'
                + ' input:not([disabled]):not([type="hidden"]),'
                + ' select:not([disabled]), textarea:not([disabled]),'
                + ' [tabindex]:not([tabindex="-1"])';
              const el = document.activeElement;
              if (!el || el === document.body) return null;
              const all = Array.from(document.querySelectorAll(focusable));
              const style = window.getComputedStyle(el);
              const name = (el.getAttribute('aria-label')
                || el.innerText || el.textContent || '')
                .trim().replace(/\\s+/g, ' ').slice(0, 200);
              return {
                role: el.getAttribute('role') || el.tagName.toLowerCase(),
                name,
                ordinal: all.indexOf(el),
                outline_style: style.outlineStyle,
                outline_width: style.outlineWidth,
                box_shadow: style.boxShadow,
                background: style.backgroundColor,
                border_width: style.borderTopWidth,
                border_color: style.borderTopColor,
              };
            }"""
        )

    async def focusable_style_baseline(
        self,
        *,
        session_id: UUID,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Pre-focus computed styles of every focusable element, keyed
        by the ordinal focused_element_state reports — the baseline an
        indicator judgement diffs against (doc 24 section 3.1)."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        return await session.page.evaluate(
            """() => {
              const focusable = 'a[href], button:not([disabled]),'
                + ' input:not([disabled]):not([type="hidden"]),'
                + ' select:not([disabled]), textarea:not([disabled]),'
                + ' [tabindex]:not([tabindex="-1"])';
              const baseline = {};
              document.querySelectorAll(focusable).forEach((el, index) => {
                if (index >= 200) return;
                const style = window.getComputedStyle(el);
                baseline[String(index)] = {
                  outline_style: style.outlineStyle,
                  outline_width: style.outlineWidth,
                  box_shadow: style.boxShadow,
                  background: style.backgroundColor,
                  border_width: style.borderTopWidth,
                  border_color: style.borderTopColor,
                };
              });
              return baseline;
            }"""
        )

    async def emulate_network(
        self,
        *,
        session_id: UUID,
        latency_ms: int,
        download_bps: int,
        upload_bps: int,
    ) -> None:
        """Apply real network throttling to a session (persona
        conditions, U-P5-04) via CDP Network.emulateNetworkConditions."""

        session = self._get_session(session_id=session_id)
        # The CDP session is deliberately NOT detached afterwards:
        # detaching clears the emulated conditions (verified against
        # Chromium — navigation returns to full speed the moment the
        # session detaches). It is reaped when the context closes.
        cdp = await session.context.new_cdp_session(session.page)
        await cdp.send("Network.enable")
        await cdp.send("Network.emulateNetworkConditions", {
            "offline": False,
            "latency": latency_ms,
            # The condition block stores bytes/second; CDP takes the
            # same unit for throughput.
            "downloadThroughput": download_bps,
            "uploadThroughput": upload_bps,
        })

    async def set_viewport(
        self,
        *,
        session_id: UUID,
        preset: Literal["mobile320", "desktop1280"],
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
        observe: bool = True,
    ) -> BrowserActionResult:
        """Use a fixed fixture-tested viewport preset."""
        if preset not in {"mobile320", "desktop1280"}:
            raise BrowserActionError("Viewport preset must be mobile320 or desktop1280.")
        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            validate_browsing_url(session, session.page.url)
            session.next_action_number()
            await session.page.set_viewport_size(
                {
                    "width": 320 if preset == "mobile320" else 1280,
                    "height": 800,
                }
            )
            if not observe:
                return BrowserActionResult(action="set_viewport", observation=None)
            screenshot = await capture_screenshot(session, label="viewport")
            return BrowserActionResult(
                action="set_viewport",
                observation=await build_observation(session, screenshot_path=screenshot),
            )

    async def navigate(
        self,
        *,
        session_id: UUID,
        url: str,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
        observe: bool = True,
    ) -> BrowserActionResult:
        """Navigate to an explicitly allowed URL and capture evidence."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        if session.offsite is not None and is_handoff_provider(url):
            session.provider_handoff_url = public_url(url).href
            self._pending_authentication.add(session.session_id)
            await self._authentication_checkpoint(session, force=True)
            return await self.get_state(session_id=session_id, execution_id=execution_id,
                                        journey_id=journey_id, observe=observe)
        if session.is_auth_only_url(url):
            handler = self._authentication_handlers.get(session.session_id)
            if handler is None:
                raise BrowserActionError(
                    "Authentication-only origins require human control."
                )
            validate_target_url(url, session.allowed_origins, session.network_policy)
            async with session.lock:
                await self._authentication_checkpoint(session, lock_held=True, force=True)
            return await self.get_state(session_id=session_id, execution_id=execution_id,
                                        journey_id=journey_id, observe=observe)
        async with self._agent_control_action(session):
            validated = await self._navigation_url(session, url)
            await resolve_and_validate_host(validated.hostname, session.network_policy)
            session.next_action_number()
            try:
                await session.page.goto(
                    validated.href,
                    wait_until="domcontentloaded",
                    timeout=session.timeout_ms,
                )
                final_url = validate_browsing_url(session, session.page.url)
                await resolve_and_validate_host(final_url.hostname, session.network_policy)
            except PlaywrightTimeoutError as exc:
                raise BrowserTimeoutError(f'Navigation to "{validated.origin}" timed out.') from exc
            except Exception as exc:
                if session.offsite is not None:
                    session.offsite.ensure_journey(session.journey_id)
                if isinstance(exc, BrowserPolicyError):
                    raise
                if session.session_id not in self._pending_authentication:
                    raise BrowserNavigationError(
                        f'Navigation to "{validated.origin}" failed.'
                    ) from exc

            await self._authentication_checkpoint(session, lock_held=True)
            if not observe:
                return BrowserActionResult(action="navigate", observation=None)
            screenshot = await capture_screenshot(session, label="navigate")
            return BrowserActionResult(
                action="navigate",
                observation=await build_observation(session, screenshot_path=screenshot),
            )

    async def _state_after_handoff(self, session, locator_strategy) -> BrowserActionResult:
        screenshot = await capture_screenshot(session, label="handoff-return")
        return BrowserActionResult(action="click", locator_strategy=locator_strategy,
                                   observation=await build_observation(session, screenshot_path=screenshot))

    async def inspect_click_approval(
        self,
        *,
        session_id: UUID,
        role: str | None = None,
        name: str | None = None,
        label: str | None = None,
        text: str | None = None,
        scope_role: ScopeRole | None = None,
        scope_name: str | None = None,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
    ) -> SensitiveActionIntent | None:
        """Inspect an exact click target and classify approval policy without acting."""
        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            ensure_low_risk_click_target(name, label, text)
            root = await scoped_root(session.page, scope_role=scope_role, scope_name=scope_name)
            locator, _ = await resolve_action_locator(
                root, role=role, name=name, label=label, text=text,
            )
            return await self._click_intent(
                locator, role=role, name=name, label=label, text=text,
                scope_role=scope_role, scope_name=scope_name, session=session,
            )

    async def _click_intent(
        self, locator: Locator, *, role: str | None, name: str | None,
        label: str | None, text: str | None, scope_role: ScopeRole | None,
        scope_name: str | None, session: JourneyBrowserSession,
    ) -> SensitiveActionIntent | None:
        # Hash page/form state inside the browser. Raw field values never cross
        # Playwright's protocol or enter traces, approval rows, logs or prompts.
        state = await locator.evaluate(
            """async (element, salt) => {
                const form = element.form || element.closest('form');
                const fields = form ? Array.from(form.elements) : [];
                const sensitive = fields.some(field =>
                    ['password', 'file'].includes(field.type) ||
                    /password|passcode|otp|one.time.code|captcha|card.number|cvv|cvc/i.test(
                        [field.name, field.id, field.autocomplete,
                         field.getAttribute('aria-label')].join(' ')));
                const description = [element.textContent, element.getAttribute('aria-label'),
                    element.getAttribute('title'), element.value].filter(Boolean).join(' ');
                const payload = JSON.stringify({salt, url: location.href,
                    element: element.outerHTML, action: form?.action, method: form?.method,
                    fields: sensitive ? [] : fields.map(field => [field.name, field.type,
                        field.value, field.checked, field.disabled])});
                const digest = await crypto.subtle.digest('SHA-256',
                    new TextEncoder().encode(payload));
                return {sensitive, description: description.slice(0, 500),
                    type: form ? element.type : null, tag: element.tagName.toLowerCase(),
                    href: element.tagName === "A" ? element.href : null, hasForm: !!form,
                    digest: Array.from(new Uint8Array(digest))
                        .map(value => value.toString(16).padStart(2, '0')).join('')};
            }""",
            self._approval_salt,
        )
        navigation_url = state.get("href")
        navigation_authorized = False
        if session.offsite is not None:
            outside_page = not self._is_strict_target(session, session.page.url)
            link = (state.get("tag") == "a" and not state.get("hasForm")
                    and isinstance(navigation_url, str))
            if outside_page and not link:
                raise BrowserActionBlockedError("Outside sites are browse-only; only navigation links may be clicked.")
            if link:
                await self._navigation_url(session, navigation_url)
                navigation_authorized = True
        if isinstance(navigation_url, str):
            try:
                validate_target_url(navigation_url, session.allowed_origins, session.network_policy)
                navigation_authorized = True
            except BrowserPolicyError:
                pass
        intent = classify_click_action(
            role=role, name=name, label=label, text=text,
            element_type=state.get("type"),
            observed_description=state.get("description"),
            state_digest=state.get("digest"),
            navigation_url=navigation_url, navigation_origin_authorized=navigation_authorized,
            element_tag=state.get("tag"), has_form=bool(state.get("hasForm")),
            explicit_fixture_approval=await self._fixture_approval_eligible(
                session=session, locator=locator, role=role, name=name,
                scope_role=scope_role, scope_name=scope_name,
            ),
        )
        if intent is not None:
            if state.get("sensitive"):
                raise BrowserActionBlockedError("Sensitive forms require human browser takeover.")
            intent.action.update(scope_role=scope_role, scope_name=scope_name)
        return intent

    async def _fixture_approval_eligible(
        self, *, session: JourneyBrowserSession, locator: Locator,
        role: str | None, name: str | None, scope_role: ScopeRole | None, scope_name: str | None,
    ) -> bool:
        """An exact owner rule makes a loopback fixture effect eligible for approval only."""
        if session.network_policy != "local_development" or not session.fixture_action_rules:
            return False
        current = validate_target_url(
            session.page.url, session.allowed_origins, session.network_policy,
        )
        hostname = urlsplit(current.href).hostname
        try:
            loopback = hostname == "localhost" or bool(
                hostname and ip_address(hostname).is_loopback,
            )
        except ValueError:
            loopback = False
        if not loopback:
            return False
        action: dict[str, object] = {"category": "form_submit", "role": role, "name": name,
                                    "scope_role": scope_role, "scope_name": scope_name}
        rule = next((rule for rule in session.fixture_action_rules if rule.matches(action)), None)
        if rule is None:
            return False
        root = await scoped_root(session.page, scope_role=scope_role, scope_name=scope_name)
        exact = root.get_by_role(rule.role, name=rule.name, exact=True)
        # A fallback label/text must not turn a rule for one control into permission
        # to dispatch a different control, even when the original exact name is stale.
        return await exact.count() == 1 and await locator.and_(exact).count() == 1

    async def sitemap_locations(self, *, session_id: UUID, url: str) -> list[str]:
        """Read a sitemap in an isolated context without changing the watched page."""
        room = self._get_session(session_id=session_id)
        handle = await self._create_sibling_session(
            room, execution_id=room.execution_id, journey_id=room.journey_id,
            purpose="worker",
        )
        try:
            await self.navigate(session_id=handle.session_id, url=url, observe=False)
            session = self._get_session(session_id=handle.session_id)
            async with self._agent_control_action(session):
                return await session.page.evaluate("""() => /xml/i.test(document.contentType)
                    ? [...document.getElementsByTagName('loc')].map(el => el.textContent.trim())
                    : []""")
        finally:
            await self.close_session(session_id=handle.session_id)

    async def ui_state_targets(self, *, session_id: UUID) -> list[dict[str, str]]:
        """Read explicit disclosure/tab controls; activation uses normal click policy."""
        session = self._get_session(session_id=session_id)
        async with self._agent_control_action(session):
            controls = session.page.locator(
                'summary,[role="tab"],button,[role="button"],[role="menuitem"],'
                'input[type="button"],input[type="submit"],a[href^="#"],a:not([href])')
            targets = []
            for index in range(await controls.count()):
                control = controls.nth(index)
                if not await control.is_visible() or not await control.is_enabled():
                    continue
                snapshot = await control.aria_snapshot(timeout=session.timeout_ms)
                match = re.match(r'^- (button|tab|link|menuitem) ("(?:[^"\\]|\\.)*")', snapshot)
                if match:
                    targets.append({"role": match[1], "name": json.loads(match[2])})
            return targets

    async def page_links(self, *, session_id: UUID) -> list[str]:
        """Read destinations without clicking or changing page state."""
        session = self._get_session(session_id=session_id)
        async with self._agent_control_action(session):
            links = await session.page.evaluate("""() => (
                [...document.querySelectorAll('a[href]')]
                .filter(a => !a.hasAttribute('download'))
                .map(a => ({url: a.href, name: a.getAttribute('aria-label') || a.innerText || ''}))
                .filter(a => /^https?:/.test(a.url))
            )""")
            from markettwin_execution_orchestrator.workflow.harness_items import classify_action

            destinations: list[str] = []
            for link in links:
                if classify_action(role="link", name=link["name"] + " " + link["url"]) != "read":
                    continue
                try:
                    ensure_low_risk_click_target(link["name"], None, link["url"])
                except BrowserPolicyError:
                    continue
                if link["url"] not in destinations:
                    destinations.append(link["url"])
            return destinations

    async def current_origin(
        self,
        *,
        session_id: UUID,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
    ) -> str:
        """Return only the current HTTP(S) origin for approval resource binding."""
        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            parsed = urlsplit(session.page.url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise BrowserActionBlockedError("Sensitive actions require an authorized page.")
            default_port = 443 if parsed.scheme == "https" else 80
            return f"{parsed.scheme}://{parsed.hostname}" + (
                f":{parsed.port}" if parsed.port and parsed.port != default_port else ""
            )

    async def get_page_index(
        self, *, session_id: UUID, execution_id: UUID, journey_id: UUID, cursor: int = 0,
        authenticated_session: bool = False,
    ) -> BrowserActionResult:
        """Index public-page interactive accessibility nodes beyond the viewport.

        Authenticated sessions are refused by default: full-page
        discovery must never read a logged-in app. The single exception
        is the harness handoff. ``begin_human_control`` marks a session
        authenticated (``session.authenticated_session``) when the
        operator takes the browser to log in personally, and the
        session's state is afterwards held only in memory by
        ``AuthSessionBroker``. The harness driver passes
        ``authenticated_session=True`` only for a session it created
        from such a broker snapshot, so the inventory can see the
        logged-in app the operator handed over. Never pass it for a
        session that was authenticated any other way.
        """
        if cursor < 0:
            raise BrowserActionError("Page index cursor must be nonnegative.")
        session = self._get_session(
            session_id=session_id, execution_id=execution_id, journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            if session.authenticated_session and not authenticated_session:
                raise BrowserPolicyError("Full-page discovery excludes authenticated sessions.")
            snapshot = await session.page.locator("body").aria_snapshot(timeout=session.timeout_ms)
            entries: list[dict[str, object]] = []
            pattern = _ARIA_SNAPSHOT_ENTRY_PATTERN
            for line in snapshot.splitlines():
                match = pattern.match(line)
                if match:
                    name = json.loads(match[2]) if match[2] else ""
                    entries.append({"ordinal": len(entries) + 1, "role": match[1],
                                    "name": name[:160],
                                    "name_source": "playwright" if len(name) <= 160
                                    else "approximate"})
            session.next_action_number()
            return BrowserActionResult(
                action="get_page_index",
                observation=await build_observation(session, aria_snapshot_override=snapshot),
                page_index=tuple(entries[cursor:cursor + 80]),
                next_cursor=cursor + 80 if cursor + 80 < len(entries) else None,
            )

    async def click(
        self,
        *,
        session_id: UUID,
        role: str | None = None,
        name: str | None = None,
        label: str | None = None,
        text: str | None = None,
        scope_role: ScopeRole | None = None,
        scope_name: str | None = None,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
        approval_fingerprint: str | None = None,
        observe: bool = True,
        form_index: int | None = None,
    ) -> BrowserActionResult:
        """Click one exact semantic element."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            ensure_low_risk_click_target(name, label, text)
            root = await scoped_root(session.page, scope_role=scope_role, scope_name=scope_name)
            if form_index is not None:
                if type(form_index) is not int or form_index < 0 or scope_role is not None:
                    raise BrowserActionBlockedError("Invalid probe form identity.")
                root = session.page.locator("form").nth(form_index)
                await require_unique(root, "Probe form")
            locator, locator_strategy = await resolve_action_locator(
                root,
                role=role,
                name=name,
                label=label,
                text=text,
            )
            if form_index is not None:
                submission = await locator.evaluate("""el => ({
                    method: el.getAttribute('formmethod') || el.form?.method || '',
                    action: el.getAttribute('formaction') ? el.formAction : el.form?.action
                })""")
                if submission.get("method", "").lower() != "get" or not submission.get("action"):
                    raise BrowserActionBlockedError("Form probing requires GET.")
                await self._navigation_url(session, submission["action"])
            intent = await self._click_intent(
                locator, role=role, name=name, label=label, text=text,
                scope_role=scope_role, scope_name=scope_name, session=session,
            )
            if (intent is None and approval_fingerprint is not None) or (
                intent is not None
                and intent.fingerprint != approval_fingerprint
            ):
                raise BrowserActionBlockedError(
                    "The click does not match its current one-time approval."
                )
            if intent is not None and approval_fingerprint is None:
                raise BrowserActionBlockedError(
                    "This action requires a valid one-time human approval."
                )
            session.next_action_number()
            try:
                href = await locator.get_attribute("href")
                if href:
                    destination = urljoin(session.page.url, href)
                    if urlsplit(destination).scheme in {"http", "https"}:
                        await self._navigation_url(session, destination)
                    else:
                        raise BrowserActionBlockedError("Non-HTTP links require human control.")
                    if session.offsite is not None and is_handoff_provider(destination):
                        session.provider_handoff_url = public_url(destination).href
                        self._pending_authentication.add(session.session_id)
                        await self._authentication_checkpoint(session, lock_held=True, force=True)
                        if not observe:
                            return BrowserActionResult(
                                action="click", observation=None,
                                locator_strategy=locator_strategy)
                        return await self._state_after_handoff(session, locator_strategy)
                if href and session.is_auth_only_url(urljoin(session.page.url, href)):
                    if session.session_id not in self._authentication_handlers:
                        raise BrowserActionBlockedError(
                            "Authentication-only origins require human control."
                        )
                    await self._authentication_checkpoint(session, lock_held=True, force=True)
                else:
                    await self._require_keyboard_focus(session, locator)
                    await self._track_pointer(session, locator)
                    if session.keyboard_only:
                        input_type = await locator.get_attribute("type")
                        await session.page.keyboard.press(
                            "Space" if role in {"checkbox", "radio"}
                            or input_type in {"checkbox", "radio"} else "Enter")
                    else:
                        await locator.click(timeout=session.timeout_ms)
            except BrowserPolicyError:
                raise
            except PlaywrightTimeoutError as exc:
                raise BrowserTimeoutError("Click timed out.") from exc
            except Exception as exc:
                if session.offsite is not None:
                    session.offsite.ensure_journey(session.journey_id)
                raise BrowserActionError("Click could not be completed.") from exc

            await self._authentication_checkpoint(session, lock_held=True)
            if not observe:
                return BrowserActionResult(
                    action="click", observation=None,
                    locator_strategy=locator_strategy)
            screenshot = await capture_screenshot(session, label="click")
            return BrowserActionResult(
                action="click",
                observation=await build_observation(session, screenshot_path=screenshot),
                locator_strategy=locator_strategy,
            )

    async def fill(
        self,
        *,
        session_id: UUID,
        label: str,
        value: str,
        scope_role: ScopeRole | None = None,
        scope_name: str | None = None,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
        observe: bool = True,
    ) -> BrowserActionResult:
        """Fill non-secret text into an exactly labelled field."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            validate_target_url(session.page.url, session.allowed_origins, session.network_policy)
            root = await scoped_root(session.page, scope_role=scope_role, scope_name=scope_name)
            locator = root.get_by_label(label, exact=True)
            await require_unique(locator)
            input_type = await locator.get_attribute("type")
            autocomplete = await locator.get_attribute("autocomplete")
            ensure_non_sensitive_fill(
                label=label,
                input_type=input_type,
                autocomplete=autocomplete,
            )
            session.next_action_number()
            await self._require_keyboard_focus(session, locator)
            await self._track_pointer(session, locator)
            try:
                if session.keyboard_only:
                    await session.page.keyboard.press("ControlOrMeta+A")
                    await session.page.keyboard.insert_text(value)
                else:
                    await locator.fill(value, timeout=session.timeout_ms)
            except PlaywrightTimeoutError as exc:
                raise BrowserTimeoutError("Fill timed out.") from exc
            except Exception as exc:
                raise BrowserActionError("Fill could not be completed.") from exc

            if not observe:
                return BrowserActionResult(action="fill", observation=None)
            screenshot = await capture_screenshot(session, label="fill")
            return BrowserActionResult(
                action="fill",
                observation=await build_observation(session, screenshot_path=screenshot),
            )

    async def select(
        self,
        *,
        session_id: UUID,
        label: str,
        value: str,
        scope_role: ScopeRole | None = None,
        scope_name: str | None = None,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
        observe: bool = True,
    ) -> BrowserActionResult:
        """Select one option from an exactly labelled select control."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            validate_target_url(session.page.url, session.allowed_origins, session.network_policy)
            root = await scoped_root(session.page, scope_role=scope_role, scope_name=scope_name)
            locator = root.get_by_label(label, exact=True)
            await require_unique(locator)
            ensure_non_sensitive_fill(
                label=label,
                input_type=await locator.evaluate("el => el.type"),
                autocomplete=await locator.get_attribute("autocomplete"),
            )
            session.next_action_number()
            await self._require_keyboard_focus(session, locator)
            await self._track_pointer(session, locator)
            try:
                if session.keyboard_only:
                    index = await locator.evaluate(
                        "(el, value) => Array.from(el.options).findIndex(o => o.value === value)", value)
                    if index < 0:
                        raise BrowserActionError("Requested option is unavailable.")
                    await session.page.keyboard.press("Home")
                    for _ in range(index):
                        await session.page.keyboard.press("ArrowDown")
                    await session.page.keyboard.press("Enter")
                    if await locator.input_value() != value:
                        raise BrowserActionError("Keyboard selection did not reach the requested option.")
                else:
                    await locator.select_option(value=value, timeout=session.timeout_ms)
            except PlaywrightTimeoutError as exc:
                raise BrowserTimeoutError("Select timed out.") from exc
            except Exception as exc:
                raise BrowserActionError("Select could not be completed.") from exc

            if not observe:
                return BrowserActionResult(action="select", observation=None)
            screenshot = await capture_screenshot(session, label="select")
            return BrowserActionResult(
                action="select",
                observation=await build_observation(session, screenshot_path=screenshot),
            )

    async def set_checked(
        self,
        *,
        session_id: UUID,
        label: str,
        checked: bool,
        scope_role: ScopeRole | None = None,
        scope_name: str | None = None,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
        observe: bool = True,
    ) -> BrowserActionResult:
        """Set an exactly labeled checkbox; no radio/file/payment activation."""
        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            validate_target_url(session.page.url, session.allowed_origins, session.network_policy)
            ensure_low_risk_click_target(label)
            root = await scoped_root(session.page, scope_role=scope_role, scope_name=scope_name)
            locator = root.get_by_label(label, exact=True)
            await require_unique(locator)
            input_type = await locator.get_attribute("type")
            ensure_non_sensitive_fill(
                label=label,
                input_type=input_type,
                autocomplete=await locator.get_attribute("autocomplete"),
            )
            if input_type != "checkbox":
                raise BrowserActionError("Check/uncheck requires a checkbox control.")
            session.next_action_number()
            await self._require_keyboard_focus(session, locator)
            await self._track_pointer(session, locator)
            try:
                if session.keyboard_only:
                    if await locator.is_checked() != checked:
                        await session.page.keyboard.press("Space")
                else:
                    await locator.set_checked(checked, timeout=session.timeout_ms)
            except PlaywrightTimeoutError as exc:
                raise BrowserTimeoutError("Checkbox action timed out.") from exc
            except Exception as exc:
                raise BrowserActionError("Checkbox action could not be completed.") from exc
            action = "check" if checked else "uncheck"
            if not observe:
                return BrowserActionResult(action=action, observation=None)
            screenshot = await capture_screenshot(session, label=action)
            return BrowserActionResult(
                action=action,
                observation=await build_observation(session, screenshot_path=screenshot),
            )

    async def scroll(
        self,
        *,
        session_id: UUID,
        direction: Literal["up", "down"],
        amount: int = 600,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
        observe: bool = True,
    ) -> BrowserActionResult:
        """Scroll the current page by a bounded amount."""

        if amount < 1 or amount > 2000:
            raise BrowserActionError("Scroll amount must be between 1 and 2000 pixels.")

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            session.next_action_number()
            delta = amount if direction == "down" else -amount
            if session.keyboard_only:
                await session.page.keyboard.press("PageDown" if direction == "down" else "PageUp")
            else:
                await session.page.mouse.wheel(0, delta)
            await session.page.wait_for_timeout(150)
            if not observe:
                return BrowserActionResult(action="scroll", observation=None)
            screenshot = await capture_screenshot(session, label="scroll")
            return BrowserActionResult(
                action="scroll",
                observation=await build_observation(session, screenshot_path=screenshot),
            )

    async def go_back(
        self,
        *,
        session_id: UUID,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
        observe: bool = True,
    ) -> BrowserActionResult:
        """Navigate back within the same policy-controlled session."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            session.next_action_number()
            try:
                await session.page.go_back(
                    wait_until="domcontentloaded",
                    timeout=session.timeout_ms,
                )
            except PlaywrightTimeoutError as exc:
                raise BrowserTimeoutError("Back navigation timed out.") from exc

            if session.page.url and session.page.url != "about:blank":
                final_url = validate_browsing_url(session, session.page.url)
                await resolve_and_validate_host(final_url.hostname, session.network_policy)

            if not observe:
                return BrowserActionResult(action="go_back", observation=None)
            screenshot = await capture_screenshot(session, label="back")
            return BrowserActionResult(
                action="go_back",
                observation=await build_observation(session, screenshot_path=screenshot),
            )

    async def wait(
        self,
        *,
        session_id: UUID,
        milliseconds: int = 500,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
        observe: bool = True,
    ) -> BrowserActionResult:
        """Wait briefly for a bounded asynchronous UI transition."""

        if milliseconds < 0 or milliseconds > 5_000:
            raise BrowserActionError("Wait must be between 0 and 5000 milliseconds.")

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            session.next_action_number()
            await session.page.wait_for_timeout(milliseconds)
            if not observe:
                return BrowserActionResult(action="wait", observation=None)
            screenshot = await capture_screenshot(session, label="wait")
            return BrowserActionResult(
                action="wait",
                observation=await build_observation(session, screenshot_path=screenshot),
            )

    async def capture_element(
        self,
        *,
        session_id: UUID,
        role: str | None = None,
        name: str | None = None,
        label: str | None = None,
        text: str | None = None,
        scope_role: ScopeRole | None = None,
        scope_name: str | None = None,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
    ) -> BrowserActionResult:
        """Scroll a rendered element into view and capture viewport and crop."""
        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            root = await scoped_root(session.page, scope_role=scope_role, scope_name=scope_name)
            locator = semantic_locator(
                root,
                role=role,
                name=name,
                label=label,
                text=text,
            )
            await require_unique(locator)
            if not await locator.is_visible():
                raise BrowserActionError("Element is not rendered visibly.")

            await locator.scroll_into_view_if_needed()
            raw_box = await locator.bounding_box()
            if raw_box is None:
                raise BrowserActionError("Element has no visible bounding box.")

            bounding_box = ElementBoundingBox(
                x=round(raw_box["x"]),
                y=round(raw_box["y"]),
                width=round(raw_box["width"]),
                height=round(raw_box["height"]),
            )
            viewport_size = session.page.viewport_size
            if viewport_size is None:
                raw_viewport_size = await session.page.evaluate(
                    "() => ({ width: window.innerWidth, height: window.innerHeight })"
                )
                viewport_width = int(raw_viewport_size["width"])
                viewport_height = int(raw_viewport_size["height"])
            else:
                viewport_width = viewport_size["width"]
                viewport_height = viewport_size["height"]

            if not bounding_box_intersects_viewport(
                bounding_box=bounding_box,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
            ):
                raise BrowserActionError(
                    "Element is rendered but does not intersect the current viewport."
                )

            session.next_action_number()
            viewport_path = await capture_screenshot(session, label="focus")
            if viewport_path is None:
                raise BrowserActionError("Screenshot capture is disabled.")

            focused_path = session.artifact_directory / (
                f"action-{session.action_number:04d}-element.png"
            )
            try:
                crop_viewport_screenshot(
                    viewport_path=viewport_path,
                    bounding_box=bounding_box,
                    output_path=focused_path,
                )
            except ValueError as exc:
                raise BrowserActionError(
                    "Element moved outside the viewport before evidence capture."
                ) from exc

            return BrowserActionResult(
                action="capture_element",
                observation=await build_observation(
                    session,
                    screenshot_path=viewport_path,
                    focused_screenshot_path=focused_path,
                ),
            )

    async def take_screenshot(
        self,
        *,
        session_id: UUID,
        role: str | None = None,
        name: str | None = None,
        label: str | None = None,
        text: str | None = None,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
    ) -> BrowserActionResult:
        """Capture explicit Journey screenshot evidence."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            session.next_action_number()
            screenshot = await capture_screenshot(session, label="explicit")
            return BrowserActionResult(
                action="take_screenshot",
                observation=await build_observation(session, screenshot_path=screenshot),
            )

    async def capture_evidence_screenshot(
        self,
        *,
        session_id: UUID,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
    ) -> str:
        """Capture a screenshot as evidence WITHOUT building an observation.

        Speed S0 (doc 18 section 7.2): callers that need the image file
        itself (the slop traversal's visual review) skip the accessibility
        snapshot and the observation build entirely. Returns the
        screenshot path, or an empty string when capture is disabled
        for the session.
        """

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            session.next_action_number()
            screenshot = await capture_screenshot(session, label="explicit")
            return str(screenshot) if screenshot is not None else ""

    async def begin_human_control(
        self,
        *,
        session_id: UUID,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
    ) -> None:
        """Pause agent tools while retaining the exact Journey BrowserContext."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with session.lock:
            session.human_network_diagnostics.clear()
            await begin_human_control(session)
            if session.provider_handoff_url is not None:
                destination, session.provider_handoff_url = session.provider_handoff_url, None
                await session.page.goto(destination, wait_until="domcontentloaded", timeout=session.timeout_ms)

    async def ensure_human_control(
        self, *, handle: BrowserSessionHandle, generation: int | None = None,
    ) -> None:
        """Fence capture before a worker attaches the human viewer."""

        session = self._get_session(
            session_id=handle.session_id,
            execution_id=handle.execution_id,
            journey_id=handle.journey_id,
        )
        async with session.lock:
            if session.state != "open":
                raise BrowserSessionStateError("Browser session is unavailable.")
            if session.control_mode == "human":
                return
            session.human_network_diagnostics.clear()
            if (generation is not None and generation > session.control_generation
                    and session.control_mode in {"none", "verifying"}
                    and not session.capture_enabled and not session.tracing_active):
                session.control_mode = "human"
                return
            await begin_human_control(session)

    async def end_human_control(
        self,
        *,
        session_id: UUID,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
        verified: bool = False,
        safe_to_capture: bool = False,
    ) -> None:
        """Resume agent tools after higher layers verify human authentication."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with session.lock:
            if verified and safe_to_capture and session.js_capture:
                # The page hook runs independently of trace capture. Discard
                # any rejections accumulated while the operator controlled it.
                await session.page.evaluate("() => { window.__mt_rejections = []; }")
                session.rejections_harvested = 0
            await end_human_control(
                session,
                verified=verified,
                safe_to_capture=safe_to_capture,
            )
            session.human_network_diagnostics.clear()

    async def verify_recovery_target(
        self, *, handle: BrowserSessionHandle, target: SemanticTarget,
    ) -> bool:
        """Read only: verify the frozen target after Release without capturing secrets."""
        session = self._get_session(
            session_id=handle.session_id, execution_id=handle.execution_id,
            journey_id=handle.journey_id,
        )
        async with session.lock:
            if session.state != "open" or session.control_mode != "verifying":
                return False
            try:
                validate_target_url(
                    session.page.url, session.allowed_origins, session.network_policy,
                )
                # A generic recovery never substitutes for approved identity verification.
                if await has_active_sensitive_challenge(session.page):
                    return False
                root = await scoped_root(
                    session.page, scope_role=target.scope_role, scope_name=target.scope_name,
                )
                locator = semantic_locator(
                    root, role=target.role, name=target.name,
                    label=target.label, text=target.text,
                )
                await require_unique(locator)
                return await locator.is_visible() and await locator.is_enabled()
            except Exception:
                return False

    async def verify_authenticated_role(
        self,
        *,
        handle: BrowserSessionHandle,
        policy: AuthVerificationPolicy,
    ) -> VerifiedPrincipal | None:
        """Verify the frozen target identity while evidence capture is fenced."""

        session = self._get_session(
            session_id=handle.session_id,
            execution_id=handle.execution_id,
            journey_id=handle.journey_id,
        )
        async with session.lock:
            if session.state != "open" or session.control_mode not in {"agent", "verifying"}:
                return None
            allowed_origins = frozenset(
                f"{origin.scheme}://{origin.hostname}"
                + (
                    f":{origin.port}"
                    if origin.port is not None
                    and origin.port != (443 if origin.scheme == "https" else 80)
                    else ""
                )
                for origin in session.allowed_origins
            )
            return await verify_authenticated_role(
                page=session.page,
                policy=policy,
                allowed_origins=allowed_origins,
            )

    async def capture_verified_auth_session(
        self,
        *,
        handle: BrowserSessionHandle,
        policy: AuthVerificationPolicy,
        scope: AuthSessionScope,
    ) -> VerifiedPrincipal | None:
        """Capture in-memory auth state only after the exact role marker verifies."""

        if (
            scope.origin != policy.origin
            or scope.role != policy.role
            or scope.account_reference != policy.account_reference
        ):
            return None
        session = self._get_session(
            session_id=handle.session_id,
            execution_id=handle.execution_id,
            journey_id=handle.journey_id,
        )
        async with session.lock:
            if session.state != "open" or session.control_mode not in {"agent", "verifying"}:
                return None
            allowed_origins = frozenset(
                f"{origin.scheme}://{origin.hostname}"
                + (
                    f":{origin.port}"
                    if origin.port is not None
                    and origin.port != (443 if origin.scheme == "https" else 80)
                    else ""
                )
                for origin in session.allowed_origins
            )
            principal = await verify_authenticated_role(
                page=session.page,
                policy=policy,
                allowed_origins=allowed_origins,
            )
            if principal is None:
                return None
            await self._auth_session_broker.capture(
                scope=scope,
                principal=principal,
                context=cast(Any, session.context),
                page=session.page,
            )
            self._auth_session_broker.retain_for_task_verification(scope)
            return principal

    def take_auth_session_snapshot(
        self,
        *,
        scope: AuthSessionScope,
        case_id: str,
    ) -> AuthSessionSnapshot:
        """Consume the authenticated state once for one isolated case."""

        return self._auth_session_broker.take(scope=scope, case_id=case_id)

    def revoke_auth_session_snapshot(self, *, scope: AuthSessionScope) -> None:
        """Discard reusable state when identity verification fails or is revoked."""

        self._auth_session_broker.revoke(scope)

    async def close_session(
        self,
        *,
        session_id: UUID,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
    ) -> BrowserSessionArtifacts:
        """Finalize local evidence and close the Journey browser."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )

        console_log_path: Path | None = None
        page_log_path: Path | None = None
        network_log_path: Path | None = None

        async with session.lock:
            try:
                if session.state not in {"closed", "failed"}:
                    await stop_trace(session)
                    (
                        console_log_path,
                        page_log_path,
                        network_log_path,
                    ) = (
                        await write_event_logs(session)
                        if session.capture_enabled and session.control_mode == "agent"
                        else (None, None, None)
                    )

                    session.state = "closed"

                trace_paths = tuple(sorted(session.artifact_directory.glob("trace-*.zip")))

            finally:
                from markettwin_execution_orchestrator.browser.owner_registry import (
                    browser_owner_registry,
                )

                browser_owner_registry.unregister(
                    BrowserSessionHandle(
                        session_id=session_id,
                        execution_id=session.execution_id,
                        journey_id=session.journey_id,
                    )
                )
                try:
                    await session.context.close()
                finally:
                    try:
                        # A proof session shares the Room's Chromium:
                        # closing it must never close the shared browser.
                        if not session.shares_browser:
                            await session.browser.close()
                    finally:
                        egress = self._egress_proxies.pop(session_id, None)
                        if egress is not None:
                            await egress.close()
                    session.human_network_diagnostics.clear()
                    self._sessions.pop(session_id, None)
                    self._session_purposes.pop(session_id, None)
                    self._authentication_handlers.pop(session_id, None)
                    self._authentication_locks.pop(session_id, None)
                    self._pending_authentication.discard(session_id)
                    self._cooperative_handlers.pop(session_id, None)
                    self._cooperative_locks.pop(session_id, None)

        return BrowserSessionArtifacts(
            trace_paths=trace_paths,
            console_log_path=console_log_path,
            page_log_path=page_log_path,
            network_log_path=network_log_path,
        )
