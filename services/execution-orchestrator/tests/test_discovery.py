"""Discovery mechanics and provenance; these tests do not measure model quality."""

from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.tools import create_browser_tools
from markettwin_execution_orchestrator.workflow.discovery import (
    DiscoveryJournal,
    DiscoveryProgressTracker,
    record_discovered_step,
)
from markettwin_shared.discovery_contract import DiscoveredJourney, DiscoveredStep
from pydantic import ValidationError


def test_observation_and_scroll_loops_are_bounded_and_actions_reset_progress() -> None:
    tracker = DiscoveryProgressTracker()
    for _ in range(3):
        assert tracker.before_call("browser_get_state", "/") is None
    assert tracker.reminder is not None
    assert tracker.before_call("browser_get_state", "/") is None
    assert tracker.before_call("browser_get_state", "/") == "observation_loop"
    tracker.reset_journey()
    for _ in range(3):
        assert tracker.before_call("browser_scroll", "/") is None
    assert tracker.before_call("browser_scroll", "/") == "observation_loop"
    assert tracker.before_call("browser_click", "/") is None
    assert tracker.reminder is None
    assert tracker.before_call("browser_scroll", "/") is None


def test_repeated_failed_locator_and_run_wide_step_budget() -> None:
    tracker = DiscoveryProgressTracker()
    assert tracker.failed_locator({"role": "button", "name": "Continue"}) is None
    assert tracker.failed_locator({"role": "button", "name": "Continue"}) == "target_not_found"
    tracker.calls = 60
    tracker.reset_journey()
    assert tracker.before_call("browser_click", "/") == "step_budget"


def test_map_drops_foreign_steps_and_never_completes_navigate_only_journey() -> None:
    journal = DiscoveryJournal(origin="https://example.test", title="Open details")
    journal.indexed_paths.add("/")
    journal.steps = [DiscoveredStep(ordinal=1, action="click", target_label="Details",
                                    execution_step_id=17)]
    journal.end(True)
    assert journal.snapshot({17}).journeys[0].completed
    dropped = journal.snapshot({999}).journeys[0]
    assert dropped.steps == ()
    assert not dropped.completed
    assert dropped.blocked_reason == "unknown"
    with pytest.raises(ValidationError):
        DiscoveredJourney(journey_key="navigate_only", title="Open", feature_key="application",
                          completed=True, steps=(DiscoveredStep(
                              ordinal=1, action="navigate", execution_step_id=1,
                          ),))


def test_steps_come_from_observation_not_model_and_require_safe_data_keys() -> None:
    journal = DiscoveryJournal(origin="https://example.test", title="Read details")
    journal.observation = {"title": "Details", "visible_elements": [
        {"role": "heading", "name": "Product details", "level": 1},
    ]}
    record_discovered_step(journal, "browser_click", {"role": "button", "name": "Details"},
                           {"step_id": 12, "locator_strategy": "role_exact"},
                           {"visible_elements": [{"role": "button", "name": "Details",
                                                   "name_source": "playwright"}]})
    assert journal.steps[0].observed_text_markers == ("Product details",)
    assert journal.steps[0].execution_step_id == 12
    with pytest.raises(ValidationError):
        DiscoveredStep(ordinal=1, action="fill", execution_step_id=1)
    with pytest.raises(ValidationError):
        DiscoveredStep(ordinal=1, action="click", execution_step_id=1,
                       target_role="button", target_name="Approximate")


def test_scroll_markers_keep_alert_status_and_h1_but_drop_section_heading():
    journal = DiscoveryJournal(origin="https://example.test", title="Update profile")
    journal.observation = {
        "url": "https://example.test/profile",
        "title": "Profile",
        "visible_elements": [
            {"role": "heading", "name": "Profile", "level": 1},
            {"role": "heading", "name": "Contact details", "level": 2},
            {"role": "alert", "name": "Email is required"},
            {"role": "status", "name": "Changes saved"},
        ],
    }
    record_discovered_step(
        journal, "browser_click", {"role": "button", "name": "Save profile"},
        {"step_id": 31, "locator_strategy": "role_exact"},
        {"url": "https://example.test/profile", "visible_elements": [
            {"role": "button", "name": "Save profile", "name_source": "playwright"},
        ]},
    )
    assert journal.steps[0].observed_text_markers == (
        "Profile", "Email is required", "Changes saved",
    )


def test_navigation_markers_keep_destination_heading():
    journal = DiscoveryJournal(origin="https://example.test", title="Open billing")
    journal.observation = {
        "url": "https://example.test/billing",
        "title": "Billing",
        "visible_elements": [
            {"role": "heading", "name": "Billing settings", "level": 2},
        ],
    }
    record_discovered_step(
        journal, "browser_click", {"role": "link", "name": "Billing"},
        {"step_id": 32, "locator_strategy": "role_exact"},
        {"url": "https://example.test/profile", "visible_elements": [
            {"role": "link", "name": "Billing", "name_source": "playwright"},
        ]},
    )
    assert journal.steps[0].observed_text_markers == ("Billing settings",)


async def test_discovery_page_index_includes_offscreen_controls_and_is_opt_in(tmp_path) -> None:
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(),
            allowed_origins=(AllowedOrigin("https", "example.test"),),
            network_policy="public_only",
        )
        # Fixture setup only: production agents cannot access the underlying page.
        session = controller._sessions[handle.session_id]
        await session.page.set_content("".join(
            f'<button style="display:block;height:100px">Button {i}</button>' for i in range(90)
        ))
        ordinary = create_browser_tools(controller=controller, handle=handle)
        tools = create_browser_tools(controller=controller, handle=handle, discovery=True)
        assert "browser_get_page_index" not in {t.__name__ for t in ordinary}
        index = next(t for t in tools if t.__name__ == "browser_get_page_index")
        first, second = await index(), await index(cursor=80)
        assert len(first["page_index"]) == 80
        assert len(second["page_index"]) == 10
        assert first["next_cursor"] == 80
        assert second["next_cursor"] is None
        assert second["page_index"][-1]["name"] == "Button 89"


def test_unused_indexed_controls_exclude_attempted_targets():
    journal = DiscoveryJournal(origin="https://example.test", title="Open help")
    journal.indexed_controls["start"] = [
        {"role": "link", "name": "Open help guide"},
        {"role": "button", "name": "Generate preview"},
        {"role": "button", "name": "Continue to next step"},
    ]
    journal.steps = [DiscoveredStep(ordinal=1, action="click", target_role="link",
                                    target_name="Open help guide", execution_step_id=8,
                                    name_source="playwright")]
    journal.end(True)
    leftover = journal.unused_indexed_controls()
    assert leftover == (
        {"role": "button", "name": "Generate preview"},
        {"role": "button", "name": "Continue to next step"},
    )


def test_indexed_offscreen_name_is_grounded_but_index_does_not_cross_pages():
    journal = DiscoveryJournal(origin="https://example.test", title="Open billing")
    journal.current_page = "root-query-page"
    journal.indexed_paths.add(journal.current_page)
    journal.indexed_controls[journal.current_page] = [
        {"role": "link", "name": "Open billing settings", "name_source": "playwright"},
    ]
    previous = journal.locator_observation()
    journal.current_page = "billing-query-page"
    journal.observation = {"title": "Billing", "visible_elements": []}
    record_discovered_step(
        journal, "browser_click", {"role": "link", "name": "Open billing settings"},
        {"step_id": 21, "locator_strategy": "role_exact"}, previous,
    )
    assert journal.steps[0].name_source == "playwright"
    assert journal.locator_observation()["visible_elements"] == []
    journal.end(True)
    assert journal.journeys[0].completed
    assert "billing-query-page" not in journal.indexed_paths
