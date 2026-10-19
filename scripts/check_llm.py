"""Make one small LLM request using MarketTwin's configured model and key.

Run from the repository root: uv run --no-sync --env-file .env python scripts/check_llm.py
"""

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import cast


async def main() -> int:
    # Keep this diagnostic out of content telemetry and provider debug logs.
    os.environ["MARKETTWIN_OBSERVABILITY_ENABLED"] = "false"
    os.environ["MARKETTWIN_OBSERVABILITY_CAPTURE_CONTENT"] = "false"
    os.environ["OTEL_SDK_DISABLED"] = "true"
    logging.disable(logging.CRITICAL)

    import litellm
    from litellm import ModelResponse
    from markettwin_execution_orchestrator.models.model_factory import (
        resolve_model_runtime_configuration,
    )
    from markettwin_shared.model_parameters import completion_parameters

    litellm.suppress_debug_info = True
    config = resolve_model_runtime_configuration(max_tokens=256)
    if config.provider != "openai":
        print(
            json.dumps(
                {"status": "not_sent", "reason": "This diagnostic supports OpenAI configuration."}
            )
        )
        return 1
    key = os.getenv("MODEL_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        print(json.dumps({"status": "not_sent", "reason": "No model API key configured."}))
        return 1
    try:
        complete = cast(Callable[..., Awaitable[ModelResponse]], vars(litellm)["acompletion"])
        async with asyncio.timeout(30):
            response = await complete(
                model=config.model_name,
                api_key=key,
                messages=[{"role": "user", "content": "Reply with only OK."}],
                num_retries=0,
                timeout=20,
                stream=False,
                **completion_parameters(config.model_name, 256),
            )
        # The fixed prompt requests no user data. Never print request headers or keys.
        choice = response.choices[0]
        print(json.dumps({
            "status": "connected", "model": config.model_name,
            "received_text": bool(choice.message.content),
            "reply_is_ok": (choice.message.content or "").strip() == "OK",
            "finish_reason": choice.finish_reason,
        }))
        return 0
    except Exception as error:
        print(json.dumps({
            "status": "failed", "model": config.model_name,
            "error_type": type(error).__name__,
            "http_status": getattr(error, "status_code", None),
        }))
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
