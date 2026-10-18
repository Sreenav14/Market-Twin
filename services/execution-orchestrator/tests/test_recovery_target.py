"""Real Chromium checks for the read-only continuation gate after human Release."""

from pathlib import Path

import pytest
from markettwin_execution_orchestrator.agents.schemas.test_case import SemanticTarget
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "verified"),
    [
        ('<section aria-label="Format"><a href="/agent">Agent</a></section>', True),
        ('<a href="/agent">Agent</a>', False),
        ('<section aria-label="Format"><a>Agent</a><a>Agent</a></section>', False),
        ('<section aria-label="Format"><a href="/agent">Agent</a></section>'
         '<input type="password">', False),
    ],
)
async def test_recovery_requires_original_unique_safe_target(
    tmp_path: Path, content: str, verified: bool,
) -> None:
    controller = BrowserController(artifact_root=tmp_path)
    from uuid import uuid4

    handle = await controller.create_session(
        execution_id=uuid4(), journey_id=uuid4(),
        allowed_origins=(AllowedOrigin("http", "127.0.0.1", 5199),),
        network_policy="local_development",
    )
    try:
        session = controller._sessions[handle.session_id]  # pyright: ignore[reportPrivateUsage]
        await session.page.route("**/*", lambda route: route.fulfill(body="<main>Ready</main>"))
        await session.page.goto("http://127.0.0.1:5199/")
        await controller.begin_human_control(session_id=handle.session_id)
        await session.page.set_content(content)
        session.control_mode = "verifying"  # Simulate the fenced owner-side Release transition.
        target = SemanticTarget(
            scope_role="region", scope_name="Format", role="link", name="Agent",
        )
        assert await controller.verify_recovery_target(handle=handle, target=target) is verified
        assert session.capture_enabled is False
        assert session.control_mode == "verifying"
        assert session.page.url == "http://127.0.0.1:5199/"  # No click or navigation.
    finally:
        await controller.close()
