"""Approved expected values must retain their exact type and case."""

from markettwin_evaluation_worker.deep_evaluator import _contract_matches_assertion
from markettwin_shared.discovery_contract import ContractAssertion
from markettwin_shared.feature_plan import ExpectedAssertion


def test_title_matching_does_not_casefold_owner_expectation() -> None:
    contract = ContractAssertion(
        assertion_id="title", oracle="title", expected_value="Welcome",
        plain_language="The title is Welcome.", source_step_ordinal=1,
    )
    expected = ExpectedAssertion(assertion_id="title", oracle="title", expected_value="Welcome")
    assert _contract_matches_assertion(contract, expected)
    assert not _contract_matches_assertion(
        contract, expected.model_copy(update={"expected_value": "WELCOME"}),
    )
