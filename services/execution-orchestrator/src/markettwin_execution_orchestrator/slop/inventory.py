"""Slop inventory accounting against the app map (doc 16 section 7).

The map's harvested element inventory is the denominator the slop
traversal is checked against: every inventoried element of a judged
page is accounted for as judged or unjudged-with-a-reason, so a page
the traversal barely touched can no longer look fully reviewed.
Verdicts are NEVER carried from the map into a run — the accounting
counts what THIS run judged; ``carried_verdicts`` is structurally 0
at the call site (doc 13's binding correction: slop verdicts are
re-judged live per run).

Pure functions; the event emission lives at the traversal call site.
"""

from __future__ import annotations

from typing import Any

from markettwin_shared.app_map_common import canonical_url

JUDGED_VERDICTS = ("clean", "slop", "slop_minor")
UNJUDGED_REASONS = (
    "not_visible_in_review",
    "duplicate_of_judged",
    "inventory_stale_mismatch",
)


def inventory_for_page(
    app_map: Any, url: str
) -> list[dict[str, Any]] | None:
    """The harvested inventory of one page as flat
    ``{role, name, state_key}`` items, or None when there is nothing
    to account against: no map, the page is not in the map, or the
    page carries no harvested elements. None means the caller emits
    no accounting event at all — behaviour without a map is
    byte-identical to before."""
    if not isinstance(app_map, dict):
        return None
    pages = app_map.get("pages")
    if not isinstance(pages, list):
        return None
    target = canonical_url(url)
    page = None
    for candidate in pages:
        if not isinstance(candidate, dict):
            continue
        urls = {
            canonical_url(str(candidate.get(key)))
            for key in ("url", "effective_url")
            if candidate.get(key)
        }
        if target in urls:
            page = candidate
            break
    if page is None:
        return None
    blocks = page.get("elements")
    if not isinstance(blocks, list):
        return None
    items: list[dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for element in block.get("elements") or []:
            if isinstance(element, dict):
                items.append(
                    {
                        "role": element.get("role"),
                        "name": element.get("name"),
                        "state_key": block.get("state_key"),
                    }
                )
    return items or None


def account_for_page(
    inventory: list[dict[str, Any]], judged: list[dict[str, Any]]
) -> dict[str, Any]:
    """Partition one page's inventory against what the run judged.

    ``judged`` entries are ``{role, name, state_key, verdict}`` for
    every element the review saw on this page (any verdict, including
    ``cant_tell``). An inventory item is judged when the same
    (state, role, name) carries a real verdict; a judged entry whose
    state_key is None (a live state the caller could not key to a
    harvested state) claims the first still-unjudged inventory item
    with its (role, name). The unjudged reasons are, in order: the
    element was judged in ANOTHER state of the page
    (``duplicate_of_judged``), the element was seen live but never
    decided (``not_visible_in_review``), or the element does not
    exist on the live page at all (``inventory_stale_mismatch``).
    The partition is exact: judged + unjudged == inventory_total.
    """
    judged_here: set[tuple[Any, Any, Any]] = set()
    judged_elsewhere: set[tuple[Any, Any]] = set()
    floating: dict[tuple[Any, Any], int] = {}
    seen: set[tuple[Any, Any]] = set()
    for entry in judged:
        key = (entry.get("role"), entry.get("name"))
        seen.add(key)
        if entry.get("verdict") in JUDGED_VERDICTS:
            judged_elsewhere.add(key)
            if entry.get("state_key") is None:
                floating[key] = floating.get(key, 0) + 1
            else:
                judged_here.add((entry.get("state_key"), *key))
    judged_count = 0
    unjudged: list[dict[str, Any]] = []
    for item in inventory:
        key = (item.get("role"), item.get("name"))
        if (item.get("state_key"), *key) in judged_here:
            judged_count += 1
        elif floating.get(key, 0) > 0:
            floating[key] -= 1
            judged_count += 1
        elif key in judged_elsewhere:
            unjudged.append({**item, "reason": "duplicate_of_judged"})
        elif key in seen:
            unjudged.append({**item, "reason": "not_visible_in_review"})
        else:
            unjudged.append({**item, "reason": "inventory_stale_mismatch"})
    return {
        "inventory_total": len(inventory),
        "judged": judged_count,
        "unjudged": unjudged,
    }
