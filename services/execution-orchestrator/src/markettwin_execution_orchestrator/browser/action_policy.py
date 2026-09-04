"""Deterministic low-risk action policy for agent-controlled browser steps."""

from markettwin_execution_orchestrator.browser.errors import BrowserActionBlockedError

_DESTRUCTIVE_CLICK_PHRASES = (
    "delete account",
    "delete workspace",
    "delete project",
    "remove account",
    "close account",
    "buy now",
    "purchase",
    "pay now",
    "submit payment",
    "confirm payment",
    "place order",
    "confirm order",
)

_SENSITIVE_LABEL_PHRASES = (
    "password",
    "passcode",
    "one-time code",
    "one time code",
    "otp",
    "verification code",
    "security code",
    "captcha",
    "card number",
    "credit card",
    "cvv",
    "cvc",
)

_SENSITIVE_INPUT_TYPES = {"password", "file"}
_SENSITIVE_AUTOCOMPLETE_VALUES = {
    "current-password",
    "new-password",
    "one-time-code",
    "cc-number",
    "cc-csc",
    "cc-exp",
    "cc-exp-month",
    "cc-exp-year",
}


def ensure_low_risk_click_target(*targets: str | None) -> None:
    """Block clearly destructive/payment clicks from autonomous agent control."""

    text = " ".join(value.strip().lower() for value in targets if value)
    if any(phrase in text for phrase in _DESTRUCTIVE_CLICK_PHRASES):
        raise BrowserActionBlockedError(
            "This click is blocked by MarketTwin's autonomous-action policy."
        )


def ensure_non_sensitive_fill(
    *,
    label: str,
    input_type: str | None,
    autocomplete: str | None,
) -> None:
    """Prevent credentials, OTPs, payment data, and file entry by the agent."""

    normalized_label = label.strip().lower()
    normalized_type = (input_type or "").strip().lower()
    normalized_autocomplete = (autocomplete or "").strip().lower()

    if (
        normalized_type in _SENSITIVE_INPUT_TYPES
        or normalized_autocomplete in _SENSITIVE_AUTOCOMPLETE_VALUES
        or any(phrase in normalized_label for phrase in _SENSITIVE_LABEL_PHRASES)
    ):
        raise BrowserActionBlockedError(
            "Sensitive credential, authentication, payment, and file fields require "
            "an approved human-assisted flow."
        )
