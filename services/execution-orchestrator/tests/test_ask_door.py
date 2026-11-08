"""U-P7 gate: the ask door degrades, never fails.

- deterministic defaults are identity functions;
- a Decisions outage with calibration on falls back to the Model;
- Model down too -> deterministic order, no exception;
- refusals are no-decisions;
- narration falls back to the caller's template.
"""

import json

import httpx
import pytest

from markettwin_execution_orchestrator.models import ask, decisions_client
from markettwin_execution_orchestrator.models.decisions_client import (
    DecisionQuestion,
    decide,
)

CANDIDATES = [
    {"id": "a", "label": "Pay button"},
    {"id": "b", "label": "Footer link"},
    {"id": "c", "label": "Search box"},
]


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "test-key")


@pytest.mark.asyncio
async def test_deterministic_defaults(monkeypatch) -> None:
    monkeypatch.delenv("ASK_BACKEND_RANK_ITEMS", raising=False)
    assert await ask.rank_items(candidates=CANDIDATES, context="board") == ["a", "b", "c"]
    assert await ask.classify_impression(kind_hint="slow_load", signal={}) == "slow_load"
    assert await ask.classify_impression(kind_hint="bogus", signal={}) == "observation"
    pages = [
        {"url": "u1", "page_signals": [], "elements": []},
        {"url": "u2", "page_signals": [{"severity": "severe"}], "elements": []},
    ]
    assert await ask.rank_slop_suspects(pages=pages) == ["u2", "u1"]


@pytest.mark.asyncio
async def test_decisions_client_parses_answers_and_refusals() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "gpt-6-luna"
        return httpx.Response(200, json={
            "answers": [
                {"id": "a", "value": 0.9},
                {"id": "b", "refusal": True},
            ],
            "usage": {"input_tokens": 42},
        })

    answers = await decide(
        [
            DecisionQuestion("a", "score", "score a"),
            DecisionQuestion("b", "score", "score b"),
        ],
        input_context="ctx",
        transport=httpx.MockTransport(handler),
    )
    by_id = {a.question_id: a for a in answers}
    assert by_id["a"].value == 0.9
    assert by_id["b"].refusal is True


@pytest.mark.asyncio
async def test_decisions_outage_falls_back_to_model_then_deterministic(monkeypatch) -> None:
    monkeypatch.setenv("ASK_BACKEND_RANK_ITEMS", "decisions")
    monkeypatch.setenv("ASK_DECISIONS_CALIBRATED_RANK_ITEMS", "true")

    def outage(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    monkeypatch.setattr(
        decisions_client.httpx, "AsyncClient",
        lambda **kw: httpx.AsyncClient(
            transport=httpx.MockTransport(outage), timeout=5,
        ),
    )

    async def model_order(system, user, *, max_tokens=512):
        return {"order": ["c", "a", "b"]}

    monkeypatch.setattr(ask, "_model_json", model_order)
    assert await ask.rank_items(candidates=CANDIDATES, context="board") == ["c", "a", "b"]

    async def model_down(system, user, *, max_tokens=512):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(ask, "_model_json", model_down)
    assert await ask.rank_items(candidates=CANDIDATES, context="board") == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_decisions_without_calibration_never_calls_decisions(monkeypatch) -> None:
    monkeypatch.setenv("ASK_BACKEND_RANK_ITEMS", "decisions")
    monkeypatch.delenv("ASK_DECISIONS_CALIBRATED_RANK_ITEMS", raising=False)
    called = False

    async def spy_decide(*args, **kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(ask, "decide", spy_decide)
    assert await ask.rank_items(candidates=CANDIDATES, context="x") == ["a", "b", "c"]
    assert called is False


@pytest.mark.asyncio
async def test_narration_falls_back_to_template(monkeypatch) -> None:
    async def model_down(system, user, *, max_tokens=512):
        raise RuntimeError("no model")

    monkeypatch.setattr(ask, "_model_json", model_down)
    quote = await ask.narrate_impression(
        persona_name="Maya", persona_type="impatient_mobile",
        kind="slow_load", signal={"load_ms": 4200}, page_title="Home",
        fallback="Template quote.",
    )
    assert quote == "Template quote."
