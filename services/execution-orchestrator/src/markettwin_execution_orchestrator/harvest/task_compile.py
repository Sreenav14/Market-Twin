"""Compile a captured task trace into a reusable draft skill
(doc 29 section 5, consults D1-D3).

One trace finds or creates a version by (scope, feature_key).
A new version starts as a draft in the exact definition shape
``build_definition`` established. Rejections are never silent and
never approximate a locator: the attempt returns its codes, the
run-close trigger records them on the run, and no skill rows are
written. Consult D1 (completeness): compile refuses unless EVERY
spec assertion has a satisfied trace result -- expected is built
from the SPEC's assertions, never from the trace's passed subset.
Consult D2: the initial navigation is prepended as step 1 (the
verification executor does not navigate on the scope's starting
URL). Consult D3: approval-gated flows refuse as unsupported.

Cleanup and documented expectations are owner knowledge: they are
inherited verbatim from a candidate for the same (scope,
feature_key) when one exists (doc 29 section 3.4/5); a state-
changing task with neither is rejected missing_cleanup rather than
invented a cleanup for.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from markettwin_shared.feature_plan import TestCaseSpec
from markettwin_shared.task_skill import task_contract_digest, validate_task_skill

from markettwin_execution_orchestrator.harvest.harvest_skill import (
    render_definition_package,
)
from markettwin_execution_orchestrator.workflow.skill_filter import (
    step_safety_class,
)

INCOMPLETE_ASSERTIONS = "incomplete_assertions"
SPEC_INVALID = "spec_invalid"


@dataclass
class CompileTaskResult:
    status: str  # "compiled" | "unchanged" | "rejected"
    codes: list[str] = field(default_factory=list)
    case_id: str | None = None
    feature_key: str | None = None
    skill: Any | None = None
    version: Any | None = None
    definition: dict[str, Any] | None = None


def _rejected(codes: list[str], *, case_id=None, feature_key=None) -> CompileTaskResult:
    return CompileTaskResult(
        status="rejected", codes=codes, case_id=case_id, feature_key=feature_key
    )


async def compile_task_trace(
    *,
    trace: dict[str, Any],
    spec: TestCaseSpec,
    app_map: Any,
    repository: Any,
    run_id: UUID | None = None,
    approved_values: dict[str, str] | None = None,
    trace_event_id: int | None = None,
) -> CompileTaskResult:
    """Compile one case's trace (doc 29 section 5). ``repository``
    is a HarvestRepository; ``approved_values`` is the source run's
    approved key->value map, used only to detect which outcomes were
    bound to which input key (values never enter the definition)."""
    approved_values = approved_values or {}
    case_id = spec.case_id
    feature_key = spec.feature_key
    trace_steps = [
        entry for entry in trace.get("spec_steps") or [] if isinstance(entry, dict)
    ]
    if len(trace_steps) != len(spec.steps) + 1:
        return _rejected(["incomplete_trace"], case_id=case_id, feature_key=feature_key)
    # D3: approval-gated steps cannot be replayed autonomously.
    if any(entry.get("approval_gated") for entry in trace_steps):
        return _rejected(["unsupported_target"], case_id=case_id, feature_key=feature_key)
    # D1: completeness -- every spec assertion satisfied in the trace.
    results = {
        entry["assertion_id"]: entry
        for entry in trace.get("assertions") or []
        if isinstance(entry, dict) and isinstance(entry.get("assertion_id"), str)
    }
    if any(
        results.get(entry.assertion_id, {}).get("status") != "satisfied"
        for entry in spec.expected
    ):
        return _rejected(
            [INCOMPLETE_ASSERTIONS], case_id=case_id, feature_key=feature_key
        )

    # Find-or-create target: an existing task skill (or candidate)
    # for this (scope, feature_key); its task block carries the
    # owner knowledge the trace cannot derive.
    skill = None
    inherited_task: dict[str, Any] = {}
    versions = []
    skills = await repository.list_skills_for_scope(
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
    )
    for candidate in skills:
        if candidate.skill_kind != "task":
            continue
        versions = await repository.list_versions_for_skill(candidate.id)
        for version in reversed(versions):
            task_block = (version.definition_json or {}).get("task") or {}
            if task_block.get("feature_key") == feature_key:
                skill = candidate
                inherited_task = task_block
                break
        if skill is not None:
            break

    # The pinned map's inventory: validation context + binding ranks.
    pages = await repository.work_list(app_map)
    states = await repository.list_states_for_map(app_map.id)
    elements_by_page: dict[UUID, list[Any]] = {}
    inventory: list[dict[str, Any]] = []
    for state in states:
        for element in await repository.list_elements_for_state(state.id):
            elements_by_page.setdefault(state.map_page_id, []).append(element)
            inventory.append(
                {
                    "role": element.role,
                    "name": element.name,
                    "label": element.label_text,
                }
            )
    page_urls = [page.canonical_url for page in pages]
    page_by_url = {page.canonical_url: page for page in pages}
    state_id_by_page: dict[UUID, str] = {}
    for state in states:
        # The first recorded state of a page is its landing state.
        state_id_by_page.setdefault(state.map_page_id, state.state_id)

    # Steps (D2: prepend the initial navigation) + locator bindings.
    start_url = str(trace.get("start_url") or "")
    native_steps: list[dict[str, Any]] = [{"action": "navigate", "url": start_url}]
    bindings: list[dict[str, Any]] = []
    for index, step in enumerate(spec.steps):
        native_steps.append(step.model_dump(mode="json", exclude_none=True))
        trace_step = (
            trace_steps[index + 1] if index + 1 < len(trace_steps) else {}
        )
        page_url = trace_step.get("source_page_url")
        target = step.target
        element: dict[str, Any] = {}
        if target is not None:
            if target.role is not None and target.name is not None:
                element = {"role": target.role, "name": target.name}
            elif target.label is not None:
                element = {"label": target.label}
            elif target.text is not None:
                element = {"text": target.text}
        locators: list[dict[str, Any]] = []
        strategy = trace_step.get("locator_strategy")
        if isinstance(strategy, str) and strategy:
            locators.append({"kind": strategy})
        page = page_by_url.get(str(page_url))
        if page is not None and target is not None:
            for candidate in elements_by_page.get(page.id, []):
                matched = (
                    target.role is not None
                    and target.name is not None
                    and candidate.role == target.role
                    and candidate.name == target.name
                ) or (
                    target.label is not None
                    and candidate.label_text == target.label
                )
                if matched:
                    for locator in candidate.locators or []:
                        if isinstance(locator, dict) and locator not in locators:
                            locators.append(locator)
        bindings.append(
            {
                "order": index + 2,
                "page_url": page_url,
                "state_id": (
                    state_id_by_page.get(page.id) if page is not None else None
                ),
                "element": element,
                "locators": locators,
                "action": step.action,
                "value_source": step.test_value_key or "none",
                **(
                    {"test_value_key": step.test_value_key}
                    if step.test_value_key
                    else {}
                ),
            }
        )

    # Expected: the spec's assertions (D1 guarantees all satisfied),
    # checkpoints remapped past the prepended navigation.
    expected: list[dict[str, Any]] = []
    observed_assertions: list[dict[str, Any]] = []
    evidence_assertions: list[dict[str, Any]] = []
    for entry in spec.expected:
        dumped = entry.model_dump(mode="json", exclude_none=True)
        if dumped.get("after_step_ordinal") is not None:
            dumped["after_step_ordinal"] = dumped["after_step_ordinal"] + 1
        expected.append(dumped)
        matching_keys = {key for key, value in approved_values.items()
                         if entry.expected_value == value}
        linked_keys = {step.test_value_key for step in spec.steps
                       if step.target is not None and step.target == entry.target
                       and step.test_value_key in matching_keys}
        candidates = linked_keys or matching_keys
        if len(candidates) > 1:
            return _rejected(["ambiguous_input_binding"], case_id=case_id, feature_key=feature_key)
        value_key = next(iter(candidates), None)
        observed_assertions.append(
            {
                "assertion_id": entry.assertion_id,
                "origin": "observation",
                "oracle": entry.oracle,
                "expected_value": entry.expected_value,
                **({"value_key": value_key} if value_key else {}),
            }
        )
        evidence_assertions.append(
            {
                "assertion_id": entry.assertion_id,
                "after_step_ordinal": dumped.get("after_step_ordinal"),
                "oracle": entry.oracle,
                "target": (
                    entry.target.model_dump(mode="json", exclude_none=True)
                    if entry.target is not None
                    else None
                ),
                "expected_value": entry.expected_value,
                "status": results[entry.assertion_id].get("status"),
                "has_evidence": results[entry.assertion_id].get("status") == "satisfied",
            }
        )

    # Inputs: the spec's keys, candidate declarations winning.
    inherited_inputs = {
        entry.get("key"): entry
        for entry in inherited_task.get("inputs") or []
        if isinstance(entry, dict) and entry.get("key")
    }
    keys: list[str] = []
    for step in spec.steps:
        if step.test_value_key and step.test_value_key not in keys:
            keys.append(step.test_value_key)
    for entry in observed_assertions:
        key = entry.get("value_key")
        if key and key not in keys:
            keys.append(key)
    inputs: list[dict[str, Any]] = []
    for key in keys:
        if key in inherited_inputs:
            inputs.append(dict(inherited_inputs[key]))
            continue
        bound_steps = [s for s in spec.steps if s.test_value_key == key]
        label = next(
            (
                s.target.label
                for s in bound_steps
                if s.target is not None and s.target.label
            ),
            key,
        )
        kind = (
            "secret_ref"
            if "password" in key or "secret" in key
            else "selection"
            if any(s.action == "select" for s in bound_steps)
            else "text"
        )
        inputs.append(
            {
                "key": key,
                "label": label,
                "kind": kind,
                "required": True,
                "disposable": any(
                    s.action in ("fill", "select") for s in bound_steps
                ),
            }
        )

    # Prerequisites: mechanically derived, unioned with the
    # candidate's owner-declared set.
    prerequisites: list[dict[str, Any]] = []
    seen_prereqs: set[tuple] = set()

    def _add_prereq(entry: dict[str, Any]) -> None:
        marker = (
            entry.get("kind"),
            entry.get("url"),
            entry.get("input_key"),
            entry.get("skill_name"),
        )
        if marker not in seen_prereqs:
            seen_prereqs.add(marker)
            prerequisites.append(entry)

    if any(
        segment.get("kind") == "assisted_login"
        for segment in trace.get("segments") or []
        if isinstance(segment, dict)
    ):
        _add_prereq({"kind": "authenticated"})
    for entry in inherited_task.get("prerequisites") or []:
        if isinstance(entry, dict):
            _add_prereq(dict(entry))

    terminal = trace.get("terminal") or {}
    changing = any(
        step_safety_class(step) in ("reversible", "irreversible")
        for step in native_steps
        if isinstance(step, dict)
    )
    cleanup = inherited_task.get("cleanup")
    if not isinstance(cleanup, dict):
        cleanup = {"kind": "none_required"} if not changing else None
    evidence_refs: list[dict[str, Any]] = [
        {
            "kind": "run_execution",
            "run_id": str(run_id) if run_id else None,
            "case_id": case_id,
        }
    ]
    if trace_event_id is not None:
        evidence_refs.append(
            {"kind": "task_trace", "event_id": str(trace_event_id)}
        )
    task_block: dict[str, Any] = {
        "purpose": spec.title[:200],
        "feature_key": feature_key,
        "source": {
            "kind": "run_execution",
            "run_id": str(run_id) if run_id else None,
            "case_id": case_id,
        },
        "prerequisites": prerequisites,
        "inputs": inputs,
        "documented_expectations": list(
            inherited_task.get("documented_expectations") or []
        ),
        "evidence_refs": evidence_refs,
        "observed_assertions": observed_assertions,
    }
    if cleanup is not None:
        task_block["cleanup"] = cleanup
    definition: dict[str, Any] = {
        "case_id": spec.case_id,
        "feature_key": feature_key,
        "title": spec.title,
        "kind": spec.kind,
        "steps": native_steps,
        "expected": expected,
        "safety": spec.safety,
        "estimated_seconds": spec.estimated_seconds,
        "locator_bindings": bindings,
        "success_assertion": {
            "kind": "terminal_state",
            "url": terminal.get("url"),
            "state_id": terminal.get("state_id"),
            "element_signature": list(terminal.get("element_signature") or []),
            "signature_superset_fallback": True,
        },
        "source_map_id": str(app_map.id),
        "source_map_version": app_map.version_number,
        "task": task_block,
    }
    task_block["contract_digest"] = task_contract_digest(definition)

    codes = validate_task_skill(
        definition,
        inventory=inventory,
        page_urls=page_urls,
        trace=trace,
        step_safety=[step_safety_class(step) for step in native_steps],
        evidence={"assertions": evidence_assertions, "owner_decisions": []},
    )
    if codes:
        if skill is not None:
            versions = await repository.list_versions_for_skill(skill.id)
            if versions:
                from markettwin_execution_orchestrator.harvest.skill_library import (
                    record_usage,
                )

                await record_usage(
                    repository,
                    versions[-1],
                    kind="compile",
                    result="refused",
                    run_id=run_id,
                    payload={"case_id": case_id, "codes": codes},
                )
        return _rejected(codes, case_id=case_id, feature_key=feature_key)

    if skill is not None:
        for existing in reversed(versions):
            saved = existing.definition_json or {}
            if (
                existing.app_map_id == app_map.id
                and existing.lifecycle_status in {"draft", "replay_verified", "active"}
                and getattr(existing, "last_replay_result", None) != "failed"
                and saved.get("steps") == native_steps
                and saved.get("expected") == expected
                and task_contract_digest(saved) == task_block["contract_digest"]
            ):
                return CompileTaskResult(
                    status="unchanged", case_id=case_id, feature_key=feature_key,
                    skill=skill, version=existing, definition=saved,
                )

    package = render_definition_package(
        definition,
        application_name=getattr(app_map, "application_name", None)
        or "the application",
        base_url=app_map.base_url,
    )
    if skill is None:
        skill, version = await repository.create_task_skill(
            app_map,
            name=package["name"],
            definition=definition,
            package=package,
        )
    else:
        version = await repository.append_skill_version(
            skill,
            app_map,
            definition=definition,
            package=package,
            source="task-compile",
        )
    from markettwin_execution_orchestrator.harvest.skill_library import (
        record_usage,
    )

    await record_usage(
        repository,
        version,
        kind="compile",
        result="applied",
        run_id=run_id,
        payload={"case_id": case_id, "feature_key": feature_key},
    )
    return CompileTaskResult(
        status="compiled",
        case_id=case_id,
        feature_key=feature_key,
        skill=skill,
        version=version,
        definition=definition,
    )


async def compile_run_traces(
    *, session_factory: Any, run_id: UUID
) -> list[CompileTaskResult]:
    """The run-close trigger (doc 29 section 5): compile every task
    trace an explore_test run persisted. Rejections are recorded on
    the run itself -- the trace's home -- as
    harness.task_skill.compile_rejected events."""
    from markettwin_database.models import RunEvent, TestRun
    from sqlalchemy import select

    from markettwin_execution_orchestrator.harvest.harvest_repository import (
        HarvestRepository,
    )
    from markettwin_execution_orchestrator.persistence.run_event_repository import (
        RunEventRepository,
    )
    from markettwin_execution_orchestrator.workflow.run_request import (
        _parse_approved_test_data,
    )

    async with session_factory() as session:
        run = await session.get(TestRun, run_id)
        if run is None or run.run_kind != "explore_test":
            return []
        snapshot = run.configuration_snapshot or {}
        block = snapshot.get("app_map") if isinstance(snapshot, dict) else None
        map_ref = block.get("map_id") if isinstance(block, dict) else None
        rows = list(
            await session.scalars(
                select(RunEvent).where(
                    RunEvent.test_run_id == run_id,
                    RunEvent.event_type == "test_case.task_trace",
                ).order_by(RunEvent.id)
            )
        )
        from markettwin_execution_orchestrator.workflow.task_spec_store import restore_task_trace

        traces = []
        for row in rows:
            try:
                payload = await restore_task_trace(
                    session, payload=row.payload, run_id=run_id, execution_id=row.execution_id,
                )
            except (ValueError, TypeError, AttributeError):
                payload = {"case_id": row.payload.get("case_id")
                           if isinstance(row.payload, dict) else None, "spec": {}}
            traces.append((row.id, payload))
        approved = {
            entry.key: entry.value
            for entry in _parse_approved_test_data(snapshot)
        }
    if not isinstance(map_ref, str):
        return []
    repository = HarvestRepository(session_factory)
    app_map = await repository.get_map(UUID(map_ref))
    if app_map is None:
        return []
    outcomes: list[CompileTaskResult] = []
    for event_id, payload in traces:
        if not isinstance(payload, dict):
            continue
        try:
            spec = TestCaseSpec.model_validate(payload.get("spec") or {})
        except Exception:
            outcome = _rejected([SPEC_INVALID])
        else:
            outcome = await compile_task_trace(
                trace=payload,
                spec=spec,
                app_map=app_map,
                repository=repository,
                run_id=run_id,
                approved_values=approved,
                trace_event_id=event_id,
            )
        outcomes.append(outcome)
        if outcome.status == "rejected":
            async with session_factory() as session:
                await RunEventRepository(session).create(
                    test_run_id=run_id,
                    event_type="harness.task_skill.compile_rejected",
                    journey_id=None,
                    execution_id=None,
                    payload={
                        "case_id": outcome.case_id,
                        "feature_key": outcome.feature_key,
                        "codes": outcome.codes,
                    },
                )
                await session.commit()
    return outcomes
