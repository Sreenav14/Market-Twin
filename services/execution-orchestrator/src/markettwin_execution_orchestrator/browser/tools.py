"""Plain Python Google ADK tools bound to one MarketTwin Journey browser."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol, cast
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from markettwin_execution_orchestrator.browser.contracts import (
    BrowserActionResult,
    BrowserSessionHandle,
    ScopeRole,
)
from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.errors import (
    BrowserActionBlockedError,
    BrowserActionError,
    BrowserPolicyError,
)
from markettwin_execution_orchestrator.browser.sensitive_action_policy import (
    SensitiveActionIntent,
)

BrowserTool = Callable[..., Awaitable[dict[str, object]]]


def create_browser_tools(
    *,
    controller: BrowserController,
    handle: BrowserSessionHandle,
    step_recorder: BrowserStepRecorder | None = None,
) -> list[BrowserTool]:
    """Create a least-privilege tool set permanently bound to one Journey."""
    # ADK may dispatch several tool calls concurrently. Serialize the complete
    # action, including database writes outside the controller's browser lock.
    action_lock = asyncio.Lock()

    async def run_recorded_action(
        *,
        action_type: str,
        action_summary: str,
        operation: Callable[[], Awaitable[BrowserActionResult]],
        click_preflight: Callable[[], Awaitable[SensitiveActionIntent | None]] | None = None,
    ) -> dict[str, object]:
        async with action_lock:
            await controller.cooperative_checkpoint(handle)
            return await execute_recorded_action(
                action_type=action_type,
                action_summary=action_summary,
                operation=operation,
                click_preflight=click_preflight,
            )

    async def execute_recorded_action(
        *,
        action_type: str,
        action_summary: str,
        operation: Callable[
            [],
            Awaitable[BrowserActionResult],
        ],
        click_preflight: Callable[[], Awaitable[SensitiveActionIntent | None]] | None = None,
    ) -> dict[str, object]:
        step_id: int | None = None

        controller.require_agent_control(handle)

        if step_recorder is not None:
            step_id = await step_recorder.start_step(
                action_type=action_type,
                action_summary=action_summary,
            )

        approval_id: UUID | None = None

        async def finish_approval(outcome: str) -> None:
            if approval_id is None:
                return
            finish = getattr(step_recorder, "finish_sensitive_action", None)
            if callable(finish):
                await asyncio.shield(cast(Callable[..., Awaitable[None]], finish)(
                    approval_id=approval_id, outcome=outcome,
                ))

        try:
            intent = await click_preflight() if click_preflight is not None else None
            if intent is not None:
                begin = getattr(step_recorder, "begin_sensitive_action", None)
                if step_id is None or not callable(begin):
                    raise BrowserActionBlockedError(
                        "This action requires the configured human approval workflow."
                    )
                origin = await controller.current_origin(
                    session_id=handle.session_id,
                    execution_id=handle.execution_id,
                    journey_id=handle.journey_id,
                )
                approval_id = await cast(Callable[..., Awaitable[UUID]], begin)(
                    step_id=step_id,
                    intent=intent,
                    current_origin=origin,
                    browser_session_id=handle.session_id,
                    revalidate_origin=lambda: controller.current_origin(
                        session_id=handle.session_id,
                        execution_id=handle.execution_id,
                        journey_id=handle.journey_id,
                    ),
                )

            result = await operation()
        except BrowserPolicyError as exc:
            await finish_approval("uncertain")
            if step_recorder is not None and step_id is not None:
                await step_recorder.finish_step(
                    step_id=step_id,
                    status="policy_blocked",
                    observation_summary=str(exc),
                )
            raise

        except BrowserActionError as exc:
            await finish_approval("uncertain")
            if step_recorder is not None and step_id is not None:
                await step_recorder.finish_step(
                    step_id=step_id,
                    status="failed",
                    observation_summary=str(exc),
                )

            payload: dict[str, object] = {
                "action": action_type,
                "status": "failed",
                "error": str(exc),
                "error_code": exc.reason_code,
                "evidence_status": "unavailable",
                "recovery": (
                    "The action did not complete successfully. Call browser_get_state "
                    "to inspect the current page before choosing another action. "
                    "Use the observed role and accessible name or field label; "
                    "do not repeat an unchanged failing locator or assume success."
                ),
            }

            if step_id is not None:
                payload["step_id"] = step_id

            # The original failure is committed first. Observe this same bound
            # session without retrying the action; controller guards still apply.
            if step_recorder is not None and step_id is not None:
                try:
                    async with asyncio.timeout(5):
                        observation = await controller.get_state(
                            session_id=handle.session_id,
                            execution_id=handle.execution_id,
                            journey_id=handle.journey_id,
                        )
                        await step_recorder.record_failure_evidence(
                            step_id=step_id, result=observation,
                        )
                    payload["observation"] = observation.observation.to_dict()
                    payload["evidence_status"] = "captured"
                except Exception:
                    # Best-effort capture must not replace the original error.
                    pass

            return payload

        except asyncio.CancelledError:
            await finish_approval("uncertain")
            if step_recorder is not None and step_id is not None:
                await asyncio.shield(
                    step_recorder.finish_step(
                        step_id=step_id,
                        status="failed",
                        observation_summary="Browser action was interrupted.",
                    )
                )
            raise

        except Exception as exc:
            await finish_approval("uncertain")
            if step_recorder is not None and step_id is not None:
                await step_recorder.finish_step(
                    step_id=step_id,
                    status="failed",
                    observation_summary=str(exc),
                )
            raise

        else:
            await finish_approval("completed")

        if step_recorder is not None and step_id is not None:
            await step_recorder.record_evidence(
                step_id=step_id,
                result=result,
            )

            await step_recorder.finish_step(
                step_id=step_id,
                status="completed",
                observation_summary=_observation_summary(result),
            )

        payload = result.to_dict()
        
        if step_id is not None:
            payload["step_id"] = step_id
            
        return payload

    async def browser_get_state() -> dict[str, object]:
        """Observe the current page without changing it."""
        return await run_recorded_action(
            action_type="get_state",
            action_summary="Observe the current browser state.",
            operation=lambda: controller.get_state(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
            ),
        )

    async def browser_navigate(url: str) -> dict[str, object]:
        """Navigate to an HTTP(S) URL allowed by this Journey's target policy."""
        return await run_recorded_action(
            action_type="navigate",
            action_summary=f"Navigate to {_safe_url_summary(url)}.",
            operation=lambda: controller.navigate(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                url=url,
            ),
        )

    async def browser_click(
        role: str | None = None,
        name: str | None = None,
        label: str | None = None,
        text: str | None = None,
        scope_role: ScopeRole | None = None,
        scope_name: str | None = None,
    ) -> dict[str, object]:
        """Click one exact semantic element by role+name, label, or visible text."""
        summary = "Click a semantic page element."
        approval_state: dict[str, SensitiveActionIntent | None] = {"intent": None}

        async def preflight() -> SensitiveActionIntent | None:
            intent = await controller.inspect_click_approval(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                role=role,
                name=name,
                label=label,
                text=text,
                scope_role=scope_role,
                scope_name=scope_name,
            )
            approval_state["intent"] = intent
            return intent

        return await run_recorded_action(
            action_type="click",
            action_summary=summary,
            operation=lambda: controller.click(
                scope_role=scope_role, scope_name=scope_name,
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                role=role,
                name=name,
                label=label,
                text=text,
                approval_fingerprint=(
                    approval_state["intent"].fingerprint
                    if approval_state["intent"] is not None
                    else None
                ),
            ),
            click_preflight=preflight,
        )

    async def browser_fill(
        label: str, value: str, scope_role: ScopeRole | None = None,
        scope_name: str | None = None,
    ) -> dict[str, object]:
        """Fill non-secret text into one exactly labelled input field."""
        return await run_recorded_action(
            action_type="fill",
            action_summary="Fill an approved non-secret text field.",
            operation=lambda: controller.fill(
                scope_role=scope_role, scope_name=scope_name,
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                label=label,
                value=value,
            ),
        )

    async def browser_select(
        label: str, value: str, scope_role: ScopeRole | None = None,
        scope_name: str | None = None,
    ) -> dict[str, object]:
        """Choose one value from an exactly labelled select control."""
        return await run_recorded_action(
            action_type="select",
            action_summary="Select an option from a labelled control.",
            operation=lambda: controller.select(
                scope_role=scope_role, scope_name=scope_name,
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                label=label,
                value=value,
            ),
        )

    async def browser_scroll(
        direction: Literal["up", "down"],
        amount: int = 600,
    ) -> dict[str, object]:
        """Scroll the page up or down by at most 2000 pixels."""
        return await run_recorded_action(
            action_type="scroll",
            action_summary=f"Scroll {direction} by {amount} pixels.",
            operation=lambda: controller.scroll(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                direction=direction,
                amount=amount,
            ),
        )

    async def browser_go_back() -> dict[str, object]:
        """Go back once within the same policy-controlled browser session."""
        return await run_recorded_action(
            action_type="go_back",
            action_summary="Navigate back one page.",
            operation=lambda: controller.go_back(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
            ),
        )

    async def browser_wait(milliseconds: int = 500) -> dict[str, object]:
        """Wait up to five seconds for a bounded asynchronous UI transition."""
        return await run_recorded_action(
            action_type="wait",
            action_summary=f"Wait {milliseconds} milliseconds.",
            operation=lambda: controller.wait(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                milliseconds=milliseconds,
            ),
        )

    async def browser_capture_element(
        role: str | None = None,
        name: str | None = None,
        label: str | None = None,
        text: str | None = None,
        scope_role: ScopeRole | None = None,
        scope_name: str | None = None,
    ) -> dict[str, object]:
        """Scroll a rendered element into view and capture focused evidence."""
        return await run_recorded_action(
            action_type="capture_element",
            action_summary="Scroll requested element into view and capture focused evidence.",
            operation=lambda: controller.capture_element(
                scope_role=scope_role, scope_name=scope_name,
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                role=role,
                name=name,
                label=label,
                text=text,
            ),
        )

    async def browser_take_screenshot() -> dict[str, object]:
        """Capture explicit screenshot evidence and return the current page state."""
        return await run_recorded_action(
            action_type="take_screenshot",
            action_summary="Capture screenshot evidence.",
            operation=lambda: controller.take_screenshot(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
            ),
        )

    async def browser_get_form_state(
        scope_role: ScopeRole, scope_name: str,
    ) -> dict[str, object]:
        """Inspect required/enabled/checked/selection/validity metadata; never field values."""
        return await run_recorded_action(
            action_type="get_form_state", action_summary="Inspect scoped form metadata.",
            operation=lambda: controller.get_form_state(
                session_id=handle.session_id, execution_id=handle.execution_id,
                journey_id=handle.journey_id, scope_role=scope_role, scope_name=scope_name,
            ),
        )

    async def browser_check(
        label: str, scope_role: ScopeRole | None = None, scope_name: str | None = None,
    ) -> dict[str, object]:
        """Check one labeled non-sensitive checkbox."""
        return await run_recorded_action(
            action_type="check", action_summary="Check a labeled checkbox.",
            operation=lambda: controller.set_checked(
                session_id=handle.session_id, execution_id=handle.execution_id,
                journey_id=handle.journey_id, label=label, checked=True,
                scope_role=scope_role, scope_name=scope_name,
            ),
        )

    async def browser_uncheck(
        label: str, scope_role: ScopeRole | None = None, scope_name: str | None = None,
    ) -> dict[str, object]:
        """Uncheck one labeled non-sensitive checkbox."""
        return await run_recorded_action(
            action_type="uncheck", action_summary="Uncheck a labeled checkbox.",
            operation=lambda: controller.set_checked(
                session_id=handle.session_id, execution_id=handle.execution_id,
                journey_id=handle.journey_id, label=label, checked=False,
                scope_role=scope_role, scope_name=scope_name,
            ),
        )

    async def browser_focus_next(reverse: bool = False) -> dict[str, object]:
        """Move focus once using Tab or Shift+Tab without activating a control."""
        return await run_recorded_action(
            action_type="focus_next", action_summary="Move keyboard focus one stop.",
            operation=lambda: controller.focus_next(
                session_id=handle.session_id, execution_id=handle.execution_id,
                journey_id=handle.journey_id, reverse=reverse,
            ),
        )

    async def browser_set_viewport(
        preset: Literal["mobile320", "desktop1280"],
    ) -> dict[str, object]:
        """Set only a fixed mobile (320px) or desktop (1280px) viewport."""
        return await run_recorded_action(
            action_type="set_viewport", action_summary=f"Use {preset} viewport preset.",
            operation=lambda: controller.set_viewport(
                session_id=handle.session_id, execution_id=handle.execution_id,
                journey_id=handle.journey_id, preset=preset,
            ),
        )

    return [
        browser_get_state,
        browser_navigate,
        browser_click,
        browser_fill,
        browser_select,
        browser_scroll,
        browser_go_back,
        browser_wait,
        browser_capture_element,
        browser_take_screenshot,
        browser_get_form_state,
        browser_focus_next,
        browser_set_viewport,
        browser_check,
        browser_uncheck,
    ]

class BrowserStepRecorder(Protocol):
    """Optional audit recorder used by bounded browser tools."""

    async def start_step(
        self,
        *,
        action_type: str,
        action_summary: str,
    ) -> int: ...

    async def finish_step(
        self,
        *,
        step_id: int,
        status: Literal[
            "completed",
            "failed",
            "policy_blocked",
        ],
        observation_summary: str | None = None,
    ) -> None: ...
    
    async def record_evidence(
        self,
        *,
        step_id: int,
        result: BrowserActionResult,
    ) -> None: ...

    async def record_failure_evidence(
        self, *, step_id: int, result: BrowserActionResult,
    ) -> None: ...

def _safe_url_summary(url: str) -> str:
    """Remove query strings and fragments from a logged URL."""

    parsed = urlsplit(url)

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            "",
            "",
        )
    )


def _observation_summary(
    result: BrowserActionResult,
) -> str:
    observation = result.observation

    return (
        f"url={_safe_url_summary(observation.url)};"
        f"action={result.action};"
        f"page_count={observation.page_count};"
        f"console_errors="
        f"{len(observation.console_errors_since_last_action)};"
        f"page_errors="
        f"{len(observation.page_errors_since_last_action)};"
        f"failed_requests="
        f"{len(observation.failed_requests_since_last_action)};"
        f"screenshot={'yes' if observation.screenshot_path else 'none'}"
    )
