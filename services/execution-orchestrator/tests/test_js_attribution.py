"""JS attribution parity (doc 24 section 4, W4-P5-04/05/06):
unhandled rejections are stamped with the URL of the document that
produced them, read at event time — never with the URL of whatever
page is current when the harvest happens to run.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from markettwin_execution_orchestrator.browser.controller import (
    BrowserController,
)


class _Buffer:
    def __init__(self):
        self.js_records = []
        self.page_errors = []
        self.console_errors = []

    def record_js(self, record):
        self.js_records.append(record)

    def record_page_error(self, message):
        self.page_errors.append(message)

    def record_console_error(self, text):
        self.console_errors.append(text)


class _Page:
    def __init__(self, url, snapshot=None):
        self.url = url
        self._snapshot = snapshot or {"doc": "", "doc_url": "", "items": []}

    async def evaluate(self, script):
        return self._snapshot


def _capture_session(page):
    return SimpleNamespace(
        js_capture=True,
        capture_enabled=True,
        control_mode="agent",
        authenticated_session=False,
        page=page,
        rejections_document="",
        rejections_harvested=0,
        rejections_dropped=0,
        rejection_harvest_failures=0,
        last_rejection_harvest_failed=False,
        page_setup_failures=0,
        event_buffer=_Buffer(),
    )


def _controller_with(session):
    controller = BrowserController()
    session_id = uuid4()
    controller._sessions[session_id] = session
    return controller, session_id


async def test_failed_rejection_harvest_exposes_failure_without_raw_exception():
    from unittest.mock import AsyncMock

    session = _capture_session(_Page("https://app.example.test/a"))
    session.page.evaluate = AsyncMock(side_effect=RuntimeError("private detail"))
    controller, session_id = _controller_with(session)
    assert await controller.harvest_js_records(session_id=session_id) == []
    diagnostics = controller.js_capture_diagnostics(session_id=session_id)
    assert diagnostics["rejection_harvest_failures"] == 1
    assert diagnostics["last_rejection_harvest_failed"] is True
    assert "private detail" not in str(diagnostics)


async def test_popup_setup_failure_is_retrieved_and_recorded():
    import asyncio
    from unittest.mock import AsyncMock

    session = _capture_session(_Page("https://app.example.test/a"))
    controller, _session_id = _controller_with(session)
    controller._configure_page = AsyncMock(side_effect=RuntimeError("private detail"))
    controller._schedule_page_setup(session, object())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert session.page_setup_failures == 1
    assert session.event_buffer.page_errors == ["Popup page setup failed."]


@pytest.mark.asyncio
async def test_rejections_are_stamped_with_their_event_time_url() -> None:
    """T-P5-J1: a rejection raised on page A, harvested while the
    session sits on page B, is attributed to A."""
    page = _Page("https://app.example.test/b", {
        "doc": "doc-a",
        "doc_url": "https://app.example.test/a",
        "items": [
            {"message": "boom", "stack": None,
             "url": "https://app.example.test/a"},
            {"message": "bang", "stack": "trace",
             "url": "https://app.example.test/a"},
        ],
    })
    session = _capture_session(page)
    controller, session_id = _controller_with(session)
    records = await controller.harvest_js_records(session_id=session_id)
    assert [r.url for r in records] == [
        "https://app.example.test/a", "https://app.example.test/a",
    ]
    assert [r.kind for r in records] == [
        "unhandled_rejection", "unhandled_rejection",
    ]
    # A second harvest over the same document adds nothing.
    again = await controller.harvest_js_records(session_id=session_id)
    assert len(again) == 2


@pytest.mark.asyncio
async def test_unattributable_rejections_drop_and_count() -> None:
    """T-P5-J2: an item with no URL of its own falls back to its
    document's URL; an item with neither is dropped and counted,
    never guessed onto the current page."""
    page = _Page("https://app.example.test/b", {
        "doc": "doc-a",
        "doc_url": "https://app.example.test/a",
        "items": [
            {"message": "no own url", "stack": None},
            {"message": "stamped", "stack": None,
             "url": "https://app.example.test/a"},
        ],
    })
    session = _capture_session(page)
    controller, session_id = _controller_with(session)
    records = await controller.harvest_js_records(session_id=session_id)
    assert [r.url for r in records] == [
        "https://app.example.test/a", "https://app.example.test/a",
    ]
    assert session.rejections_dropped == 0

    page2 = _Page("https://app.example.test/b", {
        "doc": "doc-b", "doc_url": "",
        "items": [{"message": "orphan", "stack": None}],
    })
    session2 = _capture_session(page2)
    controller2, session_id2 = _controller_with(session2)
    records2 = await controller2.harvest_js_records(session_id=session_id2)
    assert records2 == []
    assert session2.rejections_dropped == 1


def test_console_and_page_errors_stamp_at_event_time() -> None:
    """T-P5-J3: console/pageerror records carry the URL current when
    the handler ran — parity with the rejection channel."""
    page = _Page("https://app.example.test/a")
    session = _capture_session(page)
    BrowserController._record_page_error(session, "boom")
    BrowserController._on_console(session, "error", "bang")
    page.url = "https://app.example.test/b"
    BrowserController._record_page_error(session, "later")
    urls = [r.url for r in session.event_buffer.js_records]
    assert urls == [
        "https://app.example.test/a",
        "https://app.example.test/a",
        "https://app.example.test/b",
    ]


class _ObservablePage(_Page):
    """A _Page that can also survive build_observation's evaluates."""

    async def evaluate(self, script):
        if "MAX_ELEMENTS" in script:
            return []
        if "innerWidth" in script:
            return {
                "width": 1280, "height": 800,
                "scroll_y": 0, "document_height": 900,
            }
        return self._snapshot

    async def title(self):
        return "Fixture"

    def locator(self, _selector):
        from types import SimpleNamespace as _NS

        return _NS(nth=lambda _index: None)


@pytest.mark.asyncio
async def test_observation_drain_does_not_consume_js_records(
    tmp_path,
) -> None:
    """T-P5-J4: build_observation drains the per-action buffers
    (console / page errors / failed requests) into the observation —
    and only those. The JS record buffer is separate (doc 24 section
    4.3, pin case): a record captured before an observation is still
    harvested after it, and the watermark is not advanced."""
    from types import SimpleNamespace

    from markettwin_execution_orchestrator.browser.observations import (
        build_observation,
    )

    page = _ObservablePage("https://app.example.test/a", {
        "doc": "doc-a",
        "doc_url": "https://app.example.test/a",
        "items": [
            {"message": "boom", "stack": None,
             "url": "https://app.example.test/a"},
        ],
    })
    session = _capture_session(page)
    session.event_buffer.failed_requests = []
    session.context = SimpleNamespace(pages=[page])
    session.action_number = 1
    session.timeout_ms = 1000
    session.artifact_directory = tmp_path
    controller, session_id = _controller_with(session)

    BrowserController._record_page_error(session, "kaput")
    observation = await build_observation(
        session, aria_snapshot_override="",
    )
    # The per-action buffer drained into the observation...
    assert observation.page_errors_since_last_action == ("kaput",)
    assert session.event_buffer.page_errors == []
    # ...while the JS records — the page error's structured record
    # and the still-unharvested rejection — survive untouched.
    records = await controller.harvest_js_records(session_id=session_id)
    assert [r.kind for r in records] == ["uncaught", "unhandled_rejection"]
    assert records[0].message == "kaput"
    assert records[1].url == "https://app.example.test/a"
