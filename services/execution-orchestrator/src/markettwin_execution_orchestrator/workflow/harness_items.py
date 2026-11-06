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
from collections.abc import Mapping, Sequence
from typing import Literal

from markettwin_execution_orchestrator.agents.schemas.test_case import (
    CaseAction,
    ExpectedAssertion,
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


def safety_of(item: HarnessItem) -> SafetyClass:
    """The class recorded at ingest; a missing class is irreversible."""

    value = item.locator.get("safety_class")
    if value == "read" or value == "reversible":
        return value
    return "irreversible"


def case_id_for(item_id: str) -> str:
    """Deterministic, schema-valid case id for one board item."""

    return "harness_" + hashlib.sha256(item_id.encode()).hexdigest()[:24]


def case_for_item(
    *, item: HarnessItem, state_url: str, feature_key: str, start_url: str,
) -> TestCaseSpec:
    """Synthesise the single-item case for one board item.

    Shape: at most one precondition step (navigate back to the item's
    state when it is not the start state — always ≤3), exactly one
    action, and two assertions (enabled before the action, visible
    after it) — always inside the schema ceilings of steps ≤24 and
    assertions ≤8, and valid by construction (TestCaseSpec validates
    on creation).
    """

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
    if state_url != start_url:
        steps.append(CaseAction(action="navigate", url=state_url))
    steps.append(action)
    title = (
        f"Check {item.name}" if item.name
        else f"Check {item.role} {item.occurrence_index + 1}"
    )
    return TestCaseSpec(
        case_id=item.case_id, feature_key=feature_key, title=title[:160],
        kind="exploratory", priority="medium", steps=tuple(steps),
        expected=(
            ExpectedAssertion(
                assertion_id="target_enabled", oracle="enabled",
                target=target, expected_value=True, origin="inferred",
                after_step_ordinal=0,
            ),
            ExpectedAssertion(
                assertion_id="target_visible", oracle="visible",
                target=target, expected_value=True, origin="inferred",
            ),
        ),
    )


def ingest_page_index(
    state: HarnessState, *, url: str,
    entries: Sequence[Mapping[str, object]],
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
        parsed.append((
            role, name, occurrence,
            int(entry.get("ordinal", 0) or 0),
            str(entry.get("name_source", "playwright")),
        ))
    page = state.add_state(url=url, elements=pairs, form_fields=tuple(form_fields))
    new_items: list[HarnessItem] = []
    for role, name, occurrence, ordinal, name_source in parsed:
        item_id = item_id_for(page.state_id, role, name, occurrence)
        is_new = item_id not in state.items
        item = state.add_item(
            state_id=page.state_id, case_id=case_id_for(item_id),
            role=role, name=name, occurrence_index=occurrence,
        )
        if is_new:
            item.locator = {
                **item.locator,
                "ordinal": ordinal,
                "name_source": name_source,
                "safety_class": classify_action(role=role, name=name),
            }
            new_items.append(item)
    return new_items
