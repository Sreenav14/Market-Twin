"""Real Chromium classification using actual DOM metadata; transport stays synthetic."""

from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserActionBlockedError


@pytest.mark.parametrize(("markup", "allowed"), [
    ('<a href="/docs/payments">Payment docs</a>', True),
    ('<button type="button">Payment docs</button>', False),
    ('<a href="/docs/delete">Payment docs</a>', False),
    ('<a href="http://127.0.0.1:5192/docs/payments">Payment docs</a>', False),
    ('<form><a href="/docs/payments">Payment docs</a></form>', False),
])
async def test_documentation_navigation_uses_dom_and_frozen_origin(tmp_path, markup, allowed):
    async with BrowserController(artifact_root=tmp_path) as controller:
        handle = await controller.create_session(
            execution_id=uuid4(), journey_id=uuid4(),
            allowed_origins=(AllowedOrigin(scheme="http", hostname="127.0.0.1", port=5191),),
            network_policy="local_development",
        )
        page = controller._sessions[handle.session_id].page
        await page.route("http://127.0.0.1:5191/**", lambda route: route.fulfill(
            body=markup if route.request.url.endswith("/start") else "<h1>Documentation</h1>",
            content_type="text/html",
        ))
        await controller.navigate(session_id=handle.session_id, url="http://127.0.0.1:5191/start")
        role = "button" if markup.startswith("<button") else "link"
        if allowed:
            result = await controller.click(
                session_id=handle.session_id, role=role, name="Payment docs",
            )
            assert result.observation.url == "http://127.0.0.1:5191/docs/payments"
        else:
            with pytest.raises(BrowserActionBlockedError):
                await controller.click(session_id=handle.session_id, role=role, name="Payment docs")
            assert page.url == "http://127.0.0.1:5191/start"
