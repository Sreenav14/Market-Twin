"""Regression tests for browser observations."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from markettwin_execution_orchestrator.browser.observations import (
    build_observation,
)
from markettwin_execution_orchestrator.browser.session import (
    JourneyBrowserSession,
)


@pytest.mark.asyncio
async def test_observation_contains_viewport_metrics() -> None:
    """Persona observations should describe the visible page position."""

    body = MagicMock()
    body.aria_snapshot = AsyncMock(
        return_value='- heading "Software testing"'
    )

    page = MagicMock()
    page.url = "https://example.com/software-testing"
    page.locator.return_value = body
    page.title = AsyncMock(return_value="Software testing")
    page.evaluate = AsyncMock(
        side_effect=[
            {
                "width": 1280,
                "height": 900,
                "scroll_y": 0,
                "document_height": 12000,
            },
            [
                {
                    "role": "heading",
                    "name": "Software testing",
                    "tag": "h1",
                    "enabled": True,
                    "level": 1,
                    "bounding_box": {
                        "x": 184,
                        "y": 94,
                        "width": 370,
                        "height": 46,
                    },
                }
            ],
        ]
    )
    session = cast(
        JourneyBrowserSession,
        SimpleNamespace(
            page=page,
            timeout_ms=30_000,
            capture_enabled=False,
            action_number=4,
            context=SimpleNamespace(pages=[page]),
            event_buffer=SimpleNamespace(
                console_errors=[],
                page_errors=[],
                failed_requests=[],
            ),
        ),
    )

    observation = await build_observation(session)

    assert observation.viewport_width == 1280
    assert observation.viewport_height == 900
    assert observation.scroll_y == 0
    assert observation.document_height == 12000
    assert len(observation.visible_elements) == 1

    heading = observation.visible_elements[0]

    assert heading.role == "heading"
    assert heading.name == "Software testing"
    assert heading.level == 1
    assert heading.enabled is True

    assert heading.bounding_box.x == 184
    assert heading.bounding_box.y == 94
    assert heading.bounding_box.width == 370
    assert heading.bounding_box.height == 46

    assert page.evaluate.await_count == 2