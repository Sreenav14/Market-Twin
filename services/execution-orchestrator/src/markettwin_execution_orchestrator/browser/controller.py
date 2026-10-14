"""Python Playwright browser authority for MarketTwin Journey execution."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlsplit
from uuid import UUID, uuid4

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

from markettwin_execution_orchestrator.agents.schemas.test_case import ExpectedAssertion
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
        self._start_lock = asyncio.Lock()

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
        timeout_ms: int = 30_000,
    ) -> BrowserSessionHandle:
        """Create one fresh Chromium + BrowserContext for one Journey."""

        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if not allowed_origins:
            raise ValueError("At least one allowed origin is required")

        await self.start()
        assert self._playwright is not None

        session_id = uuid4()
        artifact_directory = self._artifact_root / str(execution_id) / str(session_id)
        artifact_directory.mkdir(parents=True, exist_ok=True)

        browser: Browser | None = None
        try:
            browser = await self._playwright.chromium.launch(headless=self._headless)
            context = await browser.new_context(
                viewport={
                    "width": 1280,
                    "height": 900
                },
                device_scale_factor=1,
                accept_downloads=False,
                service_workers="block",
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
        except Exception:
            self._sessions.pop(session_id, None)
            if browser is not None:
                await browser.close()
            raise

        return BrowserSessionHandle(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )

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
            raise BrowserSessionOwnershipError(
                "Browser session does not belong to this execution."
            )
        if journey_id is not None and session.journey_id != journey_id:
            raise BrowserSessionOwnershipError(
                "Browser session does not belong to this Journey."
            )
        return session

    @staticmethod
    def _ensure_agent_control(session: JourneyBrowserSession) -> None:
        if session.state == "human_control":
            raise HumanControlActiveError(
                "Agent browser tools are disabled while human control is active."
            )
        if session.state != "open":
            raise BrowserSessionStateError(
                f"Browser session is not open; current state is {session.state}."
            )

    async def _route_request(
        self,
        session: JourneyBrowserSession,
        route: Route,
    ) -> None:
        try:
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
            session.event_buffer.record_page_error(
                "Popup blocked: Journey exceeded the configured page limit."
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
            lambda error: session.event_buffer.record_page_error(str(error)),
        )
        page.on("requestfailed", lambda request: self._on_request_failed(session, request))
        page.on("dialog", lambda dialog: self._dismiss_dialog(session, dialog))
        page.on(
            "download",
            lambda _download: session.event_buffer.record_page_error(
                "Download blocked by MarketTwin policy."
            ),
        )

    @staticmethod
    def _on_console(session: JourneyBrowserSession, kind: str, text: str) -> None:
        if kind == "error":
            session.event_buffer.record_console_error(text)

    @staticmethod
    def _on_request_failed(session: JourneyBrowserSession, request: Request) -> None:
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
        session.event_buffer.record_page_error(
            f'Unexpected browser dialog dismissed: "{dialog.message}"'
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
        self._ensure_agent_control(session)
        async with session.lock:
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
        self, *, session_id: UUID, scope_role: ScopeRole, scope_name: str,
        execution_id: UUID | None = None, journey_id: UUID | None = None,
    ) -> BrowserActionResult:
        """Inspect bounded form metadata without returning entered values."""
        session = self._get_session(
            session_id=session_id, execution_id=execution_id, journey_id=journey_id,
        )
        self._ensure_agent_control(session)
        async with session.lock:
            validate_target_url(session.page.url, session.allowed_origins, session.network_policy)
            root = await scoped_root(session.page, scope_role=scope_role, scope_name=scope_name)
            # A named scope was required above, so this is a Locator.
            assert isinstance(root, Locator)
            fields, more_available = await inspect_form_fields(root)
            session.next_action_number()
            screenshot = await capture_screenshot(session, label="form-state")
            snapshot = json.dumps([asdict(field) for field in fields])
            return BrowserActionResult(
                action="get_form_state", observation=await build_observation(
                    session, screenshot_path=screenshot, aria_snapshot_override=snapshot,
                    form_fields=fields, more_available=more_available,
                ),
            )

    async def read_assertion(
        self, *, session_id: UUID, assertion: ExpectedAssertion, timeout_ms: int = 1500,
        execution_id: UUID | None = None, journey_id: UUID | None = None,
    ) -> tuple[BrowserActionResult, AssertionObservation]:
        """Read an assertion under the same origin, ownership and control guards."""
        if timeout_ms < 1 or timeout_ms > 5000:
            raise BrowserActionError("Assertion timeout must be between 1 and 5000 milliseconds.")
        session = self._get_session(
            session_id=session_id, execution_id=execution_id, journey_id=journey_id,
        )
        self._ensure_agent_control(session)
        async with session.lock:
            validate_target_url(session.page.url, session.allowed_origins, session.network_policy)
            session.next_action_number()
            if assertion.target is not None:
                target = assertion.target
                root = await scoped_root(
                    session.page, scope_role=target.scope_role, scope_name=target.scope_name,
                )
                locator = semantic_locator(
                    root, role=target.role, name=target.name, label=target.label, text=target.text,
                )
                if await locator.count() == 1 and await locator.is_visible():
                    await locator.scroll_into_view_if_needed()
                elif isinstance(root, Locator) and await root.is_visible():
                    await root.scroll_into_view_if_needed()
            outcome = await evaluate_assertion(session.page, assertion, timeout_ms=timeout_ms)
            screenshot = await capture_screenshot(session, label="assertion")
            result = BrowserActionResult(
                action="assertion", observation=await build_observation(
                    session, screenshot_path=screenshot,
                ),
            )
            return result, outcome

    async def focus_next(
        self, *, session_id: UUID, reverse: bool = False,
        execution_id: UUID | None = None, journey_id: UUID | None = None,
    ) -> BrowserActionResult:
        """Move keyboard focus one stop; no activation keys are accepted."""
        session = self._get_session(
            session_id=session_id, execution_id=execution_id, journey_id=journey_id,
        )
        self._ensure_agent_control(session)
        async with session.lock:
            validate_target_url(session.page.url, session.allowed_origins, session.network_policy)
            session.next_action_number()
            await session.page.keyboard.press("Shift+Tab" if reverse else "Tab")
            screenshot = await capture_screenshot(session, label="focus-next")
            return BrowserActionResult(
                action="focus_next",
                observation=await build_observation(session, screenshot_path=screenshot),
            )

    async def set_viewport(
        self, *, session_id: UUID, preset: Literal["mobile320", "desktop1280"],
        execution_id: UUID | None = None, journey_id: UUID | None = None,
    ) -> BrowserActionResult:
        """Use a fixed fixture-tested viewport preset."""
        if preset not in {"mobile320", "desktop1280"}:
            raise BrowserActionError("Viewport preset must be mobile320 or desktop1280.")
        session = self._get_session(
            session_id=session_id, execution_id=execution_id, journey_id=journey_id,
        )
        self._ensure_agent_control(session)
        async with session.lock:
            validate_target_url(session.page.url, session.allowed_origins, session.network_policy)
            session.next_action_number()
            await session.page.set_viewport_size({
                "width": 320 if preset == "mobile320" else 1280, "height": 800,
            })
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
        self._ensure_agent_control(session)
        async with session.lock:
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
                raise BrowserTimeoutError(
                    f'Navigation to "{validated.origin}" timed out.'
                ) from exc
            except Exception as exc:
                if isinstance(exc, BrowserPolicyError):
                    raise
                raise BrowserNavigationError(
                    f'Navigation to "{validated.origin}" failed.'
                ) from exc

            screenshot = await capture_screenshot(session, label="navigate")
            return BrowserActionResult(
                action="navigate",
                observation=await build_observation(session, screenshot_path=screenshot),
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
    ) -> BrowserActionResult:
        """Click one exact semantic element."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        self._ensure_agent_control(session)
        async with session.lock:
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
            session.next_action_number()
            try:
                href = await locator.get_attribute("href")
                if href:
                    destination = urljoin(session.page.url, href)
                    if urlsplit(destination).scheme in {"http", "https"}:
                        validate_target_url(
                            destination, session.allowed_origins, session.network_policy,
                        )
                await locator.click(timeout=session.timeout_ms)
            except BrowserPolicyError:
                raise
            except PlaywrightTimeoutError as exc:
                raise BrowserTimeoutError("Click timed out.") from exc
            except Exception as exc:
                raise BrowserActionError("Click could not be completed.") from exc

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
        self._ensure_agent_control(session)
        async with session.lock:
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
        self._ensure_agent_control(session)
        async with session.lock:
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
        self, *, session_id: UUID, label: str, checked: bool,
        scope_role: ScopeRole | None = None, scope_name: str | None = None,
        execution_id: UUID | None = None, journey_id: UUID | None = None,
    ) -> BrowserActionResult:
        """Set an exactly labeled checkbox; no radio/file/payment activation."""
        session = self._get_session(
            session_id=session_id, execution_id=execution_id, journey_id=journey_id,
        )
        self._ensure_agent_control(session)
        async with session.lock:
            validate_target_url(session.page.url, session.allowed_origins, session.network_policy)
            ensure_low_risk_click_target(label)
            root = await scoped_root(session.page, scope_role=scope_role, scope_name=scope_name)
            locator = root.get_by_label(label, exact=True)
            await require_unique(locator)
            input_type = await locator.get_attribute("type")
            ensure_non_sensitive_fill(
                label=label, input_type=input_type,
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
        self._ensure_agent_control(session)
        async with session.lock:
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
        self._ensure_agent_control(session)
        async with session.lock:
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
        self._ensure_agent_control(session)
        async with session.lock:
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
        self._ensure_agent_control(session)

        async with session.lock:
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
                raise BrowserActionError(
                    "Element is not rendered visibly."
                )

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
        self._ensure_agent_control(session)
        async with session.lock:
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

    async def end_human_control(
        self,
        *,
        session_id: UUID,
        execution_id: UUID | None = None,
        journey_id: UUID | None = None,
    ) -> None:
        """Resume agent tools after higher layers verify human authentication."""

        session = self._get_session(
            session_id=session_id,
            execution_id=execution_id,
            journey_id=journey_id,
        )
        async with session.lock:
            await end_human_control(session)

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
                    ) = await write_event_logs(session)
                    
                    session.state = "closed"
                    
                trace_paths = tuple(
                    sorted(session.artifact_directory.glob("trace-*.zip"))
                )
                
            
            finally:
                try:
                    await session.context.close()
                finally:
                    await session.browser.close()
                    self._sessions.pop(session_id, None)
                    
        return BrowserSessionArtifacts(
            trace_paths=trace_paths,
            console_log_path = console_log_path,
            page_log_path = page_log_path,
            network_log_path = network_log_path,
        )
