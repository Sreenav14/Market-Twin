"""Verify Google ADK can use the local Ollama model."""

import asyncio
from uuid import uuid4

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from markettwin_execution_orchestrator.models.model_factory import (
    create_model,
)

APP_NAME = "markettwin_ollama_check"
USER_ID = "local_developer"


async def main() -> None:
    """Run one simple ADK request against local Ollama."""

    agent = LlmAgent(
        name="ollama_check_agent",
        model=create_model(),
        instruction=(
            "Follow the user's instruction exactly and respond concisely."
        ),
    )

    runner = InMemoryRunner(
        agent=agent,
        app_name=APP_NAME,
    )

    session_id = f"ollama-check-{uuid4()}"

    await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=session_id,
    )

    message = types.Content(
        role="user",
        parts=[
            types.Part(
                text="Reply with exactly: MarketTwin ADK Ollama ready"
            ),
        ],
    )

    final_parts: list[str] = []

    try:
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session_id,
            new_message=message,
        ):
            if (
                event.is_final_response()
                and event.content
                and event.content.parts
            ):
                for part in event.content.parts:
                    if part.text:
                        final_parts.append(part.text)
    finally:
        await runner.close()

    if not final_parts:
        raise RuntimeError("ADK did not return a final response.")

    print("\nADK response:")
    print("\n".join(final_parts))


if __name__ == "__main__":
    asyncio.run(main())