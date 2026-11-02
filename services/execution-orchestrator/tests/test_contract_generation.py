"""Contract generation from discovery maps without invented assertions."""

from uuid import uuid4

from markettwin_execution_orchestrator.workflow.contract_generation import (
    generate_journey_contract,
    generate_test_contract,
)
from markettwin_shared.discovery_contract import (
    DiscoveredFeature,
    DiscoveredJourney,
    DiscoveredStep,
    DiscoveryMap,
)


def test_contract_generation_preserves_steps_and_generates_observed_checks():
    step1 = DiscoveredStep(
        ordinal=1,
        action="navigate",
        navigation_url_path="/signup",
        resulting_url_path="/signup",
        resulting_page_title="Sign Up",
        observed_text_markers=("Create Account",),
        execution_step_id=101,
        name_source="playwright",
    )
    step2 = DiscoveredStep(
        ordinal=2,
        action="fill",
        target_role="textbox",
        target_name="Email",
        target_label="Email",
        input_key="valid_email",
        resulting_url_path="/signup",
        observed_text_markers=(),
        execution_step_id=102,
        name_source="playwright",
    )
    step3 = DiscoveredStep(
        ordinal=3,
        action="click",
        target_role="button",
        target_name="Submit",
        target_label="Submit",
        resulting_url_path="/welcome",
        resulting_page_title="Welcome",
        observed_text_markers=("Welcome aboard",),
        execution_step_id=103,
        name_source="playwright",
    )
    journey = DiscoveredJourney(
        journey_key="signup_flow",
        title="Sign Up Flow",
        feature_key="registration",
        completed=True,
        steps=(step1, step2, step3),
    )
    feature = DiscoveredFeature(
        feature_key="registration",
        title="Registration",
        entry_url_path="/signup",
        journey_keys=("signup_flow",),
    )
    discovery_map = DiscoveryMap(
        target_origin="https://example.test",
        features=(feature,),
        journeys=(journey,),
        coverage_notes=(),
    )

    test_run_id = uuid4()
    contract = generate_test_contract(
        discovery_map=discovery_map,
        test_run_id=test_run_id,
    )

    assert contract.test_run_id == test_run_id
    assert contract.version == 1
    assert contract.status == "draft"
    assert len(contract.journeys) == 1

    jc = contract.journeys[0]
    assert jc.journey_key == "signup_flow"
    assert jc.title == "Sign Up Flow"
    assert jc.feature_key == "registration"
    assert not jc.excluded
    assert len(jc.steps) == 3
    assert jc.safe_test_data_keys == ("valid_email",)

    # Actions match 1:1
    assert jc.steps[0].action == "navigate"
    assert jc.steps[0].url == "/signup"
    assert jc.steps[1].action == "fill"
    assert jc.steps[1].test_value_key == "valid_email"
    assert jc.steps[2].action == "click"
    assert jc.steps[2].target.name == "Submit"

    # Assertions generated from observations
    # Draft assertions have origin None
    for a in jc.assertions:
        assert a.origin is None

    oracles = {a.oracle for a in jc.assertions}
    assert "visible" in oracles  # Submit button point of use
    assert "enabled" in oracles  # Used control was operable when discovered
    assert "visible_text" in oracles  # "Create Account", "Welcome aboard"
    assert "url_path_v1" in oracles  # Final resulting_url_path /welcome
    assert "title" in oracles  # Final resulting_page_title Welcome

    url_assertion = next(a for a in jc.assertions if a.oracle == "url_path_v1")
    assert url_assertion.expected_value == "/welcome"
    assert "welcome" in url_assertion.plain_language.lower()


def test_incomplete_journey_is_marked_excluded():
    step = DiscoveredStep(
        ordinal=1,
        action="navigate",
        navigation_url_path="/dashboard",
        resulting_url_path="/login",
        execution_step_id=201,
        name_source="unavailable",
    )
    journey = DiscoveredJourney(
        journey_key="dashboard_access",
        title="Dashboard Access",
        feature_key="dashboard",
        completed=False,
        blocked_reason="authentication_required",
        steps=(step,),
    )
    jc = generate_journey_contract(journey)
    assert jc.excluded is True


def test_fixture_contract_caps_checks_and_prioritizes_behavioral_outcomes():
    steps = [DiscoveredStep(
        ordinal=1, action="navigate", navigation_url_path="/",
        resulting_url_path="/contact", resulting_page_title="Contact preview",
        execution_step_id=300,
    )]
    outcomes = (
        "Contact address is required",
        "The contact address was accepted",
        "Preview generated",
        "Billing settings",
        "The profile was saved",
    )
    for index, marker in enumerate(outcomes, start=2):
        steps.append(DiscoveredStep(
            ordinal=index, action="click", target_role="button",
            target_name=f"Fixture action {index}", target_label=f"Fixture action {index}",
            resulting_url_path="/contact" if index < 6 else "/preview",
            resulting_page_title="Preview generated" if index == 6 else None,
            observed_text_markers=(marker,), execution_step_id=300 + index,
            name_source="playwright",
        ))
    journey = DiscoveredJourney(
        journey_key="fixture_workflows", title="Complete fixture workflows",
        feature_key="application", completed=True, steps=tuple(steps),
    )

    contract_journey = generate_journey_contract(journey)

    assert len(contract_journey.assertions) == 8
    assert [a.expected_value for a in contract_journey.assertions
            if a.oracle == "visible_text"] == list(outcomes)
    assert any(a.oracle == "url_path_v1" and a.expected_value == "/preview"
               for a in contract_journey.assertions)
    assert any(a.oracle == "title" and a.expected_value == "Preview generated"
               for a in contract_journey.assertions)
    assert [a.oracle for a in contract_journey.assertions[:7]] == [
        "visible_text", "visible_text", "visible_text", "visible_text", "visible_text",
        "url_path_v1", "title",
    ]


def test_check_and_uncheck_actions_do_not_get_incompatible_role_name_preconditions():
    for action in ("check", "uncheck"):
        journey = DiscoveredJourney(
            journey_key=f"toggle_{action}", title=f"Toggle {action}",
            feature_key="preferences", completed=True,
            steps=(DiscoveredStep(
                ordinal=1, action=action, target_role="checkbox", target_name="Email updates",
                target_label="Email updates", resulting_url_path="/preferences",
                execution_step_id=500, name_source="playwright",
            ),),
        )

        contract_journey = generate_journey_contract(journey)

        assert not any(
            assertion.oracle in {"visible", "enabled"}
            for assertion in contract_journey.assertions
        )


def test_max_journeys_excludes_overflow_without_dropping_journey_cards():
    empty_journey = DiscoveredJourney(
        journey_key="journey_empty", title="Unobservable action",
        feature_key="application", completed=True,
        steps=(DiscoveredStep(
            ordinal=1, action="click", target_label="Mystery action",
            execution_step_id=399,
        ),),
    )
    journeys = (empty_journey, *(DiscoveredJourney(
        journey_key=f"journey_{index}", title=f"Journey {index}",
        feature_key="application", completed=True,
        steps=(DiscoveredStep(
            ordinal=1, action="click", target_role="button", target_name="Save",
            target_label="Save", execution_step_id=400 + index,
            name_source="playwright",
        ),),
    ) for index in range(3)))
    discovery_map = DiscoveryMap(
        target_origin="https://example.test", journeys=journeys,
        features=(DiscoveredFeature(
            feature_key="application", title="Application", entry_url_path="/",
            journey_keys=tuple(j.journey_key for j in journeys),
        ),),
    )

    contract = generate_test_contract(
        discovery_map=discovery_map, test_run_id=uuid4(), max_journeys=2,
    )

    assert len(contract.journeys) == 4
    assert [journey.excluded for journey in contract.journeys] == [True, False, False, True]
    assert contract.journeys[0].assertions == ()
