import pytest
from markettwin_shared.contract_execution import contract_case
from markettwin_shared.discovery_contract import ContractAssertion, FrozenJourneyContract
from markettwin_shared.feature_plan import CaseAction, SemanticTarget


def test_owner_check_preserves_checkpoint_target_and_safe_input_key():
    journey = FrozenJourneyContract(
        journey_key="signup", feature_key="registration", title="Register",
        steps=(CaseAction(action="fill", target=SemanticTarget(label="Name"),
                          test_value_key="valid_name"),),
        assertions=(ContractAssertion(
            assertion_id="saved", oracle="visible_text", expected_value="Saved",
            plain_language="After entering a name, Saved appears.", source_step_ordinal=1,
            origin="user_approved",
        ),), safe_test_data_keys=("valid_name",),
    )
    case = contract_case(journey, "https://example.test")
    assert case.steps[0].test_value_key == "valid_name"
    assert case.expected[0].after_step_ordinal == 1
    assert case.expected[0].target == SemanticTarget(text="Saved")
    assert case.expected[0].origin == "user_approved"
    draft = journey.model_copy(update={"assertions": (
        journey.assertions[0].model_copy(update={"origin": None}),
    )})
    with pytest.raises(ValueError, match="approval"):
        contract_case(draft, "https://example.test")


@pytest.mark.parametrize("oracle", ["visible", "enabled"])
def test_first_click_precondition_runs_before_action(oracle: str):
    journey = FrozenJourneyContract(
        journey_key="continue", feature_key="checkout", title="Continue checkout",
        steps=(CaseAction(
            action="click", target=SemanticTarget(role="button", name="Continue"),
        ),),
        assertions=(ContractAssertion(
            assertion_id="continue_precondition", oracle=oracle,
            target_role="button", target_name="Continue", expected_value=True,
            plain_language="The Continue button is ready.", source_step_ordinal=1,
            origin="user_approved",
        ),),
    )

    case = contract_case(journey, "https://example.test")

    assert case.expected[0].after_step_ordinal == 0
    assert case.expected[0].target == case.steps[0].target
