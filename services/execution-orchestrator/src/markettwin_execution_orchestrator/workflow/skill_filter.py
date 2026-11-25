"""The skill safety-mode filter (doc 22 sections 8.1, 8.3; doc 17
section 8).

Three small questions, one home: what safety class is one replay
step, may this run's mode select a whole skill, and what does the
plan say about the snapshot's skills. Step classes come from the
harness's own classifier (workflow.harness_items.classify_action) —
never a second taxonomy. A skill is selectable only when EVERY step
is allowed in the run's mode and every test_value_key a step names
resolves against the run's approved test data (doc 22 C8).
"""

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from markettwin_shared.feature_plan import CaseAction, ExpectedAssertion, TestCaseSpec
from markettwin_shared.task_skill import task_contract_digest
from pydantic import ValidationError

from markettwin_execution_orchestrator.workflow.harness_items import (
    NOT_EXERCISED_UNAPPROVED_DATA,
    classify_action,
    execution_allowed,
    skip_reason,
)

_READ_ACTIONS = frozenset({"navigate", "wait", "set_viewport", "focus_next"})
_WRITE_ACTIONS = frozenset({"fill", "select"})


def step_safety_class(step: Any) -> str:
    """One replay step's safety class (doc 17 section 8 item 2):
    navigation and waits are read; fill/select write data, so
    reversible; a click classifies by its target through the
    harness classifier; anything uncertain is irreversible."""
    if not isinstance(step, dict):
        return "irreversible"
    action = step.get("action")
    if action in _READ_ACTIONS:
        return "read"
    if action in _WRITE_ACTIONS:
        return "reversible"
    target = step.get("target")
    role = target.get("role") if isinstance(target, dict) else ""
    name = target.get("name") if isinstance(target, dict) else ""
    return classify_action(role=str(role or ""), name=str(name or ""))


def skill_selectability(
    definition: Any, *, mode: str, approved_keys: set[str]
) -> str | None:
    """None when the skill may be selected in this run; otherwise
    the recorded reason it may not: NOT_EXERCISED_UNAPPROVED_DATA
    for a step naming test data the run does not carry, the mode's
    skip reason for a step whose class exceeds the mode, or
    'mode_filter' for a definition too malformed to judge."""
    if not isinstance(definition, dict):
        return "mode_filter"
    steps = definition.get("steps")
    if not isinstance(steps, list) or not steps:
        return "mode_filter"
    for step in steps:
        if not isinstance(step, dict):
            return "mode_filter"
        key = step.get("test_value_key")
        if isinstance(key, str) and key and key not in approved_keys:
            return NOT_EXERCISED_UNAPPROVED_DATA
        safety = step_safety_class(step)
        if not execution_allowed(safety, mode):  # type: ignore[arg-type]
            return skip_reason(safety, mode) or "mode_filter"  # type: ignore[arg-type]
    return None


def plan_skills_section(
    app_map: dict[str, Any], *, mode: str, approved_keys: set[str]
) -> dict[str, object]:
    """The plan's skills section (doc 22 section 8.1), computed at
    planning time from the pinned snapshot block: how many active
    skills the run may replay, the replay items (joined to their
    journeys by skill_id), the mode-filtered names, and the withheld
    count the snapshot itself reported."""
    skills = app_map.get("skills")
    journeys = app_map.get("journeys")
    journey_by_skill: dict[str, dict[str, Any]] = {}
    if isinstance(journeys, list):
        for journey in journeys:
            if isinstance(journey, dict) and journey.get("skill_id"):
                journey_by_skill[str(journey["skill_id"])] = journey
    replay_items: list[dict[str, object]] = []
    mode_filtered: list[str] = []
    not_selected_reasons: dict[str, str] = {}
    active = 0
    if isinstance(skills, list):
        for entry in skills:
            if not isinstance(entry, dict):
                continue
            reason = skill_selectability(
                entry.get("definition"), mode=mode, approved_keys=approved_keys
            )
            if reason is not None:
                name = entry.get("name")
                if isinstance(name, str) and name:
                    mode_filtered.append(name)
                    # Doc 22 section 8.1.2: the plan record names
                    # WHY the skill was not selected ('mode_filter',
                    # a safety skip reason, or the unapproved-data
                    # marker).
                    not_selected_reasons[name] = reason
                continue
            active += 1
            journey = journey_by_skill.get(str(entry.get("skill_id") or ""))
            if journey is None:
                # No journey joins this skill in the snapshot (a
                # platform skill such as login — consumed by its own
                # seam, never as a Board replay item).
                continue
            replay_items.append(
                {
                    "skill_id": entry.get("skill_id"),
                    "skill_version_id": entry.get("skill_version_id"),
                    "journey_name": journey.get("name"),
                    "terminal_url": journey.get("terminal_url"),
                }
            )
    withheld = app_map.get("skills_withheld")
    return {
        "active": active,
        "replay_items": replay_items,
        "mode_filtered": mode_filtered,
        "not_selected_reasons": not_selected_reasons,
        "withheld": withheld if isinstance(withheld, int) else 0,
    }


def match_read_only_task_skill(
    app_map: dict[str, Any], case: TestCaseSpec, *, mode: str, start_url: str | None = None,
) -> tuple[UUID, dict[str, Any]] | None:
    """Select one active, exact task contract safe for the shared browser."""
    if case.preconditions or any(assertion.origin == "inferred" for assertion in case.expected):
        return None
    matches = []
    for entry in app_map.get("skills") or []:
        if not isinstance(entry, dict) or not entry.get("skill_id") or (
            entry.get("skill_kind"), entry.get("lifecycle_status")
        ) != ("task", "active"):
            continue
        definition = entry.get("definition")
        if not isinstance(definition, dict) or definition.get("feature_key") != case.feature_key:
            continue
        task = definition.get("task")
        terminal = definition.get("success_assertion")
        if (
            not isinstance(task, dict) or task.get("prerequisites") or task.get("inputs")
            or task.get("cleanup") != {"kind": "none_required"}
            or not isinstance(terminal, dict) or not terminal.get("url") or not terminal.get("state_id")
        ):
            continue
        if skill_selectability(definition, mode=mode, approved_keys=set()) is not None:
            continue
        if any(step_safety_class(step) != "read" for step in definition["steps"]):
            continue
        try:
            steps = tuple(CaseAction.model_validate(step) for step in definition["steps"])
            expected = tuple(ExpectedAssertion.model_validate(row) for row in definition.get("expected") or [])
        except ValidationError:
            continue
        # The digest normalizes URL queries and fragments. Require the exact
        # executable targets and predicates too, since those parts can alter behavior.
        if steps != case.steps or expected != case.expected:
            if start_url is None or steps != (CaseAction(action="navigate", url=start_url), *case.steps):
                continue
            shifted = tuple(
                row.model_copy(update={"after_step_ordinal": row.after_step_ordinal + 1})
                if row.after_step_ordinal is not None else row
                for row in case.expected
            )
            if expected != shifted:
                continue
        digest = task_contract_digest(definition)
        if digest != task.get("contract_digest") or definition.get("safety") != case.safety:
            continue
        try:
            version_id = UUID(str(entry.get("skill_version_id")))
        except ValueError:
            continue
        matches.append((version_id, entry))
    return matches[0] if len(matches) == 1 else None


# --- Task-skill matching (doc 29 section 7, as amended by the
# 2026-11-16 Codex consult 3, which wins over the plan text) ------
#
# feature_key is FEATURE-scoped: it pre-filters, it never decides.
# Equivalence is decided on the canonical contract (steps, targets,
# input bindings, expected predicates), and the stored
# contract_digest must recompute exactly -- a definition mutated
# after stamping is stale and never matches (A-50 restamps at heal
# persist). The token-overlap fallback only NOMINATES: it never
# authorises a state-changing replay, and an exact-key candidate
# failing a gate suppresses it. A matched replay must satisfy the
# REQUESTING case's expected outcomes, with value-bound outcomes
# rebound to this run's approved values.

_TOKEN = re.compile(r"[a-z0-9]+")
NOMINATION_THRESHOLD = 0.6


@dataclass(frozen=True)
class TaskSkillMatch:
    """The matcher's verdict for one case. On a match, ``entry``
    carries the definition rebound to this run's approved values
    (the stored definition is never mutated). On a non-match,
    ``reason`` is the recorded reason -- the record the run's
    harness.skill.not_selected event persists (doc 29 section
    7.2): no_candidate, digest_mismatch, contract_mismatch,
    containment, prerequisite, missing_inputs,
    nomination_state_changing, or a selectability reason verbatim
    (mode_filter, a safety skip reason, or the unapproved-data
    marker)."""

    status: str
    skill_version_id: UUID | None = None
    entry: dict[str, Any] | None = None
    via: str | None = None
    reason: str | None = None


def _token_overlap(left: str, right: str) -> float:
    """Normalised token Jaccard -- the reproducible definition the
    0.6 threshold was missing (consult 3): lowercase alphanumeric
    token sets, |A n B| / |A u B|."""
    a = set(_TOKEN.findall(left.casefold()))
    b = set(_TOKEN.findall(right.casefold()))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _value_bound_keys(task: dict[str, Any]) -> dict[str, str]:
    """assertion_id -> input key for the definition's value-bound
    outcomes (task.observed_assertions): those outcomes assert a
    value this run supplies by key, so equivalence compares them
    against the run's approved value, not the stored literal."""
    return {
        str(entry["assertion_id"]): str(entry["value_key"])
        for entry in task.get("observed_assertions") or []
        if isinstance(entry, dict)
        and entry.get("assertion_id")
        and entry.get("value_key")
    }


def task_case_mismatch(
    definition: Any,
    case: TestCaseSpec,
    *,
    approved_values: dict[str, str],
    start_url: str | None = None,
    check_digest: bool = True,
) -> str | None:
    """None when the skill's contract is the case's contract;
    otherwise 'digest_mismatch' (the stored digest does not
    recompute -- the definition drifted after stamping) or
    'contract_mismatch'. Steps must equal the case's steps (the
    compile-prepended initial navigate is the one allowed extra),
    and the case's expected outcomes must be exactly the outcomes
    the skill checks -- with value-bound outcomes asserting THIS
    run's approved value. A replay that checked only the skill's
    own outcomes while marking the case satisfied would be false
    coverage (consult 3, worst failure); this equality is what
    forbids it."""
    if not isinstance(definition, dict):
        return "contract_mismatch"
    task = definition.get("task")
    if not isinstance(task, dict):
        return "contract_mismatch"
    if check_digest:
        stamped = task.get("contract_digest")
        if not stamped or task_contract_digest(definition) != stamped:
            return "digest_mismatch"
    if definition.get("safety") != case.safety:
        return "contract_mismatch"
    try:
        steps = tuple(
            CaseAction.model_validate(step) for step in definition["steps"]
        )
        expected = tuple(
            ExpectedAssertion.model_validate(row)
            for row in definition.get("expected") or []
        )
    except (ValidationError, KeyError, TypeError):
        return "contract_mismatch"
    shift = 0
    if steps != case.steps:
        if start_url is None:
            return "contract_mismatch"
        prepended = (CaseAction(action="navigate", url=start_url), *case.steps)
        if steps != prepended:
            return "contract_mismatch"
        shift = 1
    bound = _value_bound_keys(task)
    skill_by_id = {row.assertion_id: row for row in expected}
    if set(skill_by_id) != {row.assertion_id for row in case.expected}:
        return "contract_mismatch"
    for row in case.expected:
        skill_row = skill_by_id[row.assertion_id]
        if skill_row.oracle != row.oracle:
            return "contract_mismatch"
        ordinal = (
            row.after_step_ordinal + shift
            if row.after_step_ordinal is not None
            else None
        )
        if skill_row.after_step_ordinal != ordinal:
            return "contract_mismatch"
        key = bound.get(row.assertion_id)
        if key is not None and key in approved_values:
            # Value-bound: the case must assert the value this run
            # will actually produce under that key, and its target
            # must be the skill's target rebound to that value.
            if row.expected_value != approved_values[key]:
                return "contract_mismatch"
            skill_target = skill_row.target
            if (
                skill_target is not None
                and row.target is not None
                and skill_target.text is not None
                and skill_target.text == skill_row.expected_value
            ):
                skill_target = skill_target.model_copy(
                    update={"text": row.expected_value}
                )
            if skill_target != row.target:
                return "contract_mismatch"
            continue
        if (
            skill_row.expected_value != row.expected_value
            or skill_row.target != row.target
        ):
            return "contract_mismatch"
    return None


def _step_signature(step: CaseAction) -> tuple:
    target = step.target
    return (
        step.action,
        (
            target.role,
            target.name,
            target.label,
            target.text,
            target.scope_role,
            target.scope_name,
        )
        if target is not None
        else None,
        step.test_value_key,
    )


def _containment_reason(definition: dict[str, Any], case: TestCaseSpec) -> str | None:
    """The action-containment gate (consult 3): the skill's
    state-changing steps must be a subset of the requesting case's
    own step signatures -- a skill may never do more to the
    product than the case it replaces would have done. Defence in
    depth behind contract equivalence (which already requires
    step equality); it is the load-bearing gate if equivalence is
    ever loosened, and it guards the nomination path."""
    try:
        steps = tuple(
            CaseAction.model_validate(step) for step in definition["steps"]
        )
    except (ValidationError, KeyError, TypeError):
        return "contract_mismatch"
    case_signatures = {_step_signature(step) for step in case.steps}
    for step, raw_step in zip(steps, definition["steps"], strict=True):
        if step_safety_class(raw_step) == "read":
            continue
        if _step_signature(step) not in case_signatures:
            return "containment"
    return None


def _prerequisite_reason(
    task: dict[str, Any],
    definition: dict[str, Any],
    *,
    approved_keys: set[str],
    active_names: set[str],
    start_url: str | None,
) -> str | None:
    """Every declared prerequisite must be establishable for this
    run (doc 29 section 7.1 gate 3). 'authenticated' is noted, not
    decided, here -- the login seam establishes it at execution;
    the rest are decidable from the run's own data."""
    for entry in task.get("prerequisites") or []:
        if not isinstance(entry, dict):
            return "prerequisite"
        kind = entry.get("kind")
        if kind == "input_available":
            if entry.get("input_key") not in approved_keys:
                return "prerequisite"
        elif kind == "skill_active":
            if entry.get("skill_name") not in active_names:
                return "prerequisite"
        elif kind == "on_page":
            url = entry.get("url")
            navigations = {
                step.get("url")
                for step in definition.get("steps") or []
                if isinstance(step, dict) and step.get("action") == "navigate"
            }
            if url != start_url and url not in navigations:
                return "prerequisite"
        elif kind == "authenticated":
            continue
        else:
            return "prerequisite"
    return None


def _inputs_reason(
    task: dict[str, Any], case: TestCaseSpec, *, approved_keys: set[str]
) -> str | None:
    """Gate 4: every required declared input is approved for this
    run, and every data key the CASE's steps need is one the skill
    declares -- the skill must be able to do the task's data work,
    not merely resemble it."""
    declared: set[str] = set()
    for entry in task.get("inputs") or []:
        if not isinstance(entry, dict) or not entry.get("key"):
            return "missing_inputs"
        declared.add(str(entry["key"]))
        if entry.get("required", True) and str(entry["key"]) not in approved_keys:
            return "missing_inputs"
    for step in case.steps:
        if step.test_value_key and step.test_value_key not in declared:
            return "missing_inputs"
    return None


def _evaluate_candidate(
    entry: dict[str, Any],
    case: TestCaseSpec,
    *,
    mode: str,
    approved_values: dict[str, str],
    active_names: set[str],
    start_url: str | None,
) -> str | None:
    """One candidate through the gate pipeline; None when it
    matches, else the first failing gate's reason. Order:
    contract equivalence (incl. digest) -> containment ->
    prerequisites -> inputs -> selectability."""
    definition = entry.get("definition")
    if not isinstance(definition, dict):
        return "contract_mismatch"
    task = definition.get("task")
    if not isinstance(task, dict):
        return "contract_mismatch"
    reason = task_case_mismatch(
        definition, case, approved_values=approved_values, start_url=start_url
    )
    if reason is not None:
        return reason
    reason = _containment_reason(definition, case)
    if reason is not None:
        return reason
    if case.preconditions:
        return "prerequisite"
    reason = _prerequisite_reason(
        task,
        definition,
        approved_keys=set(approved_values),
        active_names=active_names,
        start_url=start_url,
    )
    if reason is not None:
        return reason
    reason = _inputs_reason(task, case, approved_keys=set(approved_values))
    if reason is not None:
        return reason
    return skill_selectability(
        definition, mode=mode, approved_keys=set(approved_values)
    )


def match_task_skill(
    app_map: dict[str, Any],
    case: TestCaseSpec,
    *,
    mode: str,
    approved_values: dict[str, str] | None = None,
    start_url: str | None = None,
) -> TaskSkillMatch:
    """Select the one active task skill a planned case may reuse
    (doc 29 section 7 as amended by consult 3): scope pre-filter
    over the snapshot's served skills, feature_key pre-filter,
    then the gate pipeline per candidate. Deterministic: exact-key
    matches before token nominations, then highest version. On a
    match the returned entry's definition is rebound to this
    run's approved values; the stored definition is never
    mutated. On a non-match the reason is recorded on the result
    -- the case falls back to exploration with the reason named,
    never silently."""
    values = dict(approved_values or {})
    skills = app_map.get("skills")
    entries = (
        [entry for entry in skills if isinstance(entry, dict)]
        if isinstance(skills, list)
        else []
    )
    map_id = app_map.get("map_id")
    candidates: list[dict[str, Any]] = []
    for entry in entries:
        if (entry.get("skill_kind"), entry.get("lifecycle_status")) != (
            "task",
            "active",
        ):
            continue
        if (
            entry.get("app_map_id")
            and map_id
            and str(entry["app_map_id"]) != str(map_id)
        ):
            continue
        definition = entry.get("definition")
        if not isinstance(definition, dict) or not isinstance(
            definition.get("task"), dict
        ):
            continue
        if not entry.get("skill_id"):
            continue
        try:
            UUID(str(entry.get("skill_version_id")))
        except ValueError:
            continue
        candidates.append(entry)
    active_names = {
        str(entry["name"])
        for entry in entries
        if entry.get("lifecycle_status") == "active" and entry.get("name")
    }

    def rank(entry: dict[str, Any]) -> tuple[int, str]:
        version = entry.get("version_number") or entry.get("version") or 0
        return (
            -(version if isinstance(version, int) else 0),
            str(entry.get("skill_version_id")),
        )

    def feature_key_of(entry: dict[str, Any]) -> Any:
        definition = entry["definition"]
        return definition.get("feature_key") or definition["task"].get(
            "feature_key"
        )

    def matched(entry: dict[str, Any], *, via: str) -> TaskSkillMatch:
        return TaskSkillMatch(
            status="matched",
            skill_version_id=UUID(str(entry["skill_version_id"])),
            entry={
                **entry,
                "definition": rebind_task_assertions(
                    entry["definition"], values
                ),
            },
            via=via,
        )

    exact = sorted(
        (entry for entry in candidates if feature_key_of(entry) == case.feature_key),
        key=rank,
    )
    first_reason: str | None = None
    for entry in exact:
        reason = _evaluate_candidate(
            entry,
            case,
            mode=mode,
            approved_values=values,
            active_names=active_names,
            start_url=start_url,
        )
        if reason is None:
            return matched(entry, via="exact")
        if first_reason is None:
            first_reason = reason
    if exact:
        # An exact-key candidate failed a gate: the token fallback
        # is suppressed (consult 3) and that gate's reason is the
        # recorded one.
        return TaskSkillMatch(status="not_selected", reason=first_reason)

    nominated: list[tuple[float, dict[str, Any]]] = []
    for entry in candidates:
        task = entry["definition"]["task"]
        overlap = _token_overlap(
            case.title,
            f"{entry.get('name') or ''} {task.get('purpose') or ''}",
        )
        if overlap >= NOMINATION_THRESHOLD:
            nominated.append((overlap, entry))
    nominated.sort(key=lambda pair: (-pair[0], rank(pair[1])))
    nomination_reason: str | None = None
    for _overlap, entry in nominated:
        steps = entry["definition"].get("steps") or []
        if any(step_safety_class(step) != "read" for step in steps):
            # Nomination never authorises a state-changing replay
            # (consult 3, amending OD-4): prefer a clean miss.
            if nomination_reason is None:
                nomination_reason = "nomination_state_changing"
            continue
        reason = _evaluate_candidate(
            entry,
            case,
            mode=mode,
            approved_values=values,
            active_names=active_names,
            start_url=start_url,
        )
        if reason is None:
            return matched(entry, via="token_nomination")
        if nomination_reason is None:
            nomination_reason = reason
    return TaskSkillMatch(
        status="not_selected", reason=nomination_reason or "no_candidate"
    )


def rebind_task_assertions(
    definition: Any, values: dict[str, str]
) -> dict[str, Any]:
    """A copy of a task definition with its value-bound outcomes
    rebound to the current pass's values (doc 29 sections 5-6): for
    each observed_assertions entry whose value_key is present in
    ``values``, the matching expected entry's expected_value (and
    its target text, when it equals the old value) is replaced. The
    stored definition is never mutated; secret_ref inputs are never
    value-bound (they are not in observed_assertions)."""
    import copy

    rebound = copy.deepcopy(definition)
    if not isinstance(rebound, dict):
        return rebound
    task = rebound.get("task")
    task = task if isinstance(task, dict) else {}
    bindings = {
        entry.get("assertion_id"): entry.get("value_key")
        for entry in task.get("observed_assertions") or []
        if isinstance(entry, dict) and entry.get("value_key")
    }
    for entry in rebound.get("expected") or []:
        if not isinstance(entry, dict):
            continue
        key = bindings.get(entry.get("assertion_id"))
        if key and key in values:
            old = entry.get("expected_value")
            entry["expected_value"] = values[key]
            target = entry.get("target")
            if isinstance(target, dict) and target.get("text") == old:
                target["text"] = values[key]
    return rebound
