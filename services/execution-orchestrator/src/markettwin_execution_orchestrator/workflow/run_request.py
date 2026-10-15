"""Build execution requests from persisted TestRuns."""

from ipaddress import ip_address
from typing import Literal, cast
from urllib.parse import urlsplit

from markettwin_database.models.testing import TestRun
from markettwin_shared.auth_verification import AuthVerificationPolicy

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

    fixture_approval_enabled = bool(
        getattr(test_run, "synthetic_fixture_approval_enabled", False)
    )
    if fixture_approval_enabled:
        if str(target_snapshot.get("environment", "")) not in {"local", "test"}:
            raise ValueError("Synthetic fixture approval is outside its authorized environment.")
        if not allowed_origins:
            raise ValueError("Synthetic fixture approval requires loopback origins.")
        for origin in allowed_origins:
            try:
                is_loopback = origin.hostname == "localhost" or ip_address(
                    origin.hostname
                ).is_loopback
            except ValueError:
                is_loopback = False
            if not is_loopback:
                raise ValueError("Synthetic fixture approval requires all-loopback origins.")

    raw_auth_policy = configuration_snapshot.get("auth_verification")
    auth_verification = (
        AuthVerificationPolicy.model_validate(raw_auth_policy)
        if raw_auth_policy is not None
        else None
    )
    if target_snapshot.get("requires_auth") is True and (
        auth_verification is None or execution_mode != "deep_feature_v1"
    ):
        raise ValueError("Authenticated targets require deep execution and identity verification.")
    if auth_verification is not None:
        for origin in (auth_verification.origin, *auth_verification.auth_only_origins):
            parsed_auth_origin = urlsplit(origin)
            try:
                auth_port = parsed_auth_origin.port
            except ValueError as error:
                raise ValueError("Frozen authentication origin is invalid.") from error
            if not any(
                parsed_auth_origin.scheme == allowed.scheme
                and auth_port == allowed.port
                and (
                    parsed_auth_origin.hostname == allowed.hostname
                    or (
                        allowed.include_subdomains
                        and parsed_auth_origin.hostname is not None
                        and parsed_auth_origin.hostname.endswith("." + allowed.hostname)
                    )
                )
                for allowed in allowed_origins
            ):
                raise ValueError("Frozen authentication origin is outside the authorized target.")

    return MarketTwinRunRequest(
        run_id=test_run.id,
        study_brief=study_brief,
        target_snapshot=target_snapshot,
        start_url=start_url,
        allowed_origins=allowed_origins,
        max_duration_seconds_per_journey=(
            max_duration_seconds_per_journey
        ),
        network_policy="local_development" if fixture_approval_enabled else "public_only",
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
        auth_verification=auth_verification,
        fixture_truth=fixture_approval_enabled,
        synthetic_fixture_approval_enabled=fixture_approval_enabled,
        human_action_approvals_enabled=bool(
            getattr(test_run, "human_action_approvals_enabled", False)
        ),
        created_by_user_id=getattr(test_run, "created_by_user_id", None),
    )
