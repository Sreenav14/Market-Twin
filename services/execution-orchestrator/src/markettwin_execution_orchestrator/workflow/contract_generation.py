"""Deterministic TestContract generation from discovered application journeys."""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from markettwin_shared.discovery_contract import (
    ContractAssertion,
    DiscoveredJourney,
    DiscoveredStep,
    DiscoveryMap,
    FrozenJourneyContract,
    TestContract,
)
from markettwin_shared.feature_plan import CaseAction, SemanticTarget


def _step_to_case_action(step: DiscoveredStep) -> CaseAction:
    scope_role = (
        step.scope_role
        if step.scope_role in {"form", "region", "dialog", "listitem", "navigation"}
        and step.scope_name
        else None
    )
    scope_name = step.scope_name if scope_role else None

    target: SemanticTarget | None = None
    if step.action in {"fill", "select", "check", "uncheck"}:
        label = step.target_label or step.target_name or "field"
        target = SemanticTarget(
            label=label,
            scope_role=scope_role,  # type: ignore[arg-type]
            scope_name=scope_name,
        )
    elif step.target_role and step.target_name:
        target = SemanticTarget(
            role=step.target_role,
            name=step.target_name,
            scope_role=scope_role,  # type: ignore[arg-type]
            scope_name=scope_name,
        )
    elif step.target_label:
        target = SemanticTarget(
            label=step.target_label,
            scope_role=scope_role,  # type: ignore[arg-type]
            scope_name=scope_name,
        )
    elif step.target_text:
        target = SemanticTarget(
            text=step.target_text,
            scope_role=scope_role,  # type: ignore[arg-type]
            scope_name=scope_name,
        )

    if step.action == "navigate":
        url = step.navigation_url_path or step.resulting_url_path or "/"
        return CaseAction(action="navigate", url=url)
    elif step.action == "click":
        return CaseAction(action="click", target=target)
    elif step.action == "fill":
        return CaseAction(action="fill", target=target, test_value_key=step.input_key)
    elif step.action == "select":
        return CaseAction(action="select", target=target, test_value_key=step.input_key)
    elif step.action == "check":
        return CaseAction(action="check", target=target)
    elif step.action == "uncheck":
        return CaseAction(action="uncheck", target=target)
    elif step.action == "go_back":
        return CaseAction(action="navigate", url=step.resulting_url_path or "/")
    raise ValueError(f"Unsupported discovery action: {step.action}")


def _generate_step_description(step: DiscoveredStep) -> str:
    target_desc = step.target_name or step.target_label or step.target_text or "element"
    if step.action == "click":
        return f"clicking {step.target_role or 'control'} '{target_desc}'"
    elif step.action in {"fill", "select"}:
        return f"entering input into '{target_desc}'"
    elif step.action == "check":
        return f"checking '{target_desc}'"
    elif step.action == "uncheck":
        return f"unchecking '{target_desc}'"
    elif step.action == "navigate":
        return f"navigating to '{step.navigation_url_path or '/'}'"
    return f"performing {step.action}"


def _generate_journey_assertions(journey: DiscoveredJourney) -> list[ContractAssertion]:
    assertions: list[ContractAssertion] = []
    assertion_idx = 1

    for step in journey.steps:
        step_desc = _generate_step_description(step)

        # 1. Used control visibility/enabled assertion at point of use
        # Point-of-use preconditions must share the next action's exact semantic
        # target. Form check/uncheck actions execute through their label, while
        # ContractAssertion currently carries only role/name targets.
        if step.target_role and step.target_name and step.action == "click":
            checks: tuple[tuple[Literal["visible", "enabled"], str], ...] = (
                ("visible", "is visible"),
                ("enabled", "is enabled"),
            )
            for oracle, expectation in checks:
                assertions.append(
                    ContractAssertion(
                        assertion_id=f"chk_{journey.journey_key}_s{step.ordinal}_{assertion_idx}",
                        oracle=oracle,
                        target_role=step.target_role,
                        target_name=step.target_name,
                        expected_value=True,
                        plain_language=(
                            f"At step {step.ordinal}, {step.target_role} '{step.target_name}' "
                            f"{expectation}."
                        ),
                        source_step_ordinal=step.ordinal,
                        origin=None,
                    )
                )
                assertion_idx += 1

        # 2. Observed markers appearing after the step
        # Initial navigation headings describe the starting page, rather than an
        # outcome of the journey's interactions. Final state is checked below.
        for marker in step.observed_text_markers if step.action != "navigate" else ():
            assertions.append(
                ContractAssertion(
                    assertion_id=f"chk_{journey.journey_key}_s{step.ordinal}_{assertion_idx}",
                    oracle="visible_text",
                    expected_value=marker,
                    plain_language=f"After {step_desc}, text '{marker}' appears.",
                    source_step_ordinal=step.ordinal,
                    origin=None,
                )
            )
            assertion_idx += 1

    # 3. Final step assertions (URL path and title)
    if journey.steps:
        last_step = journey.steps[-1]
        if last_step.resulting_url_path and last_step.resulting_url_path.startswith("/"):
            assertions.append(
                ContractAssertion(
                    assertion_id=f"chk_{journey.journey_key}_url_{assertion_idx}",
                    oracle="url_path_v1",
                    expected_value=last_step.resulting_url_path,
                    plain_language=(
                        f"After completing '{journey.title}', the page URL is "
                        f"'{last_step.resulting_url_path}'."
                    ),
                    source_step_ordinal=last_step.ordinal,
                    origin=None,
                )
            )
            assertion_idx += 1

        if last_step.resulting_page_title:
            assertions.append(
                ContractAssertion(
                    assertion_id=f"chk_{journey.journey_key}_title_{assertion_idx}",
                    oracle="title",
                    expected_value=last_step.resulting_page_title,
                    plain_language=(
                        f"After completing '{journey.title}', the page title is "
                        f"'{last_step.resulting_page_title}'."
                    ),
                    source_step_ordinal=last_step.ordinal,
                    origin=None,
                )
            )

    behavioral = [a for a in assertions if a.oracle in {"visible_text", "url_path_v1", "title"}]
    optional_controls = [a for a in assertions if a.oracle in {"visible", "enabled"}]
    return (behavioral + optional_controls)[:8]


def generate_journey_contract(journey: DiscoveredJourney) -> FrozenJourneyContract:
    steps = tuple(_step_to_case_action(s) for s in journey.steps)
    assertions = tuple(_generate_journey_assertions(journey))
    safe_keys = tuple(dict.fromkeys(s.input_key for s in journey.steps if s.input_key is not None))

    return FrozenJourneyContract(
        journey_key=journey.journey_key,
        title=journey.title,
        feature_key=journey.feature_key,
        steps=steps,
        assertions=assertions,
        safe_test_data_keys=safe_keys,
        excluded=not journey.completed,
    )


def generate_test_contract(
    *,
    discovery_map: DiscoveryMap,
    test_run_id: UUID,
    contract_id: UUID | None = None,
    max_journeys: int | None = None,
) -> TestContract:
    """Generate a draft TestContract from discovery observations."""
    if max_journeys is not None and max_journeys < 0:
        raise ValueError("max_journeys must be non-negative.")
    retained = 0
    generated: list[FrozenJourneyContract] = []
    for journey in discovery_map.journeys:
        try:
            contract_journey = generate_journey_contract(journey)
        except ValueError:
            # Keep the discovered card visible, but do not turn an invalid target
            # into an executable contract step.
            contract_journey = FrozenJourneyContract(
                journey_key=journey.journey_key,
                title=journey.title,
                feature_key=journey.feature_key,
                excluded=True,
            )
        replayable = bool(contract_journey.steps) and any(
            not assertion.excluded for assertion in contract_journey.assertions
        )
        if journey.completed and not replayable:
            contract_journey = contract_journey.model_copy(update={"excluded": True})
        elif journey.completed and max_journeys is not None:
            if retained >= max_journeys:
                contract_journey = contract_journey.model_copy(update={"excluded": True})
            else:
                retained += 1
        generated.append(contract_journey)
    journeys = tuple(generated)
    return TestContract(
        contract_id=contract_id or uuid4(),
        test_run_id=test_run_id,
        version=1,
        status="draft",
        journeys=journeys,
    )
