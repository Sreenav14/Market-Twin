"""Build execution requests from persisted TestRuns."""

from typing import Literal, cast

from markettwin_database.models.testing import TestRun

from markettwin_execution_orchestrator.browser import AllowedOrigin
from markettwin_execution_orchestrator.workflow.run_executor import (
    MarketTwinRunRequest,
)


def build_run_request(
    test_run: TestRun,
    *,
    max_duration_seconds_per_journey: int = 90,
) -> MarketTwinRunRequest:
    """Build the runtime request from one persisted TestRun."""

    target_snapshot = test_run.target_snapshot
    configuration_snapshot = test_run.configuration_snapshot

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
    )
