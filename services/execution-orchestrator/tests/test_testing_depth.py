"""Frozen coverage choices reach planning without changing legacy run semantics."""

import json
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_database.models.testing import TestRun
from markettwin_execution_orchestrator.browser import AllowedOrigin
from markettwin_execution_orchestrator.workflow import run_executor
from markettwin_execution_orchestrator.workflow.planning import (
    MetaPlanningRequest,
    build_planning_prompt,
)
from markettwin_execution_orchestrator.workflow.run_request import build_run_request
from markettwin_execution_orchestrator.workflow.testing_depth import (
    TestingDepth,
    feature_case_limit,
)
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.parametrize("depth,limit", [("low", 1), ("medium", 2), ("high", 4), (None, 4)])
def test_run_depth_reaches_planning_and_legacy_retains_limit(depth: str | None, limit: int) -> None:
    config: dict[str, object] = {"study_brief": "Check the stated user task"}
    if depth is not None:
        config["testing_depth"] = depth
    run = TestRun(
        id=uuid4(),
        configuration_snapshot=config,
        target_snapshot={
            "base_url": "https://example.invalid",
            "allowed_origins": [],
        },
    )
    request = build_run_request(run)
    assert request.testing_depth == (depth or "high")
    prompt = build_planning_prompt(
        MetaPlanningRequest(
            test_run_id=run.id,
            study_brief=request.study_brief,
            target_snapshot=request.target_snapshot,
            testing_depth=request.testing_depth,
        )
    )
    context = json.loads(prompt[prompt.index("{") :])
    assert context["maximum_missions"] == limit


def test_invalid_persisted_depth_does_not_silently_expand_coverage() -> None:
    run = TestRun(
        id=uuid4(),
        configuration_snapshot={"study_brief": "Some task", "testing_depth": "unlimited"},
        target_snapshot={},
    )
    with pytest.raises(KeyError):
        build_run_request(run)


@pytest.mark.parametrize("depth,limit", [("low", 3), ("medium", 6), ("high", 8)])
def test_feature_case_coverage_limits_follow_selected_depth(depth: str, limit: int) -> None:
    assert feature_case_limit(cast(TestingDepth, depth)) == limit


async def test_legacy_persona_dispatch_is_retired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U-P8: the legacy meta-plan path is gone; a legacy persona
    request refuses loudly instead of reaching a browser. The unified
    engine's own budget gate lives in the Board tests."""

    monkeypatch.setattr(run_executor, "initialize_adk_observability", lambda: None)
    request = run_executor.MarketTwinRunRequest(
        run_id=uuid4(),
        study_brief="Check the stated user task",
        target_snapshot={},
        start_url="https://example.invalid",
        testing_depth="low",
        run_kind="persona",
        allowed_origins=(AllowedOrigin(scheme="https", hostname="example.invalid"),),
    )
    with pytest.raises(ValueError, match="retired"):
        await run_executor.execute_markettwin_run(
            request, session=cast(AsyncSession, AsyncMock(spec=AsyncSession)),
        )
