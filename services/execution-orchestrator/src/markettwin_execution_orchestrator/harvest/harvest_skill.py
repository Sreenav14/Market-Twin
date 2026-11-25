"""Journey selection and skill compilation (doc 16 sections 5.7-5.8, 9).

The journey is assembled from the harvested link graph by BFS — no
model calls anywhere in this module. Compilation renders the journey
into a TestCaseSpec-shaped skill definition: the native steps are
what the case executor runs unchanged, and the ranked locator
bindings ride alongside as the heal stage's source of truth (the
executor itself never reads them).
"""

import hashlib
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from markettwin_shared.app_map_common import canonical_url

# Priority order is the listing order (doc 16 section 5.7).
CONVERSION_SEGMENTS = (
    "get-a-demo",
    "demo",
    "signup",
    "sign-up",
    "get-started",
    "contact",
    "pricing",
)


@dataclass(frozen=True)
class JourneyEdge:
    """One harvested link: clicking element on a page leads to a page."""

    from_page_id: UUID
    from_state_id: UUID  # the source page's DEFAULT state row id
    element_id: UUID
    role: str
    name: str
    locators: list[dict[str, object]]
    to_page_id: UUID
    action: str = "click"
    test_value_key: str | None = None


@dataclass(frozen=True)
class JourneyNode:
    page_id: UUID
    canonical_url: str
    default_state_id: UUID
    default_state_identity: str | None
    default_element_signature: list[str] = field(default_factory=list)


@dataclass
class JourneySelection:
    terminal: JourneyNode
    path: list[JourneyEdge]
    selection: str  # 'rule' | 'owner'
    detail: dict[str, object]


def _path_segments(url: str) -> list[str]:
    return [segment for segment in urlsplit(url).path.split("/") if segment]


def _conversion_priority(url: str) -> int | None:
    segments = set(_path_segments(url))
    for index, segment in enumerate(CONVERSION_SEGMENTS):
        if segment in segments:
            return index
    return None


def select_journey(
    *,
    nodes: dict[UUID, JourneyNode],
    edges: list[JourneyEdge],
    base_page_id: UUID,
    owner_terminal_url: str | None,
) -> JourneySelection | None:
    """BFS journey selection (doc 16 section 5.7).

    The owner's terminal wins when given. Otherwise the terminal is
    the highest-priority reachable conversion page (ties: shortest
    path, then smallest canonical URL); with no conversion page
    reachable, the terminal is the page whose shortest path from the
    base is longest (ties: smallest canonical URL).
    """
    if base_page_id not in nodes:
        return None
    adjacency: dict[UUID, list[JourneyEdge]] = {}
    for edge in edges:
        adjacency.setdefault(edge.from_page_id, []).append(edge)
    for page_edges in adjacency.values():
        page_edges.sort(key=lambda edge: (edge.role, edge.name))
    distance: dict[UUID, int] = {base_page_id: 0}
    parent: dict[UUID, JourneyEdge] = {}
    queue: deque[UUID] = deque([base_page_id])
    while queue:
        current = queue.popleft()
        for edge in adjacency.get(current, []):
            if edge.to_page_id not in distance and edge.to_page_id in nodes:
                distance[edge.to_page_id] = distance[current] + 1
                parent[edge.to_page_id] = edge
                queue.append(edge.to_page_id)

    def path_to(page_id: UUID) -> list[JourneyEdge]:
        path: list[JourneyEdge] = []
        cursor = page_id
        while cursor != base_page_id:
            edge = parent[cursor]
            path.append(edge)
            cursor = edge.from_page_id
        path.reverse()
        return path

    if owner_terminal_url:
        wanted = canonical_url(owner_terminal_url)
        for node in nodes.values():
            if node.canonical_url == wanted and node.page_id in distance:
                return JourneySelection(
                    terminal=node,
                    path=path_to(node.page_id),
                    selection="owner",
                    detail={"reason": "owner_terminal", "url": wanted},
                )
        return JourneySelection(
            terminal=nodes[base_page_id],
            path=[],
            selection="owner",
            detail={
                "reason": "owner_terminal_unreachable",
                "url": wanted,
            },
        )

    conversion_candidates: list[tuple[int, int, str, JourneyNode]] = []
    for page_id, node in nodes.items():
        if page_id == base_page_id or page_id not in distance:
            continue
        priority = _conversion_priority(node.canonical_url)
        if priority is not None:
            conversion_candidates.append(
                (priority, distance[page_id], node.canonical_url, node)
            )
    if conversion_candidates:
        conversion_candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        chosen = conversion_candidates[0][3]
        return JourneySelection(
            terminal=chosen,
            path=path_to(chosen.page_id),
            selection="rule",
            detail={
                "reason": "conversion_terminal",
                "segment_priority": conversion_candidates[0][0],
            },
        )
    farthest: list[tuple[int, str, JourneyNode]] = [
        (-distance[page_id], node.canonical_url, node)
        for page_id, node in nodes.items()
        if page_id != base_page_id and page_id in distance
    ]
    if not farthest:
        return None
    farthest.sort(key=lambda item: (item[0], item[1]))
    chosen = farthest[0][2]
    return JourneySelection(
        terminal=chosen,
        path=path_to(chosen.page_id),
        selection="rule",
        detail={"reason": "longest_path", "depth": -farthest[0][0]},
    )


def _slug(value: str, *, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    if not slug or not slug[0].isalpha():
        slug = f"{fallback}_{slug}".strip("_")
    return slug[:64]


def _identifier(value: str, *, fallback: str, salt: str) -> str:
    slug = _slug(value, fallback=fallback)
    suffix = hashlib.sha256(salt.encode("utf-8")).hexdigest()[:8]
    return f"{slug[:50]}_{suffix}"[:64]


def journey_steps(selection: JourneySelection) -> list[dict[str, object]]:
    """The stored journey steps (doc 16 section 5.7 shape)."""
    return [
        {
            "map_page_state_id": str(edge.from_state_id),
            "element_id": str(edge.element_id),
            "action": edge.action,
            "value_source": edge.test_value_key or "none",
            **({"test_value_key": edge.test_value_key} if edge.test_value_key else {}),
        }
        for edge in selection.path
    ]


def build_definition(
    *,
    selection: JourneySelection,
    base_node: JourneyNode,
    nodes: dict[UUID, JourneyNode],
    journey_name: str,
    app_map: Any,
) -> dict[str, Any] | None:
    """The skill's definition_json (doc 16 sections 5.8, 9.1).

    Top level is the serialised native TestCaseSpec (which must
    round-trip through TestCaseSpec.model_validate on its native
    subset) plus the parallel locator bindings, the success
    assertion, and the three source_* provenance keys. Returns None
    when the journey cannot compile (a path longer than the spec's
    24-step bound is an honest compile failure, not a truncation).
    """
    from markettwin_shared.feature_plan import TestCaseSpec

    clicks = selection.path
    if len(clicks) + 1 > 24:
        return None
    case_id = _identifier(
        journey_name, fallback="journey", salt=f"{app_map.id}:{journey_name}"
    )
    feature_key = _identifier(
        "map_journey", fallback="journey", salt=str(app_map.id)
    )
    native_steps: list[dict[str, Any]] = [
        {"action": "navigate", "url": base_node.canonical_url}
    ]
    bindings: list[dict[str, object]] = []
    for order, edge in enumerate(clicks, start=2):
        if edge.action not in {"click", "fill", "select", "check", "uncheck"}:
            return None
        target = {"role": edge.role, "name": edge.name}
        if edge.action != "click":
            label = next((item.get("value") for item in edge.locators
                          if item.get("kind") == "label" and item.get("value")), None)
            if not isinstance(label, str):
                return None
            target = {"label": label}
        action: dict[str, Any] = {"action": edge.action, "target": target}
        if edge.action in {"fill", "select"}:
            if not edge.test_value_key:
                return None
            action["test_value_key"] = edge.test_value_key
        elif edge.test_value_key is not None:
            return None
        native_steps.append(action)
        from_node = nodes.get(edge.from_page_id)
        bindings.append(
            {
                "order": order,
                "page_url": from_node.canonical_url if from_node else None,
                "element": {"role": edge.role, "name": edge.name},
                "locators": list(edge.locators),
                "action": edge.action,
                "value_source": edge.test_value_key or "none",
            }
        )
    terminal_url = selection.terminal.canonical_url
    native = {
        "case_id": case_id,
        "feature_key": feature_key,
        "title": f"Journey: {journey_name}"[:160],
        "kind": "happy_path",
        "steps": native_steps,
        "expected": [
            {
                "assertion_id": "terminal_url",
                "oracle": "url",
                "expected_value": terminal_url,
                "origin": "inferred",
            }
        ],
        "safety": "non_destructive",
        "estimated_seconds": min(180, 15 + 10 * len(native_steps)),
    }
    # The native subset must round-trip through the real contract.
    TestCaseSpec.model_validate(native)
    return {
        **native,
        "verification_scope": "navigation",
        "locator_bindings": bindings,
        "success_assertion": {
            "kind": "terminal_state",
            "url": terminal_url,
            "state_id": selection.terminal.default_state_identity,
            "element_signature": list(
                selection.terminal.default_element_signature
            ),
            "signature_superset_fallback": True,
        },
        "source_journey_id": None,
        "source_map_id": str(app_map.id),
        "source_map_version": app_map.version_number,
    }


def render_package(
    *,
    selection: JourneySelection,
    journey_name: str,
    application_name: str,
    app_map: Any,
    nodes: dict[UUID, JourneyNode],
    base_url: str,
) -> dict[str, Any]:
    """The section 9.2 progressive-disclosure package."""
    name = re.sub(r"[^a-z0-9]+", "-", journey_name.casefold()).strip("-")
    description = (
        f"Navigate to {selection.terminal.canonical_url} on "
        f"{application_name}. Navigation only; compiled from map v{app_map.version_number}."
    )[:200]
    step_lines: list[str] = []
    for index, edge in enumerate(selection.path, start=1):
        node = nodes.get(edge.from_page_id)
        step_lines.append(
            f"{index}. On {node.canonical_url if node else 'the page'}, "
            f"{edge.action} the {edge.role} named \"{edge.name}\""
            + (f" using input {edge.test_value_key}." if edge.test_value_key else ".")
        )
    body_md = "\n".join(
        [
            "## Preconditions",
            f"- The application is open at {base_url}, logged out, "
            "at desktop width.",
            "",
            "## Steps",
            *step_lines,
            "",
            "## Success assertion",
            "- Scope: navigation only. Arrival does not prove completion of a business task.",
            f"- The browser ends on {selection.terminal.canonical_url} and "
            "the page state matches the harvested terminal state.",
            "",
            "## Recovery branches",
            "- If a step's element is not found, walk the step's ranked "
            "locator bindings in order; never invent a new target.",
            "- If the browser leaves the journey's pages, navigate back "
            "to the starting page and restart the journey once.",
            "",
            "## Known pitfalls",
            "- Cookie-consent overlays are chrome: dismiss them before "
            "step 1 if present.",
            "- The journey was compiled from a public, logged-out "
            "harvest; it does not cover authenticated states.",
        ]
    )
    resources: list[dict[str, object]] = []
    seen_pages: list[UUID] = []
    for edge in selection.path:
        if edge.from_page_id not in seen_pages:
            seen_pages.append(edge.from_page_id)
    if selection.terminal.page_id not in seen_pages:
        seen_pages.append(selection.terminal.page_id)
    for page_id in seen_pages:
        resources.append({"kind": "page_record", "ref": str(page_id)})
    return {
        "name": name or "journey",
        "description": description,
        "body_md": body_md,
        "resources": resources,
        "catalogue": {
            "level1": ["name", "description"],
            "level2": "body_md",
            "level3": "resources",
        },
    }


def render_definition_package(
    definition: dict[str, Any],
    *,
    application_name: str = "the application",
    base_url: str = "",
) -> dict[str, Any]:
    """The progressive-disclosure package for ANY definition of the
    established shape (doc 29 section 5): the human-readable
    procedure is a projection of the executable definition --
    purpose, kinded prerequisites, numbered steps (action + target +
    input LABEL, never a value), expected outcomes, the success
    assertion, cleanup, and documented expectations under their own
    heading. One source, rendered once, at compile time, so the
    procedure cannot drift from what verification replays."""
    task = definition.get("task")
    task = task if isinstance(task, dict) else {}
    title = str(definition.get("title") or "Task")
    name = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-") or "task"
    purpose = str(task.get("purpose") or title)
    description = purpose[:200]
    bindings = {
        entry.get("order"): entry
        for entry in definition.get("locator_bindings") or []
        if isinstance(entry, dict)
    }
    lines: list[str] = ["## Purpose", f"- {purpose}", "", "## Preconditions"]
    prerequisites = [
        entry for entry in task.get("prerequisites") or []
        if isinstance(entry, dict)
    ]
    if prerequisites:
        for entry in prerequisites:
            kind = entry.get("kind")
            if kind == "authenticated":
                lines.append(
                    "- The user is signed in (the login skill or a "
                    "handover establishes the session)."
                )
            elif kind == "on_page":
                lines.append(f"- The browser is on {entry.get('url')}.")
            elif kind == "input_available":
                lines.append(
                    f"- Input {entry.get('input_key')} is available."
                )
            elif kind == "skill_active":
                lines.append(
                    f"- The {entry.get('skill_name')} skill is active."
                )
    else:
        lines.append("- None recorded.")
    lines += ["", "## Steps"]
    steps = [
        entry for entry in definition.get("steps") or []
        if isinstance(entry, dict)
    ]
    for index, step in enumerate(steps, start=1):
        action = step.get("action")
        binding = bindings.get(index) or {}
        element = binding.get("element") or {}
        target = step.get("target") or {}
        label = (
            target.get("label") or element.get("label")
            or target.get("name") or element.get("name")
            or target.get("text") or element.get("text") or "the control"
        )
        if action == "navigate":
            lines.append(f"{index}. Go to {step.get('url')}.")
        elif action in ("fill", "select"):
            verb = "Fill" if action == "fill" else "Select"
            lines.append(
                f"{index}. {verb} {label} using input "
                f"{step.get('test_value_key')}."
            )
        elif action == "click":
            lines.append(f"{index}. Click {label}.")
        elif action in ("check", "uncheck"):
            lines.append(f"{index}. {action.capitalize()} {label}.")
        elif action == "wait":
            lines.append(f"{index}. Wait.")
        else:
            lines.append(f"{index}. {action} {label}.")
    expected = [
        entry for entry in definition.get("expected") or []
        if isinstance(entry, dict)
    ]
    if expected:
        lines += ["", "## Expected outcomes"]
        for entry in expected:
            lines.append(
                f"- {entry.get('assertion_id')}: {entry.get('oracle')} "
                f"is {entry.get('expected_value')}."
            )
    success = definition.get("success_assertion") or {}
    if isinstance(success, dict) and success.get("url"):
        lines += [
            "",
            "## Success assertion",
            f"- The browser ends on {success.get('url')} and the page "
            "state matches the recorded terminal state.",
        ]
    cleanup = task.get("cleanup")
    if isinstance(cleanup, dict) and cleanup.get("kind"):
        lines += ["", "## Cleanup", f"- Cleanup: {cleanup.get('kind')}."]
    documented = [
        entry for entry in task.get("documented_expectations") or []
        if isinstance(entry, dict) and entry.get("text")
    ]
    if documented:
        lines += ["", "## Documented expectations (claims -- not executed)"]
        for entry in documented:
            lines.append(f"- {entry['text']}")
    resources: list[dict[str, object]] = []
    seen: list[str] = []
    for entry in definition.get("locator_bindings") or []:
        if isinstance(entry, dict) and entry.get("page_url"):
            url = str(entry["page_url"])
            if url not in seen:
                seen.append(url)
                resources.append({"kind": "page_record", "ref": url})
    return {
        "name": name,
        "description": description,
        "body_md": "\n".join(lines),
        "resources": resources,
        "catalogue": {
            "level1": ["name", "description"],
            "level2": "body_md",
            "level3": "resources",
        },
    }


@dataclass
class CompileResult:
    journey: Any | None
    skill_version: Any | None
    definition: dict[str, Any] | None
    package: dict[str, Any] | None
    registry_error: str | None


async def compile_journey(
    *,
    repository: Any,
    app_map: Any,
    selection: JourneySelection,
    base_node: JourneyNode,
    nodes: dict[UUID, JourneyNode],
    journey_name: str,
    application_name: str,
) -> CompileResult:
    """Write the journey row and attempt the registry write.

    The registry write runs in its OWN transaction after the journey
    row commits (doc 16 section 9): on the current schema it fails
    with the legacy NOT NULL columns (OQ2), and that failure is
    recorded in harvest_metrics — never hidden, never worked around
    with a fabricated blueprint row.
    """
    if any(edge.action in {"fill", "select"} for edge in selection.path):
        reason = "journey_input_context_unavailable"
        await repository.save_harvest_metrics(
            app_map.id, {"skill_compile": {"result": "refused", "reason": reason}},
        )
        return CompileResult(None, None, None, None, reason)
    definition = build_definition(
        selection=selection,
        base_node=base_node,
        nodes=nodes,
        journey_name=journey_name,
        app_map=app_map,
    )
    if definition is None:
        await repository.save_harvest_metrics(
            app_map.id,
            {
                "skill_compile": {
                    "result": "failed",
                    "reason": "journey_too_long",
                }
            },
        )
        return CompileResult(None, None, None, None, "journey_too_long")
    package = render_package(
        selection=selection,
        journey_name=journey_name,
        application_name=application_name,
        app_map=app_map,
        nodes=nodes,
        base_url=base_node.canonical_url,
    )
    journey = await repository.create_journey(
        app_map,
        name=journey_name,
        intent=f"Reach {selection.terminal.canonical_url}",
        preconditions=[],
        steps=journey_steps(selection),
        success_state_id=selection.terminal.default_state_id,
        selection=selection.selection,
    )
    definition["source_journey_id"] = str(journey.id)
    try:
        skill, version = await repository.create_skill_with_version(
            app_map,
            name=str(package["name"]),
            definition=definition,
            package=package,
            created_by_user_id=None,
        )
    except Exception as exc:  # OQ2: recorded honestly, never hidden
        reason = f"{type(exc).__name__}: {str(exc)[:300]}"
        await repository.save_harvest_metrics(
            app_map.id,
            {"skill_compile": {"result": "failed", "reason": reason}},
        )
        return CompileResult(journey, None, definition, package, reason)
    await repository.attach_journey_skill(journey.id, skill.id)
    await repository.save_harvest_metrics(
        app_map.id,
        {"skill_compile": {"result": "ok", "skill_id": str(skill.id)}},
    )
    return CompileResult(journey, version, definition, package, None)
