"""Knowledge tracing uses the existing exporter and instruments the actual model call."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import litellm
import pytest
from litellm.types.utils import ModelResponse  # pyright: ignore[reportMissingTypeStubs]
from markettwin_knowledge_worker import knowledge_builder, observability
from markettwin_knowledge_worker.extraction import ExtractedEvidence, ExtractionResult
from openinference.instrumentation import TraceConfig
from openinference.instrumentation.litellm import LiteLLMInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode


def test_disabled_tracing_does_not_instrument(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        observability, "initialize_observability", lambda: SimpleNamespace(enabled=False)
    )
    instrumentor = Mock()
    monkeypatch.setattr(observability, "LiteLLMInstrumentor", instrumentor)
    assert observability.initialize_knowledge_observability() is False
    instrumentor.assert_not_called()


def test_startup_instruments_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(observability, "_instrumented", False)
    monkeypatch.setattr(
        observability, "initialize_observability", lambda: SimpleNamespace(enabled=True)
    )
    monkeypatch.setattr(observability, "observability_capture_content_enabled", lambda: False)
    instrumentor = Mock()
    monkeypatch.setattr(observability, "LiteLLMInstrumentor", lambda: instrumentor)
    assert observability.initialize_knowledge_observability() is True
    assert observability.initialize_knowledge_observability() is True
    instrumentor.instrument.assert_called_once()
    config = instrumentor.instrument.call_args.kwargs["config"]
    assert config.hide_inputs and config.hide_outputs and config.hide_input_images


@pytest.mark.parametrize("capture_content", [False, True])
@pytest.mark.parametrize("fails", [False, True])
async def test_actual_builder_call_emits_success_or_failure_span(
    monkeypatch: pytest.MonkeyPatch, capture_content: bool, fails: bool,
) -> None:
    payload: dict[str, object] = {"application_knowledge": [], "artifacts": [], "skills": []}
    response = ModelResponse(
        model="test-model", choices=[{
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps(payload)},
        }],
    )
    completion = AsyncMock(
        return_value=response, side_effect=RuntimeError("provider failed") if fails else None,
    )
    monkeypatch.setattr(litellm, "acompletion", completion)
    monkeypatch.setenv("MODEL_NAME", "openai/test-model")
    monkeypatch.setenv("KNOWLEDGE_MODEL_MAX_OUTPUT_TOKENS", "16384")
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    instrumentor = LiteLLMInstrumentor()
    instrumentor.instrument(tracer_provider=provider, config=TraceConfig(
        hide_inputs=not capture_content, hide_outputs=not capture_content,
        hide_input_messages=not capture_content, hide_output_messages=not capture_content,
    ))
    try:
        call = knowledge_builder.KnowledgeBuilder().build(
            ExtractionResult(
                source_path=Path("source.txt"), units=(ExtractedEvidence(
                    evidence_type="text", content_text="private source sentinel", content_json=None,
                    source_locator={"line": 1}, extractor_name="test",
                    extractor_version="1", ordinal=1,
                ),), issues=(), source_item_count=1, processed_item_count=1,
            )
        )
        if fails:
            with pytest.raises(RuntimeError, match="provider failed"):
                await call
        else:
            result = await call
            assert result.model_dump(mode="json") == payload
    finally:
        instrumentor.uninstrument()
        provider.shutdown()
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].attributes is not None
    assert spans[0].attributes["openinference.span.kind"] == "LLM"
    assert ("private source sentinel" in json.dumps(dict(spans[0].attributes))) == capture_content
    assert spans[0].status.status_code == (StatusCode.ERROR if fails else StatusCode.OK)
    assert completion.call_args.kwargs["max_completion_tokens"] == 16384
