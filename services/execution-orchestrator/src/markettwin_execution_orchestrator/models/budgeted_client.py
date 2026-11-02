"""Apply the run budget to the exact request produced by ADK's model adapter."""

import asyncio
from typing import Any

import litellm
from google.adk.models.lite_llm import LiteLLMClient
from litellm.exceptions import APIConnectionError, RateLimitError, ServiceUnavailableError, Timeout
from markettwin_database.model_budget import model_call


class BudgetedLiteLLMClient(LiteLLMClient):
    def completion(
        self, model: Any, messages: Any, tools: Any, stream: bool = False, **kwargs: Any,
    ) -> Any:
        raise ValueError("Budgeted execution requires asynchronous non-streaming model requests.")

    async def acompletion(
        self, model: Any, messages: Any, tools: Any, **kwargs: Any,
    ) -> Any:
        if kwargs.get("stream"):
            raise ValueError("Budgeted execution requires non-streaming model responses.")
        output_tokens = int(kwargs.get("max_completion_tokens") or kwargs.get("max_tokens") or 512)
        input_tokens = litellm.token_counter(  # pyright: ignore[reportUnknownMemberType]
            model=str(model), messages=messages, tools=tools,
        )
        # One reservation represents one provider attempt; SDK retries are disabled.
        retries = int(kwargs.get("num_retries") or 0)
        kwargs["num_retries"] = 0
        kwargs["timeout"] = 60
        attempt = 0
        while True:
            try:
                async with model_call(
                    model=str(model), input_tokens=input_tokens, output_tokens=output_tokens,
                ) as call, asyncio.timeout(65):
                    response = await super().acompletion(model, messages, tools, **kwargs)
                    call.record(response)
                    return response
            except (APIConnectionError, RateLimitError, ServiceUnavailableError, Timeout):
                if attempt >= retries:
                    raise
                await asyncio.sleep(min(2 ** attempt, 4))
                attempt += 1
