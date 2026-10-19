"""Public run failure diagnostics; never include provider or browser payloads."""

import re
from typing import cast

MESSAGES = {
    "execution_failed": (
        'Execution stopped before results were collected. The '
        'original error was not retained.'
    ),
    "model_authentication": (
        'The model provider rejected authentication. Check the '
        "worker's model credentials."
    ),
    "model_permission": "The model provider denied access to the configured model.",
    "model_not_found": "The model provider could not find the configured model or endpoint.",
    "model_rate_limit": "The model provider rejected the request because of a rate or quota limit.",
    "model_connection": "The worker could not connect to the configured model provider.",
    "model_request": "The model provider rejected the planning request or its parameters.",
    "invalid_plan": "The run configuration or generated feature cases failed validation.",
    "timeout": "Planning or browser discovery exceeded its time limit.",
    "browser_navigation": (
        'Browser discovery could not navigate within the '
        'authorized target policy.'
    ),
    "interrupted": "The worker was interrupted. The run was stopped to avoid replaying actions.",
}


# Exact planner and policy sentences. Interpolated exception text is never included.
ALLOWED_REASONS = frozenset({
    "Candidate case IDs must be unique.",
    "No executable cases remain after safety validation.",
    "No executable cases fit the caller's budget.",
    "Plan cannot change the caller-owned scope or budget.",
    "Feature planner did not return a case list.",
    "Feature planner returned unexpected fields.",
    "Feature planner returned invalid JSON.",
    "Feature planner returned no schema-valid cases.",
    "Feature planner returned invalid coverage gaps.",
    "Feature planner did not return structured candidates.",
    "Fixture plan requires loopback.",
    "Case belongs to a different feature.",
    "Unknown requirement reference.",
    "Fixture truth requires explicit caller authorization.",
    "Requirement source is not owned by this request.",
    "Model cannot invent fixture provenance.",
    "Model cannot invent approved provenance.",
    "Grounded expectation must match a caller-owned oracle definition.",
    "Assertion sources must belong to the case requirements.",
    "Case requires an unsupported action.",
    "Fixture approval action requires its exact authorized candidate.",
    "Unknown safe test-data key.",
    "Navigation must use an authorized HTTP(S) URL without credentials.",
    "Navigation is outside the caller-owned feature scope.",
    "Role and name must be supplied together.",
    "Supply exactly one role/name, label or text target.",
    "Scope role and name must be supplied together.",
    "Arguments do not match the permitted action.",
    "The fixture action identity is valid only for Registration Save.",
    "Form actions require a labeled field.",
    "Element oracles require a target; page oracles do not.",
    "State expectations must be booleans.",
    "Count expectations must be nonnegative integers.",
    "Text expectations must be bounded strings.",
    "Grounded assertions require source references.",
    "This click is blocked by MarketTwin's autonomous-action policy.",
    "Sensitive credential, authentication, payment, and file fields require "
    "an approved human-assisted flow.",
    "This action is prohibited by MarketTwin's sensitive-action policy.",
    "An opaque confirmation requires human browser takeover.",
})
_LOCATION = re.compile(
    r"(?:[A-Za-z_][A-Za-z0-9_]{0,63}|\d+)"
    r"(?:\.(?:[A-Za-z_][A-Za-z0-9_]{0,63}|\d+)){0,8}"
    r":[a-z][a-z0-9_]{0,63}"
)
_CASE_ID = re.compile(r"[a-z][a-z0-9_]{0,63}")


def failure_details(code: str) -> dict[str, str]:
    """Only expose fixed, reviewed text even when reading a persisted event."""
    if code not in MESSAGES:
        code = "execution_failed"
    return {"code": code, "message": MESSAGES[code]}


def _piece_ok(value: str) -> bool:
    if value in ALLOWED_REASONS or _LOCATION.fullmatch(value):
        return True
    case_id, separator, rest = value.partition(": ")
    if separator and _CASE_ID.fullmatch(case_id) and rest in ALLOWED_REASONS:
        return True
    index, separator, location = value.partition(":")
    return bool(separator and index.isdigit() and _LOCATION.fullmatch(location))


def validation_locations(error: BaseException) -> str | None:
    """Keep Pydantic locations and type codes; drop input values and messages."""
    errors = getattr(error, "errors", None)
    if not callable(errors):
        return None
    try:
        items = errors()
    except Exception:
        return None
    if not isinstance(items, list):
        return None
    parts: list[str] = []
    for item in cast(list[object], items)[:8]:
        if not isinstance(item, dict):
            continue
        fields = cast(dict[object, object], item)
        loc = fields.get("loc")
        kind = fields.get("type")
        if not isinstance(loc, tuple) or not isinstance(kind, str):
            continue
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", kind):
            continue
        safe_loc: list[str] = []
        for part in cast(tuple[object, ...], loc):
            if isinstance(part, int) and 0 <= part <= 128:
                safe_loc.append(str(part))
            elif isinstance(part, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", part):
                safe_loc.append(part)
            else:
                safe_loc = []
                break
        if safe_loc:
            parts.append(f"{'.'.join(safe_loc)}:{kind}")
    return "; ".join(parts) or None


def reviewed_failure_reason(error: BaseException) -> str | None:
    """Return a reviewed reason, or nothing when the exception text is unreviewed."""
    locations = validation_locations(error)
    if locations:
        return locations
    reasons = getattr(error, "safe_reasons", None)
    if (
        isinstance(reasons, tuple)
        and 1 <= len(cast(tuple[object, ...], reasons)) <= 9
        and all(
            isinstance(item, str) and _piece_ok(item)
            for item in cast(tuple[object, ...], reasons)
        )
    ):
        safe_reasons = cast(tuple[str, ...], reasons)
        head, *rest = safe_reasons
        if head in ALLOWED_REASONS and rest:
            return f"{head} ({'; '.join(rest)})"
        if head in ALLOWED_REASONS:
            return head
        if all(_LOCATION.fullmatch(item) for item in safe_reasons):
            return "; ".join(safe_reasons)
    message = str(error).splitlines()[0].strip()
    if message in ALLOWED_REASONS:
        return message
    return None


def accept_stored_reason(value: object) -> str | None:
    """Re-check a persisted reason before it is shown. Unreviewed text is dropped."""
    if not isinstance(value, str) or not value or len(value) > 1200:
        return None
    if value in ALLOWED_REASONS:
        return value
    if value.endswith(")") and " (" in value:
        head, _, tail = value.rpartition(" (")
        pieces = tail[:-1].split("; ")
        if head in ALLOWED_REASONS and pieces and all(_piece_ok(piece) for piece in pieces):
            return value
    pieces = value.split("; ")
    if pieces and all(_LOCATION.fullmatch(piece) for piece in pieces):
        return value
    return None


def failure_site(error: BaseException) -> str:
    """File and line only. Traceback text can repeat an unsafe exception message."""
    site = "unknown"
    traceback = error.__traceback__
    while traceback is not None:
        filename = traceback.tb_frame.f_code.co_filename.replace("\\", "/")
        if "markettwin" in filename:
            site = f"{filename.rsplit('/', 1)[-1]}:{traceback.tb_lineno}"
        traceback = traceback.tb_next
    return site


def failure_event_payload(error: BaseException) -> dict[str, str]:
    payload = {**classify_run_failure(error), "error_type": type(error).__name__}
    reason = reviewed_failure_reason(error)
    if reason is not None:
        payload["reason"] = reason
    return payload


def public_failure_details(payload: object) -> dict[str, str]:
    code = "execution_failed"
    if isinstance(payload, dict):
        raw_code = cast(dict[object, object], payload).get("code")
        if isinstance(raw_code, str):
            code = raw_code
    details = failure_details(code)
    if isinstance(payload, dict):
        reason = accept_stored_reason(cast(dict[object, object], payload).get("reason"))
        if reason is not None:
            details["message"] = f"{details['message']} {reason}"
    return details


def classify_run_failure(error: BaseException) -> dict[str, str]:
    codes = {
        "AuthenticationError": "model_authentication",
        "PermissionDeniedError": "model_permission",
        "NotFoundError": "model_not_found",
        "RateLimitError": "model_rate_limit",
        "APIConnectionError": "model_connection",
        "BadRequestError": "model_request",
        "ValidationError": "invalid_plan",
        "BrowserTimeoutError": "timeout",
        "TimeoutError": "timeout",
        "APITimeoutError": "timeout",
        "BrowserNavigationError": "browser_navigation",
        "BrowserPolicyError": "browser_navigation",
        "CancelledError": "interrupted",
    }
    for cls in type(error).__mro__:
        if cls.__name__ in codes:
            return failure_details(codes[cls.__name__])
    if reviewed_failure_reason(error) is not None:
        return failure_details("invalid_plan")
    return failure_details("execution_failed")
