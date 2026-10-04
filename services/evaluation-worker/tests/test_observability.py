from pathlib import Path

from markettwin_evaluation_worker.observability import (
    initialize_litellm_observability,
)
from pytest import MonkeyPatch


async def test_visual_verifier_emits_a_model_span(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import json
    from unittest.mock import AsyncMock

    import litellm
    from litellm.types.utils import ModelResponse  # pyright: ignore[reportMissingTypeStubs]
    from markettwin_evaluation_worker.visual_verifier import verify_visual_criterion
    from openinference.instrumentation import TraceConfig
    from openinference.instrumentation.litellm import LiteLLMInstrumentor
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    viewport = tmp_path / "test-only-viewport.png"
    viewport.write_bytes(b"synthetic test evidence")
    response = ModelResponse(choices=[{
        "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps({
            "status": "satisfied", "rationale": "Source supports criterion", "observed_details": [],
        })},
    }])
    monkeypatch.setattr(litellm, "acompletion", AsyncMock(return_value=response))
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    instrumentor = LiteLLMInstrumentor()
    instrumentor.instrument(tracer_provider=provider, config=TraceConfig(hide_inputs=True))
    try:
        result = await verify_visual_criterion(criterion="Source criterion", viewport_path=viewport)
        assert result.status == "satisfied"
    finally:
        instrumentor.uninstrument()
        provider.shutdown()
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].attributes is not None
    assert spans[0].attributes["openinference.span.kind"] == "LLM"


def test_litellm_observability_is_disabled_by_default(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "MARKETTWIN_OBSERVABILITY_ENABLED",
        raising=False,
    )

    result = (
        initialize_litellm_observability()
    )

    assert result.enabled is False
    assert result.instrumented is False
    
def test_litellm_instrumentor_is_compatible() -> None:
    from openinference.instrumentation import (
        TraceConfig,
    )
    from openinference.instrumentation.litellm import (
        LiteLLMInstrumentor,
    )
    from opentelemetry.sdk.trace import (
        TracerProvider,
    )

    instrumentor = LiteLLMInstrumentor()

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
