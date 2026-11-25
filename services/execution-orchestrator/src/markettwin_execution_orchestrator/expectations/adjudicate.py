"""Adjudication (doc 21 section 5.4) -- THE phase's only model surface.

Spec C1: model calls exist in this file and nowhere else in Phase 2;
the AST boundary test (T-GR9) pins the allowlist to exactly this
module. Two call-points, both through the one typed ask door (the
Model API answers first, Option 3):

- ``adjudicate_match``: an ambiguous candidate + its candidate
  subject set -> a chosen candidate id or null. The model may NOT
  invent a subject; an out-of-set answer is rejected in code.
- ``draft_expectation``: an uncompilable documentation span (or a
  template-group behaviour summary) -> a statement + a proposed
  section 5.6 assertion, validated in code against the grammar and
  the subject's real graph ids; invalid -> statement-only.

Spend counts against GROUNDING_MAX_MODEL_CALLS_PER_MAP and is
recorded in grounding_metrics + 'adjudicated' events -- NEVER in
mapping_spend_* (that ledger belongs to the harvest).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .grounding import Candidate, GraphIndex, Subject

# Doc 21 section 16 settings, as module constants (prep OQ1: the
# orchestrator package has no config module; the harvest precedent).
GROUNDING_MAX_MODEL_CALLS_PER_MAP = 200  # [J]
ADJUDICATE_MAX_TOKENS = 700
DRAFT_MAX_TOKENS = 900

ADJUDICATE_SYSTEM = (
    "You match one product-documentation statement to at most one "
    "element, page, journey or form field of the same product. You are "
    "given the statement and the candidate subjects with their ids. "
    "Choose the single candidate the statement is about, or null when "
    "none of them fits. Never invent an id. Reply with JSON only: "
    '{"chosen_subject_id": <id string or null>, "confidence": '
    '<0..1>, "rationale": "<short reason>"}'
)

DRAFT_SYSTEM = (
    "You turn one product-documentation statement into a checkable "
    "expectation about the same product. You are given the statement, "
    "its matched subject (with real graph ids) and the assertion "
    "grammar. Propose the closest assertion the grammar allows, using "
    "only the given ids, or null when the statement cannot be checked "
    "that way. Reply with JSON only: "
    '{"statement": "<one sentence>", "assertion": {"kind": '
    '"element_state"|"navigation"|"page_text"|"journey_terminal"|'
    '"field_validation", "params": {...}} or null, "confidence": <0..1>}'
)

ASSERTION_KINDS = (
    "element_state",
    "navigation",
    "page_text",
    "journey_terminal",
    "field_validation",
)


class AdjudicationDoor(Protocol):
    async def complete_json(
        self, *, system: str, user: str, max_tokens: int
    ) -> dict: ...


class AskAdjudicationDoor:
    """The production door: the shared ask door's JSON completion."""

    async def complete_json(
        self, *, system: str, user: str, max_tokens: int
    ) -> dict:
        from markettwin_execution_orchestrator.models import ask

        result = await ask._model_json(system, user, max_tokens=max_tokens)
        return result if isinstance(result, dict) else {}


class AdjudicationLedger:
    """Per-map adjudication spend (section 5.4 cap semantics)."""

    def __init__(self, cap: int = GROUNDING_MAX_MODEL_CALLS_PER_MAP) -> None:
        self.cap = cap
        self.calls = 0
        self.deferred = 0

    def spend(self) -> bool:
        if self.calls >= self.cap:
            self.deferred += 1
            return False
        self.calls += 1
        return True


def build_adjudicate_prompt(
    candidate: Candidate, subjects: tuple[Subject, ...]
) -> str:
    lines = [
        "Statement:",
        candidate.text[:2000],
        "",
        "Candidate subjects:",
    ]
    for subject in subjects:
        lines.append(f"- id={subject.id} kind={subject.kind} label={subject.label}")
    lines.append("Choose at most one candidate id, or null.")
    return "\n".join(lines)


def build_draft_prompt(
    candidate: Candidate, subject: Subject, index: GraphIndex
) -> str:
    lines = [
        "Statement:",
        candidate.text[:2000],
        "",
        f"Matched subject: kind={subject.kind} id={subject.id} label={subject.label}",
    ]
    if subject.kind == "element":
        element = index.elements.get(subject.id)
        if element is not None:
            lines.append(
                f"Element ids: element_id={element.id} "
                f"state_id={element.map_page_state_id}"
            )
            target = index.target_url_for_element(element.id)
            if target is not None:
                lines.append(f"Observed navigation target: {target}")
    if subject.kind == "page":
        page = index.pages.get(subject.id)
        if page is not None:
            lines.append(f"Page: page_id={page.id} url={page.canonical_url}")
    if subject.kind == "journey":
        journey = index.journeys.get(subject.id)
        if journey is not None:
            lines.append(
                f"Journey ids: journey_id={journey.id} "
                f"success_state_id={journey.success_state_id}"
            )
    lines.append(
        "Grammar params: element_state {oracle: visible|enabled|checked}; "
        "navigation {expected_url}; page_text {text, present}; "
        "journey_terminal {}; field_validation {probe_case, expected_error_text}."
    )
    return "\n".join(lines)


def validate_adjudication(
    raw: dict, subjects: tuple[Subject, ...]
) -> tuple[Subject | None, float]:
    """Chosen subject must be one of the candidates (never invented)."""
    chosen = raw.get("chosen_subject_id")
    confidence = raw.get("confidence")
    confidence = (
        float(confidence)
        if isinstance(confidence, (int, float)) and 0.0 <= float(confidence) <= 1.0
        else 0.0
    )
    if chosen is None:
        return None, confidence
    for subject in subjects:
        if str(subject.id) == str(chosen):
            return subject, confidence
    return None, 0.0


def validate_draft_assertion(
    raw_assertion: object, subject: Subject, index: GraphIndex
) -> dict[str, object] | None:
    """Validate a drafted assertion against the grammar + real ids."""
    if not isinstance(raw_assertion, dict):
        return None
    kind = raw_assertion.get("kind")
    params = raw_assertion.get("params")
    if kind not in ASSERTION_KINDS or not isinstance(params, dict):
        return None
    if kind == "element_state":
        if subject.kind != "element":
            return None
        element = index.elements.get(subject.id)
        oracle = params.get("oracle")
        if element is None or oracle not in ("visible", "enabled", "checked"):
            return None
        return {
            "kind": kind,
            "subject": {
                "element_id": str(element.id),
                "state_id": str(element.map_page_state_id),
                "locators": list(element.locators or []),
            },
            "params": {"oracle": oracle},
        }
    if kind == "navigation":
        if subject.kind != "element":
            return None
        element = index.elements.get(subject.id)
        expected = params.get("expected_url")
        observed = (
            index.target_url_for_element(element.id) if element is not None else None
        )
        if element is None or not isinstance(expected, str):
            return None
        if expected not in index.pages_by_url and expected != observed:
            return None
        return {
            "kind": kind,
            "subject": {
                "element_id": str(element.id),
                "state_id": str(element.map_page_state_id),
                "locators": list(element.locators or []),
            },
            "params": {"expected_url": expected},
        }
    if kind == "page_text":
        if subject.kind != "page":
            return None
        text = params.get("text")
        if not isinstance(text, str) or not text.strip():
            return None
        return {
            "kind": kind,
            "subject": {"page_id": str(subject.id)},
            "params": {"text": text, "present": bool(params.get("present", True))},
        }
    if kind == "journey_terminal":
        if subject.kind != "journey":
            return None
        journey = index.journeys.get(subject.id)
        if journey is None:
            return None
        return {
            "kind": kind,
            "subject": {
                "journey_id": str(journey.id),
                "success_state_id": str(journey.success_state_id),
            },
            "params": {},
        }
    if kind == "field_validation":
        if subject.kind != "field":
            return None
        probe_case = params.get("probe_case")
        error_text = params.get("expected_error_text")
        if probe_case not in ("empty", "invalid") or not isinstance(error_text, str):
            return None
        field_row = index.fields.get(subject.id)
        return {
            "kind": kind,
            "subject": {
                "field_id": str(subject.id),
                "label": field_row.label if field_row is not None else None,
            },
            "params": {
                "probe_case": probe_case,
                "expected_error_text": error_text,
            },
        }
    return None


async def adjudicate_match(
    door: AdjudicationDoor,
    candidate: Candidate,
    subjects: tuple[Subject, ...],
    ledger: AdjudicationLedger,
) -> tuple[Subject | None, float]:
    if not ledger.spend():
        return None, 0.0
    raw = await door.complete_json(
        system=ADJUDICATE_SYSTEM,
        user=build_adjudicate_prompt(candidate, subjects),
        max_tokens=ADJUDICATE_MAX_TOKENS,
    )
    return validate_adjudication(raw, subjects)


async def draft_expectation(
    door: AdjudicationDoor,
    candidate: Candidate,
    subject: Subject,
    index: GraphIndex,
    ledger: AdjudicationLedger,
) -> tuple[str, dict[str, object] | None, float] | None:
    """Draft from an uncompilable span; None when the call is deferred
    or the reply is unusable (caller authors statement-only instead)."""
    if not ledger.spend():
        return None
    raw = await door.complete_json(
        system=DRAFT_SYSTEM,
        user=build_draft_prompt(candidate, subject, index),
        max_tokens=DRAFT_MAX_TOKENS,
    )
    statement = raw.get("statement")
    if not isinstance(statement, str) or not statement.strip():
        return None
    confidence = raw.get("confidence")
    confidence = (
        float(confidence)
        if isinstance(confidence, (int, float)) and 0.0 <= float(confidence) <= 1.0
        else 0.0
    )
    assertion = validate_draft_assertion(raw.get("assertion"), subject, index)
    return statement.strip(), assertion, confidence
