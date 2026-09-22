"""Local browser handoff demo plus an isolated current-code race reproduction.

Only synthetic credentials; no model calls, external services, or real accounts.
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from handoff_protocol import Handoff, Rejected
from markettwin_execution_orchestrator.browser import controller as controller_module
from markettwin_execution_orchestrator.browser.controller import BrowserController
from playwright.async_api import async_playwright


class ObservedLock(asyncio.Lock):
    def __init__(self):
        super().__init__()
        self.acquisitions = 0
        self.attempts = {index: asyncio.Event() for index in (1, 2, 3)}

    async def acquire(self):
        self.acquisitions += 1
        self.attempts[self.acquisitions].set()
        return await super().acquire()


async def reproduce_current_race() -> dict:
    lock = ObservedLock()
    session_id = uuid4()
    session = SimpleNamespace(
        state="open", capture_enabled=True, tracing_active=False,
        lock=lock, next_action_number=lambda: 1,
    )
    controller = BrowserController()
    controller._sessions[session_id] = session
    observed_states = []

    async def fake_observe(*args, **kwargs):
        observed_states.append(session.state)
        return SimpleNamespace()

    await lock.acquire()
    with patch.object(controller_module, "capture_screenshot", AsyncMock(return_value=None)), \
         patch.object(controller_module, "build_observation", side_effect=fake_observe):
        human = asyncio.create_task(controller.begin_human_control(session_id=session_id))
        await lock.attempts[2].wait()
        agent = asyncio.create_task(controller.get_state(session_id=session_id))
        await lock.attempts[3].wait()
        lock.release()
        await human
        await agent
    controller._sessions.clear()
    return {
        "method": "actual_controller_with_fake_session_and_observation",
        "agent_observation_executed_in_state": observed_states,
        "race_reproduced": observed_states == ["human_control"],
        "production_fix_applied": False,
    }


async def browser_demo() -> dict:
    html = """<!doctype html><title>Local handoff fixture</title>
      <label>Password <input type="password" id="password"></label>
      <button id="login">Sign in</button>
      <script>
        document.querySelector('#login').onclick = () => {
          if (document.querySelector('#password').value === 'SYNTHETIC_ONLY') {
            localStorage.setItem('fixture_identity', 'fixture_user');
            document.body.innerHTML = '<h1>Billing overview</h1><p>Plan: Test plan</p>';
          }
        };
      </script>"""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context()

            async def fixture_route(route):
                if route.request.url == "https://fixture.example/":
                    await route.fulfill(status=200, content_type="text/html", body=html)
                else:
                    await route.abort()

            await context.route("**/*", fixture_route)
            page = await context.new_page()
            await page.goto("https://fixture.example/")
            original_page = page
            await context.add_cookies([{
                "name": "journey_marker", "value": "fixture", "url": "https://fixture.example/",
            }])
            protocol = Handoff("fixture_context", frozenset({"fixture_operator"}))
            await protocol.request_handoff("fixture_context")
            lease = await protocol.claim("fixture_operator", "fixture_context", now=0, ttl=60)

            async def synthetic_human_input():
                await page.get_by_label("Password").fill("SYNTHETIC_ONLY")
                await page.get_by_role("button", name="Sign in").click()

            await protocol.human_action(lease, "fixture_context", 1, synthetic_human_input)
            protocol.record_page_event("SYNTHETIC_ONLY")
            await protocol.done(lease, "fixture_context", 2)
            state_after_done = protocol.state
            identity = await page.evaluate("localStorage.getItem('fixture_identity')")
            capture_safe = await page.locator("input[type=password]").count() == 0
            verified = await protocol.verify(
                "fixture_context", postcondition=identity == "fixture_user",
                capture_safe=capture_safe,
            )
            stale_rejected = False
            try:
                await protocol.agent_action(0, "fixture_context", page.title)
            except Rejected:
                stale_rejected = True
            title = await protocol.agent_action(protocol.epoch, "fixture_context", page.title)
            result = {
                "same_page_object": page is original_page,
                "same_context_cookie_retained": any(
                    cookie["name"] == "journey_marker" for cookie in await context.cookies()
                ),
                "state_after_done_before_verification": state_after_done,
                "verified_identity": identity == "fixture_user",
                "verified_resume": verified, "stale_agent_epoch_rejected": stale_rejected,
                "synthetic_secret_absent_from_audit": "SYNTHETIC_ONLY" not in protocol.audit,
                "resumed_page_title": title, "audit": protocol.audit,
                "model_calls": 0,
                "limitation": "Scripted human input; no viewer, SSO, MFA, or production wiring.",
            }
            await context.close()
            return result
        finally:
            await browser.close()


async def main():
    result = {
        "kind": "offline_handoff_protocol_and_local_browser_demo",
        "current_controller_race": await reproduce_current_race(),
        "proposed_protocol_browser_demo": await browser_demo(),
    }
    Path(__file__).with_name("handoff-demo-results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
