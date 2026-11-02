"""Translate approved observations into the existing deterministic case contract."""

from urllib.parse import urljoin

from markettwin_shared.discovery_contract import FrozenJourneyContract
from markettwin_shared.feature_plan import ExpectedAssertion, SemanticTarget, TestCaseSpec


def contract_case(journey: FrozenJourneyContract, origin: str) -> TestCaseSpec:
    if journey.excluded:
        raise ValueError("Excluded journeys cannot execute.")
    expected: list[ExpectedAssertion] = []
    for check in journey.assertions:
        if check.excluded:
            continue
        if check.origin != "user_approved":
            raise ValueError("Every executed check requires owner approval.")
        target = None
        if check.target_role and check.target_name:
            target = SemanticTarget(role=check.target_role, name=check.target_name)
        elif check.oracle == "visible_text" and isinstance(check.expected_value, str):
            target = SemanticTarget(text=check.expected_value)
        value = check.expected_value
        if value is None:
            raise ValueError("An approved check needs an expected value.")
        if check.oracle == "url_path_v1":
            value = urljoin(origin + "/", str(value))
        # Controls were observed at their point of use; inspect them before the action.
        checkpoint = check.source_step_ordinal - (check.oracle in {"visible", "enabled"})
        expected.append(ExpectedAssertion(
            assertion_id=check.assertion_id, oracle=check.oracle, target=target,
            expected_value=value, origin="user_approved", after_step_ordinal=checkpoint,
        ))
    steps = tuple(step.model_copy(update={"url": urljoin(origin + "/", step.url)})
                  if step.action == "navigate" and step.url else step for step in journey.steps)
    return TestCaseSpec(
        case_id=journey.journey_key, feature_key=journey.feature_key,
        title=journey.title[:160], kind="happy_path", steps=steps, expected=tuple(expected),
    )
