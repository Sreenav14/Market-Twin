"""Phase 3 re-verification poller (doc 22 sections 5.5, 9).

One pass over the newest ready map per scope:
- draft versions bound to that map are verified (two clean replays,
  harvest/harvest_replay.verify_skill);
- replay_verified versions go through the activation pass
  (harvest/skill_library.activate_current_versions);
- a suspect version gets ONE heal cycle (section 9.1): code-first
  heal, else the model-assisted diagnosis (section 9.3 — capped per
  job and per map, each call counted on the version's usage events
  and the map's durable heal_diagnosis_calls counter, the proposal
  validated in code, never an edit). The heal mints a NEW draft version with
  heal_of_version_id set; a served version's definition is never
  edited. The healed draft verifies; on success it proceeds to
  activation and the suspect retires superseded once the healed
  version is active; on failure the suspect is quarantined with the
  healed draft named in the event, the draft left in draft, and the
  journey falls back to live exploration (no active version serves
  it, so planning simply finds no skill — section 9.1's fallback is
  the absence of a served skill, recorded by the quarantine event).

The poller mirrors the harvest poller's shape: advisory claim per
map, one slot, a wall budget per pass, cadence constants in-module
(prep Q1: no orchestrator config module exists).
"""

import asyncio
import inspect
import logging
import os
from collections.abc import Callable
from typing import Any
from uuid import UUID

from markettwin_database.model_budget import ModelBudgetExceeded

from markettwin_execution_orchestrator.harvest.harvest_replay import (
    HealRecord,
    ReplayAttempt,
    heal_definition,
    verify_skill,
)
from markettwin_execution_orchestrator.harvest.skill_library import (
    activate_current_versions,
    record_usage,
    transition_version,
)

logger = logging.getLogger(__name__)

SKILL_REVERIFY_POLL_SECONDS = 5  # prep Q1 precedent (HARVEST_POLL_SECONDS)
SKILL_REVERIFY_SLOTS = 1  # one heavy browser job at a time on the host
SKILL_REVERIFY_WALL_BUDGET_SECONDS = 1800  # [J] doc 22 section 9.1
HEAL_DIAGNOSIS_CALL_CAP = 20  # doc 22 section 9.3, per heal job
HEAL_DIAGNOSIS_MAP_CALL_CAP_DEFAULT = 100  # Astra A5: durable per-map cap
HEAL_ARIA_MAX_CHARS = 12000  # doc 22 section 9.3


def _diagnosis_budget(app_map: Any) -> dict[str, int]:
    """The diagnosis budget for one map's pass (doc 22 section 9.3 +
    Astra A5): the per-pass cap, narrowed by the DURABLE per-map cap.
    The map's spent count lives in harvest_metrics, so the cap binds
    across passes and restarts -- not just within one pass. The
    charge in heal_cycle_for_suspect merge-writes the counter back
    through HarvestRepository.save_harvest_metrics BEFORE each
    provider call (reserve-before-send)."""
    try:
        map_cap = int(
            os.environ.get(
                "MARKETTWIN_HEAL_DIAGNOSIS_MAP_CALL_CAP",
                HEAL_DIAGNOSIS_MAP_CALL_CAP_DEFAULT,
            )
        )
    except ValueError:
        map_cap = HEAL_DIAGNOSIS_MAP_CALL_CAP_DEFAULT
    map_calls = int(
        (app_map.harvest_metrics or {}).get("heal_diagnosis_calls") or 0
    )
    return {
        "remaining": max(
            0, min(HEAL_DIAGNOSIS_CALL_CAP, map_cap - map_calls)
        ),
        "map_calls": map_calls,
        "map_cap": map_cap,
    }


def validate_heal_diff(
    before: dict[str, Any], after: dict[str, Any]
) -> bool:
    """The heal diff validator (doc 22 section 9.3): a heal may change
    ONLY a step's target (locator) or an existing wait's milliseconds
    (bounded at 2000). It refuses any change to the success
    assertion, the step set (count, order, actions), a step's target
    page or element identity beyond the target swap itself, or any
    test_value_key."""
    if before.get("success_assertion") != after.get("success_assertion"):
        return False
    before_steps = before.get("steps")
    after_steps = after.get("steps")
    if not isinstance(before_steps, list) or not isinstance(after_steps, list):
        return False
    if len(before_steps) != len(after_steps):
        return False
    for old, new in zip(before_steps, after_steps, strict=True):
        if not isinstance(old, dict) or not isinstance(new, dict):
            return False
        if old.get("action") != new.get("action"):
            return False
        if old.get("test_value_key") != new.get("test_value_key"):
            return False
        for key in set(old) | set(new):
            if key in ("target", "milliseconds"):
                continue
            if old.get(key) != new.get(key):
                return False
        if "milliseconds" in old or "milliseconds" in new:
            old_ms = int(old.get("milliseconds") or 0)
            new_ms = int(new.get("milliseconds") or 0)
            if new_ms < old_ms or new_ms > 2000:
                return False
    return True


async def diagnose_heal(
    definition: dict[str, Any],
    failure: ReplayAttempt,
    *,
    aria_excerpt: str,
    on_call: Callable[[], None] | None = None,
) -> tuple[dict[str, Any], HealRecord] | None:
    """The model-assisted heal diagnosis (doc 22 section 9.3): ONE
    ask-door call. The model proposes an INDEX into the failing
    step's own ranked locator bindings; code validates the proposal
    (in range, expressible as a target, different from the current
    target, diff-valid) — the model never edits the definition.
    Returns None when the proposal is unusable."""
    from markettwin_execution_orchestrator.harvest.harvest_replay import (
        _target_from_locator,
    )
    from markettwin_execution_orchestrator.models import ask

    if failure.failure_step is None:
        return None
    steps = definition.get("steps")
    bindings = definition.get("locator_bindings")
    if not isinstance(steps, list) or failure.failure_step >= len(steps):
        return None
    if not isinstance(bindings, list):
        return None
    binding = next(
        (
            item
            for item in bindings
            if isinstance(item, dict)
            and item.get("order") == failure.failure_step + 1
        ),
        None,
    )
    if binding is None:
        return None
    locators = [dict(item) for item in binding.get("locators") or []]
    if not locators:
        return None
    step = steps[failure.failure_step]
    current_target = step.get("target") or {}
    system = (
        "You choose ONE replacement locator for a failed UI test step. "
        "Reply with JSON {\"locator_index\": <int>} picking from the "
        "candidate locators by index, or {\"locator_index\": -1} if "
        "none of them can be the same element. You may not invent "
        "locators, change the step, or change the goal."
    )
    user = (
        f"Failing step: {step}\n"
        f"Current target: {current_target}\n"
        f"Candidate locators (ranked): {locators}\n"
        f"Page context (truncated): {aria_excerpt[:HEAL_ARIA_MAX_CHARS]}"
    )
    try:
        if on_call is not None:
            pending = on_call()
            if inspect.isawaitable(pending):
                await pending
        result = await ask._model_json(system, user, max_tokens=256)
    except ModelBudgetExceeded:
        # Budget exhaustion is a pass-level fact, never a "proposal
        # unusable" (Astra A5): surface it to the caller.
        raise
    except Exception:
        return None
    if not isinstance(result, dict):
        return None
    index = result.get("locator_index")
    if not isinstance(index, int) or index < 0 or index >= len(locators):
        return None
    candidate = _target_from_locator(locators[index])
    if candidate is None or candidate == current_target:
        return None
    healed = dict(definition)
    healed_steps = [dict(item) for item in steps]
    healed_steps[failure.failure_step] = {**step, "target": candidate}
    healed["steps"] = healed_steps
    if not validate_heal_diff(definition, healed):
        return None
    return healed, HealRecord(
        step=failure.failure_step,
        from_locator=dict(current_target),
        to_locator=candidate,
    )


async def heal_cycle_for_suspect(
    repository: Any,
    app_map: Any,
    skill: Any,
    version: Any,
    *,
    executor: Any,
    start_state_id: str | None,
    diagnosis_budget: dict[str, int],
) -> str:
    """One heal cycle for one suspect version (doc 22 section 9.1).
    Returns the outcome word for the pass counts."""
    if skill.skill_kind == "task":
        await record_usage(
            repository, version, kind="heal_attempt", result="refused",
            payload={"reason": "task_requires_recompilation"},
        )
        return "heal_diff_refused"
    replays = await repository.list_replays_for_version(version.id)
    failed = [row for row in replays if row.result == "failed"]
    if not failed:
        await record_usage(
            repository,
            version,
            kind="heal_attempt",
            result="failed",
            payload={"reason": "no_failure_evidence"},
        )
        return "heal_skipped_no_evidence"
    last_failure = failed[-1]
    attempt = ReplayAttempt(
        ok=False,
        failure_step=last_failure.failure_step,
        failure_site=last_failure.failure_site,
    )
    definition = version.definition_json
    healed = heal_definition(definition, attempt)
    diagnosis_calls = 0
    if healed is None and diagnosis_budget["remaining"] > 0:
        assertion = definition.get("success_assertion") or {}
        excerpt = (
            f"Terminal assertion: {assertion}\n"
            f"Element signature: {assertion.get('element_signature')}"
        )
        async def charge_diagnosis() -> None:
            nonlocal diagnosis_calls
            diagnosis_calls += 1
            diagnosis_budget["remaining"] -= 1
            if "map_calls" in diagnosis_budget:
                # Durable charge, persisted BEFORE the provider call
                # (reserve-before-send): merge-write the map's
                # counter so the cap survives passes and restarts.
                diagnosis_budget["map_calls"] += 1
                await repository.save_harvest_metrics(
                    app_map.id,
                    {"heal_diagnosis_calls": diagnosis_budget["map_calls"]},
                )

        diagnosed = await diagnose_heal(
            definition, attempt, aria_excerpt=excerpt, on_call=charge_diagnosis,
        )
        if diagnosed is not None:
            healed = diagnosed
            await record_usage(
                repository,
                version,
                kind="heal_diagnosis",
                result="applied",
                model_calls=diagnosis_calls,
                payload={"step": diagnosed[1].step},
            )
        else:
            await record_usage(
                repository,
                version,
                kind="heal_diagnosis",
                result="failed",
                model_calls=diagnosis_calls,
                payload={"reason": "proposal_unusable"},
            )
    elif (
        healed is None
        and "map_cap" in diagnosis_budget
        and diagnosis_budget["map_calls"] >= diagnosis_budget["map_cap"]
    ):
        # The durable per-map cap is spent (Astra A5): refuse the
        # diagnosis BEFORE any provider request and name the
        # exhaustion on the usage ledger -- a silent skip would read
        # as "no heal proposed" downstream.
        logger.warning(
            "Heal diagnosis refused for map %s: durable cap "
            "exhausted (%s of %s calls used)",
            app_map.id,
            diagnosis_budget["map_calls"],
            diagnosis_budget["map_cap"],
        )
        await record_usage(
            repository,
            version,
            kind="heal_diagnosis",
            result="refused",
            payload={
                "reason": "heal_diagnosis_map_cap_exhausted",
                "map_calls": diagnosis_budget["map_calls"],
                "map_cap": diagnosis_budget["map_cap"],
            },
        )
    if healed is None:
        await transition_version(
            repository,
            version.id,
            to_status="quarantined",
            kind="quarantine",
            evidence={
                "failed_replays": [str(row.id) for row in failed],
                "heal_record": {
                    "applicable": False,
                    "reason": "no_heal_proposed",
                    "diagnosis_calls": diagnosis_calls,
                },
            },
            result="failed",
        )
        return "quarantined"
    healed_definition, heal_record = healed
    if not validate_heal_diff(definition, healed_definition):
        await record_usage(
            repository,
            version,
            kind="heal_attempt",
            result="failed",
            payload={"reason": "heal_diff_refused"},
        )
        return "heal_diff_refused"
    await repository.update_skill_version(
        version.id, heal_count=(version.heal_count or 0) + 1
    )
    draft = await repository.append_skill_version(
        skill,
        app_map,
        definition=healed_definition,
        package=version.package,
        heal_of_version_id=version.id,
        source="phase-3-heal",
    )
    await record_usage(
        repository,
        version,
        kind="heal_attempt",
        result="applied",
        payload={
            "healed_draft_id": str(draft.id),
            "step": heal_record.step,
            "diagnosis_calls": diagnosis_calls,
        },
    )
    result = await verify_skill(
        repository=repository,
        app_map=app_map,
        skill_version=draft,
        definition=healed_definition,
        executor=executor,
        start_state_id=start_state_id,
        on_failure="leave_draft",
    )
    if result.lifecycle_status == "replay_verified":
        await activate_current_versions(repository, app_map)
        fresh_draft = await repository.get_skill_version(draft.id)
        if fresh_draft is not None and fresh_draft.lifecycle_status == "active":
            await transition_version(
                repository,
                version.id,
                to_status="retired",
                kind="retirement",
                evidence={
                    "retirement": {
                        "retired_reason": "superseded",
                        "superseded_by_version_id": str(draft.id),
                    }
                },
                payload={
                    "retired_reason": "superseded",
                    "superseded_by_version_id": str(draft.id),
                },
            )
            return "healed_and_active"
        return "healed_pending_activation"
    await transition_version(
        repository,
        version.id,
        to_status="quarantined",
        kind="quarantine",
        evidence={
            "failed_replays": [str(row.id) for row in failed],
            "heal_record": {
                "healed_draft_id": str(draft.id),
                "healed_draft_failed_replays": list(result.failed_replay_ids),
                "step": heal_record.step,
            },
        },
        result="failed",
    )
    return "quarantined"


async def _verify_task_version(
    repository: Any, app_map: Any, version: Any, *, controller: Any
) -> str:
    """Route one task draft through the task verification entry
    (doc 29 section 6). The profile, trace and login definition
    resolve from the version's source run."""
    from markettwin_execution_orchestrator.harvest.task_verify import (
        verify_task_draft,
    )

    outcome = await verify_task_draft(
        repository=repository,
        app_map=app_map,
        skill_version=version,
        controller=controller,
        session_factory=getattr(repository, "_session_factory", None),
    )
    return outcome["status"]


async def run_reverification_pass(
    repository: Any,
    app_map: Any,
    *,
    executor_factory: Any,
) -> dict[str, int]:
    """One map's re-verification job (doc 22 sections 5.5, 9.1):
    verify its drafts, heal its suspects, then run the activation
    pass. The diagnosis budget is per job (this pass)."""
    counts = {
        "verified": 0,
        "quarantined": 0,
        "healed_and_active": 0,
        "healed_pending_activation": 0,
        "heal_skipped_no_evidence": 0,
        "heal_diff_refused": 0,
    }
    pages = await repository.work_list(app_map)
    states = await repository.list_states_for_map(app_map.id)
    base_page = next(
        (p for p in pages if p.canonical_url == app_map.base_url),
        pages[0] if pages else None,
    )
    start_state_id = None
    if base_page is not None:
        for state in states:
            if (
                state.map_page_id == base_page.id
                and state.state_key == "default"
            ):
                start_state_id = state.state_id
                break
    diagnosis_budget = _diagnosis_budget(app_map)
    # Owner-requested journey compiles (doc 22 section 12.2) ride the
    # same pass: compile-all covers the requested journeys (it
    # compiles every uncompiled journey of the map), then the
    # request list clears.
    if (app_map.harvest_metrics or {}).get("skill_compile_requests"):
        from markettwin_execution_orchestrator.harvest.skill_library import (
            compile_all_journeys,
        )

        await compile_all_journeys(
            repository,
            app_map,
            application_name=await repository.application_name(
                app_map.application_id
            ),
        )
        await repository.save_harvest_metrics(
            app_map.id, {"skill_compile_requests": []}
        )
    skills = await repository.list_skills_for_scope(
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
    )
    executor: Any | None = None
    for skill in skills:
        versions = await repository.list_versions_for_skill(skill.id)
        for version in versions:
            if (
                version.lifecycle_status == "draft"
                and version.app_map_id == app_map.id
            ):
                if skill.skill_kind == "task":
                    # Doc 29 section 6: task drafts verify through
                    # the task entry (profile, prerequisites,
                    # cleanup) -- never the plain journey executor.
                    if executor is None:
                        executor = executor_factory(app_map)
                    outcome = await _verify_task_version(
                        repository,
                        app_map,
                        version,
                        controller=executor._controller,
                    )
                    if outcome == "replay_verified":
                        counts["verified"] += 1
                    elif outcome == "refused":
                        counts["task_refused"] = (
                            counts.get("task_refused", 0) + 1
                        )
                    continue
                if executor is None:
                    executor = executor_factory(app_map)
                result = await verify_skill(
                    repository=repository,
                    app_map=app_map,
                    skill_version=version,
                    definition=version.definition_json,
                    executor=executor,
                    start_state_id=start_state_id,
                )
                if result.lifecycle_status == "replay_verified":
                    counts["verified"] += 1
                elif result.lifecycle_status == "quarantined":
                    counts["quarantined"] += 1
            elif version.lifecycle_status == "suspect":
                if skill.skill_kind == "task":
                    await record_usage(
                        repository, version, kind="heal_attempt", result="refused",
                        payload={"reason": "task_requires_recompilation"},
                    )
                    counts["heal_diff_refused"] += 1
                    continue
                if executor is None:
                    executor = executor_factory(app_map)
                suspect_executor = executor
                outcome = await heal_cycle_for_suspect(
                    repository,
                    app_map,
                    skill,
                    version,
                    executor=suspect_executor,
                    start_state_id=start_state_id,
                    diagnosis_budget=diagnosis_budget,
                )
                counts[outcome] = counts.get(outcome, 0) + 1
    activation = await activate_current_versions(repository, app_map)
    counts["activated"] = activation["activated"]
    return counts


def _production_executor_factory(app_map: Any) -> Any:
    from markettwin_execution_orchestrator.browser.controller import (
        BrowserController,
    )
    from markettwin_execution_orchestrator.harvest.harvest_replay import (
        CaseExecutionReplayExecutor,
    )

    return CaseExecutionReplayExecutor(BrowserController(), app_map=app_map)


_reverify_tasks: dict[UUID, asyncio.Task[None]] = {}


async def _poll_once(
    repository: Any, session_factory: Any, executor_factory: Any
) -> None:
    from markettwin_execution_orchestrator.harvest.harvest_job import (
        AdvisoryClaim,
    )

    for map_id, task in list(_reverify_tasks.items()):
        if task.done():
            _reverify_tasks.pop(map_id, None)
    if len(_reverify_tasks) >= SKILL_REVERIFY_SLOTS:
        return
    seen_scopes: set[tuple[UUID, UUID]] = set()
    for app_map in await repository.list_ready_maps():
        scope = (app_map.application_id, app_map.target_id)
        if scope in seen_scopes:
            continue  # newest ready map per scope only
        seen_scopes.add(scope)
        if app_map.id in _reverify_tasks:
            continue
        skills = await repository.list_skills_for_scope(
            workspace_id=app_map.workspace_id,
            application_id=app_map.application_id,
            target_id=app_map.target_id,
        )
        pending = bool((app_map.harvest_metrics or {}).get("skill_compile_requests"))
        for skill in skills:
            versions = await repository.list_versions_for_skill(skill.id)
            for version in versions:
                if version.lifecycle_status in ("suspect", "replay_verified"):
                    pending = True
                elif (
                    version.lifecycle_status == "draft"
                    and version.app_map_id == app_map.id
                ):
                    pending = True
        if not pending:
            continue
        claim = AdvisoryClaim(session_factory, f"skill-reverify:{app_map.id}")
        if not await claim.acquire():
            continue

        async def run_claimed(
            claimed_map: Any = app_map, held: Any = claim
        ) -> None:
            try:
                async with asyncio.timeout(
                    SKILL_REVERIFY_WALL_BUDGET_SECONDS
                ):
                    await run_reverification_pass(
                        repository,
                        claimed_map,
                        executor_factory=executor_factory,
                    )
            except Exception:
                logger.exception(
                    "Skill re-verification failed for map %s", claimed_map.id
                )
            finally:
                await held.release()

        _reverify_tasks[app_map.id] = asyncio.create_task(run_claimed())
        if len(_reverify_tasks) >= SKILL_REVERIFY_SLOTS:
            break


async def run_skill_reverify_poller(
    session_factory: Any, *, executor_factory: Any = None
) -> None:
    """The worker's skill re-verification loop (doc 22 section 9.1):
    scan, claim, re-verify, heal, activate — forever, on the poll
    cadence. A claimed pass is bounded by the wall budget
    (asyncio.timeout), so a wedged pass cannot hold its slot."""
    from markettwin_execution_orchestrator.harvest.harvest_repository import (
        HarvestRepository,
    )

    repository = HarvestRepository(session_factory)
    factory = executor_factory or _production_executor_factory
    while True:
        try:
            await _poll_once(repository, session_factory, factory)
        except Exception:
            logger.exception("Skill re-verify poll failed; continuing")
        await asyncio.sleep(SKILL_REVERIFY_POLL_SECONDS)
