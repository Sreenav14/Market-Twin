# MarketTwin Execution Orchestrator

Python service that owns MarketTwin planning and Journey execution.

## Responsibilities

- run the Meta Agent and validate structured planning output
- deterministically build Persona × Mission Journeys
- create and run Persona Agents through Google ADK
- own Journey execution state and keep execution status separate from outcome
- expose only bounded, Journey-specific browser tools to Persona Agents
- own the in-process Python `BrowserController`
- enforce target URL, origin, DNS, WebSocket, browser-action, and session-ownership policy
- create isolated Playwright BrowserContexts for Journeys
- capture screenshots, accessibility snapshots, traces, console/page errors, and failed requests
- pause agent browser tools for human-assisted authentication and resume the same context
- persist execution/evidence state as the remaining V1 workflow is connected
- trigger evaluation after terminal Journeys

## Browser architecture

```text
Persona Agent / Python
        ↓
MarketTwin browser tools / Python
        ↓
BrowserController / Python
        ↓
Playwright Python
        ↓
Chromium
```

There is no separate backend Browser Runtime service and no direct `@playwright/mcp` browser path. The Persona Agent never receives raw Playwright objects.

See `docs/BROWSER_ARCHITECTURE.md` for security boundaries, evidence behavior, HITL rules, and migration acceptance criteria.

## Local browser setup

```powershell
uv sync
uv run playwright install chromium
uv run python services/execution-orchestrator/scripts/check_playwright_python.py
```

Browser artifacts are local/ignored until the MinIO/S3 evidence-persistence milestone is connected.

## Execution worker

Start the Control API with `OUTBOX_RELAY_ENABLED=true` in `.env`, then keep the
execution worker running in a separate terminal from the repository root:

```powershell
uv run --env-file .env python services/execution-orchestrator/scripts/run_execution_worker.py
```

The worker uses the same PostgreSQL and Kafka settings as the existing one-command
script. Browser execution also requires the existing model, artifact storage,
and Playwright Chromium setup. Use `uv run playwright install chromium` if the
browser is not installed.

UI Start writes the queued run and outbox event in one transaction. The Control
API relay publishes the event to Kafka. The worker processes commands sequentially,
updates the persisted run through planning, running, and completed/failed, and
the UI polls every five seconds until the run is terminal.

Kafka connection failures retry every five seconds. An execution failure marks
the run failed and allows the next command to run. Offsets are committed only
after execution finishes. Redelivered completed/failed runs are skipped. A
redelivered accepted run still in planning/running is marked failed rather than
replaying potentially state-changing browser actions. Invalid commands remain
uncommitted and are logged for operator correction. The consumer allows up to
24 hours between polls for a long execution.

The diagnostic `scripts/run_one_execution_command.py` uses the same
`process_command()` implementation, poll interval, and consumer group. It commits
only after processing returns and then exits. Stop the persistent worker before
using this diagnostic; do not run both simultaneously.

V1 supports one active execution consumer. Recovery does not establish ownership
of an in-progress run: a redelivery in planning/running is treated as interrupted
and marked failed. This is not safe for horizontal worker scaling, where a Kafka
rebalance could redeliver work while its original worker is still alive. Before
running multiple workers, add a lease/attempt-owner mechanism and only recover a
run after its owner's lease expires. Worker health is a separate future addition.

Ctrl+C stops the worker and closes its Kafka and database resources. For deployment,
run `python -m markettwin_execution_orchestrator.worker` under the deployment's
process supervisor with an automatic restart policy; closing a local terminal
stops its worker.

`GET /api/v1/health/kafka` separately checks broker connectivity/authentication
without publishing or consuming messages. It returns `connected` or `unavailable`
and whether the outbox relay is enabled. The draft test's Start controls poll it
every 15 seconds. Connected with the relay disabled is shown as a warning:
`Kafka connected · relay off`.
This checks Kafka connectivity, not worker availability, topic permissions, or
successful outbox delivery. `/health` remains a process-health endpoint.
