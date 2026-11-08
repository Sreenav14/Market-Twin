"""U-P5-05: the persona report groups quotes and carries NO verdict."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from markettwin_evaluation_worker import persona_evaluator


def _event(persona_id: str, kind: str, quote: str) -> SimpleNamespace:
    return SimpleNamespace(payload={
        "persona_id": persona_id, "persona_name": "Impatient mobile user",
        "persona_type": "impatient_mobile", "kind": kind, "quote": quote,
        "journey_url": "https://app.example.test/home", "page_title": "Home",
        "signal": {"load_ms": 4200} if kind == "slow_load" else {},
    })


@pytest.mark.asyncio
async def test_persona_report_groups_quotes_and_has_no_verdict(monkeypatch) -> None:
    events = [
        _event("impatient_mobile-1", "slow_load", "I waited 4.2 seconds…"),
        _event("impatient_mobile-1", "fast_and_clean", "That felt easy."),
        _event("expert-1", "page_errors", "Something broke…"),
    ]
    captured: dict = {}

    class _Reports:
        def __init__(self, session):
            pass

        async def create_completed_report(self, **kwargs):
            captured.update(kwargs)
            return uuid4()

    monkeypatch.setattr(persona_evaluator, "ReportRepository", _Reports)
    result = Mock()
    result.scalars = Mock(return_value=iter(events))
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    finding_ids, report_id = await persona_evaluator.evaluate_persona_run(
        test_run_id=uuid4(), session=session,
    )
    assert finding_ids == ()
    payload = captured["report_payload"]
    assert payload["run_kind"] == "persona"
    assert "verdict" not in payload
    assert payload["total_impressions"] == 3
    assert payload["friction_count"] == 2
    by_id = {p["persona_id"]: p for p in payload["personas"]}
    assert by_id["impatient_mobile-1"]["friction_count"] == 1
    assert by_id["expert-1"]["impressions"][0]["quote"] == "Something broke…"
    assert "score" not in str(payload).lower()
