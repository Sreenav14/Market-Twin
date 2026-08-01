""" playwright mcp server """

import os
from typing import Final

from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from mcp import StdioServerParameters

PLAYWRIGHT_MCP_PACKAGE: Final[str] = "@playwright/mcp@0.0.78"

PLAYWRIGHT_MCP_ALLOWED_TOOLS: Final[tuple[str, ...]] = (
    "browser_navigate",
    "browser_navigate_back",
    "browser_snapshot",
    "browser_click",
    "browser_type",
    "browser_press_key",
    "browser_select_option",
    "browser_hover",
    "browser_wait_for",
    "browser_take_screenshot",
    "browser_console_messages",
    "browser_tabs",
    "browser_close",
)

def create_playwright_toolset() -> MCPToolset:
    """ Create the Google ADK toolset for Playwright MCP """
    
    npx_command = "npx.cmd" if os.name == "nt" else "npx"
    
    return MCPToolset(
        connection_params = StdioConnectionParams(
            server_params = StdioServerParameters(
                command = npx_command,
                args = [
                    "-y",
                    PLAYWRIGHT_MCP_PACKAGE,
                    "--headless",
                    "--isolated",
                    "--codegen",
                    "none",
                    "--snapshot-mode",
                    "full",
                ],
            ),
            timeout = 90.0,
        ),
        tool_filter = list(PLAYWRIGHT_MCP_ALLOWED_TOOLS),
    )
