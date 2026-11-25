"""Malformed library entries cannot mint empty Board states."""

import pytest

from markettwin_execution_orchestrator.workflow.harness_run import _seed_skill_items
from markettwin_execution_orchestrator.workflow.harness_state import HarnessState


@pytest.mark.parametrize("assertion", [None, [], "bad", {}])
def test_missing_terminal_url_is_accounted_without_a_phantom_state(assertion):
    state = HarnessState()
    result = _seed_skill_items(
        state, app_map={"skills": [{"skill_version_id": "v1", "definition": {
            "success_assertion": assertion,
        }}]}, replay_items=[{"skill_version_id": "v1"}],
    )
    assert result == []
    assert state.states == {}
    assert state.budget_counters["skills_not_seeded_missing_terminal_url"] == 1
