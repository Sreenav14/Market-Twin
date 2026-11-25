"""Read-only graph audits (doc 21 section 11).

The evaluation worker's audits A1-A6 over the knowledge graph. The
audit is INSERT-only into graph_audit_reports: it never updates,
promotes, resolves or deletes a graph record (T-GA1 pins the import
surface — no writer modules are imported here). Eligibility is
re-proven with the ONE shared implementation (spec C3), never a
local copy.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from markettwin_database.models import RunEvent
from markettwin_database.models.knowledge import (
    AppMap,
    GraphAuditReport,
    MapConflict,
    MapElement,
    MapExpectation,
    MapExpectationEvent,
    MapJourney,
    MapPage,
    MapPageState,
)
from markettwin_shared.app_map_common import (
    ORACLE_SOURCES,
    expectation_verdict_eligible,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

# Doc 21 section 16 settings, as module constants.
AUDIT_STALE_ELEMENT_DAYS = 14
AUDIT_STALE_PURPOSE_DAYS = 30
AUDIT_CONFLICT_STALE_DAYS = 30  # [J]
AUDIT_FINDINGS_CAP = 200
AUDIT_INTERVAL_SECONDS = 6 * 3600

_KNOWN_STATUSES = ("unverified", "replay-verified", "owner-confirmed", "conflicted")


def _fingerprint(rows: list) -> str:
    """A6's self-proof hash over the graph rows the audit read."""
    parts = sorted(
        f"{type(row).__name__}:{row.id}:{row.updated_at or row.created_at}"
        for row in rows
    )
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _finding(findings: list, check: str, severity: str, detail: str, ref: str) -> None:
    findings.append(
        {"check": check, "severity": severity, "detail": detail, "ref": ref}
    )


def audit_rows(
    *,
    expectations: list[MapExpectation],
    conflicts: list[MapConflict],
    events: list[MapExpectationEvent],
    elements: list[MapElement],
    pages: list[MapPage],
    journeys: list[MapJourney],
    states: list[MapPageState],
    cited_expectation_ids: set[str],
    now: datetime,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """A1-A5 over already-loaded rows (pure; A6 wraps this)."""
    findings: list[dict[str, object]] = []
    checks: dict[str, object] = {}

    subject_ids = (
        {row.id for row in elements}
        | {row.id for row in pages}
        | {row.id for row in journeys}
        | {row.id for row in states}
    )
    expectation_ids = {row.id for row in expectations}

    # A1: orphaned records.
    orphaned = 0
    for row in expectations:
        if row.subject_id not in subject_ids:
            orphaned += 1
            _finding(findings, "A1", "warning", "Expectation subject is missing from the graph.", str(row.id))
    for row in conflicts:
        if row.expectation_id not in expectation_ids:
            orphaned += 1
            _finding(findings, "A1", "warning", "Conflict's expectation is missing.", str(row.id))
    state_ids = {row.id for row in states}
    for journey in journeys:
        if journey.success_state_id not in state_ids:
            orphaned += 1
            _finding(findings, "A1", "warning", "Journey's success state is missing.", str(journey.id))
    checks["orphaned"] = orphaned

    # A2: stale elements and purposes.
    stale_elements = 0
    for element in elements:
        verified = element.last_verified_at or element.created_at
        if verified is not None and now - verified > timedelta(days=AUDIT_STALE_ELEMENT_DAYS):
            stale_elements += 1
            _finding(findings, "A2", "info", f"Element not verified for over {AUDIT_STALE_ELEMENT_DAYS} days.", str(element.id))
    stale_purposes = 0
    for page in pages:
        enriched = page.enriched_at
        if page.purpose is None or (
            enriched is not None
            and now - enriched > timedelta(days=AUDIT_STALE_PURPOSE_DAYS)
        ):
            stale_purposes += 1
            _finding(findings, "A2", "info", f"Page purpose missing or older than {AUDIT_STALE_PURPOSE_DAYS} days.", str(page.id))
    checks["stale_elements"] = stale_elements
    checks["stale_purposes"] = stale_purposes

    # A3: taxonomy violations.
    violations = 0
    promoted_ids = {
        event.expectation_id for event in events if event.event_type == "promoted"
    }
    checked_ids = {
        event.expectation_id for event in events if event.event_type == "checked"
    }
    for row in expectations:
        problems = []
        if row.oracle_source not in ORACLE_SOURCES:
            problems.append(f"invalid oracle_source {row.oracle_source!r}")
        if row.status not in _KNOWN_STATUSES:
            problems.append(f"invalid status {row.status!r}")
        if row.promoted_by is not None and row.status != "owner-confirmed":
            problems.append("promoted_by set without owner-confirmed status")
        record = {
            "oracle_source": row.oracle_source,
            "status": row.status,
            "superseded_by_id": row.superseded_by_id,
            "assertion": row.assertion,
            "assertion_origin": row.assertion_origin,
            "promoted_by": row.promoted_by,
        }
        if (
            row.assertion_origin == "model-drafted"
            and expectation_verdict_eligible(record)
            and row.promoted_by is None
        ):
            problems.append("model-drafted assertion is verdict-eligible without promotion")
        if row.id in checked_ids and row.id not in promoted_ids and not expectation_verdict_eligible(record):
            problems.append("'checked' event on a record that is not verdict-eligible")
        for problem in problems:
            violations += 1
            _finding(findings, "A3", "critical", problem, str(row.id))
    checks["taxonomy_violations"] = violations

    # A4: eligibility re-proof — any Board-cited expectation that the
    # shared rule calls ineligible is a critical finding.
    cited_ineligible = 0
    by_id = {row.id: row for row in expectations}
    for cited in cited_expectation_ids:
        try:
            row = by_id.get(UUID(cited))
        except (ValueError, TypeError):
            continue
        if row is None:
            continue
        record = {
            "oracle_source": row.oracle_source,
            "status": row.status,
            "superseded_by_id": row.superseded_by_id,
            "assertion": row.assertion,
            "assertion_origin": row.assertion_origin,
            "promoted_by": row.promoted_by,
        }
        if not expectation_verdict_eligible(record):
            cited_ineligible += 1
            _finding(findings, "A4", "critical", "Board cited an expectation the eligibility rule rejects.", str(row.id))
    checks["cited_ineligible"] = cited_ineligible

    # A5: conflict staleness.
    stale_conflicts = 0
    for row in conflicts:
        if (
            row.status == "open"
            and row.created_at is not None
            and now - row.created_at > timedelta(days=AUDIT_CONFLICT_STALE_DAYS)
        ):
            stale_conflicts += 1
            _finding(findings, "A5", "warning", f"Open conflict older than {AUDIT_CONFLICT_STALE_DAYS} days.", str(row.id))
    checks["stale_conflicts"] = stale_conflicts
    # Section 11: findings are capped in the report, overflow counted.
    checks["findings_overflow"] = max(0, len(findings) - AUDIT_FINDINGS_CAP)
    return checks, findings[:AUDIT_FINDINGS_CAP]


async def _load(session: AsyncSession, model: Any, map_id: UUID) -> list:
    result = await session.execute(select(model).where(model.app_map_id == map_id))
    return list(result.scalars().all())


async def audit_map(
    session_factory: SessionFactory,
    app_map: AppMap,
    *,
    audit_kind: str = "scheduled",
    now: datetime | None = None,
) -> GraphAuditReport:
    """Run A1-A6 for one map and INSERT the report (the only write)."""
    now = now or datetime.now(UTC)
    async with session_factory() as session:
        expectations = await _load(session, MapExpectation, app_map.id)
        conflicts = await _load(session, MapConflict, app_map.id)
        events = await _load(session, MapExpectationEvent, app_map.id)
        elements = await _load(session, MapElement, app_map.id)
        pages = await _load(session, MapPage, app_map.id)
        journeys = await _load(session, MapJourney, app_map.id)
        states = await _load(session, MapPageState, app_map.id)
        cited: set[str] = set()
        result = await session.execute(
            select(RunEvent.payload).where(
                RunEvent.event_type == "board.item.result"
            )
        )
        for payload in result.scalars().all():
            if isinstance(payload, dict) and payload.get("expectation_id"):
                cited.add(str(payload["expectation_id"]))
        rows = expectations + conflicts + elements + pages + journeys + states
        before = _fingerprint(rows)
        checks, findings = audit_rows(
            expectations=expectations,
            conflicts=conflicts,
            events=events,
            elements=elements,
            pages=pages,
            journeys=journeys,
            states=states,
            cited_expectation_ids=cited,
            now=now,
        )
        after = _fingerprint(rows)
        checks["fingerprint_stable"] = before == after
        if before != after:
            _finding(findings, "A6", "critical", "Graph fingerprint changed during a read-only audit.", str(app_map.id))
        report = GraphAuditReport(
            id=uuid4(),
            workspace_id=app_map.workspace_id,
            application_id=app_map.application_id,
            target_id=app_map.target_id,
            app_map_id=app_map.id,
            audit_kind=audit_kind,
            checks=checks,
            findings=findings,
            graph_fingerprint=before,
        )
        session.add(report)
        await session.commit()
        return report


async def run_scheduled_audit(
    session_factory: SessionFactory,
) -> list[GraphAuditReport]:
    """Audit every map once (the poll loop's cadence entry point)."""
    async with session_factory() as session:
        result = await session.execute(select(AppMap))
        app_maps = list(result.scalars().all())
    reports = []
    for app_map in app_maps:
        reports.append(
            await audit_map(session_factory, app_map, audit_kind="scheduled")
        )
    return reports
