"""Build execution requests from persisted TestRuns."""

import re
from ipaddress import ip_address
from typing import Literal, cast
from urllib.parse import urlsplit

from markettwin_database.models.testing import TestRun
from markettwin_shared.action_approval import SensitiveActionRule
from markettwin_shared.auth_verification import AuthVerificationPolicy
from markettwin_shared.run_kind import resolve_run_kind

from markettwin_execution_orchestrator.agents.schemas.test_case import (
    SafeTestValue,
)
from markettwin_execution_orchestrator.browser import AllowedOrigin
from markettwin_execution_orchestrator.workflow.run_executor import (
    MarketTwinRunRequest,
)
from markettwin_execution_orchestrator.workflow.testing_depth import TestingDepth, mission_limit


def _parse_app_map(
    configuration_snapshot: dict[str, object],
) -> dict[str, object] | None:
    """Accept the snapshot's app_map block only in its pinned shape.

    The block is written at run creation from the application map
    (Phase 1a spec section 9.3). A malformed block is treated as
    absent (section 10.1): a run must never die over reference
    data, it simply starts uninformed.
    """

    raw = configuration_snapshot.get("app_map")
    if not isinstance(raw, dict):
        return None
    if not isinstance(raw.get("map_id"), str) or not raw.get("map_id"):
        return None
    routes = raw.get("routes")
    if not isinstance(routes, list) or not all(
        isinstance(route, str) for route in routes
    ):
        return None
    freshness = raw.get("freshness")
    if freshness is not None and not _freshness_shape_ok(freshness):
        # Doc 23 section 8.1: a malformed freshness block is treated
        # as absent — the map block itself still serves.
        raw = {
            key: value for key, value in raw.items() if key != "freshness"
        }
    return cast(dict[str, object], raw)


_FRESHNESS_STATES = ("current", "stale", "unknown")
_FRESHNESS_PREFLIGHT_STATUSES = (
    "reused",
    "completed",
    "timed_out",
    "failed",
    "not_required",
    "not_run",
)
_FRESHNESS_TTL_TRUST = ("within", "beyond", "not_applicable")
_FRESHNESS_OUTCOME_KEYS = ("present", "changed", "unreachable", "missing", "new")


def _freshness_shape_ok(value: object) -> bool:
    """The section 8.1 freshness block's pinned shape, checked
    additively exactly as the 1a block is checked: the three enums,
    the pin flag as a bool, the five outcome counts as ints.
    Anything else is malformed and the caller treats the block as
    absent. Never raises."""

    if not isinstance(value, dict):
        return False
    if value.get("state") not in _FRESHNESS_STATES:
        return False
    if value.get("preflight_status") not in _FRESHNESS_PREFLIGHT_STATUSES:
        return False
    if value.get("ttl_trust") not in _FRESHNESS_TTL_TRUST:
        return False
    if not isinstance(value.get("pinned_via_preflight"), bool):
        return False
    counts = value.get("outcome_counts")
    if not isinstance(counts, dict):
        return False
    return all(
        isinstance(counts.get(key), int) for key in _FRESHNESS_OUTCOME_KEYS
    )


def _parse_source_knowledge(
    configuration_snapshot: dict[str, object],
) -> dict[str, object] | None:
    """Accept the snapshot's source_knowledge block only in its
    pinned shape (doc 33 section 3.6). The block is written at run
    creation from the approved file index, pinned by hash. A
    malformed block is treated as absent, exactly like the app_map
    block: a run must never die over reference data. Never raises."""

    raw = configuration_snapshot.get("source_knowledge")
    if not isinstance(raw, dict):
        return None
    files = raw.get("files")
    collections = raw.get("collections")
    if not isinstance(files, list) or not isinstance(collections, list):
        return None
    for entry in files:
        if not isinstance(entry, dict):
            return None
        if not all(
            isinstance(entry.get(key), str) and entry.get(key)
            for key in ("file_id", "entry_id", "slug", "title", "object_key", "sha256")
        ):
            return None
    for entry in collections:
        if not isinstance(entry, dict):
            return None
        if not all(
            isinstance(entry.get(key), str) and entry.get(key)
            for key in ("entry_id", "manifest_object_key")
        ):
            return None
    return cast(dict[str, object], raw)


_APPROVED_TEST_DATA_KEY = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def _parse_approved_test_data(
    configuration_snapshot: dict[str, object],
) -> tuple[SafeTestValue, ...]:
    """Accept the snapshot's approved_test_data block only in its pinned shape.

    The block is written at run creation from the owner's declared
    test data (doc 17 section 5.2). An entry that fails the shape is
    dropped and a non-list block yields nothing (C7): consumption
    forgives, so the run falls back to the built-in defaults rather
    than dying over owner data. Never raises.
    """

    raw = configuration_snapshot.get("approved_test_data")
    if not isinstance(raw, list):
        return ()
    entries: list[SafeTestValue] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        value = entry.get("value")
        if not isinstance(key, str) or not _APPROVED_TEST_DATA_KEY.match(key):
            continue
        if not isinstance(value, str):
            continue
        try:
            entries.append(SafeTestValue(key=key, value=value))
        except Exception:
            continue
    return tuple(entries)


def _parse_brand_tokens(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    palette = value.get("palette_hexes")
    families = value.get("font_families")
    return {
        "palette_hexes": (
            [str(item) for item in palette if isinstance(item, str)]
            if isinstance(palette, list) else []
        ),
        "font_families": (
            [str(item) for item in families if isinstance(item, str)]
            if isinstance(families, list) else []
        ),
    }


def _parse_slop_classes(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    classes = tuple(
        item for item in value
        if isinstance(item, str) and item.strip()
    )
    return classes or None


def build_run_request(
    test_run: TestRun,
    *,
    max_duration_seconds_per_journey: int = 90,
) -> MarketTwinRunRequest:
    """Build the runtime request from one persisted TestRun."""

    target_snapshot = test_run.target_snapshot
    configuration_snapshot = test_run.configuration_snapshot
    # Unified-native runs (U-P1-06): a run_kind column value and no
    # legacy execution_mode in the snapshot. They dispatch on kind.
    unified_native = (
        getattr(test_run, "run_kind", None) is not None
        and "execution_mode" not in configuration_snapshot
    )
    resolved_kind = resolve_run_kind(
        run_kind_column=getattr(test_run, "run_kind", None),
        configuration_snapshot=configuration_snapshot,
    )
    # U-P8: persona/slop execute only as unified-native runs; legacy
    # snapshots resolving to those kinds refuse loudly at dispatch.
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
    auth_mode = configuration_snapshot.get("auth_mode", "required")
    if auth_mode not in {"required", "optional"}:
        raise ValueError("Unsupported authentication mode.")
    if (configuration_snapshot.get("runtime_human_assistance") is not True
            and target_snapshot.get("requires_auth") is True) and (
        auth_verification is None or auth_mode != "required"
    ):
        raise ValueError("Authenticated targets require mandatory identity verification.")
    if auth_mode == "optional" and auth_verification is None:
        raise ValueError("Optional authentication requires an approved identity policy.")
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
        app_map=_parse_app_map(configuration_snapshot),
        source_knowledge=_parse_source_knowledge(configuration_snapshot),
        approved_test_data=_parse_approved_test_data(configuration_snapshot),
        brand_tokens=_parse_brand_tokens(configuration_snapshot.get("brand_tokens")),
        slop_classes_enabled=_parse_slop_classes(
            configuration_snapshot.get("slop_classes_enabled")
        ),
        testing_depth=testing_depth,
        fixture_action_rules=tuple(
            SensitiveActionRule.model_validate(rule)
            for rule in cast(list[object], configuration_snapshot.get("sensitive_action_rules", []))
        ) if fixture_approval_enabled and getattr(test_run, "human_action_approvals_enabled", False)
        else (),
        run_kind=resolved_kind,
        unified_native=unified_native,
        feature_plan=cast(dict[str, object] | None, configuration_snapshot.get("feature_plan")),
        auth_verification=auth_verification,
        auth_mode=cast(Literal["required", "optional"], auth_mode),
        runtime_human_assistance=configuration_snapshot.get("runtime_human_assistance") is True,
        fixture_truth=fixture_approval_enabled,
        synthetic_fixture_approval_enabled=fixture_approval_enabled,
        human_action_approvals_enabled=bool(
            getattr(test_run, "human_action_approvals_enabled", False)
        ),
        created_by_user_id=getattr(test_run, "created_by_user_id", None),
    )
