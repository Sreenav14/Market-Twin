"""Board-based evaluation for unified Explore & Test runs (U-P1-05).

Pure computation over the run's Board document (the harness_state in
the configuration snapshot) and its board.item.result events. The
verdict comes ONLY from Board coverage and confirmed Board outcomes —
persona data of any kind is not an input (the contract-mode score leak
this replaces is deleted in P5).

Verdict (§3.6 of the implementation plan):
- coverage = (worked + broken) / (total − owner_disabled)
- "Can't tell yet" when there is nothing to judge or coverage < 0.5
- "Not ready yet" when at least one item is confirmed broken
- otherwise "Ready"
"""

from __future__ import annotations

from collections.abc import Mapping

TERMINAL_ITEM_STATUSES = frozenset({
    "worked", "broken", "could_not_check", "not_checked", "blocked",
    "owner_disabled",
})


def compute_board_verdict(
    *,
    board_document: Mapping[str, object],
    board_results: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Return {verdict, coverage, items} for one run's Board."""

    raw_items = board_document.get("items")
    items: list[Mapping[str, object]] = []
    if isinstance(raw_items, dict):
        items = [v for v in raw_items.values() if isinstance(v, dict)]
    elif isinstance(raw_items, list):
        items = [v for v in raw_items if isinstance(v, dict)]

    rows: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    missing_events = 0
    for item in items:
        item_id = str(item.get("item_id", ""))
        board_status = str(item.get("status", "pending"))
        event = board_results.get(item_id)
        missing_event = False
        if event is not None:
            effective_status = str(event.get("board_status", board_status))
        elif board_status == "owner_disabled":
            # Owner-disabled items leave the denominator by the verdict
            # formula; one without a result event is not an accounting
            # gap and must not be reclassified into it.
            effective_status = "owner_disabled"
        elif board_status in TERMINAL_ITEM_STATUSES:
            # A terminal item without its result event is an accounting
            # gap: it is reported per-item as could_not_check, never as
            # a whole-run failure and never silently dropped.
            effective_status = "could_not_check"
            missing_events += 1
            missing_event = True
        else:
            effective_status = board_status
        counts[effective_status] = counts.get(effective_status, 0) + 1
        rows.append({
            "board_item_id": item_id,
            "case_id": item.get("case_id"),
            "role": item.get("role"),
            "name": item.get("name"),
            "board_status": board_status,
            "effective_status": effective_status,
            "blocker": item.get("blocker"),
            "missing_result_event": missing_event,
            "assertions": list(event.get("assertions", [])) if event else [],
            "evidence_refs": list(event.get("evidence_refs", [])) if event else [],
        })

    total = len(items)
    denominator = total - counts.get("owner_disabled", 0)
    checked = counts.get("worked", 0) + counts.get("broken", 0)
    coverage = (checked / denominator) if denominator > 0 else 0.0
    if denominator == 0 or coverage < 0.5:
        verdict = "Can't tell yet"
    elif counts.get("broken", 0) > 0:
        verdict = "Not ready yet"
    else:
        verdict = "Ready"
    return {
        "verdict": verdict,
        "coverage": {
            "total_items": total,
            "denominator": denominator,
            "checked": checked,
            "coverage": round(coverage, 4),
            "counts": counts,
            "missing_result_events": missing_events,
        },
        "items": rows,
    }
