"""Offline browser, selector, and real-ADK integration audit. No model API calls.

Browser pages are generated locally with network requests blocked. The model is
scripted: this verifies transport/invariants, never language-model output quality.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
from collections.abc import AsyncGenerator
from pathlib import Path
from statistics import mean
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch

from budgeted_selector import Atom, Selector
from compact_observation import make_compiler, pack, unpack

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
os.environ["TIKTOKEN_CACHE_DIR"] = str(
    ROOT / ".venv/Lib/site-packages/litellm/litellm_core_utils/tokenizers"
)
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

import tiktoken  # noqa: E402
import tiktoken.load  # noqa: E402
from google.adk.agents.run_config import RunConfig  # noqa: E402
from google.adk.models.base_llm import BaseLlm  # noqa: E402
from google.adk.models.lite_llm import _get_completion_inputs  # noqa: E402
from google.adk.models.llm_request import LlmRequest  # noqa: E402
from google.adk.models.llm_response import LlmResponse  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402
from markettwin_execution_orchestrator.agents import persona_agents  # noqa: E402
from markettwin_execution_orchestrator.agents.schemas.journey import (  # noqa: E402
    PersonaJourneySpec,
)
from markettwin_execution_orchestrator.agents.schemas.mission import (  # noqa: E402
    TestMissionSpec,
)
from markettwin_execution_orchestrator.agents.schemas.persona import PersonaSpec  # noqa: E402
from markettwin_execution_orchestrator.browser.contracts import (  # noqa: E402
    BrowserActionResult,
    BrowserEventBuffer,
)
from markettwin_execution_orchestrator.browser.observations import (  # noqa: E402
    build_observation,
)
from playwright.async_api import async_playwright  # noqa: E402
from pydantic import Field  # noqa: E402


def reject_download(path: str) -> bytes:
    raise RuntimeError(f"Missing offline tokenizer cache: {path}")


tiktoken.load.read_file = reject_download
ENCODER = tiktoken.get_encoding("o200k_base")


def count(value: object) -> int:
    return len(ENCODER.encode(json.dumps(value, ensure_ascii=False)))


def normalized(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def selector_audit() -> dict:
    rng = random.Random(20260920)
    gaps = []
    invariant_failures = 0
    worst = None
    started = perf_counter()
    for case in range(250):
        atoms = [Atom("pin", "x", mandatory=True)]
        for i in range(9):
            atoms.append(Atom(
                str(i), "x" * rng.randint(1, 12),
                frozenset(str(rng.randrange(7)) for _ in range(rng.randint(1, 3))),
                frozenset({str(i - 1)}) if i and rng.random() < 0.2 else frozenset(),
                allowed=rng.random() > 0.05, valid=rng.random() > 0.05,
            ))
        selector = Selector(
            atoms, {str(i): i + 1 for i in range(7)}, rng.randint(8, 35),
            lambda chosen: sum(len(atom.text) for atom in chosen), penalty=0.01,
        )
        greedy, exact = selector.greedy(), selector.exact()
        feasible = (
            selector.tokens(greedy) <= selector.budget
            and selector.pinned <= greedy and selector.closure(greedy) == greedy
        )
        invariant_failures += not feasible
        best = selector.objective(exact) - selector.objective(selector.pinned)
        gain = selector.objective(greedy) - selector.objective(selector.pinned)
        gap = (best - gain) / best if best > 0 else 0
        gaps.append(gap)
        if worst is None or gap > worst["relative_proxy_gap"]:
            worst = {"case": case, "relative_proxy_gap": gap,
                     "greedy": sorted(greedy), "exact": sorted(exact)}
    counter = Selector([
        Atom("a", "x" * 6, frozenset({"a"})),
        Atom("b", "x" * 5, frozenset({"b"})),
        Atom("c", "x" * 5, frozenset({"c"})),
    ], {"a": 12, "b": 9, "c": 9}, 10, lambda a: sum(len(x.text) for x in a), penalty=0)
    # A deliberately unlabelled critical fact exposes proxy quality limitations.
    omitted = Selector([
        Atom("goal", "Check price", mandatory=True),
        Atom("price", "$10", frozenset({"price"})),
        Atom("qualifier", "billed annually; cancellation fee applies"),
    ], {"price": 10}, 100, lambda a: sum(len(x.text) for x in a), penalty=0.01)
    return {
        "seed": 20260920, "cases": len(gaps), "invariant_failures": invariant_failures,
        "proxy_optimum_matched": sum(gap < 1e-9 for gap in gaps),
        "mean_relative_proxy_gap": mean(gaps), "worst": worst,
        "elapsed_seconds": round(perf_counter() - started, 3),
        "constructed_counterexample": {
            "greedy_value": counter.objective(counter.greedy()),
            "exact_value": counter.objective(counter.exact()),
        },
        "unlabelled_critical_qualifier_retained": "qualifier" in omitted.greedy(),
        "quality_conclusion": "Proxy optimization is not a sufficient quality gate.",
    }


async def browser_samples() -> tuple[list[dict], dict]:
    links = "".join(
        f'<a href="#local{i}">Navigation entry {i:03d} with long accessible label</a>'
        for i in range(90)
    )
    css = """<style>
      body { margin: 0; font: 14px Arial; }
      nav { display: grid; grid-template-columns: repeat(10, 1fr); }
      nav a { height: 26px; overflow: hidden; }
      h1 { font-size: 32px; margin: 8px; }
      #cover { position: fixed; left:0; right:0; top:238px; height:60px;
        z-index:100; background:white; }
    </style>"""
    samples = {
        "simple_heading": "<h1>Software testing</h1><p>Introduction</p>",
        "dense_heading": f"<nav>{links}</nav><h1>Software testing</h1>",
        "dense_price_qualifier": (
            f"<nav>{links}</nav><h1>Pricing</h1>"
            "<p>$10 per month, billed annually. Cancellation fee applies.</p>"
        ),
        "dense_overlap": (
            f"<nav>{links}</nav><h1>Software testing</h1>"
            '<div id="cover" role="alert">Subscription required to read this article.</div>'
        ),
    }
    observations = []
    results = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(viewport={"width": 1280, "height": 900})
            await context.route("**/*", lambda route: route.abort())
            page = await context.new_page()
            for index, (name, html) in enumerate(samples.items(), 1):
                await page.set_content(css + html)
                fake_session = SimpleNamespace(
                    page=page, context=context, timeout_ms=2000, capture_enabled=False,
                    action_number=index, event_buffer=BrowserEventBuffer(),
                )
                observation = await build_observation(fake_session)
                payload = normalized(BrowserActionResult("get_state", observation).to_dict())
                payload["step_id"] = index
                packed = pack(payload)
                assert unpack(packed) == payload
                model_text = json.dumps(payload, ensure_ascii=False)
                heading = page.locator("h1")
                box = await heading.bounding_box()
                obscured = await heading.evaluate("""element => {
                    const r = element.getBoundingClientRect();
                    const hit = document.elementFromPoint(r.left + 12, r.top + r.height / 2);
                    return hit !== element && !element.contains(hit);
                }""")
                baseline_tokens, packed_tokens = count(payload), count(packed)
                results[name] = {
                    "visible_element_count": len(observation.visible_elements),
                    "heading_in_viewport": bool(box and 0 <= box["y"] < 900),
                    "heading_in_visible_elements": any(
                        element.role == "heading" for element in observation.visible_elements
                    ),
                    "heading_in_model_payload": await heading.inner_text() in model_text,
                    "qualifier_in_full_aria": "Cancellation fee" in observation.aria_snapshot,
                    "qualifier_in_model_payload": "Cancellation fee" in model_text,
                    "alert_in_full_aria": "Subscription required" in observation.aria_snapshot,
                    "alert_in_model_payload": "Subscription required" in model_text,
                    "heading_sample_point_obscured": obscured,
                    "full_aria_chars": len(observation.aria_snapshot),
                    "baseline_tool_text_tokens": baseline_tokens,
                    "packed_tool_text_tokens": packed_tokens,
                    "packed_reduction_pct": round(100 * (1 - packed_tokens / baseline_tokens), 2),
                    "all_payload_values_round_trip": True,
                }
                observations.append(payload)
            await context.close()
        finally:
            await browser.close()
    return observations, results


class ScriptedModel(BaseLlm):
    """Exercises real ADK loops and adapter serialization; never calls a provider."""

    model: str = "offline-scripted"
    snapshots: list[LlmRequest] = Field(default_factory=list)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        del stream
        self.snapshots.append(llm_request.model_copy(deep=True))
        index = len(self.snapshots)
        if index <= 3:
            part = types.Part(function_call=types.FunctionCall(
                id=f"call_{index}", name="observe_fixture", args={},
            ))
        else:
            part = types.Part(text='{"outcome":"inconclusive","scripted":true}')
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


async def adk_sample(payload: dict, *, compact: bool) -> dict:
    model = ScriptedModel()

    async def observe_fixture() -> dict:
        """Return the current offline browser fixture observation."""
        return normalized(payload)

    journey = PersonaJourneySpec(
        journey_key="audit_user__audit_mission",
        persona=PersonaSpec(
            persona_id="audit_user", name="Careful reader", perspective="A careful reader.",
            behavior_traits=("careful",), priorities=("readability",),
        ),
        mission=TestMissionSpec(
            mission_id="audit_mission", name="Heading audit",
            objective="Check the Software testing heading.",
            success_criteria=("Heading is readable and unobscured.",), priority="high",
        ),
    )
    with patch.object(persona_agents, "create_model", return_value=model):
        agent = persona_agents.create_persona_agent(
            journey=journey, browser_tools=(observe_fixture,),
        )
    async def measure_request(request):
        messages, tools, _, _ = await _get_completion_inputs(request, "openai/gpt-4o-mini")
        return count({"messages": messages, "tools": tools})

    if compact:
        agent.before_model_callback = make_compiler(measure_request)
    runner = InMemoryRunner(agent=agent, app_name="offline_audit")
    final = None
    try:
        await runner.session_service.create_session(
            app_name="offline_audit", user_id="offline", session_id="fixture",
        )
        async for event in runner.run_async(
            user_id="offline", session_id="fixture",
            new_message=types.Content(role="user", parts=[types.Part(text="Run offline fixture.")]),
            run_config=RunConfig(max_llm_calls=4),
        ):
            if event.is_final_response():
                final = "".join(part.text or "" for part in event.content.parts or [])
        session = await runner.session_service.get_session(
            app_name="offline_audit", user_id="offline", session_id="fixture",
        )
        stored = [
            part.function_response.response
            for event in session.events if event.content
            for part in event.content.parts or [] if part.function_response
        ]
        assert len(stored) == 3 and all(value == payload for value in stored)
    finally:
        await runner.close()
    per_call = []
    for request in model.snapshots:
        messages, tools, _, _ = await _get_completion_inputs(request, "openai/gpt-4o-mini")
        tool_messages = [message for message in messages if message["role"] == "tool"]
        for message in tool_messages:
            assert unpack(json.loads(message["content"])) == payload
        call_ids = [
            call["id"] for message in messages for call in message.get("tool_calls", [])
        ]
        assert [message["tool_call_id"] for message in tool_messages] == call_ids
        per_call.append({
            "serialized_messages_and_tools_tokens": count({"messages": messages, "tools": tools}),
            "tool_result_text_tokens": sum(
                len(ENCODER.encode(message["content"])) for message in tool_messages
            ),
            "tool_result_count": len(tool_messages),
        })
    return {
        "mode": "reversible_compaction" if compact else "baseline",
        "per_call": per_call,
        "sum_serialized_request_tokens": sum(
            call["serialized_messages_and_tools_tokens"] for call in per_call
        ),
        "stored_events_unchanged": True, "tool_call_pairing_preserved": True,
        "all_adapter_tool_values_round_trip": True, "scripted_final": final,
    }


async def main() -> None:
    observations, browser = await browser_samples()
    baseline = await adk_sample(observations[1], compact=False)
    compact = await adk_sample(observations[1], compact=True)
    small_baseline = await adk_sample(observations[0], compact=False)
    small_compact = await adk_sample(observations[0], compact=True)
    assert small_compact["sum_serialized_request_tokens"] <= (
        small_baseline["sum_serialized_request_tokens"]
    )
    result = {
        "kind": "offline_integration_and_adversarial_audit_not_model_quality_evaluation",
        "selector": selector_audit(), "browser": browser,
        "adk": {"baseline": baseline, "compact": compact, "reduction_pct": round(
            100 * (1 - compact["sum_serialized_request_tokens"]
                   / baseline["sum_serialized_request_tokens"]), 2,
        )},
        "tiny_observation_guard": {
            "baseline_total": small_baseline["sum_serialized_request_tokens"],
            "guarded_total": small_compact["sum_serialized_request_tokens"],
            "original_retained_without_expansion": (
                small_baseline["sum_serialized_request_tokens"]
                == small_compact["sum_serialized_request_tokens"]
            ),
        },
        "limitations": [
            "Scripted model decisions cannot validate real model output quality.",
            "Token counts cover serialized messages/tools, not provider billing or images.",
            "Browser fixture hit testing is not a general visual correctness oracle.",
            "Selector features and weights are synthetic; no learned quality predictor.",
        ],
    }
    (HERE / "validation-results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
