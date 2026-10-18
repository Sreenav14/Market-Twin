"""Python Playwright browser authority for MarketTwin Journey execution."""

from __future__ import annotations

import asyncio
import json
import re
import secrets
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urljoin, urlsplit
from uuid import UUID, uuid4

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
    scoped_root,
    semantic_locator,
)
from markettwin_execution_orchestrator.browser.assertions import (
    AssertionObservation,
    evaluate_assertion,
)
from markettwin_execution_orchestrator.browser.auth_session_broker import (
    AuthSessionBroker,
    AuthSessionScope,
    AuthSessionSnapshot,
    HumanSessionScope,
)
from markettwin_execution_orchestrator.browser.auth_verifier import (
    VerifiedPrincipal,
    verify_authenticated_role,
)
from markettwin_execution_orchestrator.browser.contracts import (
    AllowedOrigin,
    BrowserActionResult,
    BrowserSessionArtifacts,
    BrowserSessionHandle,
    ElementBoundingBox,
    FailedRequestRecord,
    NetworkPolicy,
    ScopeRole,
)
from markettwin_execution_orchestrator.browser.errors import (
    BrowserActionBlockedError,
    BrowserActionError,
    BrowserNavigationError,
    BrowserPolicyError,
    BrowserSessionNotFoundError,
    BrowserSessionOwnershipError,
    BrowserSessionStateError,
    BrowserTimeoutError,
    HumanControlActiveError,
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
from markettwin_execution_orchestrator.browser.network import resolve_and_validate_host
from markettwin_execution_orchestrator.browser.observations import (
    build_observation,
    inspect_form_fields,
)
from markettwin_execution_orchestrator.browser.policy import (
    validate_target_url,
    validate_websocket_url,
)
from markettwin_execution_orchestrator.browser.sensitive_action_policy import (
    SensitiveActionIntent,
    classify_click_action,
)
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession


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
        self._auth_session_broker = AuthSessionBroker()
        self._authentication_handlers: dict[UUID, Callable[[], Awaitable[None]]] = {}
        self._authentication_locks: dict[UUID, asyncio.Lock] = {}
        self._pending_authentication: set[UUID] = set()
        self._cooperative_handlers: dict[UUID, Callable[[], Awaitable[None]]] = {}
        self._cooperative_locks: dict[UUID, asyncio.Lock] = {}
        self._start_lock = asyncio.Lock()
        self._approval_salt = secrets.token_hex(32)

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
        try:
            browser = await self._playwright.chromium.launch(headless=self._headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                device_scale_factor=1,
                accept_downloads=False,
                service_workers="block",
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
            )
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
            if browser is not None:
                await browser.close()
            raise

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
                validate_target_url(
                    session.page.url, session.allowed_origins, session.network_policy,
                )
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
        if await session.page.locator(
            'input[type="password"]:visible, input[autocomplete="one-time-code"]:visible, '
            'input[autocomplete="username"]:visible, '
            'input[name*="otp" i]:visible, input[name*="captcha" i]:visible, '
            'iframe[title*="captcha" i]:visible, [data-captcha]:visible'
        ).count():
            return True
        # Email-only login and SSO chooser screens need an actual auth form;
        # ordinary navigation links and newsletter fields are not challenges.
        if await session.page.locator("form:visible").filter(
            has=session.page.locator('input[type="email"]:visible, input[name="username"]:visible'),
        ).filter(has=session.page.get_by_role(
            "button", name=re.compile(r"^(sign\s*in|log\s*in|continue(?: with .+)?)$", re.I),
        )).count():
            return True
        return bool(await session.page.get_by_role(
            "heading", name=re.compile(
                r"^(sign\s*in|log\s*in|login|authorize .+|permissions requested)$", re.I,
            ),
        ).count() and await session.page.get_by_role(
            "button", name=re.compile(
                r"^(continue with .+|sign\s*in.*|log\s*in.*|allow|authorize)$", re.I,
            ),
        ).count())

    async def human_continuation_ready(self, handle: BrowserSessionHandle) -> bool:
        """Validate safe continuation, without claiming an authenticated identity."""
        session = self._get_session(session_id=handle.session_id,
                                    execution_id=handle.execution_id, journey_id=handle.journey_id)
        validate_target_url(session.page.url, session.allowed_origins, session.network_policy)
        return (session.state == "open" and session.control_mode == "verifying"
                and not await self._has_authentication_challenge(session, include_pending=False))

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
            await self._auth_session_broker.capture_human_session(
                scope=HumanSessionScope(run_id=run_id, target_id=target_id, origin=origin),
                context=cast(Any, session.context), page=session.page,
            )
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
                    await handler()
                    self._pending_authentication.discard(session.session_id)
        finally:
            if lock_held:
                await session.lock.acquire()
        self._ensure_agent_control(session)

    @staticmethod
    def _ensure_agent_control(session: JourneyBrowserSession) -> None:
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
        await self.cooperative_checkpoint(handle)
        await self._authentication_checkpoint(session)
        async with session.lock:
            await self._authentication_checkpoint(session, lock_held=True)
            self._ensure_agent_control(session)
            yield

    async def _route_request(
        self,
        session: JourneyBrowserSession,
        route: Route,
    ) -> None:
        try:
            if session.control_mode != "human" and session.is_auth_only_url(route.request.url):
                if (route.request.is_navigation_request()
                        and route.request.frame.parent_frame is None):
                    self._pending_authentication.add(session.session_id)
                raise BrowserActionBlockedError("Authentication-only request blocked.")
            validated = validate_target_url(
                route.request.url,
                session.allowed_origins,
                session.network_policy,
            )
            await resolve_and_validate_host(
                validated.hostname,
                session.network_policy,
            )
            await route.continue_()
        except Exception:
            await route.abort("blockedbyclient")

    async def _route_web_socket(
        self,
        session: JourneyBrowserSession,
        route: WebSocketRoute,
    ) -> None:
        try:
            http_url = route.url.replace("wss://", "https://", 1).replace("ws://", "http://", 1)
            if session.control_mode != "human" and session.is_auth_only_url(http_url):
                raise BrowserActionBlockedError("Authentication-only socket blocked.")
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
        except Exception:
            await route.close(
                code=1008,
                reason="Blocked by MarketTwin network policy",
            )

    def _schedule_page_setup(
        self,
        session: JourneyBrowserSession,
        page: Page,
    ) -> None:
        asyncio.create_task(self._configure_page(session, page))

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
            lambda error: self._record_page_error(session, str(error)),
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
    def _record_page_error(session: JourneyBrowserSession, message: str) -> None:
        if (session.capture_enabled and session.control_mode == "agent"
                and not session.authenticated_session):
            session.event_buffer.record_page_error(message)

    @staticmethod
    def _on_console(session: JourneyBrowserSession, kind: str, text: str) -> None:
        if (kind == "error" and session.capture_enabled and session.control_mode == "agent"
                and not session.authenticated_session):
            session.event_buffer.record_console_error(text)

    @staticmethod
    def _on_request_failed(session: JourneyBrowserSession, request: Request) -> None:
        if (session.capture_enabled and session.control_mode == "agent"
                and not session.authenticated_session):
            session.event_buffer.record_failed_request(
                FailedRequestRecord(
                    url=request.url,
                    method=request.method,
                    resource_type=request.resource_type,
                    error_text=request.failure or "Unknown network error",
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
    ) -> BrowserActionResult:
        """Return the current compact browser observation."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            session.next_action_number()
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
    ) -> BrowserActionResult:
        """Inspect bounded form metadata without returning entered values."""
        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            validate_target_url(session.page.url, session.allowed_origins, session.network_policy)
            root = await scoped_root(session.page, scope_role=scope_role, scope_name=scope_name)
            # A named scope was required above, so this is a Locator.
            assert isinstance(root, Locator)
            fields, more_available = await inspect_form_fields(root)
            session.next_action_number()
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
            validate_target_url(session.page.url, session.allowed_origins, session.network_policy)
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
            outcome = await evaluate_assertion(session.page, assertion, timeout_ms=timeout_ms)
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
            screenshot = await capture_screenshot(session, label="focus-next")
            return BrowserActionResult(
                action="focus_next",
                observation=await build_observation(session, screenshot_path=screenshot),
            )

    async def set_viewport(
        self,
        *,
        session_id: UUID,
        preset: Literal["mobile320", "desktop1280"],
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
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
            validate_target_url(session.page.url, session.allowed_origins, session.network_policy)
            session.next_action_number()
            await session.page.set_viewport_size(
                {
                    "width": 320 if preset == "mobile320" else 1280,
                    "height": 800,
                }
            )
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
    ) -> BrowserActionResult:
        """Navigate to an explicitly allowed URL and capture evidence."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
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
                                        journey_id=journey_id)
        async with self._agent_control_action(session):
            validated = validate_target_url(
                url,
                session.allowed_origins,
                session.network_policy,
            )
            await resolve_and_validate_host(validated.hostname, session.network_policy)
            session.next_action_number()
            try:
                await session.page.goto(
                    validated.href,
                    wait_until="domcontentloaded",
                    timeout=session.timeout_ms,
                )
                final_url = validate_target_url(
                    session.page.url,
                    session.allowed_origins,
                    session.network_policy,
                )
                await resolve_and_validate_host(final_url.hostname, session.network_policy)
            except PlaywrightTimeoutError as exc:
                raise BrowserTimeoutError(f'Navigation to "{validated.origin}" timed out.') from exc
            except Exception as exc:
                if isinstance(exc, BrowserPolicyError):
                    raise
                if session.session_id not in self._pending_authentication:
                    raise BrowserNavigationError(
                        f'Navigation to "{validated.origin}" failed.'
                    ) from exc

            await self._authentication_checkpoint(session, lock_held=True)
            screenshot = await capture_screenshot(session, label="navigate")
            return BrowserActionResult(
                action="navigate",
                observation=await build_observation(session, screenshot_path=screenshot),
            )

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
            locator = semantic_locator(
                root, role=role, name=name, label=label, text=text,
            )
            await require_unique(locator)
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
        )
        if intent is not None:
            if state.get("sensitive"):
                raise BrowserActionBlockedError("Sensitive forms require human browser takeover.")
            intent.action.update(scope_role=scope_role, scope_name=scope_name)
        return intent

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
            locator = semantic_locator(
                root,
                role=role,
                name=name,
                label=label,
                text=text,
            )
            await require_unique(locator)
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
                        validate_target_url(
                            destination,
                            session.allowed_origins,
                            session.network_policy,
                        )
                if href and session.is_auth_only_url(urljoin(session.page.url, href)):
                    if session.session_id not in self._authentication_handlers:
                        raise BrowserActionBlockedError(
                            "Authentication-only origins require human control."
                        )
                    await self._authentication_checkpoint(session, lock_held=True, force=True)
                else:
                    await locator.click(timeout=session.timeout_ms)
            except BrowserPolicyError:
                raise
            except PlaywrightTimeoutError as exc:
                raise BrowserTimeoutError("Click timed out.") from exc
            except Exception as exc:
                raise BrowserActionError("Click could not be completed.") from exc

            await self._authentication_checkpoint(session, lock_held=True)
            screenshot = await capture_screenshot(session, label="click")
            return BrowserActionResult(
                action="click",
                observation=await build_observation(session, screenshot_path=screenshot),
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
    ) -> BrowserActionResult:
        """Fill non-secret text into an exactly labelled field."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
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
            try:
                await locator.fill(value, timeout=session.timeout_ms)
            except PlaywrightTimeoutError as exc:
                raise BrowserTimeoutError("Fill timed out.") from exc
            except Exception as exc:
                raise BrowserActionError("Fill could not be completed.") from exc

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
    ) -> BrowserActionResult:
        """Select one option from an exactly labelled select control."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with self._agent_control_action(session):
            root = await scoped_root(session.page, scope_role=scope_role, scope_name=scope_name)
            locator = root.get_by_label(label, exact=True)
            await require_unique(locator)
            session.next_action_number()
            try:
                await locator.select_option(
                    value=value,
                    timeout=session.timeout_ms,
                )
            except PlaywrightTimeoutError as exc:
                raise BrowserTimeoutError("Select timed out.") from exc
            except Exception as exc:
                raise BrowserActionError("Select could not be completed.") from exc

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
            try:
                await locator.set_checked(checked, timeout=session.timeout_ms)
            except PlaywrightTimeoutError as exc:
                raise BrowserTimeoutError("Checkbox action timed out.") from exc
            except Exception as exc:
                raise BrowserActionError("Checkbox action could not be completed.") from exc
            action = "check" if checked else "uncheck"
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
            await session.page.mouse.wheel(0, delta)
            await session.page.wait_for_timeout(150)
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
                final_url = validate_target_url(
                    session.page.url,
                    session.allowed_origins,
                    session.network_policy,
                )
                await resolve_and_validate_host(final_url.hostname, session.network_policy)

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
            await begin_human_control(session)

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
            await end_human_control(
                session,
                verified=verified,
                safe_to_capture=safe_to_capture,
            )

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
                challenges = session.page.locator(
                    'input[type="password"]:visible, '
                    'input[autocomplete="one-time-code"]:visible, '
                    'input[name*="otp" i]:visible, input[name*="captcha" i]:visible, '
                    'iframe[title*="captcha" i]:visible, [data-captcha]:visible'
                )
                if await challenges.count():
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
                    await session.browser.close()
                    self._sessions.pop(session_id, None)
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
