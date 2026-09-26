"""Tests for evaluation evidence repository behavior."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_visual_evidence_is_grouped_by_step_and_kind() -> None:
    execution_id = uuid4()

    viewport_id = uuid4()
    crop_id = uuid4()

    viewport = SimpleNamespace(
        id=viewport_id,
        execution_id=execution_id,
        step_id=7,
        artifact_type="screenshot",
        storage_provider="minio",
        bucket="markettwin",
        object_key=(
            "executions/test/steps/7/"
            "action-0007-focus.png"
        ),
        content_type="image/png",
        metadata_json={
            "kind": "viewport",
        },
    )

    crop = SimpleNamespace(
        id=crop_id,
        execution_id=execution_id,
        step_id=7,
        artifact_type="screenshot",
        storage_provider="minio",
        bucket="markettwin",
        object_key=(
            "executions/test/steps/7/"
            "action-0007-element.png"
        ),
        content_type="image/png",
        metadata_json={
            "kind": "element_crop",
        },
    )

    step = SimpleNamespace(
        id=7,
        action_type="capture_element",
    )

    artifact_result = SimpleNamespace(
        all=lambda: [
            viewport,
            crop,
        ]
    )

    step_result = SimpleNamespace(
        all=lambda: [
            step,
        ]
    )

    session = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                artifact_result,
                step_result,
            ]
        )
    )

    repository = EvaluationRepository(
        cast(AsyncSession, session),
    )

    evidence = await repository.list_visual_evidence(
        execution_id=execution_id,
        step_ids=(7,),
    )

    assert len(evidence) == 1

    evidence_step = evidence[0]

    assert evidence_step.step_id == 7
    assert evidence_step.action_type == "capture_element"
    assert (
        evidence_step.explicitly_requests_visual_verification
        is True
    )

    assert evidence_step.viewport is not None
    assert (
        evidence_step.viewport.artifact_id
        == viewport_id
    )
    assert evidence_step.viewport.kind == "viewport"

    assert evidence_step.element_crop is not None
    assert (
        evidence_step.element_crop.artifact_id
        == crop_id
    )
    assert (
        evidence_step.element_crop.kind
        == "element_crop"
    )
