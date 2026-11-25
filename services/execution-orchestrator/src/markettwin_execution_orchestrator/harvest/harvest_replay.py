"""Skill replay verification (doc 16 section 5.8; Phase 3 doc 22
section 5.1).

A compiled skill earns 'replay_verified' only by DOING the journey
twice in two separate clean browser contexts with zero model calls.
The executor runs the definition's native steps through the case
executor unchanged (it never reads the locator bindings); the
terminal check compares the live final state against the harvested
one, with the signature-superset fallback recorded when it is used.
One code-only heal cycle is allowed after a failure — a locator walk
over the failing step's bindings, or a wait raise — and it never
touches the success assertion, the step set, the target page, the
element identity, or any value. A second failure quarantines the
skill version. Lifecycle writes pass the shared transition authority
via harvest/skill_library.transition_version (doc 22 section 5.1).
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from markettwin_shared.app_map_common import canonical_url


@dataclass
class ReplayAttempt:
    ok: bool
    failure_step: int | None = None
    failure_site: str | None = None
    final_url: str | None = None
    final_state_id: str | None = None
    superset_used: bool = False


class ReplayExecutor(Protocol):
    """Runs one full replay in one clean context (faked in tests)."""

    async def run_once(self, *, definition: dict[str, Any]) -> ReplayAttempt: ...


@dataclass(frozen=True)
class HealRecord:
    step: int
    from_locator: dict[str, Any]
    to_locator: dict[str, Any]


@dataclass
class VerifyResult:
    lifecycle_status: str  # 'replay_verified' | 'quarantined' | 'draft'
    heal: HealRecord | None
    attempts: int
    replay_ids: tuple[str, ...] = ()
    failed_replay_ids: tuple[str, ...] = ()


def _target_from_locator(locator: dict[str, Any]) -> dict[str, Any] | None:
    """Express one ranked locator as a native SemanticTarget, when the
    case executor can express it (role+name, label, or text)."""
    kind = locator.get("kind")
    value = str(locator.get("value") or "")
    if kind == "role_name" and "|" in value:
        role, name = value.split("|", 1)
        return {"role": role, "name": name}
    if kind == "label" and value:
        return {"label": value}
    if kind == "text" and value:
        return {"text": value}
    return None


def heal_definition(
    definition: dict[str, Any], failure: ReplayAttempt
) -> tuple[dict[str, Any], HealRecord] | None:
    """The one code-only heal (doc 16 section 5.8): rewrite the
    failing step's target from ITS OWN element's ranked bindings, or
    raise an existing wait. Returns None when nothing healable
    applies — an honest dead end, not an invention."""
    if failure.failure_step is None:
        return None
    steps = definition.get("steps")
    bindings = definition.get("locator_bindings")
    if not isinstance(steps, list) or failure.failure_step >= len(steps):
        return None
    step = steps[failure.failure_step]
    if not isinstance(step, dict):
        return None
    if step.get("action") == "click" and isinstance(bindings, list):
        binding = next(
            (
                item
                for item in bindings
                if isinstance(item, dict)
                and item.get("order") == failure.failure_step + 1
            ),
            None,
        )
        current_target = step.get("target") or {}
        if binding is not None:
            for locator in binding.get("locators") or []:
                candidate = _target_from_locator(dict(locator))
                if candidate is not None and candidate != current_target:
                    healed = dict(definition)
                    healed_steps = [dict(item) for item in steps]
                    healed_steps[failure.failure_step] = {
                        **step,
                        "target": candidate,
                    }
                    healed["steps"] = healed_steps
                    return healed, HealRecord(
                        step=failure.failure_step,
                        from_locator=dict(current_target),
                        to_locator=candidate,
                    )
    if failure.failure_site and "timeout" in failure.failure_site.casefold():
        for index, candidate_step in enumerate(steps):
            if (
                isinstance(candidate_step, dict)
                and candidate_step.get("action") == "wait"
                and index < failure.failure_step
            ):
                current_ms = int(candidate_step.get("milliseconds") or 0)
                if current_ms < 2000:
                    healed = dict(definition)
                    healed_steps = [dict(item) for item in steps]
                    healed_steps[index] = {
                        **candidate_step,
                        "milliseconds": min(2000, current_ms + 500),
                    }
                    healed["steps"] = healed_steps
                    return healed, HealRecord(
                        step=index,
                        from_locator={"milliseconds": current_ms},
                        to_locator={"milliseconds": min(2000, current_ms + 500)},
                    )
    return None


def _restamp_task_digest(definition: dict[str, Any]) -> dict[str, Any]:
    """A heal mutates a task skill's steps, so the contract digest
    stamped at compile time no longer describes the definition; the
    read-only matcher recomputes the digest and fails closed on a
    mismatch (A-50). Restamp before the mutated definition is
    persisted. Journey definitions carry no task block and pass
    through unchanged."""
    task = definition.get("task")
    if not isinstance(task, dict) or "contract_digest" not in task:
        return definition
    from markettwin_shared.task_skill import task_contract_digest

    stamped = dict(definition)
    stamped["task"] = {
        **task,
        "contract_digest": task_contract_digest(definition),
    }
    return stamped


async def verify_skill(
    *,
    repository: Any,
    app_map: Any,
    skill_version: Any,
    definition: dict[str, Any],
    executor: ReplayExecutor,
    start_state_id: str | None = None,
    on_failure: str = "quarantine",
    allow_heal: bool = True,
) -> VerifyResult:
    """Two clean-context passes, one heal cycle, or quarantine.

    ``start_state_id`` is the verifying map's base-page default-state
    identity: when given, the version's verified_fingerprint is the
    Phase 3 pair {start_state_id, terminal_state_id} the currency
    check compares (doc 22 section 5.3); without it the 1b scalar
    (the assertion's terminal identity) is written, which the
    currency check honestly cannot compare.

    ``on_failure='leave_draft'`` (the Phase 3 heal cycle, doc 22
    section 9.1) skips the quarantine write on failure: the healed
    draft stays in draft and the CALLER quarantines the suspect it
    was healed from."""
    from markettwin_execution_orchestrator.harvest.skill_library import (
        transition_version,
    )

    replay_ids: list[str] = []
    failed_replay_ids: list[str] = []

    async def run_passes(
        active_definition: dict[str, Any], *, heal_cycle: bool
    ) -> tuple[bool, ReplayAttempt | None, int]:
        attempts = 0
        for _ in range(2):
            started = datetime.now(UTC)
            attempt = await executor.run_once(definition=active_definition)
            attempts += 1
            row = await repository.insert_replay(
                app_map,
                skill_version_id=skill_version.id,
                result="passed" if attempt.ok else "failed",
                failure_step=attempt.failure_step,
                failure_site=attempt.failure_site,
                heal_cycle=heal_cycle,
                context_kind="clean",
                model_calls=0,
                started_at=started,
                finished_at=datetime.now(UTC),
            )
            replay_ids.append(str(row.id))
            if not attempt.ok:
                failed_replay_ids.append(str(row.id))
                return False, attempt, attempts
        return True, None, attempts

    total_attempts = 0
    passed, failure, attempts = await run_passes(definition, heal_cycle=False)
    total_attempts += attempts
    heal_record: HealRecord | None = None
    active_definition = definition
    if not passed and failure is not None and allow_heal:
        healed = heal_definition(definition, failure)
        if healed is not None:
            active_definition, heal_record = healed
            active_definition = _restamp_task_digest(active_definition)
            await repository.update_skill_version(
                skill_version.id,
                definition_json=active_definition,
                heal_count=(skill_version.heal_count or 0) + 1,
            )
            passed, failure, attempts = await run_passes(
                active_definition, heal_cycle=True
            )
            total_attempts += attempts
    if passed:
        assertion = active_definition.get("success_assertion") or {}
        fingerprint: Any = assertion.get("state_id")
        if start_state_id is not None:
            fingerprint = {
                "start_state_id": start_state_id,
                "terminal_state_id": assertion.get("state_id"),
            }
        await repository.update_skill_version(
            skill_version.id,
            last_replay_result="passed",
            last_replay_at=datetime.now(UTC),
            verified_fingerprint=fingerprint,
            definition_json=active_definition,
            replay_count=(skill_version.replay_count or 0) + total_attempts,
        )
        await transition_version(
            repository,
            skill_version.id,
            to_status="replay_verified",
            kind="verification_replay",
            evidence={"two_clean_replays": replay_ids[-2:]},
            result="passed",
        )
        return VerifyResult(
            "replay_verified",
            heal_record,
            total_attempts,
            replay_ids=tuple(replay_ids),
            failed_replay_ids=tuple(failed_replay_ids),
        )
    await repository.update_skill_version(
        skill_version.id,
        last_replay_result="failed",
        last_replay_at=datetime.now(UTC),
        definition_json=active_definition,
        replay_count=(skill_version.replay_count or 0) + total_attempts,
    )
    if on_failure == "leave_draft":
        return VerifyResult(
            "draft",
            heal_record,
            total_attempts,
            replay_ids=tuple(replay_ids),
            failed_replay_ids=tuple(failed_replay_ids),
        )
    heal_evidence: dict[str, Any]
    if heal_record is not None:
        heal_evidence = {
            "step": heal_record.step,
            "from_locator": heal_record.from_locator,
            "to_locator": heal_record.to_locator,
        }
    else:
        heal_evidence = {
            "applicable": False,
            "reason": "no_healable_locator_or_wait",
        }
    await transition_version(
        repository,
        skill_version.id,
        to_status="quarantined",
        kind="quarantine",
        evidence={
            "failed_replays": failed_replay_ids,
            "heal_record": heal_evidence,
        },
        result="failed",
    )
    return VerifyResult(
        "quarantined",
        heal_record,
        total_attempts,
        replay_ids=tuple(replay_ids),
        failed_replay_ids=tuple(failed_replay_ids),
    )


class CaseExecutionReplayExecutor:
    """Production executor: the definition's native steps through
    perform_case_action in a fresh clean context, then the terminal
    state captured and identified with the harvest's own machinery."""

    def __init__(self, controller: Any, *, app_map: Any) -> None:
        self._controller = controller
        self._app_map = app_map

    async def run_once(self, *, definition: dict[str, Any]) -> ReplayAttempt:
        from markettwin_shared.feature_plan import FeatureScope, TestCaseSpec

        from markettwin_execution_orchestrator.browser.contracts import (
            AllowedOrigin,
        )
        from markettwin_execution_orchestrator.harvest.harvest_capture import (
            capture_state,
        )
        from markettwin_execution_orchestrator.harvest.harvest_inventory import (
            distil_elements,
            distil_forms,
            identity_for,
        )
        from markettwin_execution_orchestrator.workflow.case_execution import (
            perform_case_action,
        )
        from markettwin_execution_orchestrator.workflow.skill_assertions import check_skill_assertions

        native = {
            key: definition[key]
            for key in (
                "case_id",
                "feature_key",
                "title",
                "kind",
                "steps",
                "expected",
                "safety",
                "estimated_seconds",
            )
            if key in definition
        }
        spec = TestCaseSpec.model_validate(native)
        parts = urlsplit(self._app_map.base_url)
        origin = AllowedOrigin(
            scheme=parts.scheme,
            hostname=parts.hostname or "",
            port=parts.port or (443 if parts.scheme == "https" else 80),
        )
        scope = FeatureScope(
            feature_key=spec.feature_key,
            goal="Replay the compiled journey for verification.",
            starting_url=self._app_map.base_url,
            allowed_origins=(f"{parts.scheme}://{parts.netloc}",),
        )
        execution_id = uuid4()
        journey_id = uuid4()
        handle = await self._controller.create_session(
            execution_id=execution_id,
            journey_id=journey_id,
            allowed_origins=[origin],
            network_policy="public_only",
            js_capture=True,
        )
        try:
            for index, action in enumerate(spec.steps):
                try:
                    failed = await check_skill_assertions(
                        self._controller, handle, spec, checkpoint=index,
                    )
                    if failed:
                        return ReplayAttempt(ok=False, failure_site=f"skill_assertion:{failed}")
                    await perform_case_action(
                        self._controller, handle, action, scope
                    )
                except Exception as exc:
                    return ReplayAttempt(
                        ok=False,
                        failure_step=index,
                        failure_site=f"case_execution:{type(exc).__name__}",
                    )
            for checkpoint in (len(spec.steps), None):
                failed = await check_skill_assertions(
                    self._controller, handle, spec, checkpoint=checkpoint,
                )
                if failed:
                    return ReplayAttempt(ok=False, failure_site=f"skill_assertion:{failed}")
            capture = await capture_state(
                self._controller,
                handle,
                execution_id=execution_id,
                journey_id=journey_id,
            )
            elements = distil_elements(capture)
            forms = distil_forms(capture)
            live_state_id, _, _ = identity_for(capture.url, elements, forms)
            assertion = definition.get("success_assertion") or {}
            url_ok = canonical_url(capture.url) == canonical_url(
                str(assertion.get("url") or "")
            )
            state_ok = live_state_id == assertion.get("state_id")
            superset_used = False
            if not state_ok and assertion.get("signature_superset_fallback"):
                harvested = set(assertion.get("element_signature") or [])
                live = {
                    f"{element['role']}|{element['name']}" for element in elements
                }
                if harvested and harvested <= live:
                    state_ok = True
                    superset_used = True
            return ReplayAttempt(
                ok=url_ok and state_ok,
                failure_step=None if (url_ok and state_ok) else len(spec.steps),
                failure_site=None
                if (url_ok and state_ok)
                else "harvest_replay:terminal_mismatch",
                final_url=capture.url,
                final_state_id=live_state_id,
                superset_used=superset_used,
            )
        finally:
            try:
                async with asyncio.timeout(30):
                    await self._controller.close_session(
                        session_id=handle.session_id
                    )
            except Exception:
                pass
