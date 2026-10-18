"""Failure diagnostics omit raw model, validation and credential payloads."""

import asyncio

import pytest
from markettwin_shared.run_failure import (
    accept_stored_reason,
    classify_run_failure,
    failure_event_payload,
    public_failure_details,
    reviewed_failure_reason,
)
from pydantic import BaseModel, ConfigDict, ValidationError


@pytest.mark.parametrize("name,code", [
    ("NotFoundError", "model_not_found"),
    ("AuthenticationError", "model_authentication"),
    ("RateLimitError", "model_rate_limit"),
    ("ValidationError", "invalid_plan"),
    ("BrowserTimeoutError", "timeout"),
    ("UnknownProviderError", "execution_failed"),
])
def test_exception_payload_is_never_retained(name, code):
    error = type(name, (Exception,), {})("SECRET_CANARY request and credentials")
    result = classify_run_failure(error)
    assert result["code"] == code
    assert "SECRET_CANARY" not in str(result)


def test_cancellation_is_explicitly_classified():
    assert classify_run_failure(asyncio.CancelledError())["code"] == "interrupted"


def test_reviewed_validation_reason_is_retained_without_exception_text():
    error = ValueError("Feature planner returned no schema-valid cases.")
    error.safe_reasons = (  # type: ignore[attr-defined]
        "Feature planner returned no schema-valid cases.",
        "1:expected.0.target:value_error",
    )
    payload = failure_event_payload(error)
    assert payload["code"] == "invalid_plan"
    assert payload["error_type"] == "ValueError"
    assert payload["reason"] == (
        "Feature planner returned no schema-valid cases. (1:expected.0.target:value_error)"
    )
    shown = public_failure_details(payload)
    assert "expected.0.target:value_error" in shown["message"]


def test_unreviewed_exception_text_is_omitted_from_the_stored_reason():
    error = ValueError("SECRET_CANARY provider body")
    assert reviewed_failure_reason(error) is None
    payload = failure_event_payload(error)
    assert "reason" not in payload
    assert "SECRET_CANARY" not in str(payload)
    assert payload["code"] == "execution_failed"
    shown = public_failure_details({
        "code": "invalid_plan",
        "message": "SECRET_CANARY",
        "reason": "SECRET_CANARY in the stored reason",
    })
    assert "SECRET_CANARY" not in str(shown)
    assert accept_stored_reason("SECRET_CANARY") is None


def test_validation_error_keeps_location_and_drops_input():
    class Contract(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str

    with pytest.raises(ValidationError) as caught:
        Contract.model_validate({"name": "ok", "selector": "SECRET_CANARY"})
    reason = reviewed_failure_reason(caught.value)
    assert reason == "selector:extra_forbidden"
    assert "SECRET_CANARY" not in str(reason)
