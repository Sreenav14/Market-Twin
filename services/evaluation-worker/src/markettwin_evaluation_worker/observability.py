"""LiteLLM observability for MarketTwin evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from markettwin_shared.observability import (
    initialize_observability,
    observability_capture_content_enabled,
)
from openinference.instrumentation import (
    TraceConfig,
)
from openinference.instrumentation.litellm import (
    LiteLLMInstrumentor,
)


@dataclass(frozen=True, slots=True)
class LiteLLMObservabilityResult:
    """Result of configuring LiteLLM tracing."""

    enabled: bool
    instrumented: bool


_instrumentation_lock = Lock()

_instrumented = False


def initialize_litellm_observability(
) -> LiteLLMObservabilityResult:
    """Initialize safe LiteLLM tracing once."""

    global _instrumented

    bootstrap = initialize_observability()

    if not bootstrap.enabled:
        return LiteLLMObservabilityResult(
            enabled=False,
            instrumented=False,
        )

    with _instrumentation_lock:
        if _instrumented:
            return LiteLLMObservabilityResult(
                enabled=True,
                instrumented=True,
            )

        capture_content = (
            observability_capture_content_enabled()
        )
        config = TraceConfig(
            hide_inputs=not capture_content,
            hide_outputs=not capture_content,
            hide_input_messages=not capture_content,
            hide_output_messages=not capture_content,
            hide_input_images=not capture_content,
            hide_input_text=not capture_content,
            hide_output_text=not capture_content,
            hide_prompts=not capture_content,
            hide_choices=not capture_content,
            hide_llm_tools=not capture_content,
        )

        LiteLLMInstrumentor().instrument(
            config=config,
        )

        _instrumented = True

        return LiteLLMObservabilityResult(
            enabled=True,
            instrumented=True,
        )
