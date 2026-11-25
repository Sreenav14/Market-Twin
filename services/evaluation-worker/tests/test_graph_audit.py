"""Doc 21 section 11: graph audit tests (T-GA1..T-GA5)."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from markettwin_database.models.knowledge import (
    MapConflict,
    MapElement,
    MapExpectation,
    MapJourney,
    MapPage,
    MapPageState,
)
from markettwin_evaluation_worker import graph_audit

NOW = datetime(2026, 11, 14, tzinfo=UTC)
WS, APP, TGT, MAP = uuid4(), uuid4(), uuid4(), uuid4()


def _expectation(**overrides):
    values = dict(
        id=uuid4(),
        workspace_id=WS,
        application_id=APP,
        target_id=TGT,
        app_map_id=MAP,
        subject_kind="element",
        subject_id=uuid4(),
        statement="Something holds",
        oracle_source="documentation",
        status="unverified",
        source_ref="e:0",
        confidence="high",
        assertion={
            "kind": "element_state",
            "subject": {},
            "params": {"oracle": "visible"},
        },
        assertion_origin="deterministic",
        created_at=NOW,
        updated_at=NOW,
    )
    values.update(overrides)
    return MapExpectation(**values)


def _element(**overrides):
    values = dict(
        id=uuid4(),
        workspace_id=WS,
        application_id=APP,
        target_id=TGT,
        app_map_id=MAP,
        map_page_id=uuid4(),
        map_page_state_id=uuid4(),
        role="button",
        name="Buy",
        locators=[],
        actionability="click",
        safety_class="read_only",
        source="crawl",
        confidence="high",
        last_verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    values.update(overrides)
    return MapElement(**values)


def _page(**overrides):
    values = dict(
        id=uuid4(),
        workspace_id=WS,
        application_id=APP,
        target_id=TGT,
        app_map_id=MAP,
        canonical_url="https://app.example.com/",
        route_pattern="/",
        source_kinds=["sitemap"],
        crawl_status="visited",
        source="census",
        confidence="high",
        purpose="Buy things",
        enriched_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    values.update(overrides)
    return MapPage(**values)


def _audit(**kwargs):
    base = dict(
        expectations=[],
        conflicts=[],
        events=[],
        elements=[],
        pages=[],
        journeys=[],
        states=[],
        cited_expectation_ids=set(),
        now=NOW,
    )
    base.update(kwargs)
    return graph_audit.audit_rows(**base)


def test_t_ga1_audit_imports_no_writers():
    tree = ast.parse(Path(graph_audit.__file__).read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    forbidden = [
        module
        for module in modules
        if "expectations" in module
        or "control_api" in module
        or "control-api" in module
        or "repository" in module
    ]
    assert forbidden == []


def test_t_ga2_orphans_and_staleness():
    element = _element(last_verified_at=NOW - timedelta(days=40))
    orphan = _expectation()  # subject not among the graph rows
    checks, findings = _audit(
        expectations=[orphan],
        elements=[element],
        pages=[_page(purpose=None)],
    )
    assert checks["orphaned"] == 1
    assert checks["stale_elements"] == 1
    assert checks["stale_purposes"] == 1


def test_t_ga3_taxonomy_violations_are_critical():
    bad = _expectation(
        subject_id=_element().id,
        promoted_by="owner-1",
        status="unverified",  # promoted but never owner-confirmed
    )
    element = _element()
    bad.subject_id = element.id
    checks, findings = _audit(expectations=[bad], elements=[element])
    assert checks["taxonomy_violations"] >= 1
    assert any(
        finding["check"] == "A3" and finding["severity"] == "critical"
        for finding in findings
    )


def test_t_ga4_cited_ineligible_is_critical():
    element = _element()
    observation = _expectation(
        subject_id=element.id, oracle_source="observation"
    )
    doc = _expectation(subject_id=element.id)
    checks, findings = _audit(
        expectations=[observation, doc],
        elements=[element],
        cited_expectation_ids={str(observation.id), str(doc.id)},
    )
    assert checks["cited_ineligible"] == 1
    assert any(finding["check"] == "A4" for finding in findings)


def test_t_ga5_conflict_staleness_and_findings_cap():
    element = _element()
    conflict = MapConflict(
        id=uuid4(),
        workspace_id=WS,
        application_id=APP,
        target_id=TGT,
        app_map_id=MAP,
        expectation_id=uuid4(),
        observed_behaviour="differs",
        evidence_refs=[],
        status="open",
        conflict_kind="statement_vs_observation",
        detection_source="grounding",
        created_at=NOW - timedelta(days=45),
        updated_at=NOW,
    )
    orphans = [_expectation() for _ in range(250)]
    checks, findings = _audit(
        expectations=orphans, conflicts=[conflict], elements=[element]
    )
    assert checks["stale_conflicts"] == 1
    assert len(findings) == graph_audit.AUDIT_FINDINGS_CAP
    assert checks["findings_overflow"] > 0
