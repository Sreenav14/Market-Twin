"""Trace Knowledge Worker model calls through the existing OpenTelemetry exporter."""

from threading import Lock

from markettwin_shared.observability import (
    initialize_observability,
    observability_capture_content_enabled,
)
from openinference.instrumentation import TraceConfig
from openinference.instrumentation.litellm import LiteLLMInstrumentor

_instrumentation_lock = Lock()
_instrumented = False


def initialize_knowledge_observability() -> bool:
    """Instrument LiteLLM once, respecting MarketTwin's tracing and content flags."""
    global _instrumented

    if not initialize_observability().enabled:
        return False
    with _instrumentation_lock:
        if not _instrumented:
            capture_content = observability_capture_content_enabled()
            LiteLLMInstrumentor().instrument(config=TraceConfig(
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
            ))
            _instrumented = True
    return True
