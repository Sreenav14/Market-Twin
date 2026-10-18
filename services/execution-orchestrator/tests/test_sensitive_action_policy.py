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


@pytest.mark.parametrize("name,path", [
    ("View payment documentation", "/docs/payments"),
    ("Invite API reference", "/reference/invitations"),
    ("Buyer's guide", "/guides/options"),
])
def test_real_authorized_documentation_links_are_read_only(name: str, path: str) -> None:
    assert classify_click_action(
        role="link", name=name, label=None, text=None,
        navigation_url="https://example.test" + path,
        navigation_origin_authorized=True, element_tag="a",
    ) is None


@pytest.mark.parametrize("metadata", [
    {},
    {"navigation_origin_authorized": False, "element_tag": "a"},
    {"navigation_origin_authorized": True, "element_tag": "button"},
    {"navigation_origin_authorized": True, "element_tag": "a", "has_form": True},
])
def test_documentation_words_alone_do_not_bypass_restricted_action(metadata) -> None:
    with pytest.raises(BrowserActionBlockedError):
        classify_click_action(
            role="link", name="View payment documentation", label=None, text=None,
            navigation_url="https://example.test/docs/payments", **metadata,
        )


@pytest.mark.parametrize("url", [
    "javascript:deleteAccount()", "https://example.test/delete",
    "https://example.test/docs/../delete", "https://example.test/docs/%2e%2e/delete",
    "https://example.test/docs/delete", "https://example.test/docs/payments?action=pay",
    "https://user:secret@example.test/docs/payments",
])
def test_action_destinations_remain_denied_even_with_documentation_label(url: str) -> None:
    with pytest.raises(BrowserActionBlockedError):
        classify_click_action(
            role="link", name="Payment documentation", label=None, text=None,
            navigation_url=url, navigation_origin_authorized=True, element_tag="a",
        )


def test_filter_reset_is_reviewable_not_automatically_executed() -> None:
    intent = classify_click_action(
        role="button", name="Remove filters", label=None, text=None,
        element_tag="button", has_form=False, state_digest="current-filter-state",
    )
    assert intent is not None and intent.category == "update"
    with pytest.raises(BrowserActionBlockedError):
        classify_click_action(
            role="button", name="Remove account", label=None, text=None,
            element_tag="button", has_form=False,
        )
