# MarketTwin V1 Browser Architecture

## Decision

MarketTwin V1 uses one Python browser-control path inside the Execution Orchestrator.

```text
Persona Agent (Google ADK / Python)
        ↓
Journey-bound MarketTwin browser tools (Python functions)
        ↓
BrowserController (Python)
        ↓
Playwright Python
        ↓
Chromium
        ↓
Authorized target
```

`services/browser-runtime` is removed. MarketTwin does not run a separate Node/TypeScript browser backend and Persona Agents do not launch `@playwright/mcp` directly.

The React frontend remains TypeScript. Frontend Playwright E2E tests also remain TypeScript; they are development/test tooling, not a backend service.

## Why

The backend is already Python-first: FastAPI, Google ADK orchestration, planning, execution state, database persistence, and evaluation all live in Python. Keeping browser execution in the same Python runtime removes a cross-language service boundary while preserving the important security boundary between the LLM and raw Playwright.

The Persona Agent receives only bounded MarketTwin browser tools. `BrowserController` is the sole owner of Playwright objects, browser lifecycle, network enforcement, and local evidence capture.

## Journey isolation

Every Journey receives its own browser session handle and its own fresh Chromium/BrowserContext for V1. The handle is bound to `execution_id`, `journey_id`, and `session_id`. Every tool call sends those bound identifiers back to the controller and ownership mismatches are rejected.

V1 favors strong isolation and simple cleanup over browser-process reuse. We can later optimize process reuse without changing the agent-facing tool contract.

## Agent-facing tool surface

Persona Agents may use only: `browser_get_state`, `browser_navigate`, `browser_click`, `browser_fill`, `browser_select`, `browser_scroll`, `browser_go_back`, `browser_wait`, and `browser_take_screenshot`.

They do not receive raw Browser/BrowserContext/Page/CDP objects, arbitrary JavaScript, shell access, executable arbitrary selectors, network-policy controls, browser-launch controls, credential/MFA/CAPTCHA entry, file upload, or payment/destructive-action tools.

## Network and SSRF controls

Browser policy is deterministic Python code outside the LLM. Runtime validation includes HTTP/HTTPS-only normal traffic, WS/WSS validation against corresponding approved origins, credential rejection in URLs, exact scheme/hostname/effective-port matching, real-boundary subdomain matching, IDNA/lowercase/trailing-dot normalization, loopback-only local development exceptions, private/link-local/reserved/non-global IP blocking, DNS validation of every returned address, context-wide request interception, WebSocket interception, service-worker blocking, disabled downloads, bounded pages/popups, and deterministic dismissal of unexpected dialogs.

These application-level controls do not eliminate DNS rebinding/TOCTOU risk in production because Chromium performs its own network resolution. Production must add defense in depth at the OS/container/network layer with controlled DNS and egress policy.

## Low-risk autonomous actions

The controller blocks obvious payment/destructive click targets and refuses fill operations for credential, OTP/MFA, CAPTCHA, payment, and file fields based on labels and input metadata. This is an immediate guardrail, not a replacement for the persisted `execution.policy_decisions` workflow that remains part of V1 execution.

## Evidence

The Python controller retains local parity with the removed TypeScript runner for screenshots, ARIA/accessibility snapshots, Playwright trace segments, console errors, page errors, failed requests, and URL/title/page-count observations.

Local artifacts remain under ignored `artifacts/runs/`. Existing PostgreSQL `evidence.artifacts` models and MinIO/S3 infrastructure are unchanged. This migration does not claim MinIO upload and artifact-row persistence are complete; that remains a later evidence milestone.

## Human-assisted authentication

The database already models BrowserSession, HumanActionRequest, and HumanControlLease. The Python controller provides the browser-side same-context boundary: stop trace and evidence capture, mark the exact Journey session as human-controlled, disable Persona Agent browser tools, let the approved human flow operate that exact context, verify authentication at higher layers, then resume the same context and restart evidence capture.

The actual interactive human viewer/transport is not implemented by this migration. The removed TypeScript runtime also did not implement its planned noVNC stack, so no working HITL transport is being removed.

## Google ADK integration

Google ADK can use normal Python callable tools. MarketTwin therefore does not need a Playwright MCP subprocess for internal V1 browser execution. `MetaAgentFactory` receives an already-created BrowserController and BrowserSessionHandle, creates Journey-bound Python browser tools, and provides them to the Persona Agent.

This removes the old competing path `Persona Agent → McpToolset → npx @playwright/mcp → separate Chromium`. There is exactly one browser authority: BrowserController.

If MarketTwin later needs MCP compatibility for external clients, a Python MCP adapter can wrap this same controller without creating a second browser implementation.

## Local setup

```powershell
uv sync
uv run playwright install chromium
uv run python services/execution-orchestrator/scripts/check_playwright_python.py
```

The frontend keeps its own npm Playwright E2E dependencies.

## Migration acceptance gates

The structural migration is complete when there is no `services/browser-runtime`, no root npm browser-runtime workspace, no backend `npx @playwright/mcp`, no Persona Agent `McpToolset`, every browser tool is bound to execution/Journey/session ownership, URL/origin/DNS/WebSocket policies have Python tests, sensitive/destructive guardrails have Python tests, local evidence behavior is retained, and human-control state disables agent tools/evidence capture.

Full production execution still requires persisted execution steps/policy decisions, MinIO/S3 artifact persistence, actual human-control transport, network-level egress hardening, cancellation/reconciliation, and an end-to-end Journey test against a fixture application.
