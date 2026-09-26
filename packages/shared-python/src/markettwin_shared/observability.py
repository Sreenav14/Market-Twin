"""Process-level OpenTelemetry bootstrap for MarketTwin."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from threading import Lock
from typing import Final
from uuid import UUID

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import (
    ReadableSpan,
    Span,
    SpanProcessor,
    TracerProvider,
)
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
)

_OBSERVABILITY_ENABLED_ENV = (
    "MARKETTWIN_OBSERVABILITY_ENABLED"
)

_CORRELATION_ATTRIBUTE_NAMES: Final = {
    "markettwin.test_run_id",
    "markettwin.journey_id",
    "markettwin.execution_id",
    "markettwin.agent_snapshot_id",
    "markettwin.persona_id",
    "markettwin.mission_id",
    "markettwin.agent_role",
}

_TRACES_ENDPOINT_ENV = (
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
)

_SERVICE_NAME_ENV = "OTEL_SERVICE_NAME"

_DEFAULT_SERVICE_NAME = "markettwin"

_TRUE_VALUES = {
    "1",
    "true",
    "yes",
    "on",
}

_FALSE_VALUES = {
    "0",
    "false",
    "no",
    "off",
    "",
}


@dataclass(frozen=True, slots=True)
class ObservabilitySettings:
    """Safe process-level observability configuration."""

    enabled: bool
    service_name: str
    traces_endpoint: str | None


@dataclass(frozen=True, slots=True)
class ObservabilityBootstrapResult:
    """Result of initializing MarketTwin observability."""

    enabled: bool
    initialized: bool
    service_name: str
    traces_endpoint: str | None


_initialization_lock = Lock()

_initialized_result: (
    ObservabilityBootstrapResult | None
) = None

_correlation_attributes: ContextVar[dict[str, str] | None] = ContextVar(
    "markettwin_observability_correlation",
    default=None,
)

@contextmanager
def use_observability_correlation(
    *,
    test_run_id: UUID,
    journey_id: UUID | None = None,
    execution_id: UUID | None = None,
    agent_snapshot_id: UUID | None = None,
    persona_id: UUID | None = None,
    mission_id: UUID | None = None,
    agent_role: str | None = None,
) -> Generator[None, None, None]:
    """Attach safe MarketTwin IDs to spans created in this context."""

    attributes: dict[str, str] = {
        "markettwin.test_run_id": str(
            test_run_id
        ),
    }

    optional_ids = {
        "markettwin.journey_id": journey_id,
        "markettwin.execution_id": execution_id,
        "markettwin.agent_snapshot_id": (
            agent_snapshot_id
        ),
        "markettwin.persona_id": persona_id,
        "markettwin.mission_id": mission_id,
    }

    for name, value in optional_ids.items():
        if value is not None:
            attributes[name] = str(value)

    if agent_role is not None:
        normalized_role = agent_role.strip()

        if normalized_role not in {
            "meta",
            "persona",
            "visual_verifier",
        }:
            raise ValueError(
                "Unsupported observability agent role."
            )

        attributes[
            "markettwin.agent_role"
        ] = normalized_role

    if not set(attributes).issubset(
        _CORRELATION_ATTRIBUTE_NAMES
    ):
        raise RuntimeError(
            "Unexpected observability correlation attribute."
        )

    token = _correlation_attributes.set(
        attributes
    )

    try:
        yield
    finally:
        _correlation_attributes.reset(
            token
        )


def load_observability_settings(
) -> ObservabilitySettings:
    """Read safe OpenTelemetry configuration from the environment."""

    enabled = _environment_boolean(
        _OBSERVABILITY_ENABLED_ENV,
        default=False,
    )

    service_name = os.getenv(
        _SERVICE_NAME_ENV,
        _DEFAULT_SERVICE_NAME,
    ).strip()

    if not service_name:
        service_name = _DEFAULT_SERVICE_NAME

    raw_endpoint = os.getenv(
        _TRACES_ENDPOINT_ENV
    )

    traces_endpoint = (
        raw_endpoint.strip()
        if raw_endpoint
        else None
    )

    if traces_endpoint == "":
        traces_endpoint = None

    return ObservabilitySettings(
        enabled=enabled,
        service_name=service_name,
        traces_endpoint=traces_endpoint,
    )


def initialize_observability(
) -> ObservabilityBootstrapResult:
    """Initialize OpenTelemetry once for the current process."""

    global _initialized_result

    settings = load_observability_settings()

    if not settings.enabled:
        return ObservabilityBootstrapResult(
            enabled=False,
            initialized=False,
            service_name=settings.service_name,
            traces_endpoint=(
                settings.traces_endpoint
            ),
        )

    if settings.traces_endpoint is None:
        raise RuntimeError(
            "MarketTwin observability is enabled but "
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT "
            "is not configured."
        )

    with _initialization_lock:
        if _initialized_result is not None:
            return _initialized_result

        resource = Resource.create(
            {
                "service.name": (
                    settings.service_name
                ),
            }
        )

        tracer_provider = TracerProvider(
            resource=resource,
        )
        
        tracer_provider.add_span_processor(
            MarketTwinCorrelationSpanProcessor()
        )

        exporter = OTLPSpanExporter(
            endpoint=settings.traces_endpoint,
        )

        tracer_provider.add_span_processor(
            BatchSpanProcessor(
                exporter
            )
        )

        trace.set_tracer_provider(
            tracer_provider
        )

        _initialized_result = (
            ObservabilityBootstrapResult(
                enabled=True,
                initialized=True,
                service_name=(
                    settings.service_name
                ),
                traces_endpoint=(
                    settings.traces_endpoint
                ),
            )
        )

        return _initialized_result


def _environment_boolean(
    name: str,
    *,
    default: bool,
) -> bool:
    """Read one strict boolean environment variable."""

    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    value = raw_value.strip().casefold()

    if value in _TRUE_VALUES:
        return True

    if value in _FALSE_VALUES:
        return False

    raise ValueError(
        f'{name} must be one of '
        '"true", "false", "1", "0", '
        '"yes", "no", "on", or "off".'
    )

class MarketTwinCorrelationSpanProcessor(
    SpanProcessor
):
    """Copy safe MarketTwin correlation IDs onto new spans."""

    def on_start(
        self,
        span: Span,
        parent_context: Context | None = None,
    ) -> None:
        del parent_context

        for (
            name,
            value,
        ) in (
            _correlation_attributes.get() or {}
        ).items():
            span.set_attribute(
                name,
                value,
            )

    def on_end(
        self,
        span: ReadableSpan,
    ) -> None:
        del span

    def shutdown(self) -> None:
        return None

    def force_flush(
        self,
        timeout_millis: int = 30_000,
    ) -> bool:
        del timeout_millis
        return True