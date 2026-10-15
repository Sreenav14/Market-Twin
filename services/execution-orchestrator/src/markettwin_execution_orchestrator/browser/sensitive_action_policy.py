"""Deterministic policy for actions requiring a human one-time approval."""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from markettwin_execution_orchestrator.browser.errors import BrowserActionBlockedError

ActionCategory = Literal["form_submit", "save", "create", "update", "publish"]

_HARD_DENY_TERMS = (
    "delete", "remove", "purchase", "buy", "payment", "pay now", "checkout",
    "send", "invite", "grant access", "revoke access",
    "change role", "administrator", "permission", "export data", "transfer funds",
)

_APPROVAL_TERMS: tuple[tuple[ActionCategory, tuple[str, ...]], ...] = (
    ("form_submit", ("submit",)),
    ("save", ("save",)),
    ("create", ("create", "add new")),
    ("update", ("update", "edit", "apply changes")),
    ("publish", ("publish",)),
)


@dataclass(frozen=True, slots=True)
class SensitiveActionIntent:
    """Safe approval metadata; action payload values are never included."""

    category: ActionCategory
    action: dict[str, object]
    display_summary: str

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(self.action, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def classify_click_action(
    *,
    role: str | None,
    name: str | None,
    label: str | None,
    text: str | None,
    element_type: str | None = None,
    observed_description: str | None = None,
    state_digest: str | None = None,
) -> SensitiveActionIntent | None:
    """Classify a semantic click; hard-denied categories never become approvable."""

    description = " ".join(
        value.strip().lower() for value in (name, label, text, observed_description) if value
    )
    if any(term in description for term in _HARD_DENY_TERMS):
        raise BrowserActionBlockedError(
            "This action is prohibited by MarketTwin's sensitive-action policy."
        )
    if role not in {"button", "link", "menuitem", None}:
        return None
    normalized_type = (element_type or "").strip().lower()
    category: ActionCategory | None = None
    for candidate, terms in _APPROVAL_TERMS:
        if any(term in description for term in terms):
            category = candidate
            break
    if not category:
        if normalized_type == "submit" or any(
            term in description for term in ("continue", "confirm")
        ):
            raise BrowserActionBlockedError(
                "An opaque confirmation requires human browser takeover."
            )
        return None
    summaries: dict[ActionCategory, str] = {
        "form_submit": "Submit a form on the authorized target",
        "save": "Save a change on the authorized target",
        "create": "Create a record on the authorized target",
        "update": "Update a record on the authorized target",
        "publish": "Publish content on the authorized target",
    }
    return SensitiveActionIntent(
        category=category,
        action={
            "action_type": "click",
            "category": category,
            "role": role or "semantic",
            "name": name,
            "label": label,
            "text": text,
            "element_type": normalized_type or None,
            "state_digest": state_digest,
        },
        display_summary=summaries[category],
    )
