from typing import Any, cast

import pytest
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from markettwin_execution_orchestrator.mcp import playwright
from markettwin_execution_orchestrator.mcp.playwright import (
    PLAYWRIGHT_MCP_ALLOWED_TOOLS,
    create_playwright_toolset,
)


def test_playwright_toolset_keeps_agent_context_small(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def capture_toolset(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(playwright, "MCPToolset", capture_toolset)

    create_playwright_toolset()

    connection_params = cast(StdioConnectionParams, captured["connection_params"])
    server_params = connection_params.server_params

    assert captured["tool_filter"] == list(PLAYWRIGHT_MCP_ALLOWED_TOOLS)
    assert PLAYWRIGHT_MCP_ALLOWED_TOOLS == (
        "browser_navigate",
        "browser_snapshot",
        "browser_take_screenshot",
    )
    assert server_params.args[-4:] == [
        "--snapshot-mode",
        "full",
        "--image-responses",
        "omit",
    ]
