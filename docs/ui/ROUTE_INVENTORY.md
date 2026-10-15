# UI route inventory

Checked against `apps/web/src/app/App.tsx` and `apps/web/src/app/router.tsx` on 2026-10-15. This records the current UI contract; it does not imply that placeholder capabilities have backend support.

## Public and session routes

| Route | Purpose, decision, primary action | Access and data | Loading, empty, error | Destructive action | Small screen and CSS |
|---|---|---|---|---|---|
| `/` | Explain the product; open workspace or learn more. | Public content; session lookup also starts. | No API-dependent page state. | None. | Public layout stacks sections; `mt-*` in `public.css`. |
| `/how-it-works` | Explain setup, execution, result meaning, and limits; navigate to login. | Public content; session lookup also starts. | No API-dependent page state. | None. | Public layout stacks sections; `mt-*` in `public.css`. |
| `/login` | Sign into the local workspace; submit approved email. | Unauthenticated; calls `/me` and local login API. | Login errors are shown inline; retry by resubmitting. | None. | Sign-in layout; `signin.css`. |
| `/auth/callback` | Explain provider callback state. | Unauthenticated; no provider callback exchange is currently wired in this page. | Explicit provider-configuration message. | None. | Sign-in layout; `signin.css`. |

## Workspace, application, target, and knowledge routes

| Route | Purpose, decision, primary action | Access and data | Loading, empty, error | Destructive action | Small screen and CSS |
|---|---|---|---|---|---|
| `/` (authenticated) | Redirect to overview. | Authenticated session. | N/A. | None. | App shell. |
| `/login`, `/auth/callback` (authenticated) | Redirect to overview. | Authenticated session. | N/A. | None. | App shell. |
| `/overview` | See workspace activity, actionable human handoffs, and applications; open a test or application. | Workspace member; applications and tests from Control API. New test requires writer role; handoff links are scoped to listed `awaiting_human` tests. | Loading and retry; empty application/test states; stale-data refresh notice. | None. | Workspace grid stacks responsively; `workspace.css`, `product-theme.css`, page scope `mt-overview-*`. |
| `/applications` | Browse applications; open one or create. | Workspace member; application list. Creation requires writer role. | Loading, empty, and retry states. | No deletion here. | Responsive rows; `workspace.css`, `product-theme.css`. |
| `/applications/new` | Register an application. | Writer; submits name and optional description. | Form validation and API error. | None. | Form grid; `workspace.css`, `product-theme.css`. |
| `/applications/:applicationId` | Review application, targets, and tests; choose a target/test. | Workspace member; application, targets, runs. | Loading, not-found/API error. | Lifecycle deletion only owner/admin; confirmation panel. | Detail grid stacks; `workspace.css`, `product-theme.css`. |
| `/applications/:applicationId/edit` | Edit application configuration. | Current page is an explicit future-stage placeholder; update API is absent. | Placeholder explanation. | None. | App shell; `workspace.css`, `product-theme.css`. |
| `/applications/:applicationId/runs` | Browse tests for one application. | Workspace member; application runs. | Loading, empty, error/retry. | None. | Responsive test rows; run/workspace styles. |
| `/applications/:applicationId/targets` | Browse targets for an application; open/create. | Workspace member; targets. Creation requires writer role. | Loading, empty, error/retry. | Target lifecycle deletion only owner/admin. | Responsive rows; `workspace.css`, `product-theme.css`. |
| `/applications/:applicationId/targets/new` | Register an authorized target URL and environment. | Writer; submits target fields to Control API. | Validation and API error. | None. | Form grid; `workspace.css`, `product-theme.css`. |
| `/targets/:targetId` | Inspect target configuration, exact allowed origins, authorization, and tests. | Workspace member; target plus authorization. Creating tests requires write access and live unexpired authorization. | Loading, not-found/API error. | Lifecycle deletion only owner/admin. | Detail grid collapses; `workspace.css`, `product-theme.css`. |
| `/targets/:targetId/authorization` | Inspect, grant, or revoke target authorization. | Owner/admin can authorize; workspace members can view. Target and authorization APIs. | Loading, API error; missing authorization gives the required state. | Revoke requires owner/admin; backend rechecks state. | Two-column layout collapses; `workspace.css`, `product-theme.css`. |
| `/targets/:targetId/edit` | Edit target settings. | Current page is an explicit future-stage placeholder; update API is absent. | Placeholder explanation. | None. | App shell; `workspace.css`, `product-theme.css`. |
| `/targets/:targetId/network` | Inspect network policy. | Current page is an explicit future-stage placeholder; policy management API is absent. | Placeholder explanation. | None. | App shell; `workspace.css`, `product-theme.css`. |
| `/applications/:applicationId/knowledge` | Legacy redirect to `/ingestion`. | Authenticated session. | N/A. | None. | Redirect. |
| `/ingestion` | Add a file or public source for review. | Workspace member; ingestion list/status. Upload/ingest requires writer. | Loading, empty, processing progress, and retry/error. | Remove an ingestion requires writer. | Responsive forms/rows; knowledge styles and `product-theme.css`. |
| `/knowledge/review` | Find and review ingested knowledge. | Workspace member; searchable/filterable entries. | Loading, empty, retry/error; polls while processing. | Delete requires writer. | Review list adapts to narrow widths; knowledge styles and `product-theme.css`. |
| `/knowledge/review/:entryId` | Inspect source/provenance and approve, rename, or attach knowledge. | Workspace member; entry and linked applications. Mutations require writer. | Loading, missing entry/API error; unavailable extraction shown as state. | Delete requires writer. | Detail and form columns stack; knowledge styles and `product-theme.css`. |

## Test, agent, and evidence routes

| Route | Purpose, decision, primary action | Access and data | Loading, empty, error | Destructive action | Small screen and CSS |
|---|---|---|---|---|---|
| `/runs` | Browse tests and open a test or create one. | Workspace member; test list. Create requires writer and authorized target. | Loading, empty, error/retry. | None. | Responsive table/list; `run-records.css`, `product-theme.css`. |
| `/applications/:applicationId/runs/new` | Configure a test draft, then explicitly start it. | Writer; application, targets, knowledge selections, test API. Target must be authorized and active. | Loading, validation, API error. | Draft/test cancellation is explicit where offered. | Multi-step form stacks; `flow.css`, `product-theme.css`. |
| `/agents` | Inspect/edit workspace agent prompt configuration. | Workspace context and prompt API; save/rerun actions follow current page guards. | Loading, empty/configuration and API errors. | No delete action. | Prompt editor adapts; `agent-prompts.css`, `product-theme.css`. |
| `/runs/:runId` | Redirect to test overview. | Authenticated; run layout loads the test. | Parent run layout loading/error. | None. | Run shell navigation adapts; `run-records.css`. |
| `/runs/:runId/overview` | Review test status and next available result views. | Workspace member; run summary. | Loading, missing test/API error. | None. | Run layout and responsive cards; `run-records.css`, `product-theme.css`. |
| `/runs/:runId/agents` | Inspect/edit this test's agent prompt configuration. | Workspace member; prompt configuration and run context. | Loading, missing config/API error. | No delete action. | Prompt editor adapts; `agent-prompts.css`, `product-theme.css`. |
| `/runs/:runId/perspectives` | Inspect planned simulated perspectives. | Workspace member; run plan. | Loading, empty, error. | None. | Run layout; `run-records.css`, `product-theme.css`. |
| `/runs/:runId/missions` | Inspect planned missions and outcomes. | Workspace member; run plan/results. | Loading, empty, error. | None. | Run layout; `run-records.css`, `product-theme.css`. |
| `/runs/:runId/journeys` | Browse persona journeys and execution state. | Workspace member; journeys and evidence summaries. | Loading, empty, error. | None. | Responsive journey list; `journeys.css`, `product-theme.css`. |
| `/runs/:runId/journeys/:journeyId` | Inspect one journey and its ordered steps/evidence. | Workspace member; journey and artifact metadata. | Loading, missing journey/API error; unavailable artifact remains explicit. | None. | Detail columns stack; `journeys.css`, `product-theme.css`. |
| `/runs/:runId/evaluation` | Inspect evaluation lifecycle and result. | Workspace member; evaluation state. | Loading, pending, unavailable/error states. | None. | Run layout; `run-records.css`, `product-theme.css`. |
| `/runs/:runId/activity` | Inspect test activity/events. | Workspace member; event feed. | Loading, empty, error. | None. | Feed adapts; `run-records.css`, `product-theme.css`. |
| `/runs/:runId/findings` | Review findings by evidence status. | Workspace member; findings. | Loading, empty, error. | None. | Finding rows adapt; `run-records.css`, `product-theme.css`. |
| `/runs/:runId/findings/:findingId` | Inspect a finding and cited evidence. | Workspace member; finding and artifact metadata. | Loading, missing finding/API error. | None. | Detail columns stack; `run-records.css`, `product-theme.css`. |
| `/runs/:runId/evidence` | Browse run evidence artifacts. | Workspace member; artifact metadata. | Loading, empty, unavailable, error. | None. | Responsive artifact rows; `run-records.css`, `product-theme.css`. |
| `/runs/:runId/evidence/:artifactId` | Inspect or download a selected artifact. | Workspace member; artifact metadata/content endpoint. | Loading, missing/unavailable/error. | None. | Viewer constrained to viewport; `run-records.css`, `product-theme.css`. |
| `/runs/:runId/report` | Review generated report and source links. | Workspace member; report and finding/evidence data. | Loading, pending, unavailable/error. | None. | Report sections stack; `run-records.css`, `product-theme.css`. |
| `/runs/:runId/human-action` | Claim/release a human action and control the paused browser; approve or reject a requested action. | Workspace member with server-authorized session/lease; human-action API and one-use viewer ticket. | Loading, claim/lease/viewer errors, awaiting/resuming/completed/expired states. | Approval rejection is explicit and audited. | Viewer occupies available width; `run-records.css`, `product-theme.css`. |

## Settings and system routes

| Route | Purpose, decision, primary action | Access and data | Loading, empty, error | Destructive action | Small screen and CSS |
|---|---|---|---|---|---|
| `/settings` | Redirect to profile. | Authenticated session. | N/A. | None. | Settings shell. |
| `/settings/profile` | View current profile facts. | Authenticated user; read-only current API fields. | Shell/session state. | None. | Settings shell; `workspace.css`, `product-theme.css`. |
| `/settings/workspace` | View active workspace facts. | Workspace member; read-only workspace context. | Shell/session state. | None. | Settings shell; `workspace.css`, `product-theme.css`. |
| `/settings/members` | Explain member-management availability. | Current page is an explicit future-stage placeholder; management API is absent. | Placeholder explanation. | None. | Settings shell; `workspace.css`, `product-theme.css`. |
| `/settings/security` | Explain security settings availability. | Current page is an explicit future-stage placeholder; settings API is absent. | Placeholder explanation. | None. | Settings shell; `workspace.css`, `product-theme.css`. |
| `/403` | Explain a forbidden route and return to overview. | Authenticated session. | Static explanation. | None. | App shell; `workspace.css`, `product-theme.css`. |
| `/error` | Explain an unexpected view failure and return to overview. | Authenticated session. | Static explanation; no frontend data fallback. | None. | App shell; `workspace.css`, `product-theme.css`. |
| `*` | Explain unknown or unavailable route and return to overview. | Authenticated session; resource visibility may be permission-scoped. | Static explanation. | None. | App shell; `workspace.css`, `product-theme.css`. |

## Shared behavior and review notes

- The authenticated app shell loads the session, lists workspaces, provides primary navigation, and keys the outlet by workspace. Workspace-scoped queries include user/workspace identity; logout clears the query cache.
- API permission checks remain authoritative. Frontend role checks only hide or disable unavailable controls.
- Shared primitives (`PageHeader`, state panels, buttons, status badges), `workspace.css`, `run-records.css`, and `product-theme.css` provide most authenticated page styling. Public pages use `public.css`; run details add `journeys.css`, `flow.css`, and/or `agent-prompts.css` as indicated above.
- Breakpoint behavior is inherited from these layout styles; dense data should remain readable without horizontal page scrolling. Verify desktop and narrow/mobile viewports after design changes.
- Placeholder edit, network policy, member, security, and provider callback pages intentionally do not imply functioning APIs.
