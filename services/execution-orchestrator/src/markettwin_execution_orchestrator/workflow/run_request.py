"""Build execution requests from persisted TestRuns."""

from typing import Literal, cast

from markettwin_database.models.testing import TestRun

from markettwin_execution_orchestrator.browser import AllowedOrigin
from markettwin_execution_orchestrator.workflow.run_executor import (
    MarketTwinRunRequest,
)
from markettwin_execution_orchestrator.workflow.testing_depth import TestingDepth, mission_limit


def build_run_request(
    test_run: TestRun,
    *,
    max_duration_seconds_per_journey: int = 90,
) -> MarketTwinRunRequest:
    """Build the runtime request from one persisted TestRun."""

    target_snapshot = test_run.target_snapshot
    configuration_snapshot = test_run.configuration_snapshot
    execution_mode = configuration_snapshot.get("execution_mode", "legacy_persona")
    if execution_mode not in {"legacy_persona", "deep_feature_v1"}:
        raise ValueError("Unsupported execution mode.")
    testing_depth = cast(TestingDepth, configuration_snapshot.get("testing_depth", "high"))
    mission_limit(testing_depth)

    study_brief = cast(
        str,
        configuration_snapshot["study_brief"],
    )

    start_url = cast(
        str,
        target_snapshot["base_url"],
    )

    raw_origins = cast(
        list[dict[str, object]],
        target_snapshot["allowed_origins"],
    )

    allowed_origins = tuple(
        AllowedOrigin(
            scheme=cast(
                Literal["http", "https"],
                origin["scheme"],
            ),
            hostname=cast(
                str,
                origin["hostname"],
            ),
            port=cast(
                int | None,
                origin["port"],
            ),
            include_subdomains=cast(
                bool,
                origin["include_subdomains"],
            ),
        )
        for origin in raw_origins
    )

    return MarketTwinRunRequest(
        run_id=test_run.id,
        study_brief=study_brief,
        target_snapshot=target_snapshot,
        start_url=start_url,
        allowed_origins=allowed_origins,
        max_duration_seconds_per_journey=(
            max_duration_seconds_per_journey
        ),
        knowledge_context=tuple(
            cast(list[dict[str, object]], configuration_snapshot.get("knowledge", []))
        ),
        testing_depth=testing_depth,
        agent_prompt_overrides=cast(
            dict[str, dict[str, str]], configuration_snapshot.get("agent_prompt_overrides", {})
        ),
        replay_plan=cast(dict[str, object] | None, configuration_snapshot.get("replay_plan")),
        execution_mode=cast(Literal["legacy_persona", "deep_feature_v1"], execution_mode),
        feature_scope=cast(dict[str, object] | None, configuration_snapshot.get("feature_scope")),
        feature_budget=cast(dict[str, object] | None, configuration_snapshot.get("feature_budget")),
        feature_plan=cast(dict[str, object] | None, configuration_snapshot.get("feature_plan")),
    )
