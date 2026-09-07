"""Plain Python Google ADK tools bound to one MarketTwin Journey browser."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal, Protocol
from urllib.parse import urlsplit, urlunsplit

from markettwin_execution_orchestrator.browser.contracts import (
    BrowserActionResult,
    BrowserSessionHandle,
)
from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserPolicyError

BrowserTool = Callable[..., Awaitable[dict[str, object]]]


def create_browser_tools(
    *,
    controller: BrowserController,
    handle: BrowserSessionHandle,
    step_recorder: BrowserStepRecorder | None = None,
) -> list[BrowserTool]:
    """Create a least-privilege tool set permanently bound to one Journey."""
    
    async def run_recorded_action(
        *,
        action_type: str,
        action_summary: str,
        operation: Callable[
            [],
            Awaitable[BrowserActionResult],
        ],
    ) -> dict[str, object]:
        step_id: int | None = None

        if step_recorder is not None:
            step_id = await step_recorder.start_step(
                action_type=action_type,
                action_summary=action_summary,
            )

        try:
            result = await operation()

        except BrowserPolicyError as exc:
            if step_recorder is not None and step_id is not None:
                await step_recorder.finish_step(
                    step_id=step_id,
                    status="policy_blocked",
                    observation_summary=str(exc),
                )
            raise

        except Exception as exc:
            if step_recorder is not None and step_id is not None:
                await step_recorder.finish_step(
                    step_id=step_id,
                    status="failed",
                    observation_summary=str(exc),
                )
            raise

        if step_recorder is not None and step_id is not None:
            await step_recorder.finish_step(
                step_id=step_id,
                status="completed",
                observation_summary=_observation_summary(result),
            )

        return result.to_dict()

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
    ) -> dict[str, object]:
        """Click one exact semantic element by role+name, label, or visible text."""
        return await run_recorded_action(
            action_type="click",
            action_summary="Click a semantic page element.",
            operation=lambda: controller.click(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                role=role,
                name=name,
                label=label,
                text=text,
            ),
        )

    async def browser_fill(label: str, value: str) -> dict[str, object]:
        """Fill non-secret text into one exactly labelled input field."""
        return await run_recorded_action(
            action_type="fill",
            action_summary="Fill an approved non-secret text field.",
            operation=lambda: controller.fill(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                label=label,
                value=value,
            ),
        )

    async def browser_select(label: str, value: str) -> dict[str, object]:
        """Choose one value from an exactly labelled select control."""
        return await run_recorded_action(
            action_type="select",
            action_summary="Select an option from a labelled control.",
            operation=lambda: controller.select(
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

    return [
        browser_get_state,
        browser_navigate,
        browser_click,
        browser_fill,
        browser_select,
        browser_scroll,
        browser_go_back,
        browser_wait,
        browser_take_screenshot,
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