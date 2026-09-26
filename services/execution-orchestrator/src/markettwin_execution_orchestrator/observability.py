"""Google ADK observability for MarketTwin execution."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from markettwin_shared.observability import (
    initialize_observability,
)
from openinference.instrumentation import (
    TraceConfig,
)
from openinference.instrumentation.google_adk import (
    GoogleADKInstrumentor,
)


@dataclass(frozen=True, slots=True)
class AdkObservabilityResult:
    """Result of configuring Google ADK tracing."""

    enabled: bool
    instrumented: bool


_instrumentation_lock = Lock()

_instrumented = False


def initialize_adk_observability(
) -> AdkObservabilityResult:
    """Initialize safe Google ADK tracing once."""

    global _instrumented

    bootstrap = initialize_observability()

    if not bootstrap.enabled:
        return AdkObservabilityResult(
            enabled=False,
            instrumented=False,
        )

    with _instrumentation_lock:
        if _instrumented:
            return AdkObservabilityResult(
                enabled=True,
                instrumented=True,
            )

        config = TraceConfig(
            hide_inputs=True,
            hide_outputs=True,
            hide_input_messages=True,
            hide_output_messages=True,
            hide_input_images=True,
            hide_input_text=True,
            hide_output_text=True,
            hide_prompts=True,
            hide_choices=True,
            hide_llm_tools=True,
        )

        GoogleADKInstrumentor().instrument(
            config=config,
        )

        _instrumented = True

        return AdkObservabilityResult(
            enabled=True,
            instrumented=True,
        )