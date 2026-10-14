# Browser-based knowledge link ingestion

Updated 2026-10-10.

## Reported outage and recovery

The user's error, "Knowledge processing is unavailable. Please try again.", came
from the Control API's private KnowledgeWorkerClient. The worker expected on
localhost:8010 was not running. It was started using the existing .env configuration.
A real synthetic text preview then returned one knowledge entry and one skill.
The two identified failed local link sources were requeued only while their exact
status/error still matched that outage. Both completed as needs_user_review,
without errors, with four and six proposed skills respectively. Nothing was approved.

The local Control API was restarted to load browser research. Current processes:
API PID21100/session59212 on port8001; knowledge worker PID34236/session44162 on
port8010; Vite remains on5173. Existing Kafka SSL failures are separate and remain
an unresolved test-run pipeline gate; ingestion uses its own persisted processor.

## Current link inspection

The old implementation read HTML and four keyword-filtered links from the root.
The current implementation uses the already-installed Playwright1.61 Chromium:

- Renders JavaScript content in an isolated public browser context.
- Discovers same-origin links recursively from every inspected rendered state.
- Opens visible menus, tabs and disclosure controls outside forms (up to12/page).
- Reads rendered text before/after interactions and records observed URLs/actions.
- Preserves SPA hash routes and prevents duplicate document-anchor crawling.
- Saves a source-attributed text bundle through the existing draft ingestion pipeline.
- Reports inaccessible pages, remaining discovered pages and inspection limitations.

Limits:30 pages, approximately120 seconds,300 discovered URLs,180 requests,
2MB per response and40MB total responses. No claim of exhaustive site coverage.
Public pages only: no credentials, form submissions, account mutations, downloads,
media or image analysis. Pages requiring unsupported access/requests may be incomplete.
The UI describes these limits. Initial text/plain links remain supported directly.

## Network and ownership boundaries

Browser HTTP requests are intercepted and fulfilled through the existing public
DNS/IP-pinned downloader. Every fetch/redirect validates public addresses and TLS
identity; no ordinary browser route is continued directly. Only GET is allowed;
off-origin document navigation, non-GET traffic, media/images/fonts and resource
overflow are aborted. Service workers are blocked and WebSockets closed. Source
content is untrusted data, never an instruction to the knowledge model.

The Control API now declares the same Playwright version already used by the
orchestrator. No package or browser installation was performed; existing versions
of other locked dependencies were preserved. Deployments need Chromium installed
for their existing Playwright version. Do not silently fall back to HTML-only
research while claiming interactive inspection.

## Verification

14 focused link tests pass, including a real Chromium fixture with JavaScript
content, disclosure interaction, a link discovered several pages deep and blocked
POST requests. Public URL/DNS safeguards and authorization-before-network tests
remain covered. Ruff/Pyright, frontend typecheck and production build pass. The
existing frontend bundle-size warning remains. Broader focused ingestion/worker
and frontend form regressions were run afterward; see CURRENT_STATE.md for results.
Final focused backend suite:44 passed; frontend ingestion form:8 passed.

The user's exact site was not separately crawled after this upgrade because its
URL was not supplied in the message. Previously failed sources were regenerated
from their saved bundles; these successful retries validate worker recovery, not
new browser coverage of those original sites. A newly submitted link uses the
browser implementation. Approval/review remains required before testing uses skills.

## Reference map

- Control API: knowledge/link_research.py, knowledge/client.py, knowledge/processor.py,
  api/ingestion.py and tests/test_link_research.py.
- Worker: services/knowledge-worker/src/markettwin_knowledge_worker/main.py.
- Frontend: apps/web/src/pages/knowledge/IngestionPage.tsx.
- INGESTION_WORKFLOW_UI_AND_REVIEW.md: existing startup and approval workflow.
- KNOWLEDGE_GROUNDING_FIX.md: source/evidence grounding for skills.
- [Playwright network interception](https://playwright.dev/python/docs/network).
- [Context routing and service worker controls](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-route).

Control API paths are under services/control-api/src/markettwin_control_api.
