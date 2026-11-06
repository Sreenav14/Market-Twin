"""Work-graph state for harness_v1 runs: schema, identity, load/save.

The board lives as JSON in ``TestRun.configuration_snapshot["harness_state"]``
and is rewritten at every item boundary. Every rewrite also appends a
``harness.*`` RunEvent row through the existing RunEventRepository, so the
snapshot (resume state) and the audit trail cannot drift apart.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from markettwin_database.models import TestRun
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.persistence.run_event_repository import (
    RunEventRepository,
)

STATE_ABSTRACTION_VERSION = "v1"
DEFAULT_ITEM_BUDGET = 300

ItemStatus = Literal["pending", "running", "worked", "broken", "could_not_check",
                     "not_checked", "needs_human_login", "blocked"]
ITEM_STATUSES: tuple[str, ...] = ("pending", "running", "worked", "broken",
                                  "could_not_check", "not_checked",
                                  "needs_human_login", "blocked")
TERMINAL_STATUSES = frozenset({"worked", "broken", "could_not_check",
                               "not_checked", "blocked"})
HarnessStage = Literal["exploring", "testing", "needs_login", "evaluating", "done"]


def canonical_url(url: str) -> str:
    """Normalise a URL for state identity: no fragment, sorted query."""

    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunsplit((parsed.scheme.lower(), netloc, path, query, ""))


def state_id_for(url: str, elements: tuple[tuple[str, str], ...] | list[tuple[str, str]],
                 form_fields: tuple[str, ...] | list[str] = ()) -> str:
    """§1.4 identity: sha256 of canonical URL + element + form signatures."""

    element_signature = ";".join(sorted(f"{role}|{name}" for role, name in elements))
    form_signature = ";".join(sorted(f"field|{label}" for label in form_fields))
    payload = f"{canonical_url(url)}|{element_signature}|{form_signature}"
    return hashlib.sha256(payload.encode()).hexdigest()


def item_id_for(state_id: str, role: str, name: str, occurrence_index: int) -> str:
    """Item identity = state_id + role + name + occurrence index."""

    return f"{state_id}:{role}:{name}:{occurrence_index}"


@dataclass
class HarnessItem:
    """One checkable interaction on the board."""

    item_id: str
    state_id: str
    case_id: str
    role: str
    name: str
    occurrence_index: int = 0
    css_path: str | None = None
    status: ItemStatus = "pending"
    attempts: int = 0
    evidence_refs: list[str] = field(default_factory=list[str])
    locator: dict[str, object] = field(default_factory=dict[str, object])
    blocker: str | None = None
    verdict: str | None = None
    durations_ms: list[int] = field(default_factory=list[int])
    journey_id: str | None = None
    mission_id: str | None = None

    def to_document(self) -> dict[str, object]:
        return {"item_id": self.item_id, "state_id": self.state_id,
                "case_id": self.case_id, "role": self.role, "name": self.name,
                "occurrence_index": self.occurrence_index, "css_path": self.css_path,
                "status": self.status, "attempts": self.attempts,
                "evidence_refs": list(self.evidence_refs), "locator": dict(self.locator),
                "blocker": self.blocker, "verdict": self.verdict,
                "durations_ms": list(self.durations_ms), "journey_id": self.journey_id,
                "mission_id": self.mission_id}

    @classmethod
    def from_document(cls, document: dict[str, object]) -> HarnessItem:
        status = str(document["status"])
        if status not in ITEM_STATUSES:
            raise ValueError(f"Unknown harness item status: {status!r}.")
        return cls(
            item_id=str(document["item_id"]), state_id=str(document["state_id"]),
            case_id=str(document["case_id"]), role=str(document["role"]),
            name=str(document["name"]),
            occurrence_index=int(cast(int, document.get("occurrence_index", 0))),
            css_path=cast(str | None, document.get("css_path")),
            status=cast(ItemStatus, status),
            attempts=int(cast(int, document.get("attempts", 0))),
            evidence_refs=[str(v) for v in cast(list[object], document.get("evidence_refs", []))],
            locator=dict(cast(dict[str, object], document.get("locator", {}))),
            blocker=cast(str | None, document.get("blocker")),
            verdict=cast(str | None, document.get("verdict")),
            durations_ms=[int(v) for v in cast(list[object], document.get("durations_ms", []))],
            journey_id=cast(str | None, document.get("journey_id")),
            mission_id=cast(str | None, document.get("mission_id")),
        )


@dataclass
class HarnessPageState:
    """One discovered page state under the versioned abstraction."""

    state_id: str
    url: str
    element_signature: list[str] = field(default_factory=list[str])
    form_signature: list[str] = field(default_factory=list[str])

    def to_document(self) -> dict[str, object]:
        return {"state_id": self.state_id, "url": self.url,
                "element_signature": list(self.element_signature),
                "form_signature": list(self.form_signature)}

    @classmethod
    def from_document(cls, document: dict[str, object]) -> HarnessPageState:
        return cls(
            state_id=str(document["state_id"]), url=str(document["url"]),
            element_signature=[str(v) for v in cast(list[object], document.get("element_signature", []))],
            form_signature=[str(v) for v in cast(list[object], document.get("form_signature", []))],
        )


@dataclass
class HarnessState:
    """The whole board: states, items, and budget counters."""

    state_abstraction_version: str = STATE_ABSTRACTION_VERSION
    persona_id: str | None = None
    states: dict[str, HarnessPageState] = field(default_factory=dict[str, HarnessPageState])
    items: dict[str, HarnessItem] = field(default_factory=dict[str, HarnessItem])
    budget_counters: dict[str, int] = field(default_factory=lambda: {
        "item_budget": DEFAULT_ITEM_BUDGET, "items_started": 0,
        "items_finished": 0, "total_elapsed_ms": 0,
    })

    def add_state(self, *, url: str, elements: tuple[tuple[str, str], ...] | list[tuple[str, str]],
                  form_fields: tuple[str, ...] | list[str] = ()) -> HarnessPageState:
        state_id = state_id_for(url, elements, form_fields)
        existing = self.states.get(state_id)
        if existing is not None:
            return existing
        state = HarnessPageState(
            state_id=state_id, url=canonical_url(url),
            element_signature=sorted(f"{role}|{name}" for role, name in elements),
            form_signature=sorted(f"field|{label}" for label in form_fields),
        )
        self.states[state_id] = state
        return state

    def add_item(self, *, state_id: str, case_id: str, role: str, name: str,
                 occurrence_index: int = 0, css_path: str | None = None) -> HarnessItem:
        item_id = item_id_for(state_id, role, name, occurrence_index)
        existing = self.items.get(item_id)
        if existing is not None:
            return existing
        item = HarnessItem(
            item_id=item_id, state_id=state_id, case_id=case_id, role=role, name=name,
            occurrence_index=occurrence_index, css_path=css_path,
            locator={"role": role, "name": name, "css_path": css_path},
        )
        self.items[item_id] = item
        return item

    def ordered_items(self) -> list[HarnessItem]:
        return list(self.items.values())

    def next_pending(self) -> HarnessItem | None:
        return next((item for item in self.items.values() if item.status == "pending"), None)

    def counts(self) -> dict[str, int]:
        counts = {status: 0 for status in ITEM_STATUSES}
        for item in self.items.values():
            counts[item.status] += 1
        return counts

    def to_document(self) -> dict[str, object]:
        return {"state_abstraction_version": self.state_abstraction_version,
                "persona_id": self.persona_id,
                "states": {key: state.to_document() for key, state in self.states.items()},
                "items": {key: item.to_document() for key, item in self.items.items()},
                "budget_counters": dict(self.budget_counters)}

    @classmethod
    def from_document(cls, document: dict[str, object]) -> HarnessState:
        states = {str(key): HarnessPageState.from_document(cast(dict[str, object], value))
                  for key, value in cast(dict[str, object], document.get("states", {})).items()}
        items = {str(key): HarnessItem.from_document(cast(dict[str, object], value))
                 for key, value in cast(dict[str, object], document.get("items", {})).items()}
        counters = {str(key): int(cast(int, value)) for key, value in
                    cast(dict[str, object], document.get("budget_counters", {})).items()}
        counters.setdefault("item_budget", DEFAULT_ITEM_BUDGET)
        return cls(state_abstraction_version=str(document.get(
                       "state_abstraction_version", STATE_ABSTRACTION_VERSION)),
                   persona_id=cast(str | None, document.get("persona_id")),
                   states=states, items=items, budget_counters=counters)


def new_harness_state(*, item_budget: int = DEFAULT_ITEM_BUDGET) -> HarnessState:
    """An empty board with the §1.4 default item budget (300, per D10)."""

    state = HarnessState()
    state.budget_counters["item_budget"] = item_budget
    return state


async def load_harness_state(session: AsyncSession, test_run_id: UUID) -> HarnessState | None:
    """Load the board from the run snapshot; None when never initialised."""

    run = await session.get(TestRun, test_run_id)
    if run is None:
        return None
    document = run.configuration_snapshot.get("harness_state")
    if not isinstance(document, dict):
        return None
    return HarnessState.from_document(cast(dict[str, object], document))


async def persist_harness_state(
    session: AsyncSession, run: TestRun, state: HarnessState, *,
    event_type: str, stage: HarnessStage | None = None,
    journey_id: UUID | None = None, execution_id: UUID | None = None,
    payload: dict[str, object] | None = None,
) -> None:
    """Rewrite the snapshot board and append the matching harness.* event."""

    snapshot: dict[str, object] = {**run.configuration_snapshot,
                                   "harness_state": state.to_document()}
    if stage is not None:
        snapshot["harness_stage"] = stage
    run.configuration_snapshot = snapshot
    await RunEventRepository(session).create(
        test_run_id=run.id, event_type=event_type,
        payload={"state_abstraction_version": state.state_abstraction_version,
                 "counts": state.counts(),
                 "budget_counters": dict(state.budget_counters), **(payload or {})},
        journey_id=journey_id, execution_id=execution_id,
    )
    await session.flush()
