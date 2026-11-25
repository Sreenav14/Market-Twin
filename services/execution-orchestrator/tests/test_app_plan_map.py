"""Phase 1a section 10.2/10.3: map consumption in app_plan (T-P1..T-P7)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from markettwin_execution_orchestrator.browser import AllowedOrigin
from markettwin_execution_orchestrator.workflow import app_plan, run_executor

MAP_ID = "0c4b7f5e-0000-4000-8000-000000000001"


def _request(*, app_map=None):
    return run_executor.MarketTwinRunRequest(
        run_id=uuid4(), study_brief="Complete onboarding", target_snapshot={},
        start_url="https://app.test/",
        allowed_origins=(AllowedOrigin("https", "app.test", None),),
        run_kind="explore_test", unified_native=True,
        app_map=app_map,
    )


def _map_block(*, routes, pages=(), counts=None, built_at=None, version=3):
    return {"map_id": MAP_ID, "version_number": version,
            "release_state": "partial", "release_scope": "inventory",
            "built_at": built_at if built_at is not None else (
                datetime.now(timezone.utc) - timedelta(hours=2, minutes=30)
            ).isoformat(),
            "base_url": "https://app.test/", "routes": list(routes),
            "routes_truncated": False, "pages": list(pages),
            "counts": counts or {"expected": 0, "reachable": 0, "blocked_auth": 0,
                                 "blocked_wall": 0, "gone": 0}}


def _page(url, *, pattern="/x", requires_auth=False):
    return {"url": url, "effective_url": url, "pattern": pattern,
            "status": "fetch_ok", "requires_auth": requires_auth, "states": []}


@pytest.mark.asyncio
async def test_map_routes_win_over_prose_routes(monkeypatch):
    """T-P1: a map exists — the plan's routes come from the map,
    the plan is map_seeded, and no prose checks are generated."""
    block = _map_block(routes=["https://app.test/", "https://app.test/map-a",
                               "https://app.test/map-b"])
    plan = await app_plan.build_app_plan(_request(app_map=block))
    assert plan["route_source"] == "app_map"
    assert plan["status"] == "map_seeded"
    assert plan["routes"] == ["https://app.test/", "https://app.test/map-a",
                              "https://app.test/map-b"]
    assert "https://app.test/setup" not in plan["routes"]
    assert plan["map_id"] == MAP_ID
    assert plan["map_version"] == 3
    assert plan["checks"] == []


@pytest.mark.asyncio
async def test_map_routes_outside_allowed_origins_are_filtered(monkeypatch):
    """T-P2: a map route outside the allowlist is dropped by origin
    validation; the surviving route still seeds."""
    block = _map_block(routes=["https://app.test/inside",
                               "https://other.test/outside"])
    plan = await app_plan.build_app_plan(_request(app_map=block))
    assert plan["route_source"] == "app_map"
    assert plan["routes"] == ["https://app.test/", "https://app.test/inside"]


@pytest.mark.asyncio
async def test_unmapped_plans_keep_todays_behaviour(monkeypatch):
    """T-P3 (C9): without a map, the plan is start-only discovery —
    document knowledge no longer seeds routes or checks (R0), so a
    request behaves the same with or without legacy knowledge."""
    plan = await app_plan.build_app_plan(_request())
    assert plan["route_source"] == "start_only"
    assert plan["status"] == "discovery_only"
    assert plan["routes"] == ["https://app.test/"]
    assert plan["checks"] == []
    assert "map_id" not in plan


@pytest.mark.asyncio
async def test_empty_map_routes_do_not_seed(monkeypatch):
    """T-P4: an app_map whose routes list is empty does not seed —
    the plan is start-only discovery (the prose-regex fallback was
    retired with the legacy knowledge pipeline)."""
    plan = await app_plan.build_app_plan(_request(app_map=_map_block(routes=[])))
    assert plan["route_source"] == "start_only"
    assert plan["status"] == "discovery_only"
    assert plan["routes"] == ["https://app.test/"]
    assert "map_id" not in plan


def test_map_brief_renders_the_template_exactly():
    """T-P5: the brief is the section 10.3 template verbatim — counts
    from the snapshot block, patterns counted from its pages and
    sorted by page count, the login line present because one page
    requires auth."""
    built_at = (datetime.now(timezone.utc)
                - timedelta(hours=2, minutes=30)).isoformat()
    block = _map_block(
        routes=["https://app.test/"],
        pages=[_page("https://app.test/", pattern="/"),
               _page("https://app.test/a1", pattern="/a"),
               _page("https://app.test/a2", pattern="/a"),
               _page("https://app.test/login", pattern="/login",
                     requires_auth=True)],
        counts={"expected": 112, "reachable": 100, "blocked_auth": 5,
                "blocked_wall": 2, "gone": 3},
        built_at=built_at,
    )
    brief = app_plan.build_map_brief({}, SimpleNamespace(app_map=block))
    assert brief == "\n".join([
        "Application map (reference data; verify in browser):",
        f"Map: partial (inventory scope), built {built_at}, age 2h, staleness: current.",
        "Pages known: 112 — reachable 100, blocked by login 5, blocked by wall 2, gone 3.",
        "Route patterns: /a (2), / (1), /login (1)",
        "Journeys recorded: 0. Expectations from the map: 0 (map expectations arrive in Phase 2).",
        "Open conflicts: not tracked yet (Phase 2).",
        "Login: 1 pages require login; use the standard login handoff when a check needs them.",
        "Skills available: 0 (the skill library arrives in Phase 3).",
    ])


def test_map_brief_staleness_cap_and_overflow():
    """T-P6: staleness flips at the 7-day label boundary; 11 patterns
    render 10 plus the overflow count; an oversized pattern set is
    truncated on the patterns line only, inside the char budget."""
    def brief_for(**kwargs):
        return app_plan.build_map_brief(
            {}, SimpleNamespace(app_map=_map_block(routes=[], **kwargs)))

    stale = brief_for(built_at=(datetime.now(timezone.utc)
                                - timedelta(hours=169, minutes=30)).isoformat())
    assert "staleness: stale" in stale
    current = brief_for(built_at=(datetime.now(timezone.utc)
                                  - timedelta(hours=167, minutes=30)).isoformat())
    assert "staleness: current" in current

    pages = [_page(f"https://app.test/p{i}", pattern=f"/p{i}") for i in range(11)]
    brief = brief_for(pages=pages)
    assert "+1 more patterns" in brief
    assert brief.count("(1)") == 10

    long_pages = [_page(f"https://app.test/q{i}",
                        pattern="/" + "segment-" + "x" * 90 + f"-{i}")
                  for i in range(60)]
    brief = brief_for(pages=long_pages)
    assert len(brief) <= app_plan.BRIEF_MAX_CHARS
    assert "more patterns" in brief


@pytest.mark.asyncio
async def test_prepare_app_plan_appends_the_map_brief_only_for_mapped(monkeypatch):
    """T-P7 (decision D5): a map-seeded plan appends the map brief
    instead of the checks JSON; a plan whose map seeds no routes
    appends the checks JSON (with empty checks — the prose checklist
    was retired with the legacy knowledge pipeline)."""
    monkeypatch.setattr(app_plan, "RunEventRepository",
                        lambda _: SimpleNamespace(create=AsyncMock()))

    async def prepare(request):
        run = SimpleNamespace(configuration_snapshot={})
        session = SimpleNamespace(get=AsyncMock(return_value=run),
                                  commit=AsyncMock())
        prepared = await app_plan.prepare_app_plan(request, session)
        return prepared, run

    block = _map_block(routes=["https://app.test/", "https://app.test/map-a"])
    prepared, run = await prepare(_request(app_map=block))
    assert "Application map (reference data; verify in browser):" in prepared.study_brief
    assert "Application expectations" not in prepared.study_brief
    assert prepared.app_plan["route_source"] == "app_map"
    assert run.configuration_snapshot["app_plan"]["status"] == "map_seeded"

    prepared, _ = await prepare(_request(app_map=_map_block(routes=[])))
    assert "Application expectations (reference data; verify in browser):" in prepared.study_brief
    assert "Application map (reference data" not in prepared.study_brief
    assert prepared.app_plan["route_source"] == "start_only"


def test_map_brief_renders_1b_journeys_and_skills():
    """T-P8 (doc 16 section 11.2): a 1b snapshot block — journeys and
    skills keys present — renders the real counts, the first journey's
    name, and up to three skill lines, inside the char budget; the
    withheld count is never mentioned."""
    built_at = (datetime.now(timezone.utc)
                - timedelta(hours=1)).isoformat()
    block = _map_block(
        routes=["https://app.test/"],
        pages=[_page("https://app.test/", pattern="/")],
        counts={"expected": 4, "reachable": 4, "blocked_auth": 0,
                "blocked_wall": 0, "gone": 0, "expectations": 0},
        built_at=built_at,
    )
    block["journeys"] = [{
        "name": "Reach get-a-demo", "intent": "book a demo",
        "selection": "rule", "terminal_url": "https://app.test/get-a-demo",
        "steps": [{"page_url": "https://app.test/", "role": "link",
                   "name": "Get a demo"}],
    }]
    block["skills"] = [{
        "name": "reach-get-a-demo",
        "description": "Use when a run must book a demo on App. "
                       "Verified against map v3.",
        "definition": {}, "skill_version_id": "v1",
    }]
    block["skills_withheld"] = 2
    brief = app_plan.build_map_brief({}, SimpleNamespace(app_map=block))
    assert "Journeys recorded: 1." in brief
    assert "Journey: Reach get-a-demo" in brief
    assert ("Expectations from the map: 0 "
            "(map expectations arrive in Phase 2).") in brief
    assert "Skills available: 1." in brief
    assert ("Skill: reach-get-a-demo — Use when a run must book a demo "
            "on App. Verified against map v3.") in brief
    assert "withheld" not in brief
    assert "arrives in Phase 3" not in brief
    assert len(brief) <= app_plan.BRIEF_MAX_CHARS


def test_map_brief_renders_the_freshness_block():
    """T-P9 (doc 23 section 8.2): a snapshot block carrying the
    freshness key briefs the freshness block — the Map line drops its
    age/staleness segment, the three freshness lines follow the head,
    and a never-preflighted map renders the 'never' form with no
    outcome line."""
    built_at = (datetime.now(timezone.utc)
                - timedelta(days=2, hours=3, minutes=30)).isoformat()
    block = _map_block(
        routes=["https://app.test/"],
        counts={"expected": 12, "reachable": 10, "blocked_auth": 1,
                "blocked_wall": 0, "gone": 1},
        built_at=built_at,
    )
    block["freshness"] = {
        "state": "current",
        "map_built_at": built_at,
        "map_age_hours": 51,
        "last_preflight_at": "2026-11-14T09:15:00+00:00",
        "last_preflight_id": "preflight-1",
        "outcome_counts": {"present": 9, "changed": 1, "unreachable": 1,
                           "missing": 1, "new": 0},
        "pinned_via_preflight": True,
        "preflight_status": "completed",
        "ttl_trust": "not_applicable",
    }
    brief = app_plan.build_map_brief({}, SimpleNamespace(app_map=block))
    lines = brief.split("\n")
    assert lines[1] == f"Map: partial (inventory scope), built {built_at}."
    assert lines[3] == (
        "Freshness: current; map age 2d 3h; "
        "last preflight 2026-11-14T09:15:00+00:00."
    )
    assert lines[4] == (
        "Preflight outcome: 9 present, 1 changed, 1 unreachable, "
        "1 missing, 0 new (of 12 expected)."
    )
    assert lines[5] == "Trust for this run: preflight-checked before this run"

    block["freshness"] = {
        "state": "unknown",
        "map_built_at": built_at,
        "map_age_hours": 51,
        "last_preflight_at": None,
        "last_preflight_id": None,
        "outcome_counts": {"present": 0, "changed": 0, "unreachable": 0,
                           "missing": 0, "new": 0},
        "pinned_via_preflight": False,
        "preflight_status": "not_required",
        "ttl_trust": "within",
    }
    brief = app_plan.build_map_brief({}, SimpleNamespace(app_map=block))
    assert "last preflight never." in brief
    assert "Preflight outcome:" not in brief
    assert (
        "Trust for this run: within TTL (14d) — not preflighted "
        "for this run kind" in brief
    )


def test_map_brief_freshness_survives_truncation():
    """T-P10 (doc 23 section 8.2): the freshness block lives in the
    brief's head, so the patterns-then-details truncation can never
    cut it — an over-budget brief still carries all three lines
    whole."""
    built_at = (datetime.now(timezone.utc)
                - timedelta(hours=5, minutes=30)).isoformat()
    long_pages = [_page(f"https://app.test/q{i}",
                        pattern="/" + "segment-" + "x" * 90 + f"-{i}")
                  for i in range(60)]
    block = _map_block(routes=[], pages=long_pages, built_at=built_at)
    block["freshness"] = {
        "state": "stale",
        "map_built_at": built_at,
        "map_age_hours": 5,
        "last_preflight_at": "2026-11-14T09:15:00+00:00",
        "last_preflight_id": "preflight-1",
        "outcome_counts": {"present": 3, "changed": 2, "unreachable": 0,
                           "missing": 1, "new": 4},
        "pinned_via_preflight": False,
        "preflight_status": "timed_out",
        "ttl_trust": "not_applicable",
    }
    brief = app_plan.build_map_brief({}, SimpleNamespace(app_map=block))
    assert len(brief) <= app_plan.BRIEF_MAX_CHARS
    assert "Freshness: stale; map age 0d 5h;" in brief
    assert (
        "Preflight outcome: 3 present, 2 changed, 0 unreachable, "
        "1 missing, 4 new (of 0 expected)." in brief
    )
    assert (
        "Trust for this run: preflight timed out — freshness unknown"
        in brief
    )
