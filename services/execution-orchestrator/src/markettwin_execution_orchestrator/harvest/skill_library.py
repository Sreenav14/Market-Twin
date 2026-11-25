"""Phase 3 skill library operations (doc 22 sections 5.1-5.3, 6.1, 6.3).

The lifecycle AUTHORITY is the shared check
(``markettwin_shared.app_map_common.check_skill_transition``): every
lifecycle write in this service passes it at the write site, and the
transition plus its ``skill_usage_events`` row commit together via
``HarvestRepository.apply_skill_transition``. This module is the
orchestrator's half of the library (verification, compilation,
activation, platform registration); the control-api repository
carries the serving half. The transition table itself exists exactly
once, in shared code.
"""

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from markettwin_shared.app_map_common import (
    canonical_url,
    check_skill_transition,
    skill_currency_check,
)

from markettwin_execution_orchestrator.harvest.harvest_skill import (
    JourneyEdge,
    JourneyNode,
    JourneySelection,
    build_definition,
    render_package,
)


async def transition_version(
    repository: Any,
    version_id: UUID,
    *,
    to_status: str,
    kind: str,
    evidence: Mapping[str, object],
    result: str | None = None,
    run_id: UUID | None = None,
    job_ref: str | None = None,
    model_calls: int = 0,
    model_tokens: int = 0,
    payload: Mapping[str, object] | None = None,
) -> Any:
    """Check + apply + record one lifecycle transition.

    A refusal raises ValueError: a refused transition is the caller's
    bug, surfaced -- never a skipped write (doc 22 section 5.1).
    """
    version = await repository.get_skill_version(version_id)
    if version is None:
        raise ValueError(f"skill_version_unknown: {version_id}")
    from_status = version.lifecycle_status
    if not check_skill_transition(from_status, to_status, evidence):
        raise ValueError(
            f"skill_transition_refused: {from_status} -> {to_status}"
        )
    fields: dict[str, object] = {"lifecycle_status": to_status}
    if to_status == "retired":
        retirement = evidence.get("retirement")
        if isinstance(retirement, Mapping):
            reason = retirement.get("retired_reason")
            fields["retired_reason"] = reason if isinstance(reason, str) else None
        fields["retired_at"] = datetime.now(UTC)
    return await repository.apply_skill_transition(
        version_id,
        fields=fields,
        event={
            "kind": kind,
            "from_status": from_status,
            "to_status": to_status,
            "result": result,
            "run_id": run_id,
            "job_ref": job_ref,
            "model_calls": model_calls,
            "model_tokens": model_tokens,
            "evidence": dict(evidence),
            "payload": dict(payload) if payload is not None else dict(evidence),
        },
    )


async def record_usage(
    repository: Any,
    version: Any,
    *,
    kind: str,
    result: str | None = None,
    run_id: UUID | None = None,
    job_ref: str | None = None,
    model_calls: int = 0,
    model_tokens: int = 0,
    payload: Mapping[str, object] | None = None,
) -> None:
    """A usage-ledger row with NO lifecycle change (a replay, a heal
    diagnosis, a refusal)."""
    await repository.insert_usage_event(
        version,
        kind=kind,
        from_status=version.lifecycle_status,
        to_status=version.lifecycle_status,
        result=result,
        run_id=run_id,
        job_ref=job_ref,
        model_calls=model_calls,
        model_tokens=model_tokens,
        payload=dict(payload or {}),
    )


def _package_name(journey_name: str) -> str:
    """The skill's registry name for a journey: render_package's slug
    rule, applied without rendering the package."""
    name = re.sub(r"[^a-z0-9]+", "-", journey_name.casefold()).strip("-")
    return name or "journey"


async def _selection_for_journey(
    repository: Any,
    journey: Any,
    nodes: dict[UUID, JourneyNode],
) -> JourneySelection | None:
    """Rebuild a JourneySelection from a stored journey row: its
    steps name the state and element of each click; the terminal is
    the journey's success state. Returns None when any referenced
    row is gone (an honest compile failure for this journey)."""
    steps: list[Any] = cast(list[Any], journey.steps) if isinstance(journey.steps, list) else []
    terminal_state = await repository.get_state(journey.success_state_id)
    if terminal_state is None:
        return None
    terminal_node = nodes.get(terminal_state.map_page_id)
    if terminal_node is None:
        return None
    edges: list[JourneyEdge] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            return None
        step = cast(dict[str, Any], step)
        if step.get("test_value_key") is not None and not isinstance(step["test_value_key"], str):
            return None
        state = await repository.get_state(UUID(str(step.get("map_page_state_id"))))
        element = await repository.get_element(UUID(str(step.get("element_id"))))
        if state is None or element is None:
            return None
        if index + 1 < len(steps):
            next_step = steps[index + 1]
            next_state = await repository.get_state(
                UUID(str(next_step.get("map_page_state_id")))
            )
            if next_state is None:
                return None
            to_page_id = next_state.map_page_id
        else:
            to_page_id = terminal_state.map_page_id
        edges.append(
            JourneyEdge(
                from_page_id=state.map_page_id,
                from_state_id=state.id,
                element_id=element.id,
                role=element.role,
                name=element.name,
                locators=list(element.locators or []),
                to_page_id=to_page_id,
                action=str(step.get("action") or "click"),
                test_value_key=step.get("test_value_key"),
            )
        )
    return JourneySelection(
        terminal=terminal_node,
        path=edges,
        selection=journey.selection,
        detail={"reason": "compile_all", "journey_id": str(journey.id)},
    )


async def compile_all_journeys(
    repository: Any,
    app_map: Any,
    *,
    application_name: str,
) -> dict[str, int]:
    """Doc 22 section 6.1: compile EVERY journey of the map that
    lacks a version bound to this map (1b compiled only the gate
    journey). Finds-or-creates the skill row by (scope, name);
    appends a new draft version per map; sets journey.skill_id;
    records the compile on the ledger. Zero model calls."""
    counts = {"compiled": 0, "skipped": 0, "failed": 0}
    journeys = await repository.list_journeys(app_map.id)
    if not journeys:
        return counts
    pages = await repository.work_list(app_map)
    states = await repository.list_states_for_map(app_map.id)
    default_by_page: dict[UUID, Any] = {}
    for state in states:
        if state.state_key == "default":
            default_by_page[state.map_page_id] = state
    nodes: dict[UUID, JourneyNode] = {}
    pages_by_id = {page.id: page for page in pages}
    for page_id, state in default_by_page.items():
        page = pages_by_id.get(page_id)
        if page is None:
            continue
        nodes[page_id] = JourneyNode(
            page_id=page_id,
            canonical_url=page.canonical_url,
            default_state_id=state.id,
            default_state_identity=state.state_id,
            default_element_signature=(
                state.element_signature.split(";")
                if state.element_signature
                else []
            ),
        )
    base_page = next(
        (p for p in pages if p.canonical_url == app_map.base_url),
        pages[0] if pages else None,
    )
    base_node = nodes.get(base_page.id) if base_page is not None else None
    if base_node is None:
        counts["failed"] = len(journeys)
        return counts
    for journey in journeys:
        name = _package_name(journey.name)
        skill = await repository.find_graph_skill(
            workspace_id=app_map.workspace_id,
            application_id=app_map.application_id,
            target_id=app_map.target_id,
            name=name,
        )
        if skill is not None:
            versions = await repository.list_versions_for_skill(skill.id)
            if any(v.app_map_id == app_map.id for v in versions):
                counts["skipped"] += 1
                continue
        selection = await _selection_for_journey(repository, journey, nodes)
        if selection is None:
            counts["failed"] += 1
            continue
        if any(edge.action in {"fill", "select"} for edge in selection.path):
            counts["failed"] += 1
            await repository.record_event(
                app_map.id, "skill.compile_refused",
                {"journey_id": str(journey.id), "reason": "journey_input_context_unavailable"},
            )
            continue
        definition = build_definition(
            selection=selection,
            base_node=base_node,
            nodes=nodes,
            journey_name=journey.name,
            app_map=app_map,
        )
        if definition is None:
            counts["failed"] += 1
            continue
        package = render_package(
            selection=selection,
            journey_name=journey.name,
            application_name=application_name,
            app_map=app_map,
            nodes=nodes,
            base_url=base_node.canonical_url,
        )
        definition["source_journey_id"] = str(journey.id)
        if skill is None:
            skill, version = await repository.create_skill_with_version(
                app_map,
                name=name,
                definition=definition,
                package=package,
                created_by_user_id=None,
            )
            await repository.update_skill_version(
                version.id, app_map_id=app_map.id
            )
            version.app_map_id = app_map.id
        else:
            version = await repository.append_skill_version(
                skill, app_map, definition=definition, package=package
            )
        await repository.attach_journey_skill(journey.id, skill.id)
        await repository.insert_usage_event(
            version,
            kind="compile",
            from_status=None,
            to_status="draft",
            payload={"journey_id": str(journey.id)},
        )
        counts["compiled"] += 1
    return counts


async def activate_current_versions(
    repository: Any, app_map: Any
) -> dict[str, int]:
    """Doc 22 section 5.2 against THIS map as the current map (the
    orchestrator's activation pass; the control-api repository
    carries the same rule for API-time callers)."""
    counts = {
        "activated": 0,
        "retired_superseded": 0,
        "retired_journey_absent": 0,
        "currency_failed": 0,
    }
    skills = await repository.list_skills_for_scope(
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
    )
    if not skills:
        return counts
    pages = await repository.work_list(app_map)
    states = await repository.list_states_for_map(app_map.id)
    journeys = await repository.list_journeys(app_map.id)
    base_page = next(
        (p for p in pages if p.canonical_url == app_map.base_url),
        pages[0] if pages else None,
    )
    default_identity_by_page = {
        s.map_page_id: s.state_id for s in states if s.state_key == "default"
    }
    identity_by_row = {s.id: s.state_id for s in states}
    start_state_id = (
        default_identity_by_page.get(base_page.id)
        if base_page is not None
        else None
    )
    journey_by_name = {j.name: j for j in journeys}
    for skill in skills:
        versions = await repository.list_versions_for_skill(skill.id)
        active = next(
            (v for v in versions if v.lifecycle_status == "active"), None
        )
        for version in versions:
            if version.lifecycle_status != "replay_verified":
                continue
            if skill.skill_kind == "platform":
                journey_present = True
                current = version.app_map_id == app_map.id
            elif skill.skill_kind == "task":
                # Doc 29 section 6: a task has no journey to lose;
                # currency is the fingerprint pair against the
                # current map -- the base page's default state and
                # the default state of the page the task ends on.
                journey_present = True
                success = (
                    version.definition_json.get("success_assertion")
                    if isinstance(version.definition_json, Mapping)
                    else None
                )
                terminal_url = (
                    canonical_url(str(success.get("url") or ""))
                    if isinstance(success, Mapping)
                    else ""
                )
                terminal_page = next(
                    (
                        p
                        for p in pages
                        if canonical_url(p.canonical_url) == terminal_url
                    ),
                    None,
                )
                current_terminal = (
                    default_identity_by_page.get(terminal_page.id)
                    if terminal_page is not None
                    else None
                )
                current = skill_currency_check(
                    version.verified_fingerprint,
                    start_state_id,
                    current_terminal,
                )
            else:
                source_id = (
                    version.definition_json.get("source_journey_id")
                    if isinstance(version.definition_json, Mapping)
                    else None
                )
                source = (
                    await repository.get_journey(UUID(str(source_id)))
                    if source_id
                    else None
                )
                current_journey = (
                    journey_by_name.get(source.name) if source else None
                )
                journey_present = current_journey is not None
                current = journey_present and skill_currency_check(
                    version.verified_fingerprint,
                    start_state_id,
                    identity_by_row.get(current_journey.success_state_id),
                )
            if not journey_present:
                await transition_version(
                    repository,
                    version.id,
                    to_status="retired",
                    kind="retirement",
                    evidence={
                        "retirement": {"retired_reason": "journey_absent"}
                    },
                    payload={"reason": "journey_absent"},
                )
                counts["retired_journey_absent"] += 1
                continue
            if not current:
                await record_usage(
                    repository,
                    version,
                    kind="activation",
                    result="failed",
                    payload={"reason": "currency_mismatch"},
                )
                counts["currency_failed"] += 1
                continue
            if active is not None and active.id != version.id:
                await transition_version(
                    repository,
                    active.id,
                    to_status="retired",
                    kind="retirement",
                    evidence={
                        "retirement": {
                            "retired_reason": "superseded",
                            "superseded_by_version_id": str(version.id),
                        }
                    },
                    payload={
                        "retired_reason": "superseded",
                        "superseded_by_version_id": str(version.id),
                    },
                )
                counts["retired_superseded"] += 1
            await transition_version(
                repository,
                version.id,
                to_status="active",
                kind="activation",
                evidence={"currency_pass": {"app_map_id": str(app_map.id)}},
                result="passed",
            )
            active = version
            counts["activated"] += 1
    return counts


async def register_platform_skill(
    repository: Any,
    app_map: Any,
    *,
    name: str,
    definition: dict[str, object],
    package: dict[str, object],
) -> tuple[Any, Any]:
    """Doc 22 section 6.3: platform skills register through the
    library. A journey-compiled definition shape (source journey,
    locator bindings) is REFUSED -- it is not a platform skill.
    Registration is idempotent: an existing skill returns its latest
    version unchanged."""
    if definition.get("source_journey_id") or "locator_bindings" in definition:
        raise ValueError(
            "platform_registration_refused: journey-compiled definition shape"
        )
    existing = await repository.find_graph_skill(
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
        name=name,
    )
    if existing is not None:
        latest = await repository.latest_skill_version(existing.id)
        return existing, latest
    skill, version = await repository.create_platform_skill(
        app_map, name=name, definition=definition, package=package
    )
    await repository.insert_usage_event(
        version,
        kind="compile",
        from_status=None,
        to_status="draft",
        payload={"skill_kind": "platform"},
    )
    return skill, version
