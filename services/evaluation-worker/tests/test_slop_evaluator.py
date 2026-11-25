"""U-P6-05: the slop report carries three families and no verdict."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from markettwin_evaluation_worker import slop_evaluator


def _state(url: str, elements: list[dict], js: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(payload={
        "url": url, "elements": elements, "page_signals": [], "js_errors": js,
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("desktop_partial", [False, True])
async def test_slop_report_three_families_no_verdict(monkeypatch, desktop_partial) -> None:
    events = [_state("https://app.example/", [
        {"verdict": "slop", "area": 100.0},
        {"verdict": "clean", "area": 100.0},
    ], [{"rule_id": "DEF_JS_UNCAUGHT", "severity": "serious", "count": 1}])]
    captured: dict = {}
    events[0].payload.update(title="Home", viewport="mobile320", interaction_path="Menu",
        screenshot_artifact_id="saved-artifact", measurement_evidence={"client_width": 320},
        screenshot_path="evidence.png", tier_context={"template_chrome_eyebrow_sections": 4},
        page_signals=[{
            "rule_id": "AUDIT_PARTIAL_COVERAGE", "severity": "info", "detail": "34 pages pending"}])
    coverage = {"pages_pending": 34, "paths_activated": 5, "paths_not_assessed": 1}
    if desktop_partial:
        coverage.update(
            pages_recorded=1, pages_unverified=1, states_recorded=1,
            pending_urls=[f"https://app.example/pending/{index}" for index in range(34)],
            evaluation_contract={"version": 1, "expected_states": 2},
        )
        unverified = _state("https://app.example/unverified", [], [])
        unverified.payload["page_signals"] = [{
            "rule_id": "UI_STATE_UNASSESSED", "severity": "info",
            "detail": "Page could not be inspected.",
        }]
        unverified.payload.update(lane_id=3, policy_code="action_refused")
        events.append(unverified)

    class _Reports:
        def __init__(self, session):
            pass

        async def create_completed_report(self, **kwargs):
            captured.update(kwargs)
            return uuid4()

    monkeypatch.setattr(slop_evaluator, "ReportRepository", _Reports)
    result = Mock()
    result.scalars = Mock(return_value=iter(events))
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    session.scalar = AsyncMock(return_value=SimpleNamespace(payload=coverage))
    session.scalars = AsyncMock(return_value=[{"decision": "continue", "reason": "Scope remains"}])
    finding_ids, _ = await slop_evaluator.evaluate_slop_run(
        test_run_id=uuid4(), session=session, require_contract=desktop_partial,
    )
    assert finding_ids == ()
    payload = captured["report_payload"]
    assert payload["run_kind"] == "slop"
    assert payload["coverage"]["pages_pending"] == 34
    assert payload["families"]["states_visited"] == len(events)
    assert payload["families"]["pages_inspected"] == 1
    assert "verdict" not in payload
    assert payload["families"]["slop"]["percentage"] == 50.0
    assert payload["families"]["defects"]["serious"] == 1
    assert payload["families"]["effort"]["value"] is None
    assert payload["states"][0]["viewport"] == "mobile320"
    assert payload["states"][0]["title"] == "Home"
    assert payload["activity_checkpoints"] == [{"decision": "continue", "reason": "Scope remains"}]
    assert payload["states"][0]["interaction_path"] == "Menu"
    assert payload["states"][0]["screenshot_artifact_id"] == "saved-artifact"
    assert payload["states"][0]["measurement_evidence"] == {"client_width": 320}
    assert payload["states"][0]["tier_context"] == {"template_chrome_eyebrow_sections": 4}
    assert payload["states"][0]["page_signals"][0]["detail"] == "34 pages pending"
    if desktop_partial:
        assert payload["coverage"]["pages_unverified"] == 1
        assert payload["states"][1]["url"] == "https://app.example/unverified"
        assert "title" not in payload["states"][1]
        assert payload["states"][1]["policy_code"] == "action_refused"
        assert payload["states"][1]["lane_id"] == 3


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("no_states", "slop_states_missing"),
        ("no_collection", "slop_contract_missing"),
        ("bad_version", "slop_contract_version"),
        ("missing_state", "slop_state_count_mismatch"),
        ("bad_coverage", "slop_coverage_mismatch"),
    ],
)
async def test_invalid_slop_handoff_cannot_create_a_report(monkeypatch, case, code):
    reports = Mock()
    monkeypatch.setattr(slop_evaluator, "ReportRepository", reports)
    states = [] if case == "no_states" else [_state("https://app.example", [], [])]
    coverage = {
        "evaluation_contract": {
            "version": 2 if case == "bad_version" else 1,
            "expected_states": 2 if case == "missing_state" else 1,
        },
        "states_recorded": 1, "pages_recorded": 1, "pages_unverified": 0,
        "pages_pending": 1 if case == "bad_coverage" else 0, "pending_urls": [],
    }
    session = Mock()
    session.execute = AsyncMock(return_value=Mock(scalars=lambda: iter(states)))
    session.scalar = AsyncMock(return_value=(
        None if case == "no_collection" else SimpleNamespace(payload=coverage)
    ))
    with pytest.raises(slop_evaluator.InvalidEvaluationInput) as error:
        await slop_evaluator.evaluate_slop_run(
            test_run_id=uuid4(), session=session, require_contract=True,
        )
    assert error.value.code == code
    reports.assert_not_called()
