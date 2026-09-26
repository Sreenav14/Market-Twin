from collections.abc import Sequence
from uuid import uuid4

import pytest
from markettwin_shared.observability import (
    MarketTwinCorrelationSpanProcessor,
    initialize_observability,
    load_observability_settings,
    use_observability_correlation,
)
from opentelemetry.sdk.trace import (
    ReadableSpan,
    TracerProvider,
)
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from pytest import MonkeyPatch


class _RecordingExporter(SpanExporter):
    def __init__(self) -> None:
        self.spans: list[ReadableSpan] = []

    def export(
        self,
        spans: Sequence[ReadableSpan],
    ) -> SpanExportResult:
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


def test_observability_is_disabled_by_default(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "MARKETTWIN_OBSERVABILITY_ENABLED",
        raising=False,
    )

    monkeypatch.delenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        raising=False,
    )

    monkeypatch.delenv(
        "OTEL_SERVICE_NAME",
        raising=False,
    )

    result = initialize_observability()

    assert result.enabled is False
    assert result.initialized is False

    assert (
        result.service_name
        == "markettwin"
    )


def test_enabled_observability_requires_endpoint(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MARKETTWIN_OBSERVABILITY_ENABLED",
        "true",
    )

    monkeypatch.delenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        raising=False,
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
        ),
    ):
        initialize_observability()


def test_settings_do_not_capture_export_credentials(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MARKETTWIN_OBSERVABILITY_ENABLED",
        "true",
    )

    monkeypatch.setenv(
        "OTEL_SERVICE_NAME",
        "markettwin-test",
    )

    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "https://example.test/v1/traces",
    )

    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_HEADERS",
        "x-api-key=super-secret",
    )

    settings = (
        load_observability_settings()
    )

    assert settings.enabled is True

    assert (
        settings.service_name
        == "markettwin-test"
    )

    assert settings.traces_endpoint == (
        "https://example.test/v1/traces"
    )

    assert "super-secret" not in repr(
        settings
    )


def test_safe_correlation_is_added_to_spans() -> None:
    test_run_id = uuid4()
    journey_id = uuid4()
    execution_id = uuid4()
    snapshot_id = uuid4()

    exporter = _RecordingExporter()
    provider = TracerProvider()
    provider.add_span_processor(
        MarketTwinCorrelationSpanProcessor()
    )
    provider.add_span_processor(
        SimpleSpanProcessor(exporter)
    )
    tracer = provider.get_tracer(
        "markettwin-test"
    )

    with use_observability_correlation(
        test_run_id=test_run_id,
        journey_id=journey_id,
        execution_id=execution_id,
        agent_snapshot_id=snapshot_id,
        agent_role="persona",
    ):
        with tracer.start_as_current_span(
            "test-span"
        ):
            pass

    attributes = exporter.spans[0].attributes

    assert attributes is not None
    assert attributes[
        "markettwin.test_run_id"
    ] == str(test_run_id)
    assert attributes[
        "markettwin.journey_id"
    ] == str(journey_id)
    assert attributes[
        "markettwin.execution_id"
    ] == str(execution_id)
    assert attributes[
        "markettwin.agent_snapshot_id"
    ] == str(snapshot_id)
    assert attributes[
        "markettwin.agent_role"
    ] == "persona"


def test_correlation_does_not_leak_after_context() -> None:
    provider = TracerProvider()
    exporter = _RecordingExporter()
    provider.add_span_processor(
        MarketTwinCorrelationSpanProcessor()
    )
    provider.add_span_processor(
        SimpleSpanProcessor(exporter)
    )
    tracer = provider.get_tracer(
        "markettwin-test"
    )

    with use_observability_correlation(
        test_run_id=uuid4(),
        agent_role="meta",
    ):
        with tracer.start_as_current_span(
            "inside"
        ):
            pass

    with tracer.start_as_current_span(
        "outside"
    ):
        pass

    inside_attributes = (
        exporter.spans[0].attributes
    )
    outside_attributes = (
        exporter.spans[1].attributes
    )

    assert inside_attributes is not None
    assert (
        "markettwin.test_run_id"
        in inside_attributes
    )
    assert outside_attributes is not None
    assert (
        "markettwin.test_run_id"
        not in outside_attributes
    )
    assert (
        "markettwin.agent_role"
        not in outside_attributes
    )