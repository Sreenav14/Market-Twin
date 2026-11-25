"""Run-side lookups over the pinned app-map snapshot (doc 16
section 8, doc 21 section 14.4).

Pure functions over the snapshot block a run was created with — no
database, no model calls (the AST guard in test_harvest_job.py pins
that). The Lead's checkpoint evidence and any consumer ask these
questions of the map the run was pinned to, never of a newer map.
"""

from __future__ import annotations

from typing import Any

from markettwin_shared.app_map_common import canonical_url

EXPECTATIONS_SOURCE = "none_in_1b"
EXPECTATIONS_SOURCE_GRAPH = "graph"


class ExpectationsResult(list):
    """The expectations answer: the snapshot's expectation entries
    (Phase 2 blocks), each stamped with its statement, oracle source,
    status, verdict eligibility and compiled assertion by the serving
    layer. A block without expectations (a 1b map) yields the labelled
    empty result — the absence is a fact about the phase, never a
    silent gap."""

    source = EXPECTATIONS_SOURCE


def _pages(app_map: Any) -> list[dict[str, Any]]:
    if not isinstance(app_map, dict):
        return []
    pages = app_map.get("pages")
    if not isinstance(pages, list):
        return []
    return [page for page in pages if isinstance(page, dict)]


def _page_urls(page: dict[str, Any]) -> set[str]:
    urls = set()
    for key in ("url", "effective_url"):
        value = page.get(key)
        if isinstance(value, str) and value:
            urls.add(canonical_url(value))
    return urls


def find_page(app_map: Any, url: str) -> dict[str, Any] | None:
    """The snapshot page for a URL (canonical match on the page's
    URL or its effective URL), or None when the map does not know
    the page."""
    target = canonical_url(url)
    for page in _pages(app_map):
        if target in _page_urls(page):
            return page
    return None


def page_elements(app_map: Any, url: str) -> list[dict[str, Any]] | None:
    """The harvested element inventory of one page, flattened across
    its states with the state key kept on each item. None when the
    page is not in the map; an empty list when the page is known but
    carries no harvested inventory (a census-only page)."""
    page = find_page(app_map, url)
    if page is None:
        return None
    blocks = page.get("elements")
    if not isinstance(blocks, list):
        return []
    flattened: list[dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for element in block.get("elements") or []:
            if isinstance(element, dict):
                flattened.append(
                    {**element, "state_key": block.get("state_key")}
                )
    return flattened


def find_journey(
    app_map: Any, name: str | None = None
) -> dict[str, Any] | None:
    """A recorded journey: the named one, or the first when no name
    is given. None when the map has no journeys."""
    if not isinstance(app_map, dict):
        return None
    journeys = app_map.get("journeys")
    if not isinstance(journeys, list):
        return None
    for journey in journeys:
        if not isinstance(journey, dict):
            continue
        if name is None or journey.get("name") == name:
            return journey
    return None


def find_skill(app_map: Any, name: str | None = None) -> dict[str, Any] | None:
    """An active skill carried by the snapshot: the named one, or
    the first when no name is given. Withheld (non-active) skills are
    not in the block at all, so they can never be found here."""
    if not isinstance(app_map, dict):
        return None
    skills = app_map.get("skills")
    if not isinstance(skills, list):
        return None
    for skill in skills:
        if not isinstance(skill, dict):
            continue
        if name is None or skill.get("name") == name:
            return skill
    return None


def get_skill(app_map: Any, name: str) -> dict[str, Any] | None:
    """The Lead's full-record skill lookup (doc 22 section 7.4): the
    named skill's complete snapshot entry — definition and full
    package (level 3) — when the snapshot serves it. An entry the
    block carries in a non-active state is returned AS withheld
    (its lifecycle named, no package), never dressed as servable.
    Unknown names return None; the withheld COUNT (names are not in
    the block) is the snapshot's own skills_withheld field."""
    entry = find_skill(app_map, name)
    if entry is None:
        return None
    lifecycle = entry.get("lifecycle_status")
    if lifecycle not in (None, "active", "replay_verified"):
        return {
            "name": entry.get("name"),
            "lifecycle_status": lifecycle,
            "withheld": True,
        }
    return dict(entry)


def get_expectations(app_map: Any, url: str | None = None) -> ExpectationsResult:
    """Expectations for a page (or the whole map), from the pinned
    snapshot block (doc 21 section 14.4). Entries carry their
    statement, oracle source, status, verdict eligibility, compiled
    assertion summary and open-conflict flag inline. The URL filter
    matches the entry's canonical page URL; entries whose page could
    not be resolved appear only on subjectless (whole-map) calls.
    A block with no expectations key returns the labelled empty
    result, never a fabricated one."""
    if not isinstance(app_map, dict):
        return ExpectationsResult()
    entries = app_map.get("expectations")
    if not isinstance(entries, list):
        return ExpectationsResult()
    target = canonical_url(url) if url else None
    selected = [
        dict(entry)
        for entry in entries
        if isinstance(entry, dict)
        and (target is None or entry.get("page_url") == target)
    ]
    result = ExpectationsResult(selected)
    result.source = EXPECTATIONS_SOURCE_GRAPH
    return result


def get_conflicts(app_map: Any) -> list[dict[str, Any]]:
    """The map's open conflicts as pinned in the snapshot block
    (doc 21 section 14.4): both sides preserved — the documented
    statement on the expectation, the observed behaviour on the
    conflict (the split rule, section 9.2)."""
    if not isinstance(app_map, dict):
        return []
    conflicts = app_map.get("open_conflicts")
    if not isinstance(conflicts, list):
        return []
    return [dict(conflict) for conflict in conflicts if isinstance(conflict, dict)]
