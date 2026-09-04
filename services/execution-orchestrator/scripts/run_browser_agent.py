"""Run one local MarketTwin public-browser smoke mission in Python."""

import asyncio
from uuid import uuid4

from google.adk.runners import InMemoryRunner
from google.genai import types
from markettwin_execution_orchestrator.agents.browser_agent import create_browser_agent
from markettwin_execution_orchestrator.browser import AllowedOrigin, BrowserController
from markettwin_execution_orchestrator.browser.tools import create_browser_tools

AUTHORIZED_TARGET = "https://en.wikipedia.org/wiki/Software_testing"
EXPECTED_HEADING = "Software testing"
APP_NAME = "markettwin_gate_a"
USER_ID = "local_developer"


async def main() -> None:
    """Execute one authorized public-site mission without Node or Playwright MCP."""

    execution_id = uuid4()
    journey_id = uuid4()

    async with BrowserController() as browser_controller:
        browser_session = await browser_controller.create_session(
            execution_id=execution_id,
            journey_id=journey_id,
            allowed_origins=(
                AllowedOrigin(
                    scheme="https",
                    hostname="en.wikipedia.org",
                    include_subdomains=False,
                ),
            ),
            network_policy="public_only",
        )
        browser_tools = create_browser_tools(
            controller=browser_controller,
            handle=browser_session,
        )
        agent = create_browser_agent(browser_tools)
        runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
        session_id = f"gate-a-{uuid4()}"

        await runner.session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=session_id,
        )

        mission = f"""
/no_think

Authorized target: {AUTHORIZED_TARGET}

Do exactly this:
1. Call browser_navigate once with the authorized target.
2. Inspect the returned accessibility state.
3. Verify whether the heading "{EXPECTED_HEADING}" is present.
4. Call browser_take_screenshot once.
5. Stop using tools.
6. Return a final text response containing SUCCESS or FAILURE.

Never navigate more than once and never use another target.
""".strip()
        message = types.Content(role="user", parts=[types.Part(text=mission)])
        final_response_parts: list[str] = []

        try:
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id=session_id,
                new_message=message,
            ):
                for function_call in event.get_function_calls():
                    print(f"Tool selected: {function_call.name}")

                if event.is_final_response() and event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            final_response_parts.append(part.text)
        finally:
            await runner.close()
            await browser_controller.close_session(
                session_id=browser_session.session_id,
                execution_id=execution_id,
                journey_id=journey_id,
            )

        if not final_response_parts:
            raise RuntimeError("The browser agent did not return a final response.")

        print("\nFinal agent response:")
        print("\n".join(final_response_parts))


if __name__ == "__main__":
    asyncio.run(main())
