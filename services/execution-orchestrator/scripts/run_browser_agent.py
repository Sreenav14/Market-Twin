"""Run the first MarketTwin browser-agent mission."""

import asyncio
import os
from uuid import uuid4

from google.adk.runners import InMemoryRunner
from google.genai import types
from markettwin_execution_orchestrator.agents.browser_agent import (
    create_browser_agent,
)

AUTHORIZED_TARGET = ("https://en.wikipedia.org/wiki/Software_testing")
EXPECTED_HEADING = "Software testing"

APP_NAME = "markettwin_gate_a"
USER_ID = "local_developer"
MODEL_NAME = "gemini-3.5-flash-lite"


async def main() -> None:
    """Execute one authorized public-site browser mission."""

    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError(
            "GOOGLE_API_KEY is not configured in the environment."
        )

    agent = create_browser_agent(model=MODEL_NAME)

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
AUTHORIZED_TARGET: {AUTHORIZED_TARGET}

Mission:
1. Navigate only to the authorized target: {AUTHORIZED_TARGET}.
2. Inspect the page using a browser snapshot.
3. Verify that the page contains the heading "{EXPECTED_HEADING}".
4. Take a screenshot.
5. Report whether the mission succeeded.
6. Include the final page URL.

Do not navigate to any other domain.
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