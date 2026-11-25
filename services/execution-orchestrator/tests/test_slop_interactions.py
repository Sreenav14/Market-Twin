import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from markettwin_execution_orchestrator.slop import interactions
from markettwin_execution_orchestrator.browser.errors import BrowserActionBlockedError, BrowserActionError


@pytest.mark.asyncio
@pytest.mark.parametrize("crashed", [False, True])
async def test_duplicate_links_and_interruption_progress(monkeypatch, crashed):
    monkeypatch.setattr(interactions, "review_screenshots", AsyncMock(return_value=[]))
    targets = [{"role": "tab", "name": "One"}, {"role": "tab", "name": "Two"}]
    controller = SimpleNamespace(
        ui_state_targets=AsyncMock(side_effect=[targets, [], []]),
        navigate=AsyncMock(), click=AsyncMock(),
        probe_page=AsyncMock(return_value={"url": "https://app.test/", "elements": []}),
        capture_evidence_screenshot=AsyncMock(
            side_effect=RuntimeError("Disconnected") if crashed else None,
            return_value="shot.png"),
        page_links=AsyncMock(side_effect=[["https://app.test/one"], ["https://app.test/two"]]))
    progress = AsyncMock()
    kwargs = dict(controller=controller, handle=SimpleNamespace(
        session_id=1, execution_id=2, journey_id=3), url="https://app.test/",
        viewport="mobile320", page_ready=True, on_progress=progress)
    if crashed:
        with pytest.raises(RuntimeError):
            await interactions.inspect_interactions(**kwargs)
        assert progress.call_args.args[0]["result"] == "interrupted:RuntimeError"
    else:
        states, links, _, _ = await interactions.inspect_interactions(**kwargs)
        assert len(states) == 1
        assert links == ["https://app.test/one", "https://app.test/two"]
        assert progress.call_args.args[0]["result"] == "duplicate_state"


def test_hash_screens_are_distinct_but_page_anchors_merge():
    assert interactions.audit_url("https://app.test/#/settings") != interactions.audit_url("https://app.test/#/profile")
    assert interactions.audit_url("https://app.test/#footer") == interactions.audit_url("https://app.test/")


@pytest.mark.asyncio
async def test_sensitive_control_is_reported_without_clicking_and_other_controls_continue(monkeypatch):
    monkeypatch.setattr(interactions, "review_screenshots", AsyncMock(return_value=[]))
    async def preflight(**kw):
        if kw['name'] == 'Delete account':
            raise BrowserActionBlockedError('Not permitted')
        return None
    controller = SimpleNamespace(ui_state_targets=AsyncMock(side_effect=[[
        {'role': 'button', 'name': 'Delete account'},
        {'role': 'button', 'name': 'Open menu'}], []]),
        inspect_click_approval=preflight, navigate=AsyncMock(), click=AsyncMock(),
        probe_page=AsyncMock(return_value={'url': 'https://app.test/', 'elements': []}),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"), page_links=AsyncMock(return_value=[]))
    states, _, skipped, stopped = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url='https://app.test/', viewport='desktop1280', page_ready=True)
    assert not stopped and len(states) == 1
    assert controller.click.await_count == 1
    assert controller.click.call_args.kwargs['name'] == 'Open menu'
    assert 'approval_required' in skipped[0]['reason']


@pytest.mark.asyncio
@pytest.mark.parametrize("lead_stop", [False, True])
async def test_long_running_nested_states_reuse_page_and_obey_lead(monkeypatch, lead_stop):
    monkeypatch.setattr(interactions, "review_screenshots", AsyncMock(return_value=[]))
    progress = {"count": 0}

    async def targets(**kwargs):
        n = progress["count"]
        return [{"role": "button", "name": f"Section {n}"}] if n < 35 else []

    async def click(**kwargs):
        progress["count"] += 1

    async def probe(**kwargs):
        # Genuinely new states must grow the content inventory: under
        # the view-fingerprint identity, a changed word count alone no
        # longer mints a state (that was the MT-000147 fault).
        return {"url": "https://app.test/", "words": progress["count"], "elements": [
            {"kind": "interactive", "tag": "button", "role": "button",
             "name": f"Section {i}", "region": "main", "disabled": False,
             "selected": None, "expanded": None, "invalid": None}
            for i in range(progress["count"] + 1)]}

    controller = SimpleNamespace(ui_state_targets=targets, navigate=AsyncMock(),
        click=AsyncMock(side_effect=click), probe_page=probe,
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=[]))
    checkpoint = AsyncMock(return_value={"decision": "stop" if lead_stop else "continue",
                                        "reason": "Review progress"})
    progress_log = AsyncMock()
    states, _, _, stopped = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url="https://app.test/", viewport="mobile320", page_ready=True, checkpoint=checkpoint,
        on_progress=progress_log)
    assert len(states) == (15 if lead_stop else 35)
    assert stopped is lead_stop
    controller.navigate.assert_not_awaited()
    assert checkpoint.await_count == (1 if lead_stop else 2)
    assert progress_log.await_count == len(states)
    assert progress_log.call_args.args[0]["paths_attempted"] == len(states)


@pytest.mark.asyncio
async def test_unresolvable_menu_does_not_skip_remaining_controls(monkeypatch):
    monkeypatch.setattr(interactions, "review_screenshots", AsyncMock(return_value=[]))
    controller = SimpleNamespace(
        ui_state_targets=AsyncMock(side_effect=[[
            {"role": "button", "name": "MENU CLOSE"},
            {"role": "tab", "name": "Details"}], []]),
        navigate=AsyncMock(), click=AsyncMock(side_effect=[
            BrowserActionError("Ambiguous menu", reason_code="ambiguous_target"), None]),
        probe_page=AsyncMock(return_value={"url": "https://app.test/", "elements": [], "words": 50}),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=["https://app.test/next"]),
    )
    states, links, skipped, stopped = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url="https://app.test/", viewport="mobile320", deadline=time.monotonic() + 10)
    assert not stopped
    assert states[0]["interaction_path"] == "Details"
    assert links == ["https://app.test/next"]
    assert skipped[0]["state"] == "MENU CLOSE"
    assert "ambiguous_target" in skipped[0]["reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", [False, True])
async def test_state_replay_and_policy_stop(monkeypatch, blocked):
    monkeypatch.setattr(interactions, "review_screenshots", AsyncMock(return_value=[]))
    controller = SimpleNamespace(
        ui_state_targets=AsyncMock(side_effect=[[{"role": "tab", "name": "Details"}], []]),
        navigate=AsyncMock(), click=AsyncMock(side_effect=BrowserActionBlockedError("Denied") if blocked else None),
        probe_page=AsyncMock(return_value={"url": "https://app.test/", "elements": [], "words": 50}),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=["https://app.test/hidden"]),
    )
    states, links, skipped, stopped = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url="https://app.test/", viewport="desktop1280", deadline=time.monotonic() + 10)
    assert stopped is blocked
    controller.navigate.assert_awaited_once()
    if blocked:
        assert not states and skipped
        controller.probe_page.assert_not_awaited()
    else:
        assert states[0]["interaction_path"] == "Details"
        assert links == ["https://app.test/hidden"]


def _element(kind, tag, role, name, region, **extra):
    element = {"kind": kind, "tag": tag, "role": role, "name": name,
               "region": region, "disabled": False, "selected": None,
               "expanded": None, "invalid": None,
               "text": name if kind == "text" else ""}
    element.update(extra)
    return element


@pytest.mark.asyncio
async def test_menu_toggle_mints_no_state(monkeypatch):
    """MT-000147 core fault: opening a nav menu changes only chrome, so
    with the entry view seeded it is a duplicate from the first toggle —
    no state, no screenshot, no vision review."""
    review = AsyncMock(return_value=[])
    monkeypatch.setattr(interactions, "review_screenshots", review)
    nav_button = _element("interactive", "button", "button", "Industries", "nav")
    headline = _element("text", "h1", "h1", "Welcome", "main")
    base_probe = {"url": "https://app.test/", "elements": [nav_button, headline]}
    open_probe = {"url": "https://app.test/", "elements": [
        {**nav_button, "expanded": "true"},
        _element("interactive", "a", "menuitem", "Healthcare", "nav"),
        _element("interactive", "a", "menuitem", "Retail", "nav"),
        headline]}
    menu = {"open": False}

    async def probe(**kwargs):
        return open_probe if menu["open"] else base_probe

    async def click(**kwargs):
        if kwargs["name"] == "Industries":
            menu["open"] = True

    async def ui_targets(**kwargs):
        found = [{"role": "button", "name": "Industries"}]
        if menu["open"]:
            found += [{"role": "menuitem", "name": "Healthcare"},
                      {"role": "menuitem", "name": "Retail"}]
        return found

    controller = SimpleNamespace(
        ui_state_targets=AsyncMock(side_effect=ui_targets), navigate=AsyncMock(),
        click=AsyncMock(side_effect=click), probe_page=AsyncMock(side_effect=probe),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=[]))
    progress = AsyncMock()
    states, links, skipped, stopped = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url="https://app.test/", viewport="desktop1280", page_ready=True,
        known_fingerprints={interactions.view_fingerprint(base_probe)},
        on_progress=progress)
    assert states == []
    assert controller.capture_evidence_screenshot.await_count == 0
    assert review.await_count == 0
    results = [call.args[0]["result"] for call in progress.await_args_list]
    assert len(results) == 3
    assert all(result == "duplicate_state" for result in results)
    assert all(call.args[0]["actual_url"] == "https://app.test/"
               for call in progress.await_args_list)


@pytest.mark.asyncio
async def test_navigating_click_is_a_route_discovery_not_a_state(monkeypatch):
    review = AsyncMock(return_value=[])
    monkeypatch.setattr(interactions, "review_screenshots", review)
    controller = SimpleNamespace(
        ui_state_targets=AsyncMock(side_effect=[[{"role": "button", "name": "Get started"}], []]),
        navigate=AsyncMock(), click=AsyncMock(),
        probe_page=AsyncMock(return_value={"url": "https://app.test/landing", "elements": [
            _element("interactive", "button", "button", "Buy", "main")]}),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=["https://app.test/landing", "https://app.test/other"]))
    progress = AsyncMock()
    states, links, skipped, stopped = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url="https://app.test/", viewport="desktop1280", page_ready=True, on_progress=progress)
    assert states == []
    assert links == ["https://app.test/landing", "https://app.test/other"]
    payload = progress.call_args.args[0]
    assert payload["result"] == "navigated"
    assert payload["actual_url"] == "https://app.test/landing"
    assert payload["url"] == "https://app.test/"
    assert controller.capture_evidence_screenshot.await_count == 0
    assert review.await_count == 0


@pytest.mark.asyncio
async def test_rotating_headline_mints_no_state(monkeypatch):
    monkeypatch.setattr(interactions, "review_screenshots", AsyncMock(return_value=[]))
    button = _element("interactive", "button", "button", "Details", "main")
    base_probe = {"url": "https://app.test/", "elements": [
        button, _element("text", "h1", "h1", "Welcome A", "main")]}
    rotated_probe = {"url": "https://app.test/", "elements": [
        button, _element("text", "h1", "h1", "Welcome B", "main")]}
    controller = SimpleNamespace(
        ui_state_targets=AsyncMock(side_effect=[[{"role": "button", "name": "Details"}], []]),
        navigate=AsyncMock(), click=AsyncMock(),
        probe_page=AsyncMock(return_value=rotated_probe),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=[]))
    progress = AsyncMock()
    states, links, skipped, stopped = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url="https://app.test/", viewport="desktop1280", page_ready=True,
        known_fingerprints={interactions.view_fingerprint(base_probe)},
        on_progress=progress)
    assert states == []
    assert progress.call_args.args[0]["result"] == "duplicate_state"


@pytest.mark.asyncio
async def test_new_content_element_still_mints_a_state(monkeypatch):
    monkeypatch.setattr(interactions, "review_screenshots", AsyncMock(return_value=[]))
    opener = _element("interactive", "button", "button", "Open panel", "main")
    base_probe = {"url": "https://app.test/", "elements": [opener]}
    grown_probe = {"url": "https://app.test/", "elements": [
        opener, _element("interactive", "button", "button", "Pay now", "main")]}
    controller = SimpleNamespace(
        ui_state_targets=AsyncMock(side_effect=[
            [{"role": "button", "name": "Open panel"}],
            [{"role": "button", "name": "Open panel"}, {"role": "button", "name": "Pay now"}],
            [{"role": "button", "name": "Open panel"}, {"role": "button", "name": "Pay now"}]]),
        navigate=AsyncMock(), click=AsyncMock(),
        probe_page=AsyncMock(return_value=grown_probe),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=[]))
    on_state = AsyncMock()
    states, links, skipped, stopped = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url="https://app.test/", viewport="desktop1280", page_ready=True,
        known_fingerprints={interactions.view_fingerprint(base_probe)},
        on_state=on_state)
    assert len(states) == 1
    assert states[0]["interaction_path"] == "Open panel"
    on_state.assert_not_awaited()
    assert controller.capture_evidence_screenshot.await_count == 1


@pytest.mark.asyncio
async def test_checkpoint_evidence_carries_the_actual_url(monkeypatch):
    monkeypatch.setattr(interactions, "review_screenshots", AsyncMock(return_value=[]))
    names = [f"Go {i}" for i in range(16)]
    root_targets = [{"role": "button", "name": name} for name in names]
    current = {"url": "https://app.test/"}

    async def click(**kwargs):
        current["url"] = f"https://app.test/{kwargs['name'].replace(' ', '').lower()}"

    controller = SimpleNamespace(
        ui_state_targets=AsyncMock(side_effect=[root_targets] + [[] for _ in range(25)]),
        navigate=AsyncMock(), click=AsyncMock(side_effect=click),
        probe_page=AsyncMock(side_effect=lambda **kwargs: {"url": current["url"], "elements": []}),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=[]))
    checkpoint = AsyncMock(return_value={"decision": "continue", "reason": "ok"})
    states, links, skipped, stopped = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url="https://app.test/", viewport="desktop1280", page_ready=True, checkpoint=checkpoint)
    assert states == []
    assert checkpoint.await_count == 1
    evidence = checkpoint.await_args_list[0].args[0]
    assert evidence["paths_attempted"] == 15
    assert evidence["current_url"] == "https://app.test/go14"
    assert evidence["url"] == "https://app.test/"


@pytest.mark.asyncio
async def test_checkpoint_evidence_carries_notebook_facts(monkeypatch):
    """Issue 2: the Lead's evidence is finished-work facts, not movement —
    checked items and their delta, states measured, routes discovered,
    and the productive delta (new states + new routes)."""
    monkeypatch.setattr(interactions, "review_screenshots", AsyncMock(return_value=[]))
    names = [f"Go {i}" for i in range(16)]
    root_targets = [{"role": "button", "name": name} for name in names]
    current = {"url": "https://app.test/"}

    async def click(**kwargs):
        current["url"] = f"https://app.test/{kwargs['name'].replace(' ', '').lower()}"

    controller = SimpleNamespace(
        ui_state_targets=AsyncMock(side_effect=[root_targets] + [[] for _ in range(25)]),
        navigate=AsyncMock(), click=AsyncMock(side_effect=click),
        probe_page=AsyncMock(side_effect=lambda **kwargs: {"url": current["url"], "elements": []}),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=["https://app.test/landing"]))
    checkpoint = AsyncMock(return_value={"decision": "continue", "reason": "ok"})
    states, links, skipped, stopped = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url="https://app.test/", viewport="desktop1280", page_ready=True, checkpoint=checkpoint)
    assert checkpoint.await_count == 1
    evidence = checkpoint.await_args_list[0].args[0]
    assert evidence["checked_items"] == 15
    assert evidence["checked_delta"] == 15
    assert evidence["attempted_delta"] == 15
    assert evidence["states_measured"] == 0
    assert evidence["routes_discovered"] == 1
    assert evidence["productive_delta"] == 1
    assert evidence["elapsed_seconds"] >= 0
@pytest.mark.asyncio
async def test_failing_control_is_not_retried_beyond_two_attempts(monkeypatch):
    """Pace: the same control reached through different parents stops
    being retried after two failed activations."""
    monkeypatch.setattr(interactions, "review_screenshots", AsyncMock(return_value=[]))
    opened = {"menu": None}
    clicked = []

    async def targets(**kwargs):
        found = [{"role": "button", "name": name} for name in ("R1", "R2", "R3")]
        if opened["menu"] is not None:
            found.append({"role": "button", "name": "Broken"})
        return found

    async def click(**kwargs):
        clicked.append(kwargs["name"])
        if kwargs["name"] == "Broken":
            raise BrowserActionError("Cannot activate", reason_code="target_failed")
        opened["menu"] = kwargs["name"]

    controller = SimpleNamespace(
        ui_state_targets=AsyncMock(side_effect=targets), navigate=AsyncMock(),
        click=AsyncMock(side_effect=click),
        probe_page=AsyncMock(return_value={"url": "https://app.test/", "elements": []}),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=[]))
    states, links, skipped, stopped = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url="https://app.test/", viewport="desktop1280", page_ready=True)
    assert not stopped
    assert clicked.count("Broken") == 2
    assert any("not retried" in entry["reason"] for entry in skipped)


@pytest.mark.asyncio
async def test_failing_group_is_abandoned_after_five_failures(monkeypatch):
    """Pace: when five controls under one root have failed, the rest of
    that group is not retried (a broken preferences centre dies whole)."""
    monkeypatch.setattr(interactions, "review_screenshots", AsyncMock(return_value=[]))
    opened = {"value": False}
    clicked = []
    names = [f"Toggle {i}" for i in range(6)]

    async def targets(**kwargs):
        found = [{"role": "button", "name": "Panel"}]
        if opened["value"]:
            found += [{"role": "button", "name": name} for name in names]
        return found

    async def click(**kwargs):
        clicked.append(kwargs["name"])
        if kwargs["name"] == "Panel":
            opened["value"] = True
            return
        raise BrowserActionError("Cannot activate", reason_code="target_failed")

    controller = SimpleNamespace(
        ui_state_targets=AsyncMock(side_effect=targets), navigate=AsyncMock(),
        click=AsyncMock(side_effect=click),
        probe_page=AsyncMock(return_value={"url": "https://app.test/", "elements": []}),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=[]))
    states, links, skipped, stopped = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url="https://app.test/", viewport="desktop1280", page_ready=True)
    assert not stopped
    assert "Toggle 5" not in clicked
    assert clicked.count("Toggle 0") == 1
    assert any("rest of the group was not retried" in entry["reason"] for entry in skipped)


@pytest.mark.asyncio
async def test_consent_overlay_is_dismissed_once_and_never_explored(monkeypatch):
    """Consent-as-chrome: the overlay is dismissed via its standard
    control and its preference controls are never explored as product UI."""
    monkeypatch.setattr(interactions, "review_screenshots", AsyncMock(return_value=[]))
    dismissed = {"value": False}
    clicked = []

    async def targets(**kwargs):
        if dismissed["value"]:
            return [{"role": "tab", "name": "Details"}]
        return [{"role": "button", "name": "Accept all cookies"},
                {"role": "button", "name": "Manage preferences"},
                {"role": "tab", "name": "Details"}]

    async def click(**kwargs):
        clicked.append(kwargs["name"])
        if kwargs["name"] == "Accept all cookies":
            dismissed["value"] = True

    controller = SimpleNamespace(
        ui_state_targets=AsyncMock(side_effect=targets), navigate=AsyncMock(),
        click=AsyncMock(side_effect=click),
        probe_page=AsyncMock(return_value={"url": "https://app.test/", "elements": []}),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=[]))
    states, links, skipped, stopped = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url="https://app.test/", viewport="desktop1280", page_ready=True)
    assert not stopped
    assert clicked == ["Accept all cookies", "Details"]
    assert any(entry["state"] == "Cookie consent" and "dismissed" in entry["reason"]
               for entry in skipped)
    assert len(states) == 1


@pytest.mark.asyncio
async def test_traversal_actions_run_without_observations(monkeypatch):
    """T-O3 (doc 18 section 15): every traversal-internal click/navigate —
    consent dismissal, reset navigation, replay and final clicks — runs
    with observe=False, and state screenshots come from the capture-only
    method, never from an observation-building call."""
    monkeypatch.setattr(interactions, "review_screenshots", AsyncMock(return_value=[]))
    targets = [
        {"role": "button", "name": "Accept all cookies"},
        {"role": "button", "name": "Alpha"},
        {"role": "button", "name": "Beta"},
    ]
    probes = [
        {"url": "https://app.test/", "elements": [
            {"kind": "interactive", "tag": "button", "role": "button", "name": "Alpha",
             "region": "main", "disabled": False, "selected": None, "expanded": None,
             "invalid": None}]},
        {"url": "https://app.test/", "elements": [
            {"kind": "interactive", "tag": "button", "role": "button", "name": "Beta",
             "region": "main", "disabled": False, "selected": None, "expanded": None,
             "invalid": None},
            {"kind": "text", "tag": "h1", "role": "heading", "name": "More",
             "region": "main"}]},
    ]
    controller = SimpleNamespace(
        ui_state_targets=AsyncMock(side_effect=[targets, targets, targets, targets]),
        navigate=AsyncMock(), click=AsyncMock(),
        probe_page=AsyncMock(side_effect=probes),
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=[]))
    states, _, _, _ = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url="https://app.test/", viewport="desktop1280", page_ready=True)
    assert len(states) == 2
    assert controller.click.await_count == 3  # consent, Alpha, Beta
    for call in controller.click.call_args_list:
        assert call.kwargs.get("observe") is False
    assert controller.navigate.await_count == 1  # the sibling reset for Beta
    for call in controller.navigate.call_args_list:
        assert call.kwargs.get("observe") is False
    assert controller.capture_evidence_screenshot.await_count == 2


def _growing_controller(monkeypatch, *, cap, click_side_effect=None):
    """The growing-probe pattern: each click reveals one more control and
    grows the content inventory, so every click mints a genuinely new
    state until `cap` states exist."""
    progress = {"count": 0}

    async def targets(**kwargs):
        n = progress["count"]
        return [{"role": "button", "name": f"Section {n}"}] if n < cap else []

    async def click(**kwargs):
        if click_side_effect is not None:
            await click_side_effect(progress["count"])
        progress["count"] += 1

    async def probe(**kwargs):
        return {"url": "https://app.test/", "elements": [
            {"kind": "interactive", "tag": "button", "role": "button",
             "name": f"Section {i}", "region": "main", "disabled": False,
             "selected": None, "expanded": None, "invalid": None}
            for i in range(progress["count"] + 1)]}

    return SimpleNamespace(
        ui_state_targets=targets, navigate=AsyncMock(),
        click=AsyncMock(side_effect=click), probe_page=probe,
        capture_evidence_screenshot=AsyncMock(return_value="shot.png"),
        page_links=AsyncMock(return_value=[]))


@pytest.mark.asyncio
@pytest.mark.parametrize(("cap", "expected_sizes"), [(5, [5]), (20, [8, 8, 4])])
async def test_visual_review_is_batched_in_discovery_order(monkeypatch, cap, expected_sizes):
    """T-V1 (doc 18 section 15): new-state screenshots are reviewed in
    chunks of at most VISION_BATCH_MAX, in discovery order, and a chunk's
    findings land only on its first state — never spread across states."""
    calls = []

    async def review(states, **kwargs):
        calls.append([state["interaction_path"] for state in states])
        return [{"rule_id": "UI_VISUAL_REVIEW", "severity": "minor",
                 "detail": "stub finding"}]

    monkeypatch.setattr(interactions, "review_screenshots", review)
    controller = _growing_controller(monkeypatch, cap=cap)
    states, _, _, _ = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url="https://app.test/", viewport="mobile320", page_ready=True)
    assert len(states) == cap
    assert [len(call) for call in calls] == expected_sizes
    flat = [path for call in calls for path in call]
    assert flat == [state["interaction_path"] for state in states]
    leaders = {expected_sizes[0] * i for i in range(len(expected_sizes))}
    for index, state in enumerate(states):
        has_finding = any(signal["rule_id"] == "UI_VISUAL_REVIEW"
                          for signal in state["page_signals"])
        assert has_finding == (index in leaders)


@pytest.mark.asyncio
async def test_visual_review_unreached_by_budget_marks_states_unassessed(monkeypatch):
    """T-V2 (doc 18 section 15): when the traversal budget expires before
    the batched review runs, the review is never called and every minted
    state carries the named budget-expiry unassessed signal."""
    review = AsyncMock(return_value=[])
    monkeypatch.setattr(interactions, "review_screenshots", review)

    async def slow_fourth(index):
        if index >= 3:
            await asyncio.sleep(0.5)

    controller = _growing_controller(monkeypatch, cap=10, click_side_effect=slow_fourth)
    states, _, _, _ = await interactions.inspect_interactions(
        controller=controller, handle=SimpleNamespace(session_id=1, execution_id=2, journey_id=3),
        url="https://app.test/", viewport="mobile320", page_ready=True,
        deadline=time.monotonic() + 0.2)
    assert len(states) >= 3
    review.assert_not_awaited()
    for state in states:
        assert any(
            signal["rule_id"] == "UI_VISUAL_UNASSESSED"
            and "budget expired" in signal["detail"]
            for signal in state["page_signals"])
