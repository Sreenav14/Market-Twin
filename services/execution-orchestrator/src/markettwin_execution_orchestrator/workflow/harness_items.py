"""Inventory → items → single-item cases, with the safety gate.

The page index (``BrowserController.get_page_index``) is the only
inventory source. Each entry carries exactly ``ordinal``, ``role``,
``name`` and ``name_source`` — no CSS path and no form metadata — so
items use the §1.4 identity scheme (state fingerprint + role + name +
occurrence index, via ``harness_state``'s own functions) and the
locator records the index ordinal as the fallback the index data
supports; ``css_path`` stays None. The form-field signature is the
names of the index's field roles (textbox / searchbox / combobox).

Safety classification (§5 rule 3) is deterministic code over element
semantics: role + action kind + whole-token verb semantics of the
normalised name, mirroring the term sets the browser layer already
enforces in ``browser/sensitive_action_policy.py`` (including its
filter-reset special case). A name alone never classifies — every
rule also requires an actionable role — and anything uncertain is
``irreversible``. Irreversible items are inventoried and reported,
never executed autonomously. Harness budgets come from
``harness_state`` only: this module never reads ``testing_depth`` or
``feature_case_limit``.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Literal

from markettwin_execution_orchestrator.agents.schemas.test_case import (
    CaseAction,
    ExpectedAssertion,
    SafeTestValue,
    SemanticTarget,
    TestCaseSpec,
)
from markettwin_execution_orchestrator.workflow.harness_state import (
    HarnessItem,
    HarnessState,
    item_id_for,
)

SafetyClass = Literal["read", "reversible", "irreversible"]
RunSafetyMode = Literal["read_only", "standard"]

NOT_EXERCISED_IRREVERSIBLE = "not exercised — requires approval or test mode"
NOT_EXERCISED_READ_ONLY = "not exercised — read-only first run"
NOT_EXERCISED_UNAPPROVED_DATA = "not exercised — no approved test data for this field"

# The could-not-check reason for an unnamed control (doc 24 section
# 6.2): the item is formed and counted, and the harness gate accounts
# it with this reason instead of executing it.
NOT_CHECKED_UNNAMED_CONTROL = "unnamed_control"

FIELD_ROLES = frozenset({"textbox", "searchbox", "combobox"})
ACTION_ROLES = frozenset({
    "button", "link", "textbox", "searchbox", "combobox",
    "checkbox", "radio", "tab", "menuitem",
})

# Mirrors _HARD_DENY_TERMS in browser/sensitive_action_policy.py, plus
# the §5 rule 3 additions (pay, publish, withdraw, refund).
_IRREVERSIBLE_PHRASES = (
    "pay now", "grant access", "revoke access", "change role",
    "export data", "transfer funds", "close account", "delete account",
)
_IRREVERSIBLE_TOKENS = frozenset({
    "delete", "remove", "purchase", "buy", "pay", "payment", "checkout",
    "send", "publish", "invite", "grant", "revoke", "transfer",
    "administrator", "permission", "permissions", "withdraw", "refund",
})
_READ_TOKENS = frozenset({
    "search", "find", "filter", "sort", "view", "open", "show", "hide",
    "expand", "collapse", "close", "cancel", "back", "next", "previous",
    "refresh", "reload", "load", "preview", "print", "help", "dismiss",
})
_REVERSIBLE_TOKENS = frozenset({
    "save", "add", "create", "edit", "update", "apply", "submit",
    "continue", "confirm", "generate", "toggle", "enable", "disable",
    "draft", "check", "verify", "validate", "calculate", "copy",
    "duplicate", "sign", "log",
})
_FILTER_RESET_NAMES = frozenset({
    "remove filters", "clear filters", "reset filters",
})


def _tokens(name: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", name.casefold()))


def classify_action(*, role: str, name: str) -> SafetyClass:
    """Classify one inventoried action; uncertain is irreversible."""

    if role not in ACTION_ROLES:
        return "irreversible"
    normalised = " ".join(name.casefold().split())
    tokens = set(_tokens(name))
    if normalised in _FILTER_RESET_NAMES:
        return "reversible"
    if "cart" in tokens and {"remove", "delete"} & tokens:
        return "reversible"  # §5 rule 3: cart add/remove is reversible.
    if any(phrase in normalised for phrase in _IRREVERSIBLE_PHRASES):
        return "irreversible"
    if _IRREVERSIBLE_TOKENS & tokens:
        return "irreversible"
    if role in {"link", "tab", "menuitem"}:
        return "read"
    if role in FIELD_ROLES or role in {"checkbox", "radio"}:
        return "reversible"
    # role == "button": the verb tokens decide. A button with no verb
    # this table recognises is uncertain, and uncertain is irreversible.
    if _READ_TOKENS & tokens:
        return "read"
    if _REVERSIBLE_TOKENS & tokens:
        return "reversible"
    return "irreversible"


def execution_allowed(safety: SafetyClass, mode: RunSafetyMode) -> bool:
    """Whether an item of this class may execute under the run mode."""

    if safety == "irreversible":
        return False
    if mode == "read_only":
        return safety == "read"
    return True


def skip_reason(safety: SafetyClass, mode: RunSafetyMode) -> str | None:
    """The report line for an item the gate will not exercise, if any."""

    if safety == "irreversible":
        return NOT_EXERCISED_IRREVERSIBLE
    if mode == "read_only" and safety == "reversible":
        return NOT_EXERCISED_READ_ONLY
    return None


def run_safety_mode(snapshot: Mapping[str, object] | None) -> RunSafetyMode:
    """The run's safety mode from its creation snapshot.

    Fail-closed: only the exact string "standard" unlocks standard;
    an absent key, a non-dict snapshot, or any other value is read_only.
    """
    if not isinstance(snapshot, Mapping):
        return "read_only"
    return "standard" if snapshot.get("harness_run_mode") == "standard" else "read_only"


def safety_of(item: HarnessItem) -> SafetyClass:
    """The class recorded at ingest; a missing class is irreversible."""

    value = item.locator.get("safety_class")
    if value == "read" or value == "reversible":
        return value
    return "irreversible"


def structural_reason(item: HarnessItem) -> str | None:
    """The could-not-check reason for a structural-identity item.

    Exactly the items ingest formed from unnamed controls (locator
    flag set at ingest) return NOT_CHECKED_UNNAMED_CONTROL; every
    named item returns None. The harness gate consults this beside
    skip_reason and closes the item as could_not_check.
    """

    if item.locator.get("structural_identity") is True:
        return NOT_CHECKED_UNNAMED_CONTROL
    return None


def case_id_for(item_id: str) -> str:
    """Deterministic, schema-valid case id for one board item."""

    return "harness_" + hashlib.sha256(item_id.encode()).hexdigest()[:24]


def case_for_item(
    *, item: HarnessItem, state_url: str, feature_key: str, start_url: str,
) -> TestCaseSpec:
    """Synthesise the single-item case for one board item.

    Shape: optional navigation and saved view-opening steps, one
    action for the item, and two assertions (enabled before the action, visible
    after it) — plus, for checkable items (checkbox/radio), a third
    assertion on the OUTCOME of the action: the control must end up
    checked. Outcome assertions are only generated where an existing
    oracle can actually prove the outcome (the value oracle is
    deliberately unverified for privacy, and a click's destination is
    not knowable at generation time — those outcomes are proven by the
    driver's post-action re-observation and reproduction instead, never
    by a fabricated assertion). Always inside the schema ceilings of
    steps ≤24 and assertions ≤8, and valid by construction
    (TestCaseSpec validates on creation).
    """

    if structural_reason(item) is not None:
        # Never executed: the gate closes a structural item as
        # could_not_check before execution, because no frozen locator
        # strategy can target a control with no accessible name. This
        # case only keeps the gate's case-built path valid — one
        # navigate step, one target-less URL assertion.
        return TestCaseSpec(
            case_id=item.case_id, feature_key=feature_key,
            title=f"Check {item.role} {item.occurrence_index + 1}"[:160],
            kind="exploratory", priority="medium",
            steps=(CaseAction(action="navigate", url=state_url),),
            expected=(ExpectedAssertion(
                assertion_id="target_url", oracle="url", target=None,
                expected_value=state_url, origin="inferred",
            ),),
        )
    target = SemanticTarget(role=item.role, name=item.name)
    if item.role in FIELD_ROLES:
        value_key = (
            "valid_email"
            if {"email", "mail", "address"} & set(_tokens(item.name))
            else "valid_name"
        )
        action = CaseAction(
            action="select" if item.role == "combobox" else "fill",
            target=SemanticTarget(label=item.name),
            test_value_key=value_key,
        )
    elif item.role in {"checkbox", "radio"}:
        action = CaseAction(
            action="check", target=SemanticTarget(label=item.name),
        )
    else:
        action = CaseAction(action="click", target=target)
    steps: list[CaseAction] = []
    entry_steps = item.locator.get("entry_steps")
    if isinstance(entry_steps, list) and entry_steps:
        steps.append(CaseAction(action="navigate", url=state_url))
        steps.extend(CaseAction.model_validate(step) for step in entry_steps)
    elif state_url != start_url:
        steps.append(CaseAction(action="navigate", url=state_url))
    before_action = len(steps)
    steps.append(action)
    title = (
        f"Check {item.name}" if item.name
        else f"Check {item.role} {item.occurrence_index + 1}"
    )
    assertions = [
        ExpectedAssertion(
            assertion_id="target_enabled", oracle="enabled",
            target=target, expected_value=True, origin="inferred",
            after_step_ordinal=before_action,
        ),
        ExpectedAssertion(
            assertion_id="target_visible", oracle="visible",
            target=target, expected_value=True, origin="inferred",
        ),
    ]
    if item.role in {"checkbox", "radio"}:
        # The check action's outcome, asserted with the checked oracle
        # against the same target as the other assertions.
        assertions.append(
            ExpectedAssertion(
                assertion_id="target_checked", oracle="checked",
                target=target, expected_value=True,
                origin="inferred",
            )
        )
    return TestCaseSpec(
        case_id=item.case_id, feature_key=feature_key, title=title[:160],
        kind="exploratory", priority="medium", steps=tuple(steps),
        expected=tuple(assertions),
    )


def expectation_assertion(
    entry: Mapping[str, object],
) -> ExpectedAssertion | None:
    """The Board oracle for one snapshot expectation entry (doc 21
    section 8.3): the entry's compiled assertion as a case assertion.

    None when the assertion kind has no Board-case shape
    (journey_terminal rides the skill-replay path; a page_text
    absence claim cannot be asserted by the visible_text oracle).
    """

    assertion = entry.get("assertion")
    if not isinstance(assertion, Mapping):
        return None
    kind = assertion.get("kind")
    params = assertion.get("params")
    params = params if isinstance(params, Mapping) else {}
    subject = assertion.get("subject")
    subject = subject if isinstance(subject, Mapping) else {}
    role, name = subject.get("role"), subject.get("name")
    target = (
        SemanticTarget(role=str(role), name=str(name))
        if isinstance(role, str) and role and isinstance(name, str) and name
        else None
    )
    if kind == "element_state":
        oracle = params.get("oracle")
        if target is None or oracle not in {"visible", "enabled", "checked"}:
            return None
        return ExpectedAssertion(
            assertion_id="expectation", oracle=oracle, target=target,
            expected_value=True, origin="user_approved",
        )
    if kind == "navigation":
        expected_url = params.get("expected_url")
        if not isinstance(expected_url, str) or not expected_url:
            return None
        return ExpectedAssertion(
            assertion_id="expectation", oracle="url", target=None,
            expected_value=expected_url, origin="user_approved",
        )
    if kind == "page_text":
        text = params.get("text")
        if not isinstance(text, str) or not text or params.get("present") is False:
            return None
        return ExpectedAssertion(
            assertion_id="expectation", oracle="visible_text",
            target=SemanticTarget(text=text), expected_value=text,
            origin="user_approved",
        )
    if kind == "field_validation":
        error_text = params.get("expected_error_text")
        if not isinstance(error_text, str) or not error_text:
            return None
        return ExpectedAssertion(
            assertion_id="expectation", oracle="visible_text",
            target=SemanticTarget(text=error_text),
            expected_value=error_text, origin="user_approved",
        )
    return None


def case_for_expectation(
    *, entry: Mapping[str, object], item: HarnessItem, state_url: str,
    feature_key: str, start_url: str,
) -> TestCaseSpec:
    """Compile one expectation entry into its dedicated Board case.

    Navigate to the expectation's page, perform the assertion's own
    action where it has one (click for navigation, fill for field
    validation), and evaluate the compiled assertion deterministically
    through the existing case machinery (doc 21 sections 8.3, 5.6).
    """

    assertion = entry.get("assertion")
    assertion = assertion if isinstance(assertion, Mapping) else {}
    kind = assertion.get("kind")
    params = assertion.get("params")
    params = params if isinstance(params, Mapping) else {}
    subject = assertion.get("subject")
    subject = subject if isinstance(subject, Mapping) else {}
    steps: list[CaseAction] = []
    if state_url != start_url:
        steps.append(CaseAction(action="navigate", url=state_url))
    role, name = subject.get("role"), subject.get("name")
    if kind == "navigation" and isinstance(role, str) and isinstance(name, str):
        steps.append(
            CaseAction(action="click", target=SemanticTarget(role=role, name=name))
        )
    elif kind == "field_validation":
        label = subject.get("label")
        if isinstance(label, str) and label:
            steps.append(CaseAction(
                action="fill",
                target=SemanticTarget(label=label),
                test_value_key=(
                    "empty"
                    if params.get("probe_case") == "empty"
                    else "invalid_text"
                ),
            ))
    oracle = expectation_assertion(entry)
    statement = str(entry.get("statement", ""))[:120]
    return TestCaseSpec(
        case_id=item.case_id, feature_key=feature_key,
        title=f"Expectation: {statement}"[:160],
        kind="exploratory", priority="medium", steps=tuple(steps),
        expected=(oracle,) if oracle is not None else (),
    )


def missing_test_value_keys(
    case: TestCaseSpec, values: Iterable[SafeTestValue],
) -> tuple[str, ...]:
    """The fill/select keys a case needs that the values do not resolve.

    Pure: the Board loop's data guard (doc 17 section 6.4) refuses a
    case whose key is listed here, with the safety gate's accounting
    shape, rather than letting execution reach the by-key lookup
    without a value.
    """

    resolved = {entry.key for entry in values}
    missing: list[str] = []
    for step in case.steps:
        key = step.test_value_key
        if (
            step.action in {"fill", "select"}
            and key is not None
            and key not in resolved
            and key not in missing
        ):
            missing.append(key)
    return tuple(missing)


def ingest_page_index(
    state: HarnessState, *, url: str,
    entries: Sequence[Mapping[str, object]],
    entry_steps: Sequence[CaseAction] = (),
    previous_elements: Sequence[str] = (),
) -> list[HarnessItem]:
    """Fold one page index into the board; returns only the new items.

    Identity is ``harness_state``'s: the state is keyed by the §1.4
    fingerprint of the canonical URL + sorted role|name signature +
    form-field signature, and each item by state + role + name +
    occurrence index. Re-ingesting the same index adds nothing —
    that is the fingerprint dedupe the driver relies on mid-run.
    """

    pairs: list[tuple[str, str]] = []
    form_fields: list[str] = []
    parsed: list[tuple[str, str, int, int, str]] = []
    seen: dict[tuple[str, str], int] = {}
    for entry in entries:
        role = str(entry.get("role", ""))
        name = str(entry.get("name", ""))[:160]
        if role not in ACTION_ROLES:
            continue
        occurrence = seen.get((role, name), 0)
        seen[(role, name)] = occurrence + 1
        pairs.append((role, name))
        if role in FIELD_ROLES and name and name not in form_fields:
            form_fields.append(name)
        # An unnamed control forms a structural-identity item
        # (doc 24 section 6.2): counted in the denominator and
        # accounted could_not_check via structural_reason, never
        # silently skipped.
        parsed.append((
            role, name, occurrence,
            int(entry.get("ordinal", 0) or 0),
            str(entry.get("name_source", "playwright")),
        ))
    page = state.add_state(url=url, elements=pairs, form_fields=tuple(form_fields))
    if not entry_steps and any(
        item.state_id == page.state_id and item.locator.get("entry_steps")
        for item in state.items.values()
    ):
        # A routine refresh can land on a state already inventoried through
        # an opener. Preserve its replay steps and inherited-control exclusions.
        return []
    inherited = Counter(previous_elements)
    new_items: list[HarnessItem] = []
    for role, name, occurrence, ordinal, name_source in parsed:
        if entry_steps and occurrence < inherited[f"{role}|{name}"]:
            continue
        item_id = item_id_for(page.state_id, role, name, occurrence)
        is_new = item_id not in state.items
        item = state.add_item(
            state_id=page.state_id, case_id=case_id_for(item_id),
            role=role, name=name if name.strip() else "",
            occurrence_index=occurrence,
        )
        if is_new:
            item.locator = {
                **item.locator,
                "ordinal": ordinal,
                "name_source": name_source,
                "safety_class": classify_action(role=role, name=name),
            }
            if not name.strip():
                item.locator["structural_identity"] = True
            if entry_steps:
                item.locator["entry_steps"] = [step.model_dump(mode="json") for step in entry_steps]
            new_items.append(item)
    return new_items
