# MarketTwin implementation handoff

Date: 2026-09-11

This document records the implementation completed in the local working tree. No deployment, GitHub push, or database migration was performed as part of this work.

## Product language

The UI now describes the product as a way to test whether an app is usable and delivers value to users.

- Primary sign-in message: **Build an app people want to use.**
- Navigation and pages use **Tests**, **New test**, and **testing goal** rather than the more generic “Studies”.
- Existing `/runs` URLs, API paths, database table names, and Python class names remain unchanged for compatibility.

The updated sign-in page is implemented in `apps/web/src/pages/auth/LoginPage.tsx`. It keeps the existing local-email authentication request, but replaces the old oversized two-column sign-in layout with a product-readiness introduction, concise workflow, responsive form, explicit error state, and mobile layout.

## Frontend work

### Foundation and visual system

The web application remains React, TypeScript, Vite, React Router, and Tailwind. The following reusable frontend pieces were added:

- semantic color, typography, radius, focus, and responsive tokens;
- Instrument Sans for interface and reading text, with IBM Plex Mono for identifiers;
- reusable button, input, textarea, tooltip, status badge, icon, command menu, copy button, and delete-confirmation components;
- TanStack Query for cached request state and refetching;
- responsive graphite sidebar and bright workspace shell;
- keyboard skip link, visible focus states, labelled compact navigation, reduced-motion support, and mobile bottom navigation.

The main UI CSS is now separated into `tokens.css`, `base.css`, `workspace.css`, and `signin.css`. Existing legacy styles remain loaded because several older application, target, and settings screens still use them.

### Test results workflow

The frontend now consumes the existing Control API endpoint:

```text
GET /api/v1/test-runs/{test_run_id}/results
```

The client renders the real report and finding payload rather than using a production demo fallback.

Completed functionality:

- a test overview with lifecycle stages, executive summary, counts, top findings, and provenance;
- a Findings screen with URL-backed text search, severity/category filters, and ordering;
- finding detail with recommendation, journey IDs, step IDs, artifact IDs, and copyable references;
- a Report screen with summary, journey outcomes, severity distribution, findings, and scope/provenance;
- honest 409 waiting state when evaluation is not ready;
- recoverable errors for permission, missing-resource, and transport failures;
- polling for non-terminal test state and waiting evaluation state;
- test creation using authorized targets and the real `POST /api/v1/applications/{application_id}/test-runs` request.

The frontend intentionally does not pretend that an artifact ID is a downloadable artifact, that aggregate journey counts are a detailed timeline, or that an empty result proves the product has no usability problems.

### Workspace, application, target, and test pages

Implemented or updated:

- workspace overview with actual application/test counts and recent activity;
- Tests list with search and status filtering;
- application and target list/delete actions;
- application test list/delete actions;
- individual test, target, and application deletion actions;
- command menu and route-aware breadcrumbs;
- workspace role-aware create and delete controls.

The UI review screenshots are in [`docs/ui-review`](ui-review/README.md). They were rendered with explicit API fixtures and are visual test samples, not live evaluation results.

## Deletion: frontend and backend

Deletion is implemented in both layers.

### User interaction

Owners and administrators see Delete controls in:

- the Tests list and an individual test;
- application test lists;
- target lists and an individual target;
- application lists and an individual application.

Each delete action opens an accessible confirmation dialog. Cancel has initial focus. A failed request leaves the item intact and shows the server’s message. A successful request invalidates cached data and removes the deleted item from the page.

### Control API endpoints

New endpoints are registered in the Control API:

```text
DELETE /api/v1/test-runs/{id}
DELETE /api/v1/targets/{id}
DELETE /api/v1/applications/{id}
```

The implementation lives in:

- `services/control-api/src/markettwin_control_api/api/lifecycle.py`
- `services/control-api/src/markettwin_control_api/main.py`

These endpoints perform database deletes in SQLAlchemy transactions. They are not frontend-only hiding behavior.

Server-side protections:

- only owner and admin workspace members can delete;
- access is scoped to the current user’s workspace;
- rows are locked during deletion to reduce races with new dependencies;
- `planning`, `queued`, and `running` tests cannot be deleted;
- tests with active journey execution cannot be deleted;
- completed tests cannot be deleted while evaluation is absent or generating;
- a target cannot be deleted while tests reference it;
- an application cannot be deleted while tests or targets reference it;
- foreign-key conflicts return HTTP 409 rather than silently deleting partial data.

Deletion order is test, then target, then application. Existing database foreign keys cascade from a deleted test to related database rows such as report data, findings, events, execution records, and artifact metadata where the schema defines cascades.

Object-storage files are **not** deleted by these endpoints. The current database schema records artifact metadata, while S3/MinIO object retention needs a separate storage-retention policy and background deletion mechanism. The confirmation dialog tells the user this.

No database migration was created because the deletion behavior uses existing tables and foreign-key relationships.

More deletion detail and the exact repeat command are in [`docs/ui-review/DELETION.md`](ui-review/DELETION.md).

## Backend persistence and evidence work completed earlier

The execution and evaluation work already present in this local tree includes:

- `S3ArtifactStorage`, configured from `S3_BUCKET`, `S3_REGION`, and optional `S3_ENDPOINT_URL`, with MinIO selected when an endpoint URL exists;
- SHA-256 and size collection for uploaded artifacts;
- `ArtifactRepository` for persisted artifact metadata;
- evidence recording for screenshots and accessibility snapshots per execution step;
- session artifact recording for Playwright trace archives, console logs, page errors, and failed network logs;
- sanitized final URLs in journey result events, removing credentials, query parameters, and fragments;
- final `journey.result` RunEvent creation alongside final agent execution state;
- shared SQLAlchemy execution, evidence, and evaluation models moved to `markettwin-database`, while service-local paths remain compatibility exports;
- `boto3` declared in `services/execution-orchestrator/pyproject.toml` as `boto3>=1.35,<2`.

The shared-model move did not require an Alembic migration because it changes Python ownership of existing ORM mappings, not the PostgreSQL schema.

## Features intentionally still incomplete

These routes exist but are placeholders because the browser-facing backend contracts are not implemented yet:

- **Human in the loop**: `HumanActionPage` only states the future intention for login, MFA, OTP, SSO, reset, and CAPTCHA handoff. There is no working user request queue, browser-control lease flow, live handoff, or resume action in the frontend.
- **Evidence inspector**: artifact IDs are shown in a finding, but there are no signed download URLs, screenshot rendering, trace viewer, or secure artifact retrieval API.
- **Journey detail**: no detailed journey/persona/mission API is exposed to the frontend.
- **Live activity**: no browser-facing server-sent events or live event timeline has been integrated.
- **Planning/perspectives/missions**: their existing route pages remain placeholders until their corresponding APIs are exposed.

The UI deliberately keeps these unavailable rather than creating fake data or controls that appear to work.

## Validation completed

The following checks passed after the changes:

| Check | Result |
| --- | --- |
| Frontend TypeScript | Passed |
| Frontend production build | Passed |
| Frontend unit tests | 9 passed |
| Playwright desktop and Pixel 7 tests | 32 passed |
| Control API test suite | 44 passed |
| PostgreSQL deletion/cascade integration check | 1 passed |
| Ruff for lifecycle API and deletion tests | Passed |

The browser suite covers sign-in, route protection, test creation, completed results, report and finding pages, waiting/error states, role restrictions, responsive overflow, automated accessibility, deletion confirmation, deletion failure, successful delete behavior, and the absence/disablement of delete controls for insufficient permissions or active tests.

The PostgreSQL integration check created isolated temporary rows for a user, workspace, application, target, completed test, report, and event. It verified that the target could not be deleted before its test, that deleting the test removed its report/event rows, and that the target and application could then be deleted. The outer transaction was rolled back, so it did not leave those test rows in the database.

Automated accessibility checks found no WCAG A/AA issues on the tested fixture screens. This is useful regression coverage, but it is not a claim of complete accessibility conformance or usability validation with real people.

## Run locally

From the repository root:

```powershell
npm.cmd run dev --workspace=@markettwin/web
```

The web app is available at `http://localhost:5173` and proxies `/api` to the Control API on port 8000.

In another terminal, run the Control API:

```powershell
uv run --package markettwin-control-api uvicorn markettwin_control_api.main:app --reload --host 127.0.0.1 --port 8000
```

If your local dependencies are stopped:

```powershell
docker compose --env-file .env -f infra/compose/docker-compose.yml up -d postgres kafka minio
```

To rerun the frontend checks:

```powershell
npm.cmd run typecheck --workspace=@markettwin/web
npm.cmd run test --workspace=@markettwin/web -- --maxWorkers=1
npm.cmd run build --workspace=@markettwin/web
npm.cmd run test:e2e --workspace=@markettwin/web -- --workers=1
```

To verify deletion against local PostgreSQL:

```powershell
$env:MARKETTWIN_TEST_DATABASE = '1'
uv run pytest services/control-api/tests/test_lifecycle_database.py -q
Remove-Item Env:MARKETTWIN_TEST_DATABASE
```

## Important local-state notes

- The working tree contains uncommitted changes. Review and commit them when ready.
- `image.png` in the repository root is the screenshot supplied during the review; it is untracked.
- `MARKETTWIN_UI_UX_IMPLEMENTATION_SPEC.md` is also currently untracked.
- No production deployment or GitHub action was taken.
