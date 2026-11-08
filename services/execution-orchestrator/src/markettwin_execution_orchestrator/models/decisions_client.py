"""Decisions API client (U-P7): raw HTTPS, behind the ask door.

The Decisions endpoint (POST /v1/decisions, model gpt-6-luna) is not
reachable through LiteLLM 1.93, so this is a raw httpx call. It
answers TYPED questions only — predicate (yes/no + probability),
choice (one of a fixed set), score — in batches that share one
input. Answers can be `refusal`, which the door treats as
no-decision and falls back. The call runs inside the existing run
budget with role "decisions": reservations estimate input tokens
with the same tokenizer the budgeted client uses; output is
unmetered (decisions pricing is input-only), so completion is
recorded as 0. After the call, the recorded prompt tokens are the
response's reported input_tokens when present, and the reservation
estimate otherwise — spend is never recorded as zero or left
invisible.
"""

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
import litellm

from markettwin_database.model_budget import model_call, model_role

DECISIONS_MODEL = "gpt-6-luna"
_DEFAULT_BASE = "https://api.openai.com"


class DecisionsUnavailable(RuntimeError):
    """The Decisions backend cannot answer right now; degrade."""


@dataclass(frozen=True)
class DecisionQuestion:
    question_id: str
    kind: str  # predicate | choice | score
    prompt: str
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionAnswer:
    question_id: str
    kind: str
    value: Any = None
    probability: float | None = None
    refusal: bool = False


def _api_key() -> str | None:
    return os.getenv("DECISIONS_API_KEY") or os.getenv("MODEL_API_KEY") \
        or os.getenv("OPENAI_API_KEY")


def _base_url() -> str:
    return os.getenv("DECISIONS_API_BASE", _DEFAULT_BASE).rstrip("/")


async def decide(
    questions: list[DecisionQuestion], *, input_context: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[DecisionAnswer]:
    """Ask a batch of typed questions. Raises DecisionsUnavailable on
    any transport/API/shape failure — the door falls back."""

    if not questions:
        return []
    if len(questions) > 400:
        raise ValueError("Decisions accepts at most 400 questions per request.")
    api_key = _api_key()
    if not api_key:
        raise DecisionsUnavailable("No API key configured for Decisions.")
    body = {
        "model": DECISIONS_MODEL,
        "input": input_context,
        "questions": [
            {
                "id": q.question_id,
                "type": q.kind,
                "prompt": q.prompt,
                **({"choices": list(q.choices)} if q.choices else {}),
            }
            for q in questions
        ],
    }
    estimated_input = litellm.token_counter(  # pyright: ignore[reportUnknownMemberType]
        model=f"openai/{DECISIONS_MODEL}",
        messages=[{"role": "user", "content": json.dumps(body)}],
    )
    try:
        with model_role("decisions"):
            async with model_call(
                model=DECISIONS_MODEL,
                input_tokens=int(estimated_input),
                output_tokens=1,
            ) as call:
                async with httpx.AsyncClient(
                    timeout=30, transport=transport,
                ) as client:
                    response = await client.post(
                        f"{_base_url()}/v1/decisions",
                        json=body,
                        headers={"Authorization": f"Bearer {api_key}"},
                    )
                if response.status_code != 200:
                    raise DecisionsUnavailable(
                        f"Decisions returned HTTP {response.status_code}."
                    )
                payload = response.json()
                answers = _parse_answers(payload, questions)
                usage = payload.get("usage") or {}
                prompt_tokens = usage.get("input_tokens")
                call.prompt_tokens = (
                    int(prompt_tokens) if isinstance(prompt_tokens, int)
                    else int(estimated_input)
                )
                call.completion_tokens = 0
                return answers
    except DecisionsUnavailable:
        raise
    except Exception as error:
        raise DecisionsUnavailable(
            f"Decisions call failed: {type(error).__name__}"
        ) from error


def _parse_answers(
    payload: dict[str, Any], questions: list[DecisionQuestion],
) -> list[DecisionAnswer]:
    raw_answers = payload.get("answers")
    if not isinstance(raw_answers, list):
        raise DecisionsUnavailable("Decisions response has no answers list.")
    by_id = {q.question_id: q for q in questions}
    parsed: list[DecisionAnswer] = []
    for raw in raw_answers:
        if not isinstance(raw, dict):
            raise DecisionsUnavailable("Decisions answer is not an object.")
        question_id = str(raw.get("id", ""))
        question = by_id.get(question_id)
        if question is None:
            continue
        if raw.get("refusal"):
            parsed.append(DecisionAnswer(
                question_id=question_id, kind=question.kind, refusal=True,
            ))
            continue
        probability = raw.get("probability")
        parsed.append(DecisionAnswer(
            question_id=question_id,
            kind=question.kind,
            value=raw.get("value", raw.get("choice", raw.get("score"))),
            probability=(
                float(probability) if isinstance(probability, (int, float))
                else None
            ),
        ))
    if not parsed:
        raise DecisionsUnavailable("Decisions returned no usable answers.")
    return parsed
