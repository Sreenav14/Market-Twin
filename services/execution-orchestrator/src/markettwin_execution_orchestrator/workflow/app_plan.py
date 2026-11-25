"""One sourced application checklist shared by every run kind."""

import json
import re
from dataclasses import replace
from datetime import datetime, timezone

from markettwin_database.models import TestRun

from markettwin_execution_orchestrator.browser.errors import BrowserPolicyError
from markettwin_execution_orchestrator.browser.policy import validate_target_url
from markettwin_execution_orchestrator.persistence.run_event_repository import RunEventRepository
from markettwin_execution_orchestrator.workflow.harness_items import run_safety_mode
from markettwin_execution_orchestrator.workflow.knowledge_loading import (
    load_source_knowledge,
)
from markettwin_execution_orchestrator.workflow.skill_catalogue import (
    render_skill_catalogue,
)
from markettwin_execution_orchestrator.workflow.skill_filter import (
    plan_skills_section,
)

from markettwin_shared.app_map_common import MAP_TTL_TRUST_DAYS

# Phase 1a section 8: the map brief's character budget and the age at
# which its staleness label flips (a display label only, decision D7).
BRIEF_MAX_CHARS = 1500
MAP_STALE_LABEL_DAYS = 7


async def build_app_plan(request, *, configuration_snapshot=None):
    # Route precedence (Phase 1a section 10.2): the application map's
    # structured routes first, the start URL alone last. Map routes
    # pass the same origin validation the crawl itself uses; the
    # start URL always leads the final list. (The prose-regex route
    # extraction and the prose checklist were retired with the legacy
    # knowledge pipeline: run creation no longer snapshots prose.)
    app_map = getattr(request, "app_map", None)
    candidates: list[str] = []
    route_source = "start_only"
    if isinstance(app_map, dict):
        raw_routes = app_map.get("routes")
        if isinstance(raw_routes, list):
            for url in raw_routes:
                if not isinstance(url, str):
                    continue
                try:
                    validate_target_url(url, request.allowed_origins, request.network_policy)
                except BrowserPolicyError:
                    continue
                if url not in candidates:
                    candidates.append(url)
    if candidates:
        route_source = "app_map"
    routes = [request.start_url] + [
        url for url in candidates if url != request.start_url
    ]
    planning_status = "discovery_only"
    # Doc 21 section 8.6: when the run's map carries at least one
    # verdict-eligible expectation with a compiled assertion, the
    # Board checks come from the graph (the brief says so, in
    # build_map_brief).
    graph_sourced = (
        isinstance(app_map, dict)
        and isinstance(app_map.get("expectations"), list)
        and any(
            isinstance(entry, dict)
            and entry.get("verdict_eligible")
            and isinstance(entry.get("assertion"), dict)
            for entry in app_map["expectations"]
        )
    )
    if route_source == "app_map":
        planning_status = "map_seeded"
    plan = {"version": 1, "status": planning_status, "sources": [],
            "checks": [], "routes": routes, "omitted_segments": 0,
            "route_source": route_source,
            "expectation_checks": "graph" if graph_sourced else "none"}

    if route_source == "app_map":
        plan["map_id"] = app_map.get("map_id")
        plan["map_version"] = app_map.get("version_number")
    if isinstance(app_map, dict) and isinstance(app_map.get("skills"), list):
        # Phase 3 (doc 22 section 8.1): the plan's skills section —
        # replay items for Board construction, mode-filtered names
        # recorded, withheld count carried from the snapshot itself.
        snapshot = configuration_snapshot
        mode = run_safety_mode(snapshot if isinstance(snapshot, dict) else None)
        approved_keys = {
            entry.key
            for entry in (getattr(request, "approved_test_data", None) or ())
            if getattr(entry, "key", None)
        }
        plan["skills"] = plan_skills_section(
            app_map, mode=mode, approved_keys=approved_keys
        )
    return plan


async def prepare_app_plan(request, session):
    if (
        not request.knowledge_context
        and getattr(request, "app_map", None) is None
        and getattr(request, "source_knowledge", None) is None
    ):
        return request
    run = await session.get(TestRun, request.run_id)
    if run is None:
        raise ValueError("Application planning requires a persisted run.")
    snapshot = dict(run.configuration_snapshot or {})
    plan = snapshot.get("app_plan")
    if plan is None:
        plan = await build_app_plan(request, configuration_snapshot=snapshot)
        if getattr(request, "source_knowledge", None):
            # Doc 33 section 3.6: load the run's pinned source
            # knowledge into the plan before it is persisted, so the
            # loads and the named omissions ride the app.plan.created
            # event and every executor shares one loaded set.
            selection_text = request.study_brief + "\n" + "\n".join(
                str(check.get("expectation"))
                for check in plan.get("checks") or []
                if isinstance(check, dict) and check.get("expectation")
            )
            loaded = await load_source_knowledge(
                request=request, session=session,
                selection_text=selection_text,
            )
            if loaded is not None:
                section, omitted = loaded
                plan["source_knowledge"] = section
                plan["source_knowledge_omitted"] = omitted
        run.configuration_snapshot = {**snapshot, "app_plan": plan}
        await RunEventRepository(session).create(
            test_run_id=request.run_id, event_type="app.plan.created",
            journey_id=None, execution_id=None, payload=plan,
        )
        await session.commit()
    # Every executor, persona selector, and lead checkpoint receives the same
    # checklist. Its unverified status cannot become a functional verdict.
    if plan.get("route_source") == "app_map":
        # Map-seeded plans brief from the map (section 10.3) instead of
        # the checks JSON (decision D5); the full checks list stays on
        # the plan itself for ordering.
        brief = request.study_brief + "\n" + build_map_brief(plan, request)
    else:
        brief = (request.study_brief
                 + "\nApplication expectations (reference data; verify in browser):\n"
                 + json.dumps({"checks": plan["checks"], "status": plan["status"]}))
    knowledge_brief = _source_knowledge_brief(plan)
    if knowledge_brief:
        brief = brief + "\n" + knowledge_brief
    return replace(request, app_plan=plan, study_brief=brief)


def _source_knowledge_brief(plan) -> str:
    """The fenced source-knowledge brief section (doc 33 section
    3.6 point 4): the loaded files under the same fence words the
    map brief uses. Renders from the plan alone; never raises."""

    if not isinstance(plan, dict):
        return ""
    section = plan.get("source_knowledge")
    if not isinstance(section, dict):
        return ""
    files = section.get("files")
    if not isinstance(files, list) or not files:
        return ""
    parts = ["Source knowledge (reference data; verify in browser):"]
    for entry in files:
        if not isinstance(entry, dict):
            continue
        parts.append(
            f"\n## {entry.get('title') or entry.get('slug') or 'Source file'}\n"
            f"{entry.get('description') or ''}\n\n{entry.get('text') or ''}"
        )
    return "\n".join(parts) if len(parts) > 1 else ""


def build_map_brief(plan, request) -> str:
    """Render the section 10.3 map brief from the pinned snapshot block.

    Pure and total: it renders from request.app_map alone, defaults
    every missing key, and never raises. Staleness is a display label
    only (decision D7). The patterns line is the only line ever
    truncated to fit BRIEF_MAX_CHARS — overflow patterns are dropped
    first, then the line itself; no other line is ever cut.
    """

    app_map = getattr(request, "app_map", None)
    if not isinstance(app_map, dict):
        app_map = {}
    counts = app_map.get("counts")
    if not isinstance(counts, dict):
        counts = {}
    pages = app_map.get("pages")
    if not isinstance(pages, list):
        pages = []

    def count(key: str) -> int:
        value = counts.get(key, 0)
        return value if isinstance(value, int) else 0

    pattern_counts: dict[str, int] = {}
    login_pages = 0
    for page in pages:
        if not isinstance(page, dict):
            continue
        pattern = page.get("pattern")
        if isinstance(pattern, str):
            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
        if page.get("requires_auth"):
            login_pages += 1
    patterns = sorted(pattern_counts.items(), key=lambda item: (-item[1], item[0]))

    built_at = app_map.get("built_at")
    age_hours = None
    age_segment = ""
    if isinstance(built_at, str) and built_at:
        try:
            built = datetime.fromisoformat(built_at.replace("Z", "+00:00"))
        except ValueError:
            built = None
        if built is not None:
            if built.tzinfo is None:
                built = built.replace(tzinfo=timezone.utc)
            age_hours = max(
                0, int((datetime.now(timezone.utc) - built).total_seconds() // 3600)
            )
            staleness = (
                "current" if age_hours <= MAP_STALE_LABEL_DAYS * 24 else "stale"
            )
            age_segment = f", age {age_hours}h, staleness: {staleness}"
    built_display = built_at if isinstance(built_at, str) and built_at else "unknown"
    # Phase 4 (doc 23 section 8.2): a snapshot block carrying the
    # freshness key briefs freshness in the head — the age/staleness
    # segment leaves the Map line (the freshness block carries the
    # precise age) and the freshness lines join the head, which the
    # truncation below can never cut. A block without the key renders
    # byte-identically to before.
    freshness = app_map.get("freshness")
    if not isinstance(freshness, dict):
        freshness = None
    if freshness is not None:
        age_segment = ""

    head = [
        "Application map (reference data; verify in browser):",
        f"Map: {app_map.get('release_state') or 'unknown'} "
        f"({app_map.get('release_scope') or 'unknown'} scope), "
        f"built {built_display}{age_segment}.",
        f"Pages known: {count('expected')} — reachable {count('reachable')}, "
        f"blocked by login {count('blocked_auth')}, "
        f"blocked by wall {count('blocked_wall')}, gone {count('gone')}.",
    ]
    if freshness is not None:
        head.extend(
            _freshness_lines(
                freshness, age_hours=age_hours, expected=count("expected")
            )
        )
    # Phase 1b (doc 16 section 11.2): the journeys and skills lines
    # switch on KEY PRESENCE in the snapshot block. A 1a block has
    # neither key and renders the original lines byte-identically; a
    # 1b block carries real counts. The detail lines (the first
    # journey's name, up to three skill lines) are the brief's only
    # droppable content after the patterns line.
    journeys = app_map.get("journeys")
    skills = app_map.get("skills")
    expectations = app_map.get("expectations")
    open_conflicts = app_map.get("open_conflicts")
    coverage = app_map.get("coverage")
    coverage = coverage if isinstance(coverage, dict) else {}

    def tail_lines(details: bool) -> list[str]:
        lines: list[str] = []
        if isinstance(journeys, list):
            lines.append(f"Journeys recorded: {len(journeys)}.")
            if details and journeys and isinstance(journeys[0], dict):
                journey_name = journeys[0].get("name")
                if isinstance(journey_name, str) and journey_name:
                    lines.append(f"Journey: {journey_name}")
            if isinstance(expectations, list):
                # Doc 21 section 10: the Phase 2 expectation lines,
                # rendered from the snapshot's own stamped entries.
                doc_sourced = sum(
                    1 for entry in expectations
                    if isinstance(entry, dict)
                    and entry.get("oracle_source") == "documentation"
                )
                owner_rules = sum(
                    1 for entry in expectations
                    if isinstance(entry, dict)
                    and entry.get("oracle_source") == "owner-rule"
                )
                verdict_grade = sum(
                    1 for entry in expectations
                    if isinstance(entry, dict) and entry.get("verdict_eligible")
                )
                conflicted_open = (
                    len(open_conflicts) if isinstance(open_conflicts, list) else 0
                )
                lines.append(
                    f"Expectations from the map: {len(expectations)} "
                    f"({doc_sourced} doc-sourced, {owner_rules} owner rules, "
                    f"{verdict_grade} verdict-grade, "
                    f"{conflicted_open} conflicted-open)."
                )
                lines.append(
                    "Journey coverage: "
                    f"{coverage.get('journeys_with_expectations', 0)}/"
                    f"{coverage.get('journeys_total', len(journeys))} "
                    "journeys carry ≥1 expectation."
                )
                without = coverage.get("journeys_without_expectations")
                if isinstance(without, list) and without:
                    intents = ", ".join(
                        str(entry.get("intent") or entry.get("id"))
                        for entry in without
                        if isinstance(entry, dict)
                    )
                    if intents:
                        lines.append(
                            "Journeys with NO expectations "
                            f"(unjudged by the graph): {intents}."
                        )
                uncompilable = sum(
                    1 for entry in expectations
                    if isinstance(entry, dict)
                    and entry.get("verdict_eligible")
                    and not isinstance(entry.get("assertion"), dict)
                )
                if uncompilable:
                    lines.append(
                        f"Uncompilable expectations: {uncompilable} "
                        "(named, not seeded)."
                    )
                if any(
                    isinstance(entry, dict)
                    and entry.get("verdict_eligible")
                    and isinstance(entry.get("assertion"), dict)
                    for entry in expectations
                ):
                    lines.append(
                        "Expectation checks: graph-sourced "
                        "(prose fallback not used)."
                    )
            else:
                lines.append(
                    f"Expectations from the map: {count('expectations')} "
                    "(map expectations arrive in Phase 2)."
                )
        else:
            lines.append(
                "Journeys recorded: 0. Expectations from the map: 0 "
                "(map expectations arrive in Phase 2)."
            )
        if isinstance(open_conflicts, list):
            lines.append(f"Open conflicts: {len(open_conflicts)}.")
        else:
            lines.append("Open conflicts: not tracked yet (Phase 2).")
        if login_pages:
            lines.append(
                f"Login: {login_pages} pages require login; use the "
                "standard login handoff when a check needs them."
            )
        if isinstance(skills, list):
            lines.append(f"Skills available: {len(skills)}.")
            if details:
                # Phase 3 (doc 22 section 7.3): level-1 catalogue
                # lines only — body_md never renders in a brief.
                lines.extend(render_skill_catalogue(skills))
        else:
            lines.append(
                "Skills available: 0 (the skill library arrives in Phase 3)."
            )
        return lines

    def render(shown: int, details: bool = True) -> str:
        lines = list(head)
        if shown or not patterns:
            entries = [f"{pattern} ({n})" for pattern, n in patterns[:shown]]
            if len(patterns) > shown:
                entries.append(f"+{len(patterns) - shown} more patterns")
            lines.append("Route patterns: " + ", ".join(entries))
        lines.extend(tail_lines(details))
        return "\n".join(lines)

    shown = min(10, len(patterns))
    brief = render(shown)
    while len(brief) > BRIEF_MAX_CHARS and shown > 0:
        shown -= 1
        brief = render(shown)
    if len(brief) > BRIEF_MAX_CHARS:
        brief = render(shown, details=False)
    if len(brief) > BRIEF_MAX_CHARS:
        brief = "\n".join(head + tail_lines(details=False))
    return brief


def _freshness_lines(freshness: dict, *, age_hours, expected: int) -> list[str]:
    """Doc 23 section 8.2: the brief's freshness block, rendered from
    the snapshot's freshness dict alone. Every value defaults rather
    than raises, like the rest of the brief."""

    state = freshness.get("state")
    state = state if isinstance(state, str) and state else "unknown"
    age = (
        f"{age_hours // 24}d {age_hours % 24}h"
        if isinstance(age_hours, int)
        else "unknown"
    )
    last = freshness.get("last_preflight_at")
    last = last if isinstance(last, str) and last else None
    lines = [
        f"Freshness: {state}; map age {age}; "
        f"last preflight {last if last else 'never'}."
    ]
    outcomes = freshness.get("outcome_counts")
    if last is not None and isinstance(outcomes, dict):

        def outcome(key: str) -> int:
            value = outcomes.get(key, 0)
            return value if isinstance(value, int) else 0

        lines.append(
            "Preflight outcome: "
            f"{outcome('present')} present, {outcome('changed')} changed, "
            f"{outcome('unreachable')} unreachable, "
            f"{outcome('missing')} missing, {outcome('new')} new "
            f"(of {expected} expected)."
        )
    lines.append(
        "Trust for this run: "
        + _freshness_trust_line(freshness, has_preflight=last is not None)
    )
    return lines


def _freshness_trust_line(freshness: dict, *, has_preflight: bool) -> str:
    """The section 8.2 trust line: what this run may assume about the
    map it was pinned to, in one sentence."""

    status = freshness.get("preflight_status")
    if status == "timed_out":
        return "preflight timed out — freshness unknown"
    if status == "failed":
        return "preflight failed — freshness unknown"
    if status in ("reused", "completed"):
        return "preflight-checked before this run"
    ttl = freshness.get("ttl_trust")
    if ttl == "within":
        return (
            f"within TTL ({MAP_TTL_TRUST_DAYS}d) — not preflighted "
            "for this run kind"
        )
    if ttl == "beyond":
        return (
            f"beyond TTL ({MAP_TTL_TRUST_DAYS}d) — not preflighted "
            "for this run kind"
        )
    if has_preflight:
        return "preflight-checked before this run"
    return (
        f"within TTL ({MAP_TTL_TRUST_DAYS}d) — not preflighted "
        "for this run kind"
    )


def planned_routes(request):
    return (getattr(request, "app_plan", None) or {}).get("routes", [request.start_url])


def next_planned_item(state, request):
    """Prioritize observed controls relevant to expectations; never invent actions."""
    plan = getattr(request, "app_plan", None)
    if not plan:
        return state.next_pending()
    words = set(re.findall(r"[a-z]{4,}", " ".join(
        check["expectation"] for check in plan["checks"]).lower()))
    pending = [item for item in state.ordered_items() if item.status == "pending"]
    return max(pending, key=lambda item: len(words.intersection(
        re.findall(r"[a-z]{4,}", item.name.lower()))), default=None)
