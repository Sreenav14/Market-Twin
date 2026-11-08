"""Feature-scope helpers re-homed from deep_run (U-P8).

The deep_feature_v1 executor is retired; these pure helpers are
still load-bearing for the unified engine (the harness driver builds
its scope and case journeys from them). They carry no
execution-mode behaviour.
"""

from __future__ import annotations

import json
import textwrap
from typing import TYPE_CHECKING, cast

from markettwin_execution_orchestrator.agents.schemas.journey import PersonaJourneySpec
from markettwin_execution_orchestrator.agents.schemas.mission import TestMissionSpec
from markettwin_execution_orchestrator.agents.schemas.persona import PersonaSpec
from markettwin_execution_orchestrator.agents.schemas.test_case import (
    FeatureScope,
    Requirement,
    SafeTestValue,
    TestCaseSpec,
)
from markettwin_execution_orchestrator.browser import AllowedOrigin

if TYPE_CHECKING:
    from markettwin_execution_orchestrator.workflow.run_executor import MarketTwinRunRequest


def origin_url(origin: AllowedOrigin) -> str:
    host = f"[{origin.hostname}]" if ":" in origin.hostname else origin.hostname
    return f"{origin.scheme}://{host}" + (f":{origin.port}" if origin.port else "")


def default_scope(request: MarketTwinRunRequest) -> FeatureScope:
    requirements, omitted = knowledge_requirements(request.knowledge_context)
    return FeatureScope(
        feature_key="selected_feature",
        goal=request.study_brief[:1000],
        starting_url=request.start_url,
        allowed_origins=tuple(origin_url(origin) for origin in request.allowed_origins),
        safe_test_data=(
            SafeTestValue(key="valid_name", value="Visitor"),
            SafeTestValue(key="valid_email", value="fixture@example.test"),
            SafeTestValue(key="invalid_email", value="invalid"),
            SafeTestValue(key="empty", value=""),
        ),
        requirements=requirements,
        unknown_requirements=("Undocumented behavior has inferred expectations only.",)
        + (
            (f"Requirement budget omitted {omitted} approved knowledge segments.",)
            if omitted else ()
        ),
        out_of_scope=("credentials", "payments", "uploads", "destructive actions"),
    )


def knowledge_requirements(
    knowledge: tuple[dict[str, object], ...],
) -> tuple[tuple[Requirement, ...], int]:
    """Select sourced prose segments and evidence references within the scope budget."""
    selected: list[Requirement] = []
    omitted = 0
    for item in knowledge:
        if "id" not in item:
            continue
        records: list[tuple[str, dict[str, object]]] = []
        for kind in ("skills", "application_knowledge", "artifacts"):
            values = item.get(kind)
            if isinstance(values, list):
                for record in cast(list[object], values):
                    if isinstance(record, dict):
                        records.append((kind, cast(dict[str, object], record)))
        if not records:
            records = [("source", {"name": item.get("name", "Approved source")})]
        for kind, record in records:
            evidence = json.dumps(record.get("evidence_ordinals", []), separators=(",", ":"))
            # A bounded prefix is metadata, never a chopped JSON document.
            prefix = f"{kind}; evidence_ordinals={evidence}"
            if len(prefix) > 200:
                omitted += 1
                continue
            for key in ("name", "content", "definition", "steps"):
                value = record.get(key)
                if not value:
                    continue
                fields = (
                    cast(dict[str, object], value).items()
                    if isinstance(value, dict) else ((key, value),)
                )
                for field, content in fields:
                    texts = (
                        cast(list[object] | tuple[object, ...], content)
                        if isinstance(content, (list, tuple)) else (content,)
                    )
                    for text in texts:
                        if not isinstance(text, str):
                            continue
                        # Keep JSON structure out of prose chunks; references stay on each segment.
                        for segment in textwrap.wrap(
                            text, width=750, break_long_words=False, break_on_hyphens=False,
                        ):
                            rendered = f"{prefix}; {field}: {segment}"
                            if len(rendered) > 1000 or len(selected) >= 32:
                                omitted += 1
                                continue
                            selected.append(Requirement(
                                requirement_id=f"knowledge_{len(selected)}",
                                source="approved_knowledge", source_id=str(item["id"]),
                                text=rendered,
                            ))
    return tuple(selected), omitted


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


