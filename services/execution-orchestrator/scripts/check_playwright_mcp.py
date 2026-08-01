""" Verify the Playwright MCP server is running """

import asyncio

from markettwin_execution_orchestrator.mcp.playwright import (
    create_playwright_toolset,
)


async def main() -> None:
    """ Connect to playwright mcp and print its available tools"""
    
    toolset = create_playwright_toolset()
    
    try:
        tools = await toolset.get_tools()
        tool_names = sorted(tool.name for tool in tools)
        
        print(f"Discoverd {len(tool_names)} Playwright MCP tools:")
        
        for tool_name in tool_names:
            print(f"- {tool_name}")
    finally:
        await toolset.close()
        
        
if __name__ == "__main__":
    asyncio.run(main())