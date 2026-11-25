"""Reconcile-don't-replace: the successor version (doc 23 section 7).

When a preflight outcome carries changed, missing or new pages, this
module mints version V+1 of the same (application, target) inside the
same job: census and harvest rows are copied forward, changed pages
are re-observed from the sweep's retained captures (no second
render), new pages get a scoped harvest visit, missing pages are
carried as ``gone``, and unreachable pages are carried byte-identical.
The successor passes through the same pure gates as any version, its
release may not exceed the base version's without a gate behind it,
touched template groups are re-enriched under the mapping cap, and —
last — the active skill versions whose fingerprints the sweep proved
stale are demoted through Phase 3's transition authority.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from markettwin_shared.app_map_common import (
    compute_harvest_gate,
    compute_inventory_gate,
)

logger = logging.getLogger(__name__)

BUILDER_VERSION = "preflight-4.1"


def carried_row_values(
    row: Any,
    *,
    remap: dict[str, dict[UUID, UUID]],
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Column values for a copy-forward of ``row`` under a new version.

    One generic copier for every versioned table: identity and
    timestamps are dropped (the database fills fresh ones), foreign
    keys named in ``remap`` are rewritten to the successor's rows, and
    ``overrides`` wins over the carried value. Evidence objects are
    shared by key — a copied evidence row points at the base version's
    object, which is correct: the store is content-addressed and no
    deletion path exists (doc 23 section 7.2).
    """

    values: dict[str, Any] = {}
    for column in row.__table__.columns:
        if column.name in ("id", "created_at", "updated_at"):
            continue
        value = getattr(row, column.name)
        mapping = remap.get(column.name)
        if mapping is not None and value in mapping:
            value = mapping[value]
        values[column.name] = value
    if overrides:
        values.update(overrides)
    values["id"] = uuid4()
    return values


async def reconcile_preflight(
    repository,
    preflight: Any,
    app_map: Any,
    result: Any,
    delta: dict,
    *,
    visit_new_pages: Callable[..., Any],
    persist_changed_pages: Callable[..., Any],
    enrich_touched: Callable[..., Any],
    demote_skills: Callable[..., Any],
    new_page_cap: int,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> UUID:
    """Mint and build the successor; return its id.

    The three composition seams (scoped harvest visit for new pages,
    capture-persist for changed pages, scoped enrichment) and the
    demotion step are injected callables wired by the job's production
    stages from the harvest package — this module owns the version
    arithmetic, the copy-forward, the gates and the ordering
    (demotion last, doc 23 section 7.5).
    """

    completed_at = now()
    changed_urls = {entry["url"] for entry in delta["changed"]}
    missing_urls = {entry["url"] for entry in delta["missing"]}
    unreachable_urls = {entry["url"] for entry in delta["unreachable"]}
    new_entries = list(delta["new"])
    overflow_new = new_entries[new_page_cap:]
    scoped_new = new_entries[:new_page_cap]

    successor = await repository.mint_successor(
        app_map,
        preflight=preflight,
        builder_version=BUILDER_VERSION,
        freshness_metrics={
            "preflight_id": str(preflight.id),
            "outcome_counts": delta["counts"],
            "deferred_count": len(result.deferred) + len(overflow_new),
            "basis_counts": delta["basis_counts"],
            "completed_at": completed_at.isoformat(),
            **({"remap_recommended": True} if overflow_new else {}),
        },
        completed_at=completed_at,
    )
    # The successor is findable from the preflight from mint time on,
    # so a crash mid-reconcile leaves an honest 'building' version.
    await repository.set_resulting_map(preflight.id, successor.id)

    ledger = await repository.copy_forward(
        base=app_map,
        successor=successor,
        changed_urls=changed_urls,
        missing_urls=missing_urls,
        new_pages=[
            {
                "canonical_url": entry["url"],
                "source_kinds": entry["source_kinds"],
                "fingerprint": result.page_fingerprints.get(entry["url"]),
                "render": result.tier2.get(entry["url"]),
            }
            for entry in scoped_new
        ],
        observed_at=completed_at,
    )
    for entry in overflow_new:
        result.deferred.append({"url": entry["url"], "reason": "new_page_cap"})

    # Changed pages: re-observed from the sweep's retained captures.
    # New pages: the scoped harvest visit. Both write under V+1 only.
    await persist_changed_pages(
        repository, successor, result, changed_urls, observed_at=completed_at
    )
    if scoped_new:
        await visit_new_pages(
            repository, successor, [entry["url"] for entry in scoped_new],
            observed_at=completed_at,
        )

    # Gates over the successor's own rows, then the release ceiling:
    # freshness restores currency, it does not manufacture trust.
    inventory_gate = compute_inventory_gate(
        await repository.page_status_counts(successor.id),
        overflow_count=int(successor.census_metrics.get("overflow_count", 0))
        if isinstance(successor.census_metrics, dict)
        else 0,
    )
    harvest_gate = None
    if changed_urls or scoped_new:
        harvest_gate = compute_harvest_gate(
            await repository.harvest_counts(successor.id)
        )
    await repository.apply_successor_gates(
        successor,
        release=successor_release(app_map, inventory_gate, harvest_gate),
        ledger=ledger,
    )

    # Scoped re-enrichment for the touched template groups only,
    # cap-accounted on the successor (doc 23 section 7.4).
    await enrich_touched(repository, successor, changed_urls, scoped_new)

    # Demotion last (section 7.5): active versions whose verified
    # fingerprint names a state the sweep proved changed, or a journey
    # crossing a missing page, go active -> suspect through Phase 3's
    # transition authority — never a direct lifecycle write here.
    demoted = await demote_skills(
        repository, successor, delta, observed_at=completed_at
    )
    if demoted:
        delta["skills_demoted"] = demoted
    return successor.id


_SCOPE_RANK = {None: 0, "inventory": 1, "harvest": 2}


def successor_release(base: Any, inventory_gate: Any, harvest_gate: Any) -> dict:
    """The successor's release, decided from the gates + the ceiling.

    The map's ``status`` is the census lifecycle's: it follows the
    inventory gate. The harvest gate, when re-observation ran, decides
    ``harvest_status`` and the release pair (its own contract already
    falls back to the inventory scope when harvest fails — a failed
    harvest never fails the map). The ceiling (doc 23 section 7.3)
    clamps a scope above the base version's on the inventory-only
    path: an inventory-only reconcile can never lift a version past
    its base, while a genuinely re-run harvest gate earns its own
    scope.
    """

    if inventory_gate.status == "failed":
        return {
            "status": "failed",
            "harvest_status": base.harvest_status,
            "release_state": "failed",
            "release_scope": None,
            "failure_code": inventory_gate.failure_code,
            "failure_message": inventory_gate.failure_message,
            "gate_metrics": inventory_gate.metrics(),
        }
    if harvest_gate is not None:
        return {
            "status": "ready",
            "harvest_status": harvest_gate.harvest_status,
            "release_state": harvest_gate.release_state,
            "release_scope": harvest_gate.release_scope,
            "failure_code": None,
            "failure_message": None,
            "gate_metrics": harvest_gate.metrics(),
        }
    release_scope = inventory_gate.release_scope
    if _SCOPE_RANK[release_scope] > _SCOPE_RANK[base.release_scope]:
        release_scope = base.release_scope
    return {
        "status": inventory_gate.status,
        "harvest_status": base.harvest_status,
        "release_state": inventory_gate.release_state,
        "release_scope": release_scope,
        "failure_code": None,
        "failure_message": None,
        "gate_metrics": inventory_gate.metrics(),
    }
