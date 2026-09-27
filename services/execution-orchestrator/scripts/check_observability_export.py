"""Send one harmless MarketTwin telemetry span."""

from uuid import uuid4

from markettwin_shared.observability import (
    initialize_observability,
    use_observability_correlation,
)
from opentelemetry import trace


def main() -> None:
    result = initialize_observability()

    if not result.enabled:
        raise RuntimeError(
            "Observability is disabled. "
            "Set MARKETTWIN_OBSERVABILITY_ENABLED=true."
        )

    tracer = trace.get_tracer(
        "markettwin.observability.smoke"
    )

    test_run_id = uuid4()

    with use_observability_correlation(
        test_run_id=test_run_id,
        agent_role="meta",
    ):
        with tracer.start_as_current_span(
            "markettwin.observability.smoke"
        ):
            pass

    provider = trace.get_tracer_provider()

    force_flush = getattr(
        provider,
        "force_flush",
        None,
    )

    if callable(force_flush):
        force_flush()

    print("Observability smoke span exported.")
    print(f"TestRun correlation ID: {test_run_id}")


if __name__ == "__main__":
    main()