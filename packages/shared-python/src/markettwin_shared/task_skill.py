"""The task-skill contract validator (doc 29 section 3.3, as amended
by the 2026-11-16 Codex consults).

One pure function beside the lifecycle table: every writer of a task
skill definition (candidate creation, trace compile, verification
entry, heal re-check) calls it, and a definition that fails is never
written as a version -- the rejection codes are recorded on the
attempt instead. Documented expectations live in the definition's
``task.documented_expectations`` and are NEVER executed; only
observed, browser-checkable outcomes may sit in ``expected``.

Outcome authorisation is an ALLOWLIST (consult B1): an ``expected``
entry is authorised only by an ``observation`` or ``owner-rule``
declaration in ``task.observed_assertions``, and the declaration is
never self-proving -- it must resolve against the TRUSTED EVIDENCE
CONTEXT the host supplies (``evidence``): the recorded assertion
occurrences from the source execution (specs + results, assembled
host-side) and the authenticated owner decision records. Resolution
is by canonical predicate equality (consult B3): P = (scope,
checkpoint, oracle, full semantic target, type(expected_value),
expected_value) with safe_url normalisation on URL values (B5).
Assertion-ID membership is NOT evidence: IDs are case-local and the
executor copies origin from the expectation, so an ID match with a
changed value is a mismatch. ``inferred`` (and every other
non-allowlist origin) rejects, never translates (B6); the Jaccard
text gate is a secondary tripwire for near-verbatim claim copies,
never the load-bearing check (B4).

The validator works on raw definition dicts. Caller context it
cannot see on its own: the pinned map's inventory (``inventory`` /
``page_urls``), the source trace (``trace``, for the trace-shape
rules), the trusted evidence context (``evidence``), and step safety
classes (``step_safety``, parallel to ``steps``); without a safety
classifier, fill/select steps -- the data-writing actions -- are
treated as state-changing, the conservative reading for the cleanup
rule.
"""

import hashlib
import json
import re
from typing import Any, get_args

from markettwin_shared.feature_plan import CaseAction, Oracle

MISSING_TASK_BLOCK = "missing_task_block"
MALFORMED_PREREQUISITE = "malformed_prerequisite"
MISSING_EVIDENCE = "missing_evidence"
UNSUPPORTED_TARGET = "unsupported_target"
MISSING_INPUT_BINDING = "missing_input_binding"
UNCHECKABLE_OUTCOME = "uncheckable_outcome"
MARKETING_CLAIM_OUTCOME = "marketing_claim_outcome"
UNOBSERVED_OUTCOME = "unobserved_outcome"
OUTCOME_EVIDENCE_MISMATCH = "outcome_evidence_mismatch"
INCOMPLETE_TRACE = "incomplete_trace"
ASSISTED_STEP_UNCOMPILABLE = "assisted_step_uncompilable"
MISSING_CLEANUP = "missing_cleanup"

_ORACLES = set(get_args(Oracle))
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_TOKEN = re.compile(r"[a-z0-9]+")
_PREREQUISITE_KINDS = ("authenticated", "on_page", "input_available", "skill_active")
_INPUT_KINDS = ("text", "secret_ref", "selection")
_ALLOWED_ORIGINS = ("observation", "owner-rule")
_TARGET_FIELDS = ("role", "name", "label", "text", "scope_role", "scope_name")
# The token-overlap tripwire (doc 29 section 3.3) [J] -- secondary
# only; the evidence resolution above is the load-bearing gate.
MARKETING_TEXT_THRESHOLD = 0.8


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.casefold()))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _canonical_url_key(url: str) -> str:
    return url.rstrip("/") or "/"


def _url_key(value: Any) -> Any:
    """safe_url normalisation (consult B5): strip query + fragment."""
    if isinstance(value, str):
        return value.split("?")[0].split("#")[0]
    return value


def _canonical_target(target: Any) -> tuple | None:
    if not isinstance(target, dict):
        return None
    return tuple(
        sorted(
            (field, str(target[field]))
            for field in _TARGET_FIELDS
            if target.get(field) is not None
        )
    )


def _canonical_value(oracle: Any, value: Any) -> Any:
    if oracle in ("url", "url_path_v1"):
        value = _url_key(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _predicate(
    scope: Any, *, checkpoint: Any, oracle: Any, target: Any, expected_value: Any
) -> tuple:
    """The canonical outcome predicate (consult B3)."""
    return (
        str(scope or ""),
        checkpoint if isinstance(checkpoint, int) else None,
        str(oracle or ""),
        _canonical_target(target),
        type(expected_value).__name__,
        _canonical_value(oracle, expected_value),
    )


def _entry_predicate(scope: Any, entry: dict[str, Any]) -> tuple:
    return _predicate(
        scope,
        checkpoint=entry.get("after_step_ordinal"),
        oracle=entry.get("oracle"),
        target=entry.get("target"),
        expected_value=entry.get("expected_value"),
    )


def task_contract_digest(definition: Any) -> str:
    """The contract digest (consult A1): a canonical hash of the
    steps, targets, input bindings, prerequisites and expected
    outcome predicates of a task-skill definition. feature_key is
    feature-scoped and shared by many cases, so selection matches
    on this digest; the key is only a cheap pre-filter."""
    if not isinstance(definition, dict):
        return ""
    task = definition.get("task")
    task = task if isinstance(task, dict) else {}
    scope = task.get("feature_key") or definition.get("feature_key")
    steps: list[Any] = []
    for step in definition.get("steps") or []:
        if not isinstance(step, dict):
            continue
        target = step.get("target")
        steps.append(
            {
                "action": step.get("action"),
                "url": _url_key(step.get("url")) if step.get("url") else None,
                "target": (
                    {field: target.get(field) for field in _TARGET_FIELDS
                     if isinstance(target, dict) and target.get(field) is not None}
                    if isinstance(target, dict) else None
                ),
                "test_value_key": step.get("test_value_key"),
                "milliseconds": step.get("milliseconds"),
                "action_id": step.get("action_id"),
                "preset": step.get("preset"),
            }
        )
    inputs = sorted(
        json.dumps({key: entry.get(key) for key in (
            "key", "kind", "required", "disposable", "generator", "prefix", "label"
        )}, sort_keys=True, default=str)
        for entry in task.get("inputs") or []
        if isinstance(entry, dict) and entry.get("key")
    )
    prerequisites = sorted(
        json.dumps(
            {
                key: entry.get(key)
                for key in ("kind", "url", "input_key", "skill_name")
                if entry.get(key) is not None
            },
            sort_keys=True,
            default=str,
        )
        for entry in task.get("prerequisites") or []
        if isinstance(entry, dict)
    )
    expected = sorted(
        json.dumps(list(_entry_predicate(scope, entry)), default=str)
        for entry in definition.get("expected") or []
        if isinstance(entry, dict)
    )
    canonical = {
        "feature_key": scope,
        "steps": steps,
        "inputs": inputs,
        "prerequisites": prerequisites,
        "expected": expected,
        "success_assertion": definition.get("success_assertion"),
        "cleanup": task.get("cleanup"),
        "locator_bindings": definition.get("locator_bindings"),
        "safety": definition.get("safety"),
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def validate_task_skill(
    definition: Any,
    *,
    inventory: list[dict[str, Any]] | None = None,
    page_urls: list[str] | None = None,
    trace: dict[str, Any] | None = None,
    step_safety: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
) -> list[str]:
    """Return the rejection codes for one task-skill definition;
    an empty list means the definition satisfies the contract."""
    codes: list[str] = []

    def reject(code: str) -> None:
        if code not in codes:
            codes.append(code)

    if not isinstance(definition, dict):
        return [MISSING_TASK_BLOCK]
    task = definition.get("task")
    if not isinstance(task, dict):
        return [MISSING_TASK_BLOCK]

    purpose = task.get("purpose")
    if not isinstance(purpose, str) or not 1 <= len(purpose) <= 200:
        reject(MISSING_TASK_BLOCK)
    feature_key = task.get("feature_key")
    if (
        not isinstance(feature_key, str)
        or len(feature_key) > 64
        or not _IDENTIFIER.match(feature_key)
    ):
        reject(MISSING_TASK_BLOCK)
    scope = feature_key or definition.get("feature_key")

    # --- evidence (missing_evidence) --------------------------------
    source = task.get("source")
    source_kind = source.get("kind") if isinstance(source, dict) else None
    if source_kind == "run_execution":
        evidence_refs = task.get("evidence_refs")
        kinds = (
            {entry.get("kind") for entry in evidence_refs if isinstance(entry, dict)}
            if isinstance(evidence_refs, list)
            else set()
        )
        if not (
            source.get("run_id")
            and source.get("case_id")
            and kinds & {"run_execution", "task_trace"}
        ):
            reject(MISSING_EVIDENCE)
    elif source_kind == "document":
        if not (isinstance(source, dict) and source.get("document_ref")):
            reject(MISSING_EVIDENCE)
    else:
        reject(MISSING_EVIDENCE)

    # --- prerequisites (kinded, never free text) ---------------------
    prerequisites = task.get("prerequisites")
    if prerequisites is None:
        prerequisites = []
    if not isinstance(prerequisites, list):
        reject(MALFORMED_PREREQUISITE)
        prerequisites = []
    for entry in prerequisites:
        if not isinstance(entry, dict) or entry.get("kind") not in _PREREQUISITE_KINDS:
            reject(MALFORMED_PREREQUISITE)
            continue
        if entry["kind"] == "on_page" and not isinstance(entry.get("url"), str):
            reject(MALFORMED_PREREQUISITE)
        if entry["kind"] == "input_available" and not isinstance(
            entry.get("input_key"), str
        ):
            reject(MALFORMED_PREREQUISITE)
        if entry["kind"] == "skill_active" and not isinstance(
            entry.get("skill_name"), str
        ):
            reject(MALFORMED_PREREQUISITE)

    # --- declared inputs ---------------------------------------------
    inputs = task.get("inputs")
    if inputs is None:
        inputs = []
    declared: dict[str, dict[str, Any]] = {}
    if not isinstance(inputs, list):
        reject(MISSING_INPUT_BINDING)
        inputs = []
    for entry in inputs:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("key"), str)
            or not _IDENTIFIER.match(str(entry.get("key")))
            or entry.get("kind") not in _INPUT_KINDS
        ):
            reject(MISSING_INPUT_BINDING)
            continue
        declared[str(entry["key"])] = entry
        generator = entry.get("generator")
        if generator is not None and (
            generator not in {"unique_text", "unique_email"} or entry["kind"] != "text"
        ):
            reject(MISSING_INPUT_BINDING)

    # --- steps: native schema + (optionally) map inventory -----------
    steps = definition.get("steps")
    if steps is None:
        steps = []
    if not isinstance(steps, list):
        reject(UNSUPPORTED_TARGET)
        steps = []
    inventory_entries = inventory or []
    known_pages = (
        {_canonical_url_key(url) for url in page_urls}
        if page_urls is not None
        else None
    )
    bound_keys: set[str] = set()
    for step in steps:
        if not isinstance(step, dict):
            reject(UNSUPPORTED_TARGET)
            continue
        try:
            action = CaseAction.model_validate(step)
        except Exception:
            reject(UNSUPPORTED_TARGET)
            continue
        if action.test_value_key:
            bound_keys.add(action.test_value_key)
        if inventory is None:
            continue
        if action.action == "navigate":
            if (
                known_pages is not None
                and action.url is not None
                and _canonical_url_key(action.url) not in known_pages
            ):
                reject(UNSUPPORTED_TARGET)
            continue
        target = action.target
        if target is None:
            continue
        resolved = False
        if target.role is not None and target.name is not None:
            resolved = any(
                entry.get("role") == target.role and entry.get("name") == target.name
                for entry in inventory_entries
            )
        elif target.label is not None:
            resolved = any(
                entry.get("label") == target.label for entry in inventory_entries
            )
        elif target.text is not None:
            resolved = any(
                entry.get("name") == target.text for entry in inventory_entries
            )
        if not resolved:
            reject(UNSUPPORTED_TARGET)

    # --- input bindings (missing_input_binding) ----------------------
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("action") in ("fill", "select"):
            key = step.get("test_value_key")
            if not isinstance(key, str) or key not in declared:
                reject(MISSING_INPUT_BINDING)
    observed = task.get("observed_assertions")
    observed_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(observed, list):
        for entry in observed:
            if isinstance(entry, dict) and isinstance(entry.get("assertion_id"), str):
                observed_by_id[str(entry["assertion_id"])] = entry
                if isinstance(entry.get("value_key"), str):
                    bound_keys.add(str(entry["value_key"]))
    for key, entry in declared.items():
        if entry.get("required", True) and key not in bound_keys:
            reject(MISSING_INPUT_BINDING)

    # --- outcomes: allowlist origins + trusted evidence resolution ---
    expected = definition.get("expected")
    if expected is None:
        expected = []
    if not isinstance(expected, list):
        reject(UNCHECKABLE_OUTCOME)
        expected = []
    if not expected and source_kind == "run_execution":
        reject(UNCHECKABLE_OUTCOME)
    documented_texts: list[str] = []
    documented = task.get("documented_expectations")
    if isinstance(documented, list):
        for entry in documented:
            if isinstance(entry, dict) and isinstance(entry.get("text"), str):
                documented_texts.append(entry["text"])
    recorded: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    if isinstance(evidence, dict):
        recorded = [
            entry for entry in evidence.get("assertions") or []
            if isinstance(entry, dict)
        ]
        decisions = [
            entry for entry in evidence.get("owner_decisions") or []
            if isinstance(entry, dict)
        ]
    for entry in expected:
        if not isinstance(entry, dict):
            reject(UNCHECKABLE_OUTCOME)
            continue
        oracle = entry.get("oracle")
        value = entry.get("expected_value")
        if oracle not in _ORACLES or value is None:
            reject(UNCHECKABLE_OUTCOME)
        assertion_id = entry.get("assertion_id")
        declaration = (
            observed_by_id.get(str(assertion_id))
            if isinstance(assertion_id, str)
            else None
        )
        origin = (
            declaration.get("origin")
            if declaration is not None
            else entry.get("origin")
        )
        if origin in ("documentation", "model-draft"):
            reject(MARKETING_CLAIM_OUTCOME)
            continue
        if oracle == "value" and origin != "observation":
            # A field's current value is provable only by having
            # read it back in a browser (doc 29 section 3.3).
            reject(UNCHECKABLE_OUTCOME)
        resolved = False
        if origin == "observation":
            if declaration is None:
                reject(UNOBSERVED_OUTCOME)
                continue
            predicate = _entry_predicate(scope, entry)
            matches = [
                record for record in recorded
                if _entry_predicate(scope, record) == predicate
            ]
            resolved = (
                bool(matches)
                and all(record.get("status") == "satisfied"
                        and record.get("has_evidence") is True for record in matches)
            )
            if not resolved:
                reject(OUTCOME_EVIDENCE_MISMATCH)
        elif origin == "owner-rule":
            decision_ref = (
                declaration.get("decision_ref")
                if declaration is not None
                else None
            )
            predicate = _entry_predicate(scope, entry)
            resolved = (
                isinstance(decision_ref, str)
                and bool(decision_ref)
                and any(
                    record.get("decision_ref") == decision_ref
                    and _entry_predicate(scope, record) == predicate
                    for record in decisions
                )
            )
            if not resolved:
                reject(OUTCOME_EVIDENCE_MISMATCH)
        else:
            # Allowlist (B1/B6): inferred, phase-2 eligibility and
            # every other origin reject; nothing translates.
            reject(UNOBSERVED_OUTCOME)
        if not resolved and documented_texts and isinstance(value, (str, int, bool)):
            # Secondary tripwire (B4): a near-verbatim copy of a
            # documented claim standing in for an outcome.
            outcome_tokens = _tokens(f"{assertion_id or ''} {value}")
            for text in documented_texts:
                if _jaccard(outcome_tokens, _tokens(text)) >= MARKETING_TEXT_THRESHOLD:
                    reject(MARKETING_CLAIM_OUTCOME)
                    break
    if source_kind == "run_execution" and steps:
        success = definition.get("success_assertion")
        if not isinstance(success, dict) or not success.get("url"):
            reject(UNCHECKABLE_OUTCOME)

    # --- cleanup for state-changing steps (missing_cleanup) ----------
    if steps:
        if step_safety is not None and len(step_safety) == len(steps):
            classes = list(step_safety)
        else:
            classes = [
                "reversible"
                if isinstance(step, dict) and step.get("action") in ("fill", "select")
                else "irreversible"
                if not isinstance(step, dict) or step.get("action") in ("click", "check", "uncheck")
                else "read"
                for step in steps
            ]
        changing = [
            index for index, kind in enumerate(classes)
            if kind in ("reversible", "irreversible")
        ]
        if changing:
            cleanup = task.get("cleanup")
            if not isinstance(cleanup, dict) or cleanup.get("kind") not in (
                "compensating_steps",
                "reset_action",
            ):
                reject(MISSING_CLEANUP)
            for index in changing:
                step = steps[index]
                if not isinstance(step, dict):
                    continue
                if step.get("action") in ("fill", "select"):
                    key = step.get("test_value_key")
                    entry = declared.get(str(key))
                    if entry is not None and not entry.get("disposable", False):
                        # Verification replays must use disposable data even with cleanup:
                        # cleanup cannot guarantee reversal of effects involving real inputs.
                        reject(MISSING_CLEANUP)

    # --- trace-shape rules (compile time) -----------------------------
    if trace is not None:
        if trace.get("complete") is not True or not isinstance(
            trace.get("terminal"), dict
        ):
            reject(INCOMPLETE_TRACE)
        for item in trace.get("spec_steps") or []:
            if isinstance(item, dict) and item.get("outcome") == "failed":
                reject(INCOMPLETE_TRACE)
        for segment in trace.get("segments") or []:
            if isinstance(segment, dict) and segment.get("kind") == "assisted_other":
                reject(ASSISTED_STEP_UNCOMPILABLE)

    return codes
