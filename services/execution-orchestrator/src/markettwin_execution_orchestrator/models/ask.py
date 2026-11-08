"""The ask door (U-P7): ONE typed doorway for every label,
probability, ranking and short-writing question inside a run.

Owner decision (Option 3, 2026-11-08): call-points go through this
door with typed inputs/outputs; the Model API answers behind the
door first; the Decisions API drops in behind the SAME door later,
only for high-volume call-points and only after ~100-example
calibration per question type — the calibration flag is
ASK_DECISIONS_CALIBRATED_<POINT>=true, set by the owner after the
calibration exercise, never by code.

Backend selection per call-point: ASK_BACKEND_<POINT> in
{deterministic, model, decisions}. Defaults: narration = model
(language work — Decisions cannot write text), everything else =
deterministic. Fallback chain: decisions -> model -> deterministic.
rank_slop_suspects is the one exception: it is deterministic-only
for now, because its consumer (the vision pass) has not landed —
ASK_BACKEND_RANK_SLOP_SUSPECTS has no effect yet.
NOTHING in this module raises into a run: a label is never worth
failing a test run over.
"""

import json
import os
from typing import Any

import litellm

from markettwin_database.model_budget import model_call, model_role

from markettwin_execution_orchestrator.models.decisions_client import (
    DecisionQuestion,
    decide,
)
from markettwin_execution_orchestrator.models.model_factory import (
    resolve_model_runtime_configuration,
)

IMPRESSION_KINDS = (
    "slow_load", "page_errors", "small_targets",
    "no_keyboard_focus", "fast_and_clean", "observation",
)


def _backend_for(point: str) -> str:
    default = "model" if point == "narrate_impression" else "deterministic"
    value = os.getenv(f"ASK_BACKEND_{point.upper()}", default).strip().lower()
    return value if value in {"deterministic", "model", "decisions"} else default


def _decisions_calibrated(point: str) -> bool:
    return os.getenv(
        f"ASK_DECISIONS_CALIBRATED_{point.upper()}", "",
    ).strip().lower() == "true"


async def _model_json(system: str, user: str, *, max_tokens: int = 512) -> Any:
    """One budgeted Model API call expecting a JSON answer."""

    configuration = resolve_model_runtime_configuration(max_tokens=max_tokens)
    model = configuration.model_name
    request: dict[str, Any] = {
        "model": model,
        "timeout": 60,
        "num_retries": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    api_key = os.getenv("MODEL_API_KEY") or os.getenv("OPENAI_API_KEY")
    if api_key:
        request["api_key"] = api_key
    input_tokens = litellm.token_counter(  # pyright: ignore[reportUnknownMemberType]
        model=model, messages=request["messages"],
    )
    with model_role("ask"):
        async with model_call(
            model=model, input_tokens=int(input_tokens),
            output_tokens=max_tokens,
        ) as call:
            response = await litellm.acompletion(**request)  # pyright: ignore[reportUnknownMemberType]
            call.record(response)
    content = response.choices[0].message.content
    if not isinstance(content, str):
        raise ValueError("Model returned no content.")
    return json.loads(content)


# --- classify_impression -------------------------------------------------

async def classify_impression(*, kind_hint: str, signal: dict[str, Any]) -> str:
    """The impression kind for a measured signal. The measurement
    layer already derives kinds deterministically; the door exists so
    a future backend can re-classify ambiguous cases without callers
    changing."""

    deterministic = kind_hint if kind_hint in IMPRESSION_KINDS else "observation"
    backend = _backend_for("classify_impression")
    if backend == "deterministic":
        return deterministic
    if backend == "decisions" and _decisions_calibrated("classify_impression"):
        try:
            answers = await decide(
                [DecisionQuestion(
                    question_id="kind", kind="choice",
                    prompt=(
                        "Which impression kind best matches this measured "
                        f"signal? Signal: {json.dumps(signal)}"
                    ),
                    choices=IMPRESSION_KINDS,
                )],
                input_context="Persona walk impression classification.",
            )
            if answers and not answers[0].refusal and answers[0].value in IMPRESSION_KINDS:
                return str(answers[0].value)
        except Exception:
            pass  # fall through to the Model backend
    if backend in {"model", "decisions"}:
        try:
            result = await _model_json(
                "Answer with JSON: {\"kind\": one of "
                + json.dumps(list(IMPRESSION_KINDS)) + "}",
                f"Measured signal: {json.dumps(signal)}",
                max_tokens=64,
            )
            if isinstance(result, dict) and result.get("kind") in IMPRESSION_KINDS:
                return str(result["kind"])
        except Exception:
            pass
    return deterministic


# --- narrate_impression ----------------------------------------------------

async def narrate_impression(
    *, persona_name: str, persona_type: str, kind: str,
    signal: dict[str, Any], page_title: str, fallback: str,
) -> str:
    """First-person wording for a measured impression. Language work:
    Model API only (Decisions cannot write text). Any failure ->
    the caller's template fallback."""

    if _backend_for("narrate_impression") == "deterministic":
        return fallback
    try:
        result = await _model_json(
            "You write ONE first-person sentence as the persona named, "
            "describing only the measured facts given. No scores, no "
            "ratings, no invented details. Answer with JSON: "
            "{\"quote\": \"...\"}",
            json.dumps({
                "persona": persona_name, "type": persona_type,
                "kind": kind, "page": page_title, "signal": signal,
            }),
            max_tokens=128,
        )
        if isinstance(result, dict):
            quote = result.get("quote")
            if isinstance(quote, str) and 0 < len(quote) <= 400:
                return quote
    except Exception:
        pass
    return fallback


# --- rank_items --------------------------------------------------------------

async def rank_items(
    *, candidates: list[dict[str, str]], context: str,
) -> list[str]:
    """Order candidate ids by value-of-testing-next. Deterministic
    default = the caller's order (Board order is already a decision).
    Rankings reorder work; they never drop a candidate."""

    ids = [c["id"] for c in candidates]
    backend = _backend_for("rank_items")
    if backend == "deterministic" or len(ids) < 2:
        return ids
    if backend == "decisions" and _decisions_calibrated("rank_items"):
        try:
            questions = [
                DecisionQuestion(
                    question_id=c["id"], kind="score",
                    prompt=(
                        "Score 0..1: how valuable is it to test this item "
                        f"next? Item: {c.get('label', c['id'])}"
                    ),
                )
                for c in candidates
            ]
            answers = await decide(questions, input_context=context)
            scored = {
                a.question_id: (
                    float(a.value) if isinstance(a.value, (int, float))
                    else (a.probability or 0.0)
                )
                for a in answers if not a.refusal
            }
            if scored:
                return sorted(
                    ids, key=lambda i: (-scored.get(i, -1.0), ids.index(i)),
                )
        except Exception:
            pass  # fall through to the Model backend
    if backend in {"model", "decisions"}:
        try:
            result = await _model_json(
                "Rank the candidate ids by value of testing next. "
                "Answer with JSON: {\"order\": [ids...]} — every id, "
                "exactly once.",
                json.dumps({"context": context, "candidates": candidates}),
                max_tokens=512,
            )
            if isinstance(result, dict) and isinstance(result.get("order"), list):
                order = [str(x) for x in result["order"]]
                if sorted(order) == sorted(ids):
                    return order
        except Exception:
            pass
    return ids


# --- rank_slop_suspects --------------------------------------------------------

async def rank_slop_suspects(
    *, pages: list[dict[str, Any]],
) -> list[str]:
    """Order page urls by suspicion for expensive follow-up (vision).
    Deterministic default: most page signals, then most unjudged."""

    def suspicion(page: dict[str, Any]) -> tuple[int, int]:
        severe = sum(
            1 for s in page.get("page_signals", [])
            if s.get("severity") == "severe"
        )
        cant_tell = sum(
            1 for e in page.get("elements", [])
            if e.get("verdict") == "cant_tell"
        )
        return (severe, cant_tell)

    ordered = sorted(
        pages, key=lambda p: suspicion(p), reverse=True,
    )
    return [str(p.get("url")) for p in ordered]
