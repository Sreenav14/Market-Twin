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
