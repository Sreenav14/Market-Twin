"""Negative cases for the audit's request-method and corrupt-image boundaries."""

from types import SimpleNamespace

import pytest
from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserPolicyError
from markettwin_execution_orchestrator.freshness.phash import screenshot_phash


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_captcha_exception_does_not_authorize_sensitive_submission(method):
    # BRW-1, restated under the owner's allow-by-default rule (2026-11-24):
    # the captcha exception authorizes the widget's own token calls, never
    # a submission carrying sensitive data through a captcha URL.
    request = SimpleNamespace(
        url="https://js.hcaptcha.com/1/api.js", method=method,
        post_data="password=hunter2",
    )
    with pytest.raises(BrowserPolicyError, match="sensitive data"):
        BrowserController._validated_subresource_url(object(), object(), request)


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_captcha_assets_remain_available(method):
    request = SimpleNamespace(url="https://js.hcaptcha.com/1/api.js", method=method)
    result = BrowserController._validated_subresource_url(object(), object(), request)
    assert result.hostname == "js.hcaptcha.com"


def test_corrupt_screenshot_is_not_a_job_failure():
    assert screenshot_phash(b"not an image") is None
    assert screenshot_phash(b"\x89PNG\r\n\x1a\ntruncated") is None


def test_short_ihdr_png_is_not_a_job_failure():
    # ORC1-03: an IHDR chunk shorter than the 13 bytes the stdlib
    # decoder unpacks raised struct.error out of screenshot_phash,
    # breaking its "None, never a job failure" contract.
    import struct

    crafted = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 5)
        + b"IHDR"
        + b"\x00\x00\x00\x01\x00"
        + b"\x00\x00\x00\x00"
    )
    assert screenshot_phash(crafted) is None


def test_unknown_testing_depth_is_a_named_validation_error():
    from markettwin_execution_orchestrator.workflow.testing_depth import mission_limit

    with pytest.raises(ValueError, match="Unknown testing_depth: 'future'"):
        mission_limit("future")


@pytest.mark.parametrize("task", ["malformed", [1], True])
def test_rebinding_malformed_task_does_not_crash_or_mutate(task):
    from markettwin_execution_orchestrator.workflow.skill_filter import rebind_task_assertions

    definition = {"task": task, "expected": []}
    assert rebind_task_assertions(definition, {"name": "fixture"}) == definition


def test_browser_event_flood_is_bounded_even_after_incremental_drain():
    from markettwin_execution_orchestrator.browser.contracts import (
        BrowserEventBuffer, FailedRequestRecord, JsErrorRecord,
    )

    buffer = BrowserEventBuffer()
    request = FailedRequestRecord("https://example.test", "GET", "fetch", "failed")
    record = JsErrorRecord("uncaught", "failed", None, "https://example.test")
    for index in range(1011):
        buffer.record_console_error("failed")
        buffer.record_page_error("failed")
        buffer.record_failed_request(request)
        buffer.record_js(record)
        if index == 999:
            buffer.console_errors.clear()
            buffer.page_errors.clear()
            buffer.failed_requests.clear()
    assert len(buffer.all_console_errors) == len(buffer.all_page_errors) == 1000
    assert len(buffer.all_failed_requests) == len(buffer.js_records) == 1000
    assert buffer.console_errors == buffer.page_errors == buffer.failed_requests == []
    assert buffer.dropped_console_errors == buffer.dropped_page_errors == 11
    assert buffer.dropped_failed_requests == buffer.dropped_js_records == 11
    buffer.clear_all()
    assert buffer.dropped_console_errors == buffer.dropped_page_errors == 0
    assert buffer.dropped_failed_requests == buffer.dropped_js_records == 0
    buffer.record_console_error("new session phase")
    assert buffer.all_console_errors == ["new session phase"]
