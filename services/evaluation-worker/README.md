# markettwin-evaluation-worker

MarketTwin evaluation and report-generation worker.

This is an independently deployable MarketTwin component.

Run it continuously from the repository root:

```powershell
uv run --env-file .env python -m markettwin_evaluation_worker.worker
```

The worker discovers completed tests without a version-1 report in PostgreSQL.
It runs the existing deterministic and visual evaluation workflow, then persists
findings and the report. Evaluation runs independently of the Kafka execution
consumer. The UI already polls until the completed report becomes available.

A database advisory lock owns each evaluation while it runs. An existing report
prevents duplicate evaluation. Failures roll back uncommitted findings/report
data and are retried; browser execution is never replayed by this worker.
The current worker checks every five seconds and evaluates one test at a time.
The existing one-shot script reuses the same ownership/completion path, so it
skips a test already owned or reported by the persistent worker.

Tracing uses MarketTwin's existing `MARKETTWIN_OBSERVABILITY_ENABLED`, content
capture flag, and `OTEL_EXPORTER_OTLP_*` settings. Look for `evaluation.run` and
its LiteLLM model calls in the configured LangSmith project. Deterministic
evaluations without visual criteria produce no LLM child calls.
