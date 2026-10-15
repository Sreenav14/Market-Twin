"""Hard-denied and opaque actions cannot acquire generic approval."""

import pytest
from markettwin_shared.action_approval import SensitiveActionRule
from pydantic import ValidationError

from markettwin_execution_orchestrator.browser.errors import BrowserActionBlockedError
from markettwin_execution_orchestrator.browser.sensitive_action_policy import classify_click_action


@pytest.mark.parametrize("name", ["Delete", "Send invitation", "Checkout", "Grant access", "Continue", "Confirm"])
def test_denied_and_opaque_actions_are_not_approvable(name: str) -> None:
    with pytest.raises(BrowserActionBlockedError):
        classify_click_action(role="button", name=name, label=None, text=None)


@pytest.mark.parametrize("name", ["Save", "Create record", "Update profile", "Publish draft", "Submit"])
def test_eligible_actions_bind_the_current_resource_state(name: str) -> None:
    original = classify_click_action(
        role="button", name=name, label=None, text=None, state_digest="state-one",
    )
    changed = classify_click_action(
        role="button", name=name, label=None, text=None, state_digest="state-two",
    )
    assert original is not None and changed is not None
    assert original.fingerprint != changed.fingerprint
    assert "state-one" not in original.display_summary


def test_observed_target_cannot_hide_a_hard_denied_effect_behind_locator_text() -> None:
    with pytest.raises(BrowserActionBlockedError):
        classify_click_action(
            role="button", name="Save", label=None, text=None,
            observed_description="Save and send invitation",
        )


def test_user_declared_rule_is_exact_and_requires_reset_confirmation() -> None:
    rule = SensitiveActionRule(
        category="save", name="Save", resource_reference="fixture-row-v1",
        test_data_reset_confirmed=True,
    )
    intent = classify_click_action(role="button", name="Save", label=None, text=None)
    assert intent is not None and rule.matches(intent.action)
    assert not rule.matches({**intent.action, "name": "Save all"})
    assert not rule.matches({**intent.action, "scope_role": "form", "scope_name": "Other"})
    with pytest.raises(ValidationError):
        SensitiveActionRule.model_validate({
            "category": "save", "name": "Save", "resource_reference": "fixture-row-v1",
            "test_data_reset_confirmed": False,
        })
