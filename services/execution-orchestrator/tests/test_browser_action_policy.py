from __future__ import annotations

import pytest

from markettwin_execution_orchestrator.browser.action_policy import (
    ensure_low_risk_click_target,
    ensure_non_sensitive_fill,
)
from markettwin_execution_orchestrator.browser.errors import BrowserActionBlockedError


def test_allows_low_risk_click() -> None:
    ensure_low_risk_click_target("Pricing")


def test_blocks_payment_click() -> None:
    with pytest.raises(BrowserActionBlockedError):
        ensure_low_risk_click_target("Place order")


def test_blocks_password_field() -> None:
    with pytest.raises(BrowserActionBlockedError):
        ensure_non_sensitive_fill(
            label="Password",
            input_type="password",
            autocomplete="current-password",
        )


def test_blocks_otp_by_autocomplete() -> None:
    with pytest.raises(BrowserActionBlockedError):
        ensure_non_sensitive_fill(
            label="Code",
            input_type="text",
            autocomplete="one-time-code",
        )


def test_allows_normal_text_field() -> None:
    ensure_non_sensitive_fill(
        label="Search",
        input_type="text",
        autocomplete="off",
    )
