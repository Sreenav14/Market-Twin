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
async def test_slop_report_three_families_no_verdict(monkeypatch) -> None:
    events = [_state("https://app.example/", [
        {"verdict": "slop", "area": 100.0},
        {"verdict": "clean", "area": 100.0},
    ], [{"rule_id": "DEF_JS_UNCAUGHT", "severity": "serious", "count": 1}])]
    captured: dict = {}

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
    finding_ids, _ = await slop_evaluator.evaluate_slop_run(
        test_run_id=uuid4(), session=session,
    )
    assert finding_ids == ()
    payload = captured["report_payload"]
    assert payload["run_kind"] == "slop"
    assert "verdict" not in payload
    assert payload["families"]["slop"]["percentage"] == 50.0
    assert payload["families"]["defects"]["serious"] == 1
    assert payload["families"]["effort"]["value"] is None
