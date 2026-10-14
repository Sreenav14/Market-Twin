"""Real MCP sessions exposing only one journey's controlled Playwright tools."""

from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from google.adk.tools import BaseTool, ToolContext
from google.genai import types as genai_types
from mcp import ClientSession, types
from mcp.server import Server
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy.exc import SQLAlchemyError

from markettwin_execution_orchestrator.browser.errors import BrowserPolicyError
from markettwin_execution_orchestrator.browser.tools import BrowserTool


class ControlledBrowserMCPTool(BaseTool):
    """Dispatch once; a transport error must never replay a browser action."""

    def __init__(self, *, specification: types.Tool, client: ClientSession) -> None:
        # ADK's public BaseTool constructor lacks annotations for name/description.
        super().__init__(name=specification.name, description=specification.description or "")  # pyright: ignore[reportUnknownMemberType]
        self.specification = specification
        self.client = client

    def _get_declaration(self) -> genai_types.FunctionDeclaration:
        return genai_types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema=self.specification.inputSchema,
        )

    async def run_async(self, *, args: dict[str, Any], tool_context: ToolContext) -> object:
        result = await self.client.call_tool(self.name, arguments=args)
        if result.isError:
            if (
                result.structuredContent
                and result.structuredContent.get("error_kind") == "persistence_failed"
            ):
                raise SQLAlchemyError(str(result.structuredContent["message"]))
            if (
                result.structuredContent
                and result.structuredContent.get("error_kind") == "policy_blocked"
            ):
                raise BrowserPolicyError(str(result.structuredContent["message"]))
            message = " ".join(
                item.text for item in result.content if isinstance(item, types.TextContent)
            )
            raise RuntimeError(message or "Controlled browser MCP call failed.")
        if result.structuredContent is None:
            raise RuntimeError("Controlled browser MCP returned no structured observation.")
        return result.structuredContent


@asynccontextmanager
async def connect_controlled_browser_tools(
    browser_tools: Sequence[BrowserTool],
) -> AsyncGenerator[list[ControlledBrowserMCPTool], None]:
    """Initialize/discover MCP tools over memory streams; close both ends on exit.

    The server functions retain their original handle, policy checks, recorder,
    and shared action lock. No network listener or second browser is created.
    """
    registry = FastMCP("markettwin_controlled_playwright")
    for function in browser_tools:
        registry.add_tool(function)
    server: Server[object] = Server("markettwin_controlled_playwright")

    async def list_tools() -> list[types.Tool]:
        tools = await registry.list_tools()
        return [
            tool.model_copy(
                update={"inputSchema": {**tool.inputSchema, "additionalProperties": False}}
            )
            for tool in tools
        ]

    async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
        try:
            return await registry.call_tool(name, arguments)
        except Exception as exc:
            # FastMCP wraps callback errors. Preserve the existing journey policy
            # outcome rather than presenting a policy rejection as an action failure.
            cause: BaseException | None = exc
            while cause is not None:
                if isinstance(cause, (BrowserPolicyError, SQLAlchemyError)):
                    error_kind = (
                        "policy_blocked"
                        if isinstance(cause, BrowserPolicyError)
                        else "persistence_failed"
                    )
                    return types.CallToolResult(
                        isError=True,
                        content=[types.TextContent(type="text", text=str(cause))],
                        structuredContent={"error_kind": error_kind, "message": str(cause)},
                    )
                cause = cause.__cause__
            raise

    server.list_tools()(list_tools)
    server.call_tool()(call_tool)
    async with create_connected_server_and_client_session(server) as client:
        discovered = await client.list_tools()
        yield [
            ControlledBrowserMCPTool(specification=tool, client=client) for tool in discovered.tools
        ]
