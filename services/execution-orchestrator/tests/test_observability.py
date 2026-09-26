from markettwin_execution_orchestrator.observability import (
    initialize_adk_observability,
)
from pytest import MonkeyPatch


def test_adk_observability_is_disabled_by_default(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "MARKETTWIN_OBSERVABILITY_ENABLED",
        raising=False,
    )

    result = initialize_adk_observability()

    assert result.enabled is False
    assert result.instrumented is False
    
def test_google_adk_instrumentor_is_compatible() -> None:
    from openinference.instrumentation import (
        TraceConfig,
    )
    from openinference.instrumentation.google_adk import (
        GoogleADKInstrumentor,
    )
    from opentelemetry.sdk.trace import (
        TracerProvider,
    )

    instrumentor = GoogleADKInstrumentor()

    provider = TracerProvider()

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

    instrumentor.instrument(
        tracer_provider=provider,
        config=config,
    )

    instrumentor.uninstrument()