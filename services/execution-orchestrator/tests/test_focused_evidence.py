"""Regression coverage for focused crops and paired screenshot persistence."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser.contracts import (
    BrowserActionResult,
    BrowserObservation,
    ElementBoundingBox,
)
from markettwin_execution_orchestrator.browser.evidence import crop_viewport_screenshot
from markettwin_execution_orchestrator.persistence.step_recorder import ExecutionStepRecorder
from PIL import Image


def test_focused_crop_preserves_clipped_viewport_pixels(tmp_path: Path) -> None:
    viewport = tmp_path / "viewport.png"
    focused = tmp_path / "element.png"
    original = Image.new("RGB", (100, 80), "white")
    original.putpixel((0, 10), (255, 0, 0))
    original.save(viewport)

    crop_viewport_screenshot(
        viewport_path=viewport,
        bounding_box=ElementBoundingBox(x=-10, y=10, width=40, height=100),
        output_path=focused,
        padding=0,
    )

    with Image.open(focused) as crop:
        assert crop.size == (30, 70)
        assert crop.getpixel((0, 0)) == (255, 0, 0)
    with Image.open(viewport) as unchanged:
        assert unchanged.tobytes() == original.tobytes()


@pytest.mark.asyncio
async def test_record_evidence_persists_viewport_and_crop() -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    storage = MagicMock()
    storage.upload = AsyncMock(side_effect=["viewport-stored", "crop-stored"])
    execution_id = uuid4()
    recorder = ExecutionStepRecorder(
        session=session, execution_id=execution_id, storage=storage,
    )
    observation = BrowserObservation(
        url="https://example.com", title="Example", aria_snapshot="",
        viewport_width=100, viewport_height=80, scroll_y=0, document_height=200,
        screenshot_path="action-0001-focus.png",
        focused_screenshot_path="action-0001-element.png",
    )
    repository = MagicMock()
    repository.create = AsyncMock()
    with patch(
        "markettwin_execution_orchestrator.persistence.step_recorder.ArtifactRepository",
        return_value=repository,
    ):
        await recorder.record_evidence(
            step_id=7,
            result=BrowserActionResult(action="capture_element", observation=observation),
        )

    uploads = storage.upload.await_args_list
    assert [call.kwargs["object_key"] for call in uploads] == [
        f"executions/{execution_id}/steps/7/action-0001-focus.png",
        f"executions/{execution_id}/steps/7/action-0001-element.png",
    ]
    records = repository.create.await_args_list
    assert [call.kwargs["metadata"] for call in records] == [
        {"kind": "viewport", "browser_action": "capture_element"},
        {"kind": "element_crop", "browser_action": "capture_element"},
    ]
    assert [call.kwargs["stored"] for call in records] == [
        "viewport-stored", "crop-stored",
    ]
    assert all(call.kwargs["artifact_type"] == "screenshot" for call in records)
    assert observation.to_dict()["focused_screenshot_path"] == "action-0001-element.png"
    session.commit.assert_awaited_once()
