"""Signal companion (MT-000237 lane fix, INTEGRATION-REPORT S1/S2):
a challenge-check timeout is recorded on the page state as the boolean
field ``challenge_check_timed_out`` — never as a UI_STATE_UNASSESSED
page signal.

Why a field and not the signal the Fix C spec originally named: in
this codebase any state carrying a UI_STATE_UNASSESSED signal is
treated as unassessed (workflow/slop_run.py ``_is_unassessed`` — the
slop.page.inspected outcome, the state-publishing filter and the
report accounting all test page_signals only). A timed-out page WAS
measured; the field records the timeout with the same honesty and no
outcome effect.

The channel under test: BrowserController._has_authentication_challenge
sets ``session.challenge_check_timed_out`` when Fix C's
inspect_sensitive_challenge reports timed_out;
BrowserController.take_challenge_check_timeout returns and clears it;
workflow/slop_run.py _inspect_page drains it onto the measured entry
state immediately after ``page_ctx.entry_state = measured``; the field
is on the _publish_states whitelist so it reaches published
slop.state.result events.

Fake controllers/sessions throughout, in the style of
tests/test_slop_pool.py — no network, no real browser, no real model.
The one real-browser-shaped piece is the controller unit test, which
uses a real BrowserController with a fake page (house pattern).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.session import JourneyBrowserSession
from markettwin_execution_orchestrator.workflow import slop_run
from markettwin_execution_orchestrator.workflow.slop_run import (
    _SlopAbsorber,
    _is_unassessed,
)


def make_absorber(*, synchronous, lane_count=2, desktop_scan=False):
    """Copied from tests/test_slop_pool.py (Fix A's harness)."""
    request = SimpleNamespace(
        run_id=uuid4(),
        allowed_origins=(), network_policy="public_only",
        study_brief="Audit UI", app_map=None)
    created = []

    async def create(**kwargs):
        created.append(kwargs)

    events = SimpleNamespace(create=create)
    session = SimpleNamespace(commit=AsyncMock())
    run = SimpleNamespace(configuration_snapshot={})
    absorber = _SlopAbsorber(
        request=request, session=session, events=events, run=run,
        journey_id=uuid4(), execution_id=uuid4(),
        controller=SimpleNamespace(), lane_count=lane_count,
        synchronous=synchronous, desktop_scan=desktop_scan)
    absorber.created_events = created
    return absorber


def _desktop_absorber():
    """An absorber ready for one measured desktop inspection: the
    request carries a start_url distinct from the claim URL, the
    absorber's own controller can harvest JS records and capture
    screenshots, and the claim page's layout is already reviewed so
    review_desktop_page stays out of the way."""
    absorber = make_absorber(synchronous=False, lane_count=1, desktop_scan=True)
    absorber.request.start_url = "https://x.test/"
    absorber.controller = SimpleNamespace(
        harvest_js_records=AsyncMock(return_value=[]),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
    )
    absorber.reviewed_layouts.add(("page", ()))
    return absorber


def _measured_controller(*, timed_out):
    """A fake lane controller that measures one page cleanly and, when
    asked, reports a drained challenge-check timeout. Returns the
    controller and the list of session_ids the drain was called with."""
    take_calls = []

    def take_challenge_check_timeout(*, session_id):
        take_calls.append(session_id)
        return timed_out

    controller = SimpleNamespace(
        navigate=AsyncMock(),
        wait=AsyncMock(),
        probe_page=AsyncMock(return_value={
            "url": "https://x.test/page", "elements": [], "words": 50}),
        page_links=AsyncMock(return_value=[]),
        take_challenge_check_timeout=take_challenge_check_timeout,
    )
    return controller, take_calls


async def _inspect_one(absorber, controller):
    absorber.ledger.seed(["https://x.test/page"])
    claim = absorber.ledger.claim_next(0)
    handle = SimpleNamespace(session_id=uuid4())
    await slop_run._inspect_page(
        absorber=absorber, controller=controller, handle=handle, claim=claim)
    await absorber.aclose(wait=True)
    assert len(absorber.states) == 1
    return absorber.states[0], handle


def _inspected_outcome(absorber):
    events = [kwargs for kwargs in absorber.created_events
              if kwargs.get("event_type") == "slop.page.inspected"]
    assert len(events) == 1
    return events[0]["payload"]["outcome"]


async def _published_payload(state):
    published = []

    async def create(**kwargs):
        published.append(kwargs)

    await slop_run._publish_states(
        SimpleNamespace(create=create), run_id=uuid4(), journey_id=uuid4(),
        execution_id=uuid4(), states=[state])
    assert len(published) == 1
    return published[0]["payload"]


# ----------------------------------------------------------------
# Workflow level: the drain lands on the measured entry state as a
# field; the page is still measured; the field is published.
# ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_drained_timeout_becomes_a_field_and_the_page_stays_measured():
    absorber = _desktop_absorber()
    controller, take_calls = _measured_controller(timed_out=True)
    state, handle = await _inspect_one(absorber, controller)

    assert take_calls == [handle.session_id]  # drained exactly once
    assert state["challenge_check_timed_out"] is True
    # The whole point of the field design: nothing about the timeout
    # touches page_signals, so the unassessed accounting cannot fire.
    assert not _is_unassessed(state)
    assert all(signal.get("rule_id") != "UI_STATE_UNASSESSED"
               for signal in state["page_signals"])
    assert _inspected_outcome(absorber) == "measured"
    payload = await _published_payload(state)
    assert payload["challenge_check_timed_out"] is True


@pytest.mark.asyncio
async def test_no_timeout_reported_means_the_field_is_absent():
    absorber = _desktop_absorber()
    controller, take_calls = _measured_controller(timed_out=False)
    state, handle = await _inspect_one(absorber, controller)

    assert take_calls == [handle.session_id]
    assert "challenge_check_timed_out" not in state
    assert _inspected_outcome(absorber) == "measured"
    payload = await _published_payload(state)
    assert "challenge_check_timed_out" not in payload


@pytest.mark.asyncio
async def test_controller_without_the_accessor_still_inspects():
    """The drain is defensive (getattr), matching how optional
    controller methods are consumed elsewhere: a controller with no
    take_challenge_check_timeout — every pre-companion fake — inspects
    exactly as before and records no field."""
    absorber = _desktop_absorber()
    controller, _ = _measured_controller(timed_out=True)
    del controller.take_challenge_check_timeout
    state, _handle = await _inspect_one(absorber, controller)

    assert "challenge_check_timed_out" not in state
    assert _inspected_outcome(absorber) == "measured"


# ----------------------------------------------------------------
# Controller level: the flag is set by the checkpoint on timeout, and
# the accessor returns-and-clears it.
# ----------------------------------------------------------------

def test_take_challenge_check_timeout_returns_and_clears():
    controller = BrowserController()
    session_id = uuid4()
    session = SimpleNamespace(
        session_id=session_id, challenge_check_timed_out=True)
    controller._sessions[session_id] = session
    assert controller.take_challenge_check_timeout(session_id=session_id) is True
    assert session.challenge_check_timed_out is False
    assert controller.take_challenge_check_timeout(session_id=session_id) is False


@pytest.mark.asyncio
async def test_checkpoint_records_challenge_check_timeout_on_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A challenge inspection that cannot answer does not raise out of
    _has_authentication_challenge; it answers False and leaves the
    timeout on the session for the caller to drain exactly once."""
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.browser.auth_verifier"
        ".SENSITIVE_CHALLENGE_TIMEOUT_SECONDS",
        0.2,
        raising=False,
    )

    class HangingLocator:
        async def count(self) -> int:
            await asyncio.Event().wait()
            return 0

    class QuietLocator:
        def filter(self, **_kwargs: object) -> "QuietLocator":
            return self

        async def count(self) -> int:
            return 0

    class Page:
        url = "https://target.invalid/dashboard"

        def locator(self, selector: str) -> object:
            return HangingLocator() if "password" in selector else QuietLocator()

        def get_by_role(self, *_args: object, **_kwargs: object) -> QuietLocator:
            return QuietLocator()

    controller = BrowserController()

    async def no_checkpoint_signals(*, session_id: UUID) -> dict:
        return {"text": "", "scripts": [], "controls": 0}

    monkeypatch.setattr(controller, "discovery_page_signals", no_checkpoint_signals)
    session = cast(JourneyBrowserSession, SimpleNamespace(
        page=Page(), session_id=uuid4(), challenge_check_timed_out=False,
        is_auth_only_url=lambda _: False,
    ))
    assert await controller._has_authentication_challenge(session) is False
    assert session.challenge_check_timed_out is True
    # The drain is one-shot: a second take reports nothing.
    session_id = session.session_id
    controller._sessions[session_id] = session
    assert controller.take_challenge_check_timeout(session_id=session_id) is True
    assert controller.take_challenge_check_timeout(session_id=session_id) is False
