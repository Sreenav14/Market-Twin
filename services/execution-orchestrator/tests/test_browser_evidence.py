"""Regression tests for browser screenshot evidence."""

from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from markettwin_execution_orchestrator.browser.contracts import (
    ElementBoundingBox,
)
from markettwin_execution_orchestrator.browser.evidence import (
    capture_screenshot,
    crop_viewport_screenshot,
)
from markettwin_execution_orchestrator.browser.session import (
    JourneyBrowserSession,
)
from PIL import Image


@pytest.mark.asyncio
async def test_screenshot_capture_is_viewport_scoped(
    tmp_path: Path,
) -> None:
    """Automatic evidence must capture the visible viewport only."""

    screenshot = AsyncMock()

    session = cast(
        JourneyBrowserSession,
        SimpleNamespace(
            capture_enabled=True,
            artifact_directory=tmp_path,
            action_number=7,
            page=SimpleNamespace(
                screenshot=screenshot,
            ),
        ),
    )

    path = await capture_screenshot(
        session,
        label="navigate",
    )

    expected_path = (
        tmp_path
        / "action-0007-navigate.png"
    )

    assert path == expected_path

    screenshot.assert_awaited_once_with(
        path=expected_path,
        full_page=False,
    )


def test_focused_crop_uses_element_box_with_padding(
    tmp_path: Path,
) -> None:
    """Focused evidence should come from the existing viewport image."""

    viewport_path = tmp_path / "viewport.png"
    crop_path = tmp_path / "crop.png"

    Image.new(
        "RGB",
        (1280, 900),
        "white",
    ).save(viewport_path)

    crop_viewport_screenshot(
        viewport_path=viewport_path,
        bounding_box=ElementBoundingBox(
            x=200,
            y=100,
            width=300,
            height=50,
        ),
        output_path=crop_path,
        padding=48,
    )

    with Image.open(crop_path) as crop:
        assert crop.size == (
            396,
            146,
        )


def test_focused_crop_clamps_to_viewport_edges(
    tmp_path: Path,
) -> None:
    """Padding must never extend outside the captured viewport."""

    viewport_path = tmp_path / "viewport.png"
    crop_path = tmp_path / "crop.png"

    Image.new(
        "RGB",
        (1280, 900),
        "white",
    ).save(viewport_path)

    crop_viewport_screenshot(
        viewport_path=viewport_path,
        bounding_box=ElementBoundingBox(
            x=10,
            y=10,
            width=100,
            height=40,
        ),
        output_path=crop_path,
        padding=48,
    )

    with Image.open(crop_path) as crop:
        assert crop.size == (
            158,
            98,
        )


@pytest.mark.parametrize(
    "bounding_box",
    [
        ElementBoundingBox(x=100, y=-100, width=50, height=20),
        ElementBoundingBox(x=100, y=900, width=50, height=20),
        ElementBoundingBox(x=-100, y=100, width=20, height=50),
        ElementBoundingBox(x=1280, y=100, width=20, height=50),
    ],
)
def test_focused_crop_rejects_fully_offscreen_element(
    tmp_path: Path,
    bounding_box: ElementBoundingBox,
) -> None:
    """Padding must not turn an offscreen element into focused evidence."""

    viewport_path = tmp_path / "viewport.png"
    crop_path = tmp_path / "crop.png"
    Image.new("RGB", (1280, 900), "white").save(viewport_path)

    with pytest.raises(
        ValueError,
        match="Focused crop does not intersect the viewport",
    ):
        crop_viewport_screenshot(
            viewport_path=viewport_path,
            bounding_box=bounding_box,
            output_path=crop_path,
        )

    assert not crop_path.exists()
