"""Deterministic grounding core (doc 21 sections 5.2, 5.3, 6.2, 9.1).

No model imports, no I/O: the graph index, candidate matching in the
pinned key order, assertion compilation into the section 5.6 grammar,
observation-fact extraction, deterministic journey assembly, and the
verification sweep. The grounding job drives these; adjudication
(expectations/adjudicate.py) is the only model surface and consumes
this module's ambiguous sets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin
from uuid import UUID, uuid4

from markettwin_database.models.knowledge import (
    AppMap,
    MapElement,
    MapField,
    MapForm,
    MapJourney,
    MapPage,
    MapPageState,
    MapTransition,
)
from markettwin_shared.app_map_common import canonical_url, route_pattern_for

_URL_RE = re.compile(r"https?://[^\s'\"<>\)]+")


def _clean_token(raw: str) -> str:
    """Drop sentence punctuation a regex match swallows ('.../pricing.')."""
    return raw.rstrip(".,;:")
_PATH_RE = re.compile(r"(?<![\w/])(/[a-z0-9][a-z0-9\-/_{}]*)", re.IGNORECASE)
_QUOTED_RE = re.compile(r"'([^']{2,80})'|\"([^\"]{2,80})\"")
_NAV_VERBS = ("navigates to", "navigates", "leads to", "goes to", "opens", "redirects to")


@dataclass(frozen=True)
class Candidate:
    """One knowledge item from an approved ingestion entry (section 5.2)."""

    entry_id: UUID
    ordinal: int
    name: str
    content: str
    source_kind: str
    ref: str | None = None

    @property
    def source_ref(self) -> str:
        if self.ref is not None:
            return self.ref
        return f"{self.entry_id}:{self.ordinal}"

    @property
    def text(self) -> str:
        return f"{self.name}\n{self.content}"


@dataclass(frozen=True)
class Subject:
    kind: str  # 'page' | 'element' | 'journey' | 'field' | 'form'
    id: UUID
    label: str


@dataclass(frozen=True)
class MatchResult:
    outcome: str  # 'matched' | 'ambiguous' | 'unmatched'
    subject: Subject | None
    candidates: tuple[Subject, ...]
    match_key: str | None  # 'route' | 'element' | 'journey' | 'field'


class GraphIndex:
    """In-memory index over one map version's harvested graph."""

    def __init__(
        self,
        *,
        pages: list[MapPage],
        states: list[MapPageState],
        elements: list[MapElement],
        forms: list[MapForm],
        fields: list[MapField],
        transitions: list[MapTransition],
        journeys: list[MapJourney],
    ) -> None:
        self.pages = {page.id: page for page in pages}
        self.pages_by_url = {page.canonical_url: page for page in pages}
        self.pages_by_pattern: dict[str, list[MapPage]] = {}
        for page in pages:
            self.pages_by_pattern.setdefault(page.route_pattern, []).append(page)
        self.states = {state.id: state for state in states}
        self.default_state_by_page = {
            state.map_page_id: state
            for state in states
            if state.state_key == "default"
        }
        self.elements = {element.id: element for element in elements}
        self.elements_by_name: dict[str, list[MapElement]] = {}
        for element in elements:
            if element.name:
                self.elements_by_name.setdefault(
                    element.name.strip().lower(), []
                ).append(element)
        self.forms = {form.id: form for form in forms}
        self.fields = {field_row.id: field_row for field_row in fields}
        self.fields_by_label: dict[str, list[MapField]] = {}
        for field_row in fields:
            if field_row.label:
                self.fields_by_label.setdefault(
                    field_row.label.strip().lower(), []
                ).append(field_row)
        self.transitions = list(transitions)
        self.transitions_by_element: dict[UUID, list[MapTransition]] = {}
        for transition in transitions:
            if transition.via_element_id is not None:
                self.transitions_by_element.setdefault(
                    transition.via_element_id, []
                ).append(transition)
        self.journeys = {journey.id: journey for journey in journeys}
        self.journeys_by_name: dict[str, list[MapJourney]] = {}
        for journey in journeys:
            for key in (journey.name, journey.intent or ""):
                if key:
                    self.journeys_by_name.setdefault(key.strip().lower(), []).append(
                        journey
                    )

    def page_url(self, page_id: UUID) -> str | None:
        page = self.pages.get(page_id)
        return page.canonical_url if page is not None else None

    def element_page_url(self, element: MapElement) -> str | None:
        return self.page_url(element.map_page_id)

    def target_url_for_element(self, element_id: UUID) -> str | None:
        """The observed navigation target of an element, if exactly one."""
        targets: set[str] = set()
        for transition in self.transitions_by_element.get(element_id, []):
            state = self.states.get(transition.to_state_id)
            if state is not None:
                url = self.page_url(state.map_page_id)
                if url is not None:
                    targets.add(url)
        if len(targets) == 1:
            return next(iter(targets))
        return None


_META_SECTIONS = ("uncertainties", "source references")


def _markdown_sections(markdown: str) -> list[tuple[str, str]]:
    """Split a rendered knowledge file into (heading, body) pairs at
    H2 boundaries; frontmatter is dropped."""
    lines = markdown.splitlines()
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                lines = lines[index + 1 :]
                break
    sections: list[tuple[str, str]] = []
    heading: str | None = None
    body: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if heading is not None:
                sections.append((heading, "\n".join(body).strip()))
            heading = line[3:].strip()
            body = []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(body).strip()))
    return sections


def _file_sections(file: object) -> list[tuple[str, str, str]]:
    """(slug, heading, body) per section from a knowledge-file record.

    Accepts the stored shape (slug + rendered Markdown text, split at
    H2 boundaries) and the structured shape (slug + sections of
    heading/body_md, the shared knowledge_markdown contract). The
    Uncertainties and Source references sections are file furniture,
    not knowledge claims, and never become candidates.
    """
    if isinstance(file, dict):
        slug = file.get("slug")
        sections = file.get("sections")
        text = file.get("content", file.get("markdown"))
    else:
        slug = getattr(file, "slug", None)
        sections = getattr(file, "sections", None)
        text = getattr(file, "content", getattr(file, "markdown", None))
    if not isinstance(slug, str) or not slug:
        return []
    found: list[tuple[str, str]] = []
    if sections:
        for section in sections:
            if isinstance(section, dict):
                heading = section.get("heading")
                body = section.get("body_md", section.get("body"))
            else:
                heading = getattr(section, "heading", None)
                body = getattr(section, "body_md", getattr(section, "body", None))
            if isinstance(heading, str) and isinstance(body, str):
                found.append((heading, body.strip()))
    elif isinstance(text, str) and text.strip():
        found = _markdown_sections(text)
    return [
        (slug, heading, body)
        for heading, body in found
        if body and heading.casefold() not in _META_SECTIONS
    ]


def extract_candidates(entries: list) -> list[Candidate]:
    """Candidate pool from approved entries' Markdown files (doc 33 step 6).

    One candidate per file section; its source ref is
    entry:slug:section-heading, traceable to the exact file section it
    came from. The entries handed in are the repository's approved,
    application-linked set -- approval stays the repository's gate.
    """
    candidates: list[Candidate] = []
    for entry in entries:
        files = getattr(entry, "knowledge_files", None)
        if not isinstance(files, (list, tuple)):
            continue
        ordinal = 0
        for file in files:
            for slug, heading, body in _file_sections(file):
                candidates.append(
                    Candidate(
                        entry_id=entry.id,
                        ordinal=ordinal,
                        name=heading,
                        content=body,
                        source_kind="owner_document",
                        ref=f"{entry.id}:{slug}:{heading}",
                    )
                )
                ordinal += 1
    return candidates


def _route_subjects(candidate: Candidate, index: GraphIndex) -> list[Subject]:
    subjects: list[Subject] = []
    seen: set[UUID] = set()
    for raw in _URL_RE.findall(candidate.text) + _PATH_RE.findall(candidate.text):
        raw = _clean_token(raw)
        url = raw if raw.startswith("http") else raw
        page = index.pages_by_url.get(canonical_url(url)) if url.startswith("http") else None
        if page is None:
            pattern = route_pattern_for(url)
            matches = index.pages_by_pattern.get(pattern, [])
            page = matches[0] if len(matches) == 1 else None
        if page is not None and page.id not in seen:
            seen.add(page.id)
            subjects.append(
                Subject(kind="page", id=page.id, label=page.canonical_url)
            )
    return subjects


def _label_subjects(
    candidate: Candidate, index: GraphIndex
) -> dict[str, list[Subject]]:
    """Candidate subjects per key class (section 5.2 step 1 order b-d)."""
    labels: set[str] = set()
    for match in _QUOTED_RE.findall(candidate.text):
        labels.add((match[0] or match[1]).strip().lower())
    if candidate.name.strip():
        labels.add(candidate.name.strip().lower())
    found: dict[str, list[Subject]] = {"element": [], "journey": [], "field": []}
    seen: set[tuple[str, UUID]] = set()
    for label in labels:
        for element in index.elements_by_name.get(label, []):
            key = ("element", element.id)
            if key not in seen:
                seen.add(key)
                found["element"].append(
                    Subject(kind="element", id=element.id, label=element.name)
                )
        for journey in index.journeys_by_name.get(label, []):
            key = ("journey", journey.id)
            if key not in seen:
                seen.add(key)
                found["journey"].append(
                    Subject(kind="journey", id=journey.id, label=journey.name)
                )
        for field_row in index.fields_by_label.get(label, []):
            key = ("field", field_row.id)
            if key not in seen:
                seen.add(key)
                found["field"].append(
                    Subject(kind="field", id=field_row.id, label=field_row.label)
                )
    return found


def match_candidate(candidate: Candidate, index: GraphIndex) -> MatchResult:
    """Deterministic subject matching (section 5.2 step 1).

    Key classes in pinned order -- route, element label, journey name,
    form/field label. The first class with exactly one hit wins; a
    class with several hits makes the candidate ambiguous with that
    set attached; no hits anywhere leaves it unmatched.
    """
    route = _route_subjects(candidate, index)
    if len(route) == 1:
        return MatchResult("matched", route[0], (), "route")
    if len(route) > 1:
        return MatchResult("ambiguous", None, tuple(route), "route")
    by_class = _label_subjects(candidate, index)
    for key_class in ("element", "journey", "field"):
        hits = by_class[key_class]
        if len(hits) == 1:
            return MatchResult("matched", hits[0], (), key_class)
        if len(hits) > 1:
            return MatchResult("ambiguous", None, tuple(hits), key_class)
    return MatchResult("unmatched", None, (), None)


def compile_assertion(
    candidate: Candidate, subject: Subject, index: GraphIndex
) -> dict[str, object] | None:
    """Compile the deterministic assertion where the shape allows (§5.2/§5.6).

    Returns the {kind, subject, params} assertion or None when the
    statement's shape does not compile deterministically (the record
    is then statement-only or routed to drafting).
    """
    text = candidate.text.lower()
    if subject.kind == "element":
        element = index.elements.get(subject.id)
        if element is None:
            return None
        bindings = {
            "element_id": str(element.id),
            "state_id": str(element.map_page_state_id),
            "role": element.role,
            "name": element.name,
            "locators": list(element.locators or []),
        }
        if any(verb in text for verb in _NAV_VERBS):
            # The assertion carries the target the STATEMENT names --
            # that is the doc claim the graph is checked against
            # (section 9.1 point 1), whether or not that page exists
            # in the graph yet. No named target -> no navigation
            # claim can be compiled from the statement alone.
            own_url = index.element_page_url(element)
            for raw in _URL_RE.findall(candidate.text) + _PATH_RE.findall(
                candidate.text
            ):
                raw = _clean_token(raw)
                named = (
                    canonical_url(raw)
                    if raw.startswith("http")
                    else canonical_url(urljoin(own_url or "", raw))
                )
                if named and named != own_url:
                    return {
                        "kind": "navigation",
                        "subject": bindings,
                        "params": {"expected_url": named},
                    }
        return {
            "kind": "element_state",
            "subject": bindings,
            "params": {"oracle": "visible"},
        }
    if subject.kind == "page":
        quoted = _QUOTED_RE.search(candidate.content)
        if quoted is not None:
            phrase = quoted.group(1) or quoted.group(2)
            return {
                "kind": "page_text",
                "subject": {"page_id": str(subject.id)},
                "params": {"text": phrase, "present": True},
            }
        return None
    if subject.kind == "journey":
        journey = index.journeys.get(subject.id)
        if journey is None:
            return None
        return {
            "kind": "journey_terminal",
            "subject": {
                "journey_id": str(journey.id),
                "success_state_id": str(journey.success_state_id),
            },
            "params": {},
        }
    return None


@dataclass(frozen=True)
class ObservationFact:
    """One code-authored observation expectation (section 5.3)."""

    subject_kind: str
    subject_id: UUID
    statement: str
    source_ref: str
    assertion: dict[str, object]


def observation_facts(index: GraphIndex) -> list[ObservationFact]:
    """The closed set of observation shapes (section 5.3).

    Navigation facts from transitions on named elements; presence
    facts for primary actions (clickable buttons on default states --
    the graph carries no literal primary_action flag; this is the
    closest incumbent classification, recorded in the build report).
    Probed validation facts arrive via probing (section 7.4), not here.
    """
    facts: list[ObservationFact] = []
    for transition in index.transitions:
        if transition.via_element_id is None or transition.via_action != "click":
            continue
        element = index.elements.get(transition.via_element_id)
        if element is None or not element.name:
            continue
        to_state = index.states.get(transition.to_state_id)
        if to_state is None:
            continue
        target_url = index.page_url(to_state.map_page_id)
        if target_url is None:
            continue
        facts.append(
            ObservationFact(
                subject_kind="element",
                subject_id=element.id,
                statement=(
                    f"Clicking '{element.name}' navigates to {target_url}"
                ),
                source_ref=f"transition:{transition.id}",
                assertion={
                    "kind": "navigation",
                    "subject": {
                        "element_id": str(element.id),
                        "state_id": str(element.map_page_state_id),
                        "role": element.role,
                        "name": element.name,
                        "locators": list(element.locators or []),
                    },
                    "params": {"expected_url": target_url},
                },
            )
        )
    default_state_ids = {
        state.id for state in index.default_state_by_page.values()
    }
    for element in index.elements.values():
        if element.map_page_state_id not in default_state_ids:
            continue
        if element.role != "button" or element.actionability != "click":
            continue
        if not element.name:
            continue
        facts.append(
            ObservationFact(
                subject_kind="element",
                subject_id=element.id,
                statement=f"'{element.name}' is present and visible",
                source_ref=f"census:{element.id}",
                assertion={
                    "kind": "element_state",
                    "subject": {
                        "element_id": str(element.id),
                        "state_id": str(element.map_page_state_id),
                        "role": element.role,
                        "name": element.name,
                        "locators": list(element.locators or []),
                    },
                    "params": {"oracle": "visible"},
                },
            )
        )
    return facts


def verify_assertion_against_graph(
    expectation, index: GraphIndex
) -> tuple[str, str, UUID | None] | None:
    """Deterministic verification of one assertion (section 9.1 point 2).

    Returns (conflict_kind, observed_behaviour, observed_subject_id)
    when the harvested graph contradicts the assertion, else None.
    Only graph-checkable kinds are verified here; page_text and
    field_validation need the live app (Board checks, section 8.4).
    """
    assertion = expectation.assertion
    if not isinstance(assertion, dict):
        return None
    kind = assertion.get("kind")
    params = assertion.get("params") if isinstance(assertion.get("params"), dict) else {}
    if kind == "navigation":
        expected_url = params.get("expected_url")
        element = index.elements.get(expectation.subject_id)
        if element is None:
            return (
                "statement_vs_observation",
                "The asserted element is absent from the harvested graph.",
                expectation.subject_id,
            )
        observed = index.target_url_for_element(element.id)
        if observed is not None and expected_url is not None and observed != expected_url:
            return (
                "navigation_mismatch",
                (
                    f"Clicking '{element.name}' navigates to {observed}, "
                    f"not {expected_url}."
                ),
                element.id,
            )
    if kind == "element_state":
        if index.elements.get(expectation.subject_id) is None:
            return (
                "statement_vs_observation",
                "The asserted element is absent from the harvested graph.",
                expectation.subject_id,
            )
    if kind == "journey_terminal":
        if index.journeys.get(expectation.subject_id) is None:
            return (
                "statement_vs_observation",
                "The asserted journey is absent from the harvested graph.",
                expectation.subject_id,
            )
    return None


@dataclass
class JourneyAssembly:
    assembled: int = 0
    terminals_named: int = 0
    journeys: list[MapJourney] = field(default_factory=list)


def assemble_journeys(
    app_map: AppMap,
    index: GraphIndex,
    *,
    terminal_page_ids: dict[UUID, str],
) -> JourneyAssembly:
    """Deterministic journey assembly (section 6.2 stage 6).

    BFS over map_transitions from the map's base page through default
    states; one journey per named terminal (doc-grounded
    journey_terminal expectations + conversion-segment pages, chosen
    by the caller). Steps reuse doc 16 section 5.7's shape verbatim.
    Idempotency is the caller's (repository) concern via
    (success_state_id, name) matching against existing rows.
    """
    from markettwin_execution_orchestrator.harvest.harvest_skill import (
        CONVERSION_SEGMENTS,
    )

    base_page = index.pages_by_url.get(canonical_url(app_map.base_url))
    result = JourneyAssembly()
    if base_page is None:
        return result
    # BFS over pages via transitions between default states.
    default_by_page = index.default_state_by_page
    edges: dict[UUID, list[tuple[UUID, MapTransition]]] = {}
    state_page = {state.id: state.map_page_id for state in index.states.values()}
    for transition in index.transitions:
        from_page = state_page.get(transition.from_state_id)
        to_page = state_page.get(transition.to_state_id)
        if from_page is None or to_page is None or from_page == to_page:
            continue
        if default_by_page.get(from_page) is None:
            continue
        if default_by_page[from_page].id != transition.from_state_id:
            continue
        if default_by_page.get(to_page) is None:
            continue
        edges.setdefault(from_page, []).append((to_page, transition))

    def path_to(terminal: UUID) -> list[MapTransition] | None:
        if terminal == base_page.id:
            return []
        visited: dict[UUID, tuple[UUID, MapTransition] | None] = {base_page.id: None}
        queue: list[UUID] = [base_page.id]
        while queue:
            current = queue.pop(0)
            for to_page, transition in edges.get(current, []):
                if to_page in visited:
                    continue
                visited[to_page] = (current, transition)
                if to_page == terminal:
                    path: list[MapTransition] = []
                    node = to_page
                    while visited[node] is not None:
                        previous, step = visited[node]  # type: ignore[misc]
                        path.append(step)
                        node = previous
                    return list(reversed(path))
                queue.append(to_page)
        return None

    existing = {
        (journey.success_state_id, journey.name) for journey in index.journeys.values()
    }
    for terminal_id, naming in terminal_page_ids.items():
        terminal_page = index.pages.get(terminal_id)
        if terminal_page is None:
            continue
        terminal_state = default_by_page.get(terminal_id)
        if terminal_state is None:
            continue
        path = path_to(terminal_id)
        if path is None:
            continue
        segments = [
            segment
            for segment in terminal_page.canonical_url.split("/")
            if segment
        ]
        last_segment = segments[-1].replace("-", " ") if segments else "page"
        name = naming or f"Reach {last_segment}"
        if (terminal_state.id, name) in existing:
            continue
        steps: list[dict[str, object]] = []
        for transition in path:
            steps.append(
                {
                    "map_page_state_id": str(transition.from_state_id),
                    "element_id": (
                        str(transition.via_element_id)
                        if transition.via_element_id is not None
                        else None
                    ),
                    "action": transition.via_action or "click",
                    "value_source": "none",
                }
            )
        result.journeys.append(
            MapJourney(
                id=uuid4(),
                workspace_id=app_map.workspace_id,
                application_id=app_map.application_id,
                target_id=app_map.target_id,
                app_map_id=app_map.id,
                name=name,
                intent=f"Reach {terminal_page.canonical_url}",
                preconditions=[],
                steps=steps,
                success_state_id=terminal_state.id,
                skill_id=None,
                selection="rule",
                source="grounding",
                confidence="high",
                last_verified_at=None,
            )
        )
        result.assembled += 1
        if any(
            segment in CONVERSION_SEGMENTS
            for segment in terminal_page.canonical_url.lower().split("/")
        ) or naming:
            result.terminals_named += 1
    return result
