"""Reconcile a finished run against its pinned application map.

Pure matcher (Phase 1a spec section 10.6): it takes the snapshot's
app_map block plus three run facts — the live states absorbed during
the run, the URLs whose navigation was attempted and failed, and the
frontier still unvisited at completion — and partitions every
expected URL into exactly one category. It reads no database, calls
no model, and treats missing keys as empty collections: a run must
never die over reference data.

Phase 4 (doc 23 section 6.5) adds the second producer of the same
partition, ``build_preflight_delta``, over one shared core
(``_partition``): a preflight outcome and a run's coverage delta can
be placed side by side without translation.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping


def _seeded_state_ids(pages: list) -> dict[str, set[str]]:
    """Snapshot page URL -> all state identities the map claimed for it."""

    seeded: dict[str, set[str]] = {}
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("url"), str):
            continue
        states = page.get("states")
        if not isinstance(states, list):
            continue
        for entry in states:
            if isinstance(entry, dict) and isinstance(entry.get("state_id"), str):
                seeded.setdefault(page["url"], set()).add(entry["state_id"])
    return seeded


def _expected_pages(map_block: dict) -> tuple[dict[str, str], dict[str, set[str]], int]:
    """(expected url -> status, seeded url -> state_id, expected total).

    The snapshot reading both producers share: malformed shapes read
    as empty, never as an error (the module's standing posture).
    """

    pages = map_block.get("pages") if isinstance(map_block, dict) else None
    if not isinstance(pages, list):
        pages = []
    expected: dict[str, str] = {}
    for page in pages:
        if isinstance(page, dict) and isinstance(page.get("url"), str):
            status = page.get("status")
            expected[page["url"]] = status if isinstance(status, str) else ""
    counts_block = map_block.get("counts") if isinstance(map_block, dict) else None
    map_expected_total = (
        counts_block.get("expected") if isinstance(counts_block, dict) else None
    )
    if not isinstance(map_expected_total, int):
        map_expected_total = len(expected)
    return expected, _seeded_state_ids(pages), map_expected_total


def _partition(expected_urls, classify: Callable[[str], tuple[str, object] | None]):
    """The one partition core (doc 23 section 6.5).

    Walk the expected URLs in canonical order; ``classify`` returns a
    ``(category, entry)`` pair or ``None`` to leave the URL
    unclassified (the preflight's deferred pages: never swept, never
    forced into a category).
    """

    buckets: dict[str, list] = {
        "present": [],
        "changed": [],
        "unreachable": [],
        "missing": [],
    }
    for url in sorted(expected_urls):
        verdict = classify(url)
        if verdict is None:
            continue
        category, entry = verdict
        buckets[category].append(entry)
    return buckets


def build_coverage_delta(*, map_block: dict, absorbed: dict[str, str],
                         attempted_failed: list[str],
                         frontier_remaining: list[str]) -> dict:
    """Partition the map's expected URLs against what the run absorbed.

    Categories, each expected URL in exactly one, evaluated in order:
    changed — absorbed, but the live state_id differs from the seeded
    one; present — absorbed; unreachable — in attempted_failed;
    missing — everything else (frontier_remaining members land here by
    construction: queued but never absorbed and never attempted).
    Absorbed URLs the map never carried are reported as new.
    """

    expected, seeded, map_expected_total = _expected_pages(map_block)
    failed = set(attempted_failed or [])

    def classify(url: str):
        live_state_id = absorbed.get(url)
        if live_state_id is not None:
            seeded_state_ids = seeded.get(url)
            if seeded_state_ids and live_state_id not in seeded_state_ids:
                return "changed", {"url": url, "seeded_state_id": sorted(seeded_state_ids)[0],
                                   "live_state_id": live_state_id}
            return "present", url
        if url in failed:
            return "unreachable", url
        return "missing", {"url": url, "status": expected[url]}

    buckets = _partition(expected, classify)
    present = buckets["present"]
    changed = buckets["changed"]
    unreachable = buckets["unreachable"]
    missing = buckets["missing"]
    new = sorted(url for url in absorbed if url not in expected)
    return {
        "map_id": map_block.get("map_id") if isinstance(map_block, dict) else None,
        "map_version": (map_block.get("version_number")
                        if isinstance(map_block, dict) else None),
        "expected_in_snapshot": len(expected),
        "map_expected_total": map_expected_total,
        "delta_scope": ("snapshot_truncated"
                        if isinstance(map_block, dict)
                        and map_block.get("routes_truncated") else "full"),
        "present": present,
        "present_count": len(present),
        "missing": missing,
        "unreachable": unreachable,
        "changed": changed,
        "new": new,
        "counts": {"present": len(present), "missing": len(missing),
                   "unreachable": len(unreachable), "changed": len(changed),
                   "new": len(new)},
    }


def build_preflight_delta(*, map_block: dict, tier1: dict, tier2: dict,
                          recollected: Mapping) -> dict:
    """Partition the swept version's expected URLs by preflight outcome.

    The Phase 4 producer of the section 10.6 partition (doc 23
    sections 4.2 and 6.5). Inputs are the sweep's own records:

    - ``tier1``: url -> ``{http_status, fetch_error, differs}`` for
      every expected URL the tier-1 fetch attempted;
    - ``tier2``: url -> ``{outcome, recorded_state_id, live_state_id,
      basis, reason, html_drift}`` for every rendered candidate;
    - ``recollected``: url -> source kinds, the tier-0 collection.

    Evaluation order per expected URL, exactly: changed (a tier-2
    mismatch — for signature-less pages the sweep's tier-2 verdict
    itself carries ``basis: 'html'``, the tier-1 difference standing
    through the render) -> missing (dual-confirmed: absent from
    ``recollected`` AND tier-1 status 404/410) -> unreachable
    (attempted, failed or walled; a 404 the site's own sources still
    claim lands here as ``fetch_error``) -> present (everything else
    re-observed). An expected URL with no tier-1 record was never
    swept: it is left unclassified, named by the caller in
    ``deferred``, and the payload's ``delta_scope`` reads
    ``'partial_sweep'``.
    """

    expected, _seeded, map_expected_total = _expected_pages(map_block)
    tier1 = tier1 or {}
    tier2 = tier2 or {}
    recollected = recollected or {}

    def classify(url: str):
        rendered = tier2.get(url)
        if isinstance(rendered, dict):
            outcome = rendered.get("outcome")
            if outcome == "changed":
                return "changed", {
                    "url": url,
                    "recorded_state_id": rendered.get("recorded_state_id"),
                    "live_state_id": rendered.get("live_state_id"),
                    "basis": rendered.get("basis") or "state",
                }
            if outcome == "unreachable":
                return "unreachable", {
                    "url": url,
                    "reason": rendered.get("reason") or "fetch_error",
                }
            if outcome == "present":
                return "present", url
        fetched = tier1.get(url)
        if not isinstance(fetched, dict):
            return None  # never swept: deferred, not classified
        http_status = fetched.get("http_status")
        if url not in recollected and http_status in (404, 410):
            return "missing", {"url": url, "http_status": http_status}
        if fetched.get("fetch_error") or http_status in (404, 410):
            return "unreachable", {"url": url, "reason": "fetch_error"}
        if fetched.get("differs"):
            return None  # differed but never rendered: deferred
        return "present", url

    buckets = _partition(expected, classify)
    present = buckets["present"]
    changed = buckets["changed"]
    unreachable = buckets["unreachable"]
    missing = buckets["missing"]
    classified = len(present) + len(changed) + len(unreachable) + len(missing)
    new = [
        {"url": url, "source_kinds": sorted(recollected[url])}
        for url in sorted(recollected)
        if url not in expected
    ]
    basis_counts = {"state": 0, "html": 0}
    for entry in changed:
        basis = entry.get("basis")
        if basis in basis_counts:
            basis_counts[basis] += 1
    html_drift_count = sum(
        1
        for url, rendered in tier2.items()
        if url in expected
        and isinstance(rendered, dict)
        and rendered.get("outcome") == "present"
        and rendered.get("html_drift")
    )
    return {
        "map_id": map_block.get("map_id") if isinstance(map_block, dict) else None,
        "map_version": (map_block.get("version_number")
                        if isinstance(map_block, dict) else None),
        "expected_in_snapshot": len(expected),
        "map_expected_total": map_expected_total,
        "delta_scope": "partial_sweep" if classified < len(expected) else "full",
        "present": present,
        "present_count": len(present),
        "missing": missing,
        "unreachable": unreachable,
        "changed": changed,
        "new": new,
        "counts": {"present": len(present), "missing": len(missing),
                   "unreachable": len(unreachable), "changed": len(changed),
                   "new": len(new)},
        "basis_counts": basis_counts,
        "html_drift_count": html_drift_count,
    }
