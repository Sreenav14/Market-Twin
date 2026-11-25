"""Feature-scope helpers re-homed from deep_run (U-P8).

The deep_feature_v1 executor is retired; these pure helpers are
still load-bearing for the unified engine (the harness driver builds
its scope and case journeys from them). They carry no
execution-mode behaviour.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from markettwin_execution_orchestrator.agents.schemas.journey import PersonaJourneySpec
from markettwin_execution_orchestrator.agents.schemas.mission import TestMissionSpec
from markettwin_execution_orchestrator.agents.schemas.persona import PersonaSpec
from markettwin_execution_orchestrator.agents.schemas.test_case import (
    FeatureScope,
    SafeTestValue,
    TestCaseSpec,
)
from markettwin_execution_orchestrator.browser import AllowedOrigin

if TYPE_CHECKING:
    from markettwin_execution_orchestrator.workflow.run_executor import MarketTwinRunRequest


def origin_url(origin: AllowedOrigin) -> str:
    host = f"[{origin.hostname}]" if ":" in origin.hostname else origin.hostname
    return f"{origin.scheme}://{host}" + (f":{origin.port}" if origin.port else "")


DEFAULT_SAFE_TEST_DATA: tuple[SafeTestValue, ...] = (
    SafeTestValue(key="valid_name", value="Visitor"),
    SafeTestValue(key="valid_email", value="fixture@example.test"),
    SafeTestValue(key="invalid_email", value="invalid"),
    SafeTestValue(key="empty", value=""),
    SafeTestValue(key="invalid_text", value="invalid"),
)


def merge_safe_test_data(
    base: tuple[SafeTestValue, ...], *overrides: tuple[SafeTestValue, ...],
) -> tuple[SafeTestValue, ...]:
    """Merge test-data tables (doc 17 section 6.3).

    Per key, the last table supplying the key wins; a key keeps the
    position of its first appearance and new keys append. Pure and
    deterministic: the same inputs always build the same scope table.
    """

    merged: dict[str, SafeTestValue] = {}
    for table in (base, *overrides):
        for entry in table:
            merged[entry.key] = entry
    return tuple(merged.values())


def default_scope(request: MarketTwinRunRequest) -> FeatureScope:
    return FeatureScope(
        feature_key="selected_feature",
        goal=request.study_brief[:1000],
        starting_url=request.start_url,
        allowed_origins=tuple(origin_url(origin) for origin in request.allowed_origins),
        safe_test_data=merge_safe_test_data(
            DEFAULT_SAFE_TEST_DATA, request.approved_test_data,
        ),
        requirements=(),
        unknown_requirements=("Undocumented behavior has inferred expectations only.",),
        out_of_scope=("credentials", "payments", "uploads", "destructive actions"),
    )


def case_journey(case: TestCaseSpec) -> PersonaJourneySpec:
    persona = PersonaSpec(
        persona_id="feature_tester_v1",
        name="Feature tester",
        perspective="Bounded execution of approved feature cases.",
        behavior_traits=("methodical",),
        priorities=("observable assertions",),
    )
    mission = TestMissionSpec(
        mission_id=case.case_id,
        name=case.title[:100],
        objective=case.title[:500],
        success_criteria=tuple(
            f"{item.assertion_id}: {item.oracle} expected {item.expected_value}"
            for item in case.expected
        ),
        priority=case.priority,
    )
    return PersonaJourneySpec(
        journey_key=f"feature_tester_v1__{case.case_id}",
        persona=persona,
        mission=mission,
    )


