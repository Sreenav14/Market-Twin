"""Run the first MarketTwin browser-agent mission."""

import asyncio
from uuid import uuid4

from google.adk.runners import InMemoryRunner
from google.genai import types
from markettwin_execution_orchestrator.agents.browser_agent import (
    create_browser_agent,
)
from markettwin_execution_orchestrator.mcp.playwright import (
    create_playwright_toolset,
)

AUTHORIZED_TARGET = ("https://en.wikipedia.org/wiki/Software_testing")
EXPECTED_HEADING = "Software testing"

APP_NAME = "markettwin_gate_a"
USER_ID = "local_developer"


async def main() -> None:
    """Execute one authorized public-site browser mission."""

    playwright_toolset = create_playwright_toolset()
    agent = create_browser_agent(
        playwright_toolset=playwright_toolset,
    )

    runner = InMemoryRunner(
        agent=agent,
        app_name=APP_NAME,
    )

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
2. Call browser_snapshot once.
3. Verify whether the heading "{EXPECTED_HEADING}" is present.
4. Call browser_take_screenshot once.
5. Call browser_close once.
6. STOP using tools.
7. Return a final text response containing SUCCESS or FAILURE.

Never navigate more than once.
Do not call any other tools.
""".strip()
    message = types.Content(
        role="user",
        parts=[
            types.Part(text=mission),
        ],
    )

    final_response_parts: list[str] = []

    try:
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session_id,
            new_message=message,
        ):
            function_calls = event.get_function_calls()

            for function_call in function_calls:
                print(
                    f"Tool selected: {function_call.name}"
                )

            if (
                event.is_final_response()
                and event.content
                and event.content.parts
            ):
                for part in event.content.parts:
                    if part.text:
                        final_response_parts.append(part.text)
    finally:
        await runner.close()

    if not final_response_parts:
        raise RuntimeError(
            "The browser agent did not return a final response."
        )

    print("\nFinal agent response:")
    print("\n".join(final_response_parts))


if __name__ == "__main__":
    asyncio.run(main())
