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
        browser_tools = [
            tool
            for tool in create_browser_tools(
                controller=browser_controller,
                handle=browser_session,
            )
            if tool.__name__
            in {
                "browser_navigate",
                "browser_get_state",
                "browser_take_screenshot",
            }
        ]
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
        selected_tools: list[str] = []
        completed_tools: list[str] = []

        try:
            try:
                async for event in runner.run_async(
                    user_id=USER_ID,
                    session_id=session_id,
                    new_message=message,
                ):
                    for function_call in event.get_function_calls():
                        selected_tools.append(function_call.name or "")
                        print(f"Tool selected: {function_call.name}")

                    for function_response in event.get_function_responses():
                        response = function_response.response
                        if not isinstance(response, dict) or "error" not in response:
                            completed_tools.append(function_response.name or "")

                    if (
                        event.content
                        and event.content.parts
                        and not event.get_function_calls()
                        and not event.partial
                    ):
                        for part in event.content.parts:
                            if part.text:
                                final_response_parts.append(part.text)
            finally:
                await runner.close()

            final_state = await browser_controller.get_state(
                session_id=browser_session.session_id,
                execution_id=execution_id,
                journey_id=journey_id,
            )
        finally:
            await browser_controller.close_session(
                session_id=browser_session.session_id,
                execution_id=execution_id,
                journey_id=journey_id,
            )

        if not final_response_parts:
            raise RuntimeError(
                "The browser agent did not return a final response. "
                f"tools_selected={selected_tools}; "
                f"tools_completed={completed_tools}."
            )

        final_response = "\n".join(final_response_parts).strip()
        print("\nFinal agent response:")
        print(final_response)

        navigate_completed = (
            selected_tools.count("browser_navigate") == 1
            and completed_tools.count("browser_navigate") == 1
        )
        screenshot_completed = (
            selected_tools.count("browser_take_screenshot") == 1
            and completed_tools.count("browser_take_screenshot") == 1
        )
        expected_heading_present = (
            f'heading "{EXPECTED_HEADING}"'.casefold()
            in final_state.observation.aria_snapshot.casefold()
        )

        smoke_result = (
            "SUCCESS"
            if navigate_completed
            and screenshot_completed
            and expected_heading_present
            else "FAILURE"
        )
        print(f"\nSmoke result: {smoke_result}")

        if smoke_result == "FAILURE":
            raise RuntimeError(
                "Browser smoke agent failed its deterministic contract: "
                f"navigate_once={navigate_completed}, "
                f"screenshot_once={screenshot_completed}, "
                f"expected_heading_present={expected_heading_present}"
            )


if __name__ == "__main__":
    asyncio.run(main())
