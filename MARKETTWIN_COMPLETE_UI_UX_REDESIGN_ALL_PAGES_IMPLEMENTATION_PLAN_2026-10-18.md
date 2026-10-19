# MarketTwin — Complete Application-Wide UI/UX Redesign Implementation Plan

**An actionable, route-by-route and file-by-file execution guide**  
**Prepared:** October 18, 2026  
**Application:** [Sreenav14/Market-Twin](https://github.com/Sreenav14/Market-Twin)  
**Inspected base:** `feat/batch-1-aws-observability` at `660487b65984226002d1c6df743d5a1cb745cf45`  
**Existing isolated design pilot:** draft [PR #5](https://github.com/Sreenav14/Market-Twin/pull/5), branch `design/evidence-ledger-report-20261018`  
**Chosen visual concept:** **Evidence Ledger** — a restrained, distinctive, evidence-first investigative workspace.

> **READ FIRST — evidence and boundaries:** The page inventory and route paths below are based on the GitHub source at the pinned commit, not on a running authenticated React application. The previous Evidence Ledger prototype was rendered separately; its screenshots are **not** screenshots of the actual integrated application. Draft PR #5 exists but has **not** passed an independently executed React/Vitest/Playwright or integrated backend suite in this review. Check the active checkout, uncommitted changes and latest GitHub HEAD before applying anything. **No page should gain fake data, dead controls, unauthorized access, invented metrics, or a UI promise that the backend cannot fulfill.**

---

## 0. What to build — in one paragraph

MarketTwin is an authorized, evidence-backed application testing workbench. It helps teams select an application and approved target, optionally attach approved product knowledge, plan bounded browser tests and simulated personas, watch actual permitted browser execution, safely intervene when a person is needed, review the steps and their evidence, and determine what is **verified**, **unverified** or **a test-execution limitation**. The redesign must make that path effortless to understand. It must not merely repaint the dashboard, hide security controls, or confuse simulated testing with genuine customer research.

### Why this is a full-product redesign, not a landing-page task

The base repository has **57 tracked files under `apps/web/src/pages/`** (including tests and non-route supporting components), a nested authenticated router, public routes, multi-page application and target setup, ingestion and approval, test setup, live browser/HITL, journeys, evidence, findings, assessment, report, agent inspection, settings and error pages. A screen can look excellent in isolation and still fail if adjacent states, cross-links, permissions, browser control or data semantics are inconsistent. Every route and its actual affordances are covered below.

### Non-negotiable outcome

A first-time user should be able to answer, on any major page:

1. **Where am I?** Workspace, app, target, test, tester, step and/or result.
2. **What happened?** An actual persisted state, not simulated progress.
3. **What matters?** Verified product outcome versus unverified observation versus MarketTwin execution problem.
4. **What can I do now?** One prominent, permission-valid, genuinely functioning action.
5. **Where is the proof?** The exact permitted screenshot/artifact/step, or explicit unavailability.

---

## 1. Product understanding and research-derived UX principles

### Users and jobs

| User | Primary job | Default UI needs | Advanced needs |
|---|---|---|---|
| QA engineer / QA lead | Assess a release or flow with reproducible evidence | Define scope, launch, triage, reproduce, share a report | Step assertions, trace, policy, coverage gap, repeatability |
| Developer | Diagnose an actual product regression | Which step? Expected vs observed? Screenshot and context? | Technical request/selector trace as supported by API |
| Product / design lead | Decide whether a behavior works for intended users | Clear conclusion, limitations and next actions | Compare supporting journeys and criteria |
| Workspace owner / admin | Operate safely within authorized targets | Authority, allowed origins, human-action approvals | Security controls and immutable snapshot history |
| First-time developer | Complete first meaningful test | Guided app → target → test path; plain-language guidance | Prompt YAML, models, worker diagnostics later |

### UX insights from similar systems

- **Playwright Trace Viewer:** Action selection and step-attached screenshots make failures inspectable. Adapt the evidence-linking principle, not its raw technical density. Source: https://playwright.dev/docs/trace-viewer
- **mabl / Momentic / BrowserStack Test Observability / TestRail / Checkly:** Useful patterns include result triage, run filtering, grouped repeated failures, testing context and reproducible reports. Do not assume or copy their proprietary designs. Sources: https://www.mabl.com/platform , https://momentic.ai/ , https://www.browserstack.com/test-observability , https://support.testrail.com/ , https://www.checklyhq.com/
- **EasyUI** (https://easyui.site/components): inspect restrained interactive controls, state feedback and accessible micro-motion. Borrow selected patterns only when valuable; avoid installing an entire ornamental kit.
- **Bencho** (https://bencho.dev/): use ideas from resizable panes, tree/step views, access requests and time navigation. Avoid orbit cards, flashy effects and interaction for interaction's sake.
- **Refero and SaaSFrame:** research *complete sequences* (signup → dashboard → detail → error → recovery), density and whitespace at real viewports. https://refero.design/ ; https://www.saasframe.io/
- **NN/g Progressive Disclosure / usability heuristics / complex applications:** Defer optional advanced setup, retain visibility of status, explain errors and preserve user control. https://www.nngroup.com/articles/progressive-disclosure/ ; https://www.nngroup.com/articles/ten-usability-heuristics/ ; https://www.nngroup.com/articles/complex-application-design/
- **WebArena / VisualWebArena / BrowserGym:** Reliable browser testing needs exact goals, observable results and grounded evaluation. These are agent evaluation references, **not** proof of MarketTwin accuracy. https://arxiv.org/abs/2307.13854 ; https://aclanthology.org/2024.acl-long.50/ ; https://arxiv.org/abs/2412.05467
- **WCAG 2.2 AA:** Keyboard, contrast, focus, status messages, labeling and no traps are minimum targets. https://www.w3.org/TR/WCAG22/

### Three considered art directions

| Direction | Visual premise | Advantages | Why selected or rejected |
|---|---|---|---|
| **Evidence Ledger** | Warm paper / deep evergreen / thin proof rails / precise tables / editorial typography | Trust, differentiation, readability and strong report/evidence identity | **SELECTED:** best fit across technical and product users |
| Signal Room | Dark technical operating console / lime signals / split panes | Strong live-browser focus | Use **only** as a localized browser-stage mood; a global generic dark console would weaken approachability |
| Field Notes | Sand / clay / expressive editorial narrative | Human warmth, memorable reading | Valuable for narrative hierarchy, but insufficiently dense for QA operations |

**Do not combine all three aesthetics on every page.** Use one Evidence Ledger system; the browser viewport may be dark when necessary for image fidelity. Every page may use a different composition (list, reader, workbench, form, inspector) while sharing typography, rules, status language, interaction behavior and navigation.

---

## 2. Source-of-truth route inventory and treatment

**Key:** `P0` must precede a convincing product release; `P1` builds cohesive main UX; `P2` improves secondary/advanced experiences. `P0-BE` needs backend work first. Routes are **existing** paths: do not rename without a deliberate redirect and deep-link migration. Here `:id`, `:runId`, `:entryId` and `:artifactId` refer to existing router params, not new APIs.

### 2.1 Public, authentication and global shell

| Existing URL | Existing file | Current contract | Planned change | Priority |
|---|---|---|---|---|
| `/` | `pages/public/PublicPages.tsx` → `HomePage` | Public landing; interactive *illustration* | Evidence-led story with explicit demo label, credible mechanism and one primary CTA | P1 |
| `/how-it-works` | `pages/public/PublicPages.tsx` → `HowPage` | Explains authorized flow/limitations | More scannable step-by-step, screenshots/diagram **only if true**, accessible jump links | P1 |
| `/login` | `pages/auth/LoginPage.tsx` | Local approved-email sign-in | Human, clear sign-in and error/focus states; no fictitious SSO | P1 |
| `/auth/callback` | `pages/auth/AuthCallbackPage.tsx` | Informational Cognito callback placeholder | Mark unsupported clearly; do not mock auth completion | P2 / backend dependency |
| *auth/root routing* | `app/App.tsx` | Public-route bypass and session gate | Harmonize boot/error/redirect states; preserve session behavior | P0 regression check |
| *authenticated shell* | `layouts/AppShell.tsx` | Sidebar, workspace switch, breadcrumbs, command menu | Rebuild hierarchy and responsive behavior without changing routes or role scope | P1 |
| `/403` | `pages/system/ForbiddenPage.tsx` | Forbidden | Clear missing permission, safe return, no action requiring denied role | P2 |
| `/error` | `pages/system/UnexpectedErrorPage.tsx` | Error | Specific retry/exit only if available, no fake saved-state claim | P2 |
| `*` | `pages/system/NotFoundPage.tsx` | Not found | Distinguish unavailable / nonexistent where allowed, workspace-safe return | P2 |

### 2.2 Workspace, applications and targets

| Existing URL | Existing file | Current contract | Planned change | Priority |
|---|---|---|---|---|
| `/overview` | `pages/overview/OverviewPage.tsx` | Real workspace test/app summaries | Attention-first operations overview, current run and report readiness | P1 |
| `/applications` | `pages/applications/ApplicationsPage.tsx` | List real apps | Clear table/rows, linked targets, ownership and next-action context | P1 |
| `/applications/new` | `pages/applications/NewApplicationPage.tsx` | Create app | Focused short creation form + preview of next target step | P1 |
| `/applications/:applicationId` | `pages/applications/ApplicationOverviewPage.tsx` | App, targets, recent tests | App-centric hub with authorization and one next action | P1 |
| `/applications/:applicationId/edit` | `pages/applications/EditApplicationPage.tsx` | **FutureStagePage; no update endpoint** | Keep honest unavailable state; suppress misleading Edit action elsewhere | P2 / backend dependency |
| `/applications/:applicationId/runs` | `pages/applications/ApplicationRunsPage.tsx` | App-specific run list | Reuse compact TestRow with project context and state | P1 |
| `/applications/:applicationId/targets` | `pages/targets/TargetsPage.tsx` | Target list | Origin + authorization summary, concise entry to scope | P1 |
| `/applications/:applicationId/targets/new` | `pages/targets/NewTargetPage.tsx` | Create target then navigate to authorization | Two-step security setup, no implied authorization on create | P0 |
| `/targets/:targetId` | `pages/targets/TargetOverviewPage.tsx` | Target and authorization read | Authorization receipt, visible allowed origins + last known status | P0 |
| `/targets/:targetId/authorization` | `pages/targets/TargetAuthorizationPage.tsx` | Authorize/revoke + exact execution scope | Explicit irreversible/sensitive consequences, confirmations, real state | P0 |
| `/targets/:targetId/network` | `pages/targets/TargetNetworkPolicyPage.tsx` | Request scope revisions; pending ≠ approved | Diff exact origins, requested/authorized separation, audit-friendly receipt | P0 |
| `/targets/:targetId/edit` | `pages/targets/EditTargetPage.tsx` | **FutureStagePage; target edits unsupported** | Keep read-only and avoid fake editing; backend must define reauthorization | P2 / backend dependency |
| `/applications/:applicationId/knowledge` | `app/router.tsx` | Redirects to `/ingestion` | Preserve redirect, optionally pass app context without breaking workspace role | P2 |

### 2.3 Knowledge ingestion and approval

| Existing URL | Existing file | Current contract | Planned change | Priority |
|---|---|---|---|---|
| `/ingestion` | `pages/knowledge/IngestionPage.tsx` | Upload or link-research entry + sources list | Source-first form, clear constraints, immediate processing navigation **after backend queue fix** | P0-BE |
| `/knowledge/review` | `pages/knowledge/ReviewKnowledgePage.tsx` | Filtered list and status | Knowledge index: source, lifecycle, approval, attached apps | P1 |
| `/knowledge/review/:entryId` | `pages/knowledge/KnowledgeReviewPage.tsx` | Poll source; retry, review and explicit approval | Stage ledger, evidence-to-knowledge split, approval decision | P0-BE + P1 |
| *child UI* | `pages/knowledge/IngestionProgress.tsx` | Uses fixed 20/50% values | **Remove fabricated percentages**; named or indeterminate truthful stages | P0 |
| *child UI* | `pages/knowledge/KnowledgeResult.tsx` | Knowledge/artifacts/skills/evidence/issues | Source-linked tabs/sections with source locator and review tools | P1 |
| *child UI* | `pages/knowledge/KnowledgeSettings.tsx` | Rename/attach knowledge to apps | Calm role-aware controls and clear association success/failure | P1 |

### 2.4 Tests, live execution and results

| Existing URL | Existing file | Current contract | Planned change | Priority |
|---|---|---|---|---|
| `/runs` | `pages/runs/RunsPage.tsx` | Search, filter and run list | High-density TestTable with meaningful states, readable mode and next action | P1 |
| `/applications/:applicationId/runs/new` | `pages/runs/NewRunPage.tsx` | **458-line** test composer, requires authorized target | Goal-first progressive form and scope receipt, preserve every safety option | P0 |
| `/runs/:runId` | `layouts/RunLayout.tsx` | Redirects to `overview` | Keep redirect; apply unified test shell | P1 |
| `/runs/:runId/overview` | `pages/runs/RunOverviewPage.tsx` | Lifecycle, findings, config | Truthful run verdict and most relevant next action | P0 |
| `/runs/:runId/activity` | `pages/runs/RunActivityPage.tsx` | Real live metadata, browser observation, pause + activity, assisted control | Primary workbench with selected goal → actual browser → step timeline | P0 |
| `/runs/:runId/journeys` | `pages/runs/RunJourneysPage.tsx` | Journey list + collection data | Group by mission and completion, make persona secondary, connect evidence | P0 |
| `/runs/:runId/journeys/:journeyId` | `pages/runs/JourneyDetailPage.tsx` | Step selection + artifacts + findings | 3-pane evidence inspector; preserve step ID and paging | P0 |
| `/runs/:runId/findings` | `pages/runs/RunFindingsPage.tsx` | Already groups classified findings and has inspector | Sharpen grouping, avoid duplicated UI, preserve filtering and evidence links | P0 |
| `/runs/:runId/findings/:findingId` | `pages/runs/FindingDetailPage.tsx` | Evidence-based finding detail + artifact access | Reproduction story, expected/observed where persisted, exact citations | P0 |
| `/runs/:runId/evidence` | `pages/runs/RunEvidencePage.tsx` | Artifact index scoped through journeys | Finder/filter by journey, step, kind; no phantom global artifact list | P1 |
| `/runs/:runId/evidence/:artifactId` | `pages/runs/EvidenceDetailPage.tsx` | **Functional wrapper around `ArtifactEvidence`**, not a dead placeholder | Full viewer and safe return to source journey/finding | P1 |
| `/runs/:runId/report` | `pages/runs/RunReportPage.tsx` | Old repeated-report hierarchy | **Draft PR #5 pilot**: evidence-first report, separated categories, grouped diagnostics | P0; review PR first |
| `/runs/:runId/human-action` | `pages/runs/HumanActionPage.tsx` | Real claim, renew, release, skip, approval decisions | Prominent assistance state; do not duplicate lease/controller | P0 |
| `/runs/:runId/evaluation` | `pages/runs/RunEvaluationPage.tsx` | Assessment, visual evaluation records, agent diagnostics | Evidence table and explanation; advanced model info collapsed | P1 |
| `/runs/:runId/perspectives` | `pages/runs/RunPerspectivesPage.tsx` | **Functional tester summaries**, not placeholders | Tester roles in user language; deep mode explicitly has no personas | P2 |
| `/runs/:runId/missions` | `pages/runs/RunMissionsPage.tsx` | **Functional testing-goal summaries**, not placeholders | Goal-first criteria coverage view | P1 |
| `/runs/:runId/agents` | `pages/runs/AgentPromptsPage.tsx` | Run tester tree and advanced prompts/runtime metadata | Novice tester/goal first; advanced config expandable | P2 |
| `/agents` | `pages/runs/AgentPromptsPage.tsx` | Global project/run agent browser | Treat as advanced; link to real runs and saved snapshots | P2 |
| *child UI* | `pages/runs/LiveBrowserObserver.tsx` | Actual read-only captured frame | Fenced frame and stale state; NEVER input or fake video | P0 |
| *child UI* | `pages/runs/HumanBrowserViewer.tsx` | Protected WebSocket control with leased viewer ticket | Improve ergonomic controls only where existing transport permits; no credential logging | P0 |

### 2.5 Settings and support

| Existing URL | Existing file | Current contract | Planned change | Priority |
|---|---|---|---|---|
| `/settings` | `layouts/SettingsLayout.tsx` | Redirects to profile | Preserve and simplify subnavigation | P2 |
| `/settings/profile` | `pages/settings/ProfileSettingsPage.tsx` | **Read-only** account data | Clear read-only profile, hide technical ID by default | P2 |
| `/settings/workspace` | `pages/settings/WorkspaceSettingsPage.tsx` | **Read-only** workspace details | Role and status, access explanation, optional advanced ID | P2 |
| `/settings/members` | `pages/settings/MembersSettingsPage.tsx` | **FutureStagePage; no member management API** | Unavailable state with honest explanation, do not show fake invitations | P2 / backend dependency |
| `/settings/security` | `pages/settings/SecuritySettingsPage.tsx` | **FutureStagePage; no security management API** | Honest scope; no fake MFA, SSO, session revocation toggles | P2 / backend dependency |

**Inventory correction:** `RunPerspectivesPage` and `RunMissionsPage` are **not** blank placeholders in this pinned branch; they fetch journey data. `EvidenceDetailPage` is short but actually calls `ArtifactEvidence`. Conversely, application edit, target edit, members and security settings are explicitly not yet backed by update/management APIs. A future implementation must preserve these differences.

---

## 3. Proposed information architecture — not a router rewrite

### 3.1 Global navigation hierarchy

Default main navigation:

```text
MarketTwin                         Workspace switcher
├── Overview                       Attention, latest tests, next actions
├── Applications                   All applications and their targets
├── Tests                          In progress, waiting, finished, reported
├── Knowledge                      Reviewed, pending, approved knowledge
└── More / Settings
    ├── Add knowledge              Actual `/ingestion` route
    ├── Agent settings             Actual `/agents` route, advanced
    ├── How it works               Public `/how-it-works`
    └── Settings                   `/settings/profile`
```

**Do not require a new sidebar to reach basic testing.** Existing sidebar in `AppShell.tsx:197–240` can be adapted. Merge the perceived duplication of “Knowledge” and “Add knowledge”: Knowledge = library/list, contextual “Add source” = CTA pointing to `/ingestion`. Do not delete the existing URL; hide/reposition only the redundant nav entry, not capability.

### 3.2 Application subnavigation

```
Application detail
  Summary → Targets → Tests
               |       |
        Authorization   New test
        Network scope   Latest result
        Target details
```

Avoid a second always-visible global sidebar. Use local tabs and breadcrumb. Show current authorization next to target names; do **not** imply that an app existing means test execution is authorized.

### 3.3 Test subnavigation

Default user-oriented order: **Summary | Live execution | Journeys | Findings | Evidence | Report**. Under `More`: **Goals | Simulated testers | Evaluation details | Human assistance | Agent configuration**. A pending human action must also appear as a prominent cross-route banner/primary action. A report-ready state should surface on Summary and Tests—not require users to hunt.

`RunLayout.tsx:199–230` already has most of this. Refine grouping and labeling; keep nested routes and the existing `HumanAssistanceHost` mounted once. The `RunFlowPanel` should become a compact expandable technical section rather than permanent competing right rail on every content-heavy view.

### 3.4 Vocabulary contract

| Internal/backend concept | Default text | Advanced detail |
|---|---|---|
| `TestRun` | Test | Test ID, status, schema and snapshot |
| `RunPersona` | Simulated tester | Persona ID and prompt |
| `RunMission` | Testing goal / task | Mission ID and criteria schema |
| `PersonaJourney` | Journey | Agent execution ID, attempt ID |
| Feature-case executor | Feature case / planned check | `deep_feature_v1` mode and steps |
| HITL | Human assistance / Take control | Lease state, generation and target authority |
| Target authorization | Approved testing scope | Allowed origins and attestation |
| Source ingestion | Source processing | Worker/entry status, source metadata |
| Artifact | Evidence | Signed URL, kind, object ID |
| Evaluator result | Verification result | Deterministic/visual/model classification |
| Agent failure | Test execution problem | Tool failures and error codes |

No term should imply real customer testing, proof from repeated model opinions, a clean bill of health from zero findings, or successful execution because Kafka merely accepted a request.

---

## 4. Design system: exact recommended implementation

### 4.1 Preserve existing infrastructure

Keep React + TypeScript, React Router 7, React Query, Vite, Radix Dialog/Tooltip, current Button/Input/Textarea primitives, `StatusBadge`, role helpers, API client, Playwright viewer, TestRun/Knowledge models and backend authorization. Current dependencies are already enough for the redesign; do **not** install an entire animation or component library for aesthetics.

### 4.2 Typography

- **Existing primary:** `Instrument Sans Variable` (already installed), regular body 15–16px/1.5–1.65, headings 600–650 with controlled tracking.
- **Existing secondary:** `IBM Plex Mono` (already installed) for timestamps, source references, brief overline labels and counts; not body paragraphs.
- **Editorial accent:** sparse Georgia italic in report headings and public story elements only; do not put serif text inside forms, table headers or app controls.
- Scale: display 52/56 desktop, 36/40 compact; H1 32/38; H2 24/30; H3 18/24; body 15–16/24; secondary 13/20; metadata 12/17 with readable contrast.
- Real content constraints: heading no more than ~70 characters before wrapping gracefully; use `min-width:0`, `overflow-wrap:anywhere` for URLs/IDs; avoid `text-transform:uppercase` on long phrases.

### 4.3 Color and semantics

**Proposed Evidence Ledger palette:**

```css
/* Add as scoped semantic tokens first, not as a surprise global :root rewrite. */
.evidence-ledger-theme {
  --ledger-paper: #F5F4ED;
  --ledger-surface: #FFFEFA;
  --ledger-ink: #1B302E;
  --ledger-muted: #586965;
  --ledger-rule: #D4DAD1;
  --ledger-accent: #156B55;
  --ledger-accent-soft: #E8F1E8;
  --ledger-caution: #99512E;
  --ledger-caution-soft: #F6EADD;
  --ledger-failed: #903A3D;
  --ledger-technical: #4F6570;
  --ledger-focus: #0D735D;
}
```

- The base repository's `styles/tokens.css` currently defines **dark teal / mint** root tokens. Draft PR #5 introduces scoped report-only paper styling. **Do not replace global `:root` in the same PR as every page migration.**
- Create paired light/dark semantic mappings only after mapping existing selectors. If a user-selectable theme is not supported yet, don't introduce a theme toggle with no state or inaccessible persistency.
- Status words stay explicit: `Verified`, `Needs verification`, `Execution issue`, `Policy blocked`, `Timed out`, `Awaiting human`, `Ready for review`, `Approved`, `Failed`. Never use hue alone.
- WCAG 2.2 AA contrast: 4.5:1 ordinary text, 3:1 large text and meaningful UI boundaries. Recalculate for actual state badges: proposed hex colors are **not** an automatic passing audit.

### 4.4 Composition, grids and rhythm

| Surface | Structure | Important restraint |
|---|---|---|
| Public site | Editorial story + real mechanism illustration | No false testimonials, fake metrics, decorative orbit art |
| Overview | Attention queue above efficient test list | Do not elevate zero-valued metric cards |
| Data lists | Dense readable rows with accessible sort/filter | No repeated big decorative cards |
| New test | Strong goal field + progressive groups + final scope receipt | Never hide mandatory authorization behind “Advanced” |
| Live execution | Selected task (left), owned browser (center), ordered events (right) | Keep authority and staleness unmistakable |
| Finding detail | Claim/evidence/next action with step-linked inspector | Do not imply evidence if IDs are absent |
| Knowledge review | Source and draft outcome side by side | Human approves only in backend-valid state |
| Report | Editorial document with a small evidence/coverage rail | No endless five-zero severity summaries |
| Settings | Quiet factual forms/lists; honest unsupported states | No fake toggles |

Spacing tokens: 4, 8, 12, 16, 24, 32, 48 and 64px. Radii 4–8px for controls/panels, not giant repetitive cards. Make controls accessible touch targets; at least 24px under WCAG 2.2 AA minimum target-sizing conditions, prefer ~40–44px for primary actions.

### 4.5 Component build plan and ownership

**Refactor/reuse existing before creating parallel implementations:**

| Component | Existing source or proposed source | What should change | Critical contract |
|---|---|---|---|
| `PageHeader` | `components/ui/PageHeader.tsx` | Consistent title, context, one strong action and optional meta | No duplicate H1; responsive button wrap |
| `Button/Input/Textarea` | `components/ui/{button,input,textarea}.tsx` | Sizes, focus, disabled, validation tokens | Retain existing props/ARIA and controlled inputs |
| `StatusBadge` | `components/ui/StatusBadge.tsx` | More readable text + severity/status variants | Underlying status semantics unchanged |
| `StateViews` | `components/ui/StateViews.tsx` | Empty, pending, error, stale, forbidden, role-limited patterns | Never replace backend failure with fake empty success |
| `BrandMark` | `components/ui/BrandMark.tsx` | Consider uniquely identifiable proof-line shape | Test legibility 16/24/48 px |
| `CommandMenu` | `components/markettwin/CommandMenu.tsx` | Search/navigation grouping; shortcut explanation | Keyboard focus/escape; only real routes/actions |
| `RunFlowPanel` | `components/markettwin/RunFlowPanel.tsx` | Compact technical inspector, not competing permanent diagram | Preserve `/flow` API and execution-mode truth |
| `CopyButton` | `components/markettwin/CopyButton.tsx` | Clear success/failure feedback | Copy *real* report summary, not misleading synthesis |
| `FindingListItem` | `components/markettwin/FindingListItem.tsx` | Standardized finding-row semantics | Shared verified classification from `lib/results.ts` |
| `RunAssessmentView` | `components/markettwin/RunAssessmentView.tsx` | Human-friendly assessment and evidence limitations | Generic unavailable reason remains truthful |
| `FeatureCases` | `components/markettwin/FeatureCases.tsx` | Strong assertions/evidence pairs | Deterministic feature mode is not persona mode |
| `HumanAssistanceHost` | Inside `pages/runs/HumanActionPage.tsx` | Continue one controlling lease across tabs | **Never mount duplicate lease owners** |
| `LiveBrowserObserver` | `pages/runs/LiveBrowserObserver.tsx` | Read-only stage with stale/reconnect/no-frame signals | No input capability on observer |
| `HumanBrowserViewer` | `pages/runs/HumanBrowserViewer.tsx` | Keyboard instructions, focus handoff, safe explicit Done | Lease ticket, WebSocket, generation must stay secure |
| `EvidenceRail` | **propose** `components/markettwin/EvidenceRail.tsx` | Link criterion → step → artifact → verification | Render only valid saved references; no guessed fallback |
| `ScopeReceipt` | **propose** `components/markettwin/ScopeReceipt.tsx` | Present exact target and permitted origins at create/review | Request ≠ authorization |
| `CoverageSummary` | **propose** `components/markettwin/CoverageSummary.tsx` | Separate total, normal completion, verified checks | Denominator must come from saved run, not UI estimates |
| `RunListRow` | **propose** `components/markettwin/RunListRow.tsx` | Consistent run list in Overview/Tests/Application | Source from existing `TestRun` data only |
| `ExecutionDiagnosticGroup` | **propose** `components/markettwin/ExecutionDiagnosticGroup.tsx` | Group same reliable failure reason with link to each original | Grouping is display-only; never delete original records |

**IMPORTANT:** Suggested component paths are **new proposals**, not files already present. Before creating any, inspect import/caller graph and ask whether shared rendering actually reduces duplication. Keep components near the domain when only one page uses them.

### 4.6 Motion/focus behaviors

- 120–180 ms hover and focus; 180–240 ms menu/drawer change; reduced motion disables nonessential animation.
- No endless pseudo-progress, glowing AI orbs, shaking controls, random smooth scrolling, fake streamed typing or celebratory confetti for “0 defects.”
- Live activity updates must not steal focus, jump scrolling or replace a selected step while a user investigates history.
- Use `aria-live` **only for significant state changes**; rate-limit repetitive live-event announcements.
- Preserve route focus behavior in `AppShell.tsx` and ensure modal focus return/escape works with Radix.

---
## 5. Page-by-page implementation instructions: public, entry, workspace

Each page below names **an existing file**, expected UI change, primary state(s), and completion check. Treat the changes as implementation instructions, not a claim that they are already coded.

### 5.1 Public homepage — `pages/public/PublicPages.tsx` / `HomePage`

**Keep:** existing real product positioning, authorized-testing claim, correctly labeled interactive illustration, links to `/login` and `/how-it-works`.

**Change:**

1. Hero uses a compact evidence metaphor: testing question on the left and a **clearly labeled illustrative** observation/evidence sequence on the right. One primary CTA “Open workspace”; one secondary “See how it works”.
2. Replace any repetitive generic three-card marketing section with a single visual workflow: **Define outcome → Observe action → Check evidence → Decide next action**. Keep simulated-persona caveat visible.
3. A “Sample report anatomy” can show categories (`Verified`, `Needs verification`, `Execution issue`), but its data must be explicitly an illustration, not claimed customer statistics.
4. Provide a short “Who is it for?” strip for QA/developer/product/security without fake testimonials.
5. Use intentional type and fine rules instead of robot imagery, nebula backgrounds, glossy metric tiles, or excessive animated icons.

**Test:** 320/390/768/1440 widths, skip link, reduced motion, CTA routing, no deceptive social proof.

### 5.2 How it works — `pages/public/PublicPages.tsx` / `HowPage`

**Keep:** sections for setup, execution, result categories and limits; factual explanations of feature/persona modes.

**Change:** a readable numbered article with sticky in-page contents on wide screens, a single trace diagram (question → scope → browser → evidence → conclusion), concise copy, and a “Common reasons a test is inconclusive” disclosure group. Make examples generic and explicitly illustrative. Reflect **actual** three-persona planner behavior in the currently shipped mode; do not describe proposed smarter planning as already available.

**Test:** anchor offsets, narrow-screen links, status distinction, generated content never masquerading as independent human research.

### 5.3 Sign-in — `pages/auth/LoginPage.tsx`

**Keep:** approved-email local authentication, `api.login`, error handling, local environment warning, and existing session state. Do not add password, Google login or SSO controls unsupported by the backend.

**Change:** visually quieter two-area desktop / single-column mobile screen; strong trust copy and exact local sign-in instruction; focused labeled email input; error space reserved to avoid layout shift; submit state announces “Signing in…”. On failure, focus/announce the error without erasing entered email. Remove decorative process cards if they distract from access.

**Test:** invalid email, unapproved email, 401 vs 5xx, no double-submit, Enter, tab/focus, mobile keyboard, actual `onAuthenticated` flow.

### 5.4 Auth callback — `pages/auth/AuthCallbackPage.tsx`

The current route is **informational** and explicitly says production Cognito flow is not implemented in local V1. Preserve that honesty. Style as a simple guarded state, never present a loading spinner that will never complete. Route activation needs separately specified backend PKCE/session support; out of visual-redesign scope.

### 5.5 Global layout — `layouts/AppShell.tsx`, `app/App.tsx`, `app/router.tsx`

**Priority: every authenticated page inherits this.**

1. Keep workspace switcher and cache invalidation; show current workspace label and role without exposing IDs by default.
2. Default nav order: Overview, Applications, Tests, Knowledge. Surface “Add source” contextually in Knowledge; move “Agent settings” to secondary/advanced navigation.
3. Current page and breadcrumbs need one consistent naming dictionary; `AppShell.tsx:25–82` currently constructs generic path labels. Create `lib/navigationLabels.ts` if needed, with static semantic route definitions; avoid exposing raw `:id` strings or `human-action` in the breadcrumb.
4. Desktop: restrained slim navigation rail and generous content width; mobile: existing Radix drawer with real focus trap and close on route change. Do not create a second competing sidebar.
5. Command menu must navigate to only real routes and close on selection/Escape; role-prohibited actions should not be advertised as available.
6. Keep skip link, `main` focus on navigation, logout button and stale-request handling. An overlay must never obscure Human Assistance state.
7. Use an attention signal (label and actionable link) only when existing data reports an actual waiting-human run; no decorative notification badge without a backed count.
8. Avoid broad `window.scrollTo(0)` when switching tabs where preserving inspector context is valuable; evaluate per route, preserve user focus rules. Do not abruptly remove without route-focused tests.

**Test:** workspace A → B cannot show stale A data, all nav keyboard accessible, active route naming, 320px drawer scroll, sign out and protected route gating, 200% zoom.

### 5.6 Workspace overview — `pages/overview/OverviewPage.tsx`

**Current:** `useWorkspaceTests` returns applications and runs; counters for apps/tests/in progress/execution completed; attention queue; recent rows; knowledge tools.

**Change:**

1. First section conditionally prioritizes **Human assistance required** when there is an actual `awaiting_human` run. Provide correct run name, target, and “Open assistance” route.
2. If no human action, show currently running/queued tests with current server status. If report-ready runs exist, show latest meaningful review path. Do not imply a report is ready from `run.status === "completed"` alone.
3. Keep compact metrics as secondary context, not four equally loud cards; labels clearly separate *execution complete* and *verified outcome*.
4. Recent tests use shared `RunListRow`; application links remain present as a small index.
5. Empty workspace: one “Add application” path for writers; explain lack of permission for read-only roles; no dead start button.
6. Knowledge prompt is contextual, optional, clearly labels approval requirement. Do not imply auto-ingested documents are instantly usable.
7. Refresh errors use last loaded data with “Unable to refresh; showing previous information” and Retry (currently partly implemented).

**Test:** zero apps, 1 app and no target, several apps, 0 runs, waiting-human, running, failed, completed-with-pending-evaluation, read-only role, stale refresh.

---

## 6. Page-by-page implementation instructions: applications and target security

### 6.1 Applications directory — `pages/applications/ApplicationsPage.tsx`

- Replace oversized generic panels with an information-dense list showing app name, actual status, and a clear link into its detail. Display authorized-target count or last test **only when available from an existing queried endpoint**; otherwise omit, don't show invented zeros.
- Provide “Add application” CTA to writers and an explanation of role-based limitations to readers.
- Add search only if client-side list is bounded and useful; preserve exact list fetch. No new `/search` backend assumed.
- States: loading skeleton with non-deceptive data geometry; empty; network error/retry; long names; 100+ apps pagination/virtualization only after measured need.

### 6.2 Add application — `pages/applications/NewApplicationPage.tsx`

- Reduce the form to primary required fields currently accepted by `api.createApplication`.
- Title and helper: “Create an application” / “Next you will add a target environment and authorize testing.”
- Display inline validation, busy state and cancel; preserve create → `/applications/{id}` navigation.
- Do not combine this with target creation unless backend contracts and partial-failure recovery are consciously designed.

### 6.3 Application overview — `pages/applications/ApplicationOverviewPage.tsx`

- Header: application name + status, one relevant next action (Add target, Authorize target, or New test if a valid target exists).
- Left primary: targets with exact authorization status; lower: recent tests with meaningful execution/report states. Right/secondary: knowledge entry point and descriptive metadata if available.
- Retain existing `api.getApplication`, `api.listTargets`, and `api.listRuns` queries; avoid repeatedly fetching duplicate records from child components.
- Do **not** enable “Start test” before target authorization. “Edit application” remains unavailable in backend; avoid misleading prominent edit affordance.
- States: app not found, forbidden workspace, targets empty, runs empty, partially failed secondary query, archived app, mobile.

### 6.4 Edit application — `pages/applications/EditApplicationPage.tsx`

**Current:** `FutureStagePage`, backend update endpoint not present. **Design treatment:** honest “Editing is not available in this version” with Back to application and a plain reason; no editable mock form or Save button. Only activate editing with a separate backend contract including authorization, audit trail and changing references.

### 6.5 Application tests — `pages/applications/ApplicationRunsPage.tsx`

- Share the same `RunListRow` presentation as `/runs` but scoped to the selected app. Show name, environment, mode, status, clear action: Watch, Assist, Review when accurately known.
- Preserve application context breadcrumb and create-new-test target. Empty list shows “No tests for this application” rather than global zero.
- Reuse existing `api.listRuns(applicationId)` and route to `/runs/{id}/overview`.

### 6.6 Targets directory — `pages/targets/TargetsPage.tsx`

- Display target name and environment with a clearly separated authorized/pending/revoked status, using authorization data **only if actually loaded**. Never infer approval from `target.status === 'active'`.
- Provide Add target CTA if role permits. Each row links to detail; pending approval link should be explicit if data supports it.
- Error/empty and long origins tested. Avoid showing production safety statuses in decorative colors only.

### 6.7 Add target — `pages/targets/NewTargetPage.tsx`

- Keep actual form fields and `api.createTarget` contract; preserve successful redirect to `/targets/{id}/authorization`.
- Intro tells user: “Creating the environment does not authorize a browser to test it.”
- Distinguish base URL from *allowed execution origins*, and public-only network policy from login assistance.
- Provide exact URL examples with no claim that arbitrary production sites are permitted; validate malformed URLs, trailing paths, wildcard assumptions and protocol early.
- Before create: short scope explanation; after create: genuine authorization step; don't silently auto-approve a scope.

### 6.8 Target overview — `pages/targets/TargetOverviewPage.tsx`

- Show a **Scope Receipt**: origin, environment, authorized/revoked/pending status, current allowed origins, permission basis and expiry if available.
- One actionable next step based on real state (Review authorization, Review scope, or Start test via app route). Avoid reconstructing role permissions in view-only markup; use existing permission helpers.
- Show `auth-only` origins distinct from execution origins where data supports it. Unavailable authorization state should not look green.

### 6.9 Target authorization — `pages/targets/TargetAuthorizationPage.tsx`

- Treat as a security approval document, not a celebratory onboarding screen.
- Visually separate **Requested scope** from **Currently authorized scope**; show exact hostnames and explain that subdomains are not implicitly allowed.
- Require existing attestation/confirmation before actual `api.authorizeTarget`; keep `api.revokeAuthorization` with explicit confirmation of consequence.
- Keep role checks and backend authority; never surface enabled Approve/Revoke to viewer roles.
- When authorization expires/revokes, show targeted next action and make test creation reflect the new state.
- Test click race, double submit, stale authorization, 403/409, expired session, revocation while viewing.

### 6.10 Target execution scope — `pages/targets/TargetNetworkPolicyPage.tsx`

- Make revisions visually comparable: `current approved origins` beside `requested additions/removals` **only when revision data actually provides both**. A simple semantic list is better than invented diff semantics.
- Label scope requests as **Pending — does not grant test permission**. Link to target authorization for the approval step.
- Preserve `api.listScopeRevisions` and `api.requestScopeRevision`, confirmation requirement and business basis validation.
- The Klaviyo report's `marketplace.klaviyo.com` policy block is a good fixture. Correct UI language: “This destination is outside approved scope. Request approval if authorized.” **Never provide a one-click automatic allowlist expansion.**
- Test denied/untrusted origins, duplicate origins, pending vs authorized labels, read-only access and concurrent revisions.

### 6.11 Edit target — `pages/targets/EditTargetPage.tsx`

**Current:** `FutureStagePage` because changing URL/allowed origins needs reauthorization. Keep an honest unavailable state and link to the scope-request workflow. Do **not** implement a visual Edit form without explicit backend invalidation and reapproval semantics.

### 6.12 Legacy knowledge redirect — `app/router.tsx` `/applications/:applicationId/knowledge`

Keep the existing redirect to `/ingestion` for old deep links. If the create-source form gains an application preselection, pass it only after verifying workspace-scoped target/application membership and ensuring link state cannot bypass permissions. Do not delete the route during visual cleanup.

---

## 7. Page-by-page implementation instructions: knowledge ingestion and review

### 7.1 Add knowledge — `pages/knowledge/IngestionPage.tsx`

**Critical functional dependency:** `services/control-api/src/markettwin_control_api/api/ingestion.py:101–122` currently calls `research_link()` **before** persisting the ingestion entry. The frontend only navigates after the HTTP response. When research fails, no durable processing page is reached. CSS cannot fix that.

**Expected finished workflow:**

```
Choose source (document / public link)
  → Validate local form & authorized workspace
  → Persist original source/URL manifest in private storage
  → Create ingestion entry (durable ID)
  → Return HTTP 202 promptly
  → Navigate `/knowledge/review/:entryId`
  → Background processing updates persisted states
  → Explicit human review
  → Approve and optionally attach to app
```

**Frontend instructions:**

1. Present source choice as compact segmented tabs or clearly labeled radio buttons; file and URL paths share an accessible name/purpose section.
2. Explain allowed link research: public, permitted, read-only pages; login/payment/destructive actions not supported by ingestion.
3. Show file size/types based on actual backend configuration; never advertise unsupported formats.
4. On submission, show “Saving source…” only until the server returns the durable entry. Then navigate immediately. Do not promise 20 minutes of work inside the form.
5. On validation rejection, keep entered text/file selection where safe and move focus to the issue. On auth rejection, show scope explanation.
6. Source list below the form should include current states and a route to review; avoid a second identical Knowledge page embedded inside.

**Backend prerequisite (separate reviewed PR):** `api/ingestion.py`, `knowledge/processor.py`, `knowledge/repository.py`, `knowledge/link_research.py`, SQLAlchemy model and Alembic migration as required. Reuse existing Postgres-backed processor and knowledge worker. Do not substitute Kafka just to update a progress bar.

### 7.2 Truthful processing status — `pages/knowledge/IngestionProgress.tsx`

**Current confirmed issue:** `<progress value={queued ? 20 : 50}>` is a made-up percentage. **Replace it.**

**Before the backend emits detailed stages:** render factual `queued` / `processing` and an indeterminate progress indicator, with text “Source saved” / “Generating preview”; no numeric progress. **After** backend adds persisted stages, render `queued → researching (link only) → generating → ready for review / failed`, supported by source timestamps only if stored. Stage names must exactly match the contract; do not infer completion from HTTP polling count.

Do not lose retryable failure state. Avoid screen-reader announcements on every 1.5-second poll: announce **stage changes** only.

### 7.3 Knowledge library — `pages/knowledge/ReviewKnowledgePage.tsx`

- List name, source type, processing/approval state, roles, assigned apps only where the list response includes them.
- Existing filters (all/draft/approved/pending/failed) remain URL/query-backed; make active filter and count visible.
- On empty result from filter, offer Clear; on globally empty library, Add a source for writers, explanation for readers.
- Highlight needs-review sources requiring a user decision, but never auto-approve.
- Preserve links to `/knowledge/review/:entryId`. Long document names/URLs wrap; failed processing gets a clear Retry detail link.

### 7.4 Knowledge review detail — `pages/knowledge/KnowledgeReviewPage.tsx`

**This is a critical decision screen.** Current source already polls the entry, provides original-source access, and requires a review checkbox before approval. Keep these working safeguards.

Composition:

- Header: source name and source purpose; original source link; true stage.
- Left main: extracted `Application knowledge`, `Artifacts`, `Skills`, `Evidence`, `Extraction issues` with source anchors.
- Right rail: source access, review checklist, explicit Approve or Attach controls; disabled until backend-valid state.
- If processing: show stage ledger, last server update only if available, a truthful “You can leave this page”.
- If failed: exact safe error and retry; no disabled approval masquerading as “Ready”.
- If approved: show Approved / Available for tests and attached applications; no ambiguous button to approve twice.
- If source-access signing fails: allow reading saved preview where authorized but show a separate source-preview error.

**Security/correctness gate:** Backend `approve_ingestion` should explicitly require the exact `needs_user_review` asset state before approving. Frontend must reflect but cannot substitute for that guard.

### 7.5 Result components — `pages/knowledge/KnowledgeResult.tsx`

- Preserve existing content categories and source locators; establish consistent readable numbered evidence markers, not decorative blobs.
- Source citations open the **actual** accessible source or named locator; no link to a guessed page/hash.
- Clearly distinguish `Generated summary` from `Source evidence`; raw model content is not automatically trustworthy.
- Make long snippets collapsible and keyboard accessible; preserve exact text on copy, display truncation only, never silently alter stored content.
- Extraction issues remain visible and do not disappear just because some knowledge items were successfully generated.

### 7.6 Review settings — `pages/knowledge/KnowledgeSettings.tsx`

- Existing rename form uses `api.renameIngestion`; application attachment uses `api.attachIngestion`. Preserve roles and API constraints.
- Keep two deliberate actions: Rename knowledge set / Attach approved knowledge to applications. Put these below source review, not in a confusing global settings-like card.
- Confirm success, explain no applications, and avoid claiming a set is selectable until association and approval are saved.
- Regression test disabled/read-only, duplicate selection, revalidation and workspace ownership.

---

## 8. Page-by-page implementation instructions: testing workflow

### 8.1 All tests — `pages/runs/RunsPage.tsx`

- Keep current search and status filters in URL query; make filter clearable and keyboard-operable.
- Replace generic `study-row` with consistent `RunListRow`: test name, target, execution mode, phase, next action. Derive action based on actual run state; status alone cannot promise report readiness.
- Proposed list grouping: Action required / Running / Finished / Drafts, but only if backed by real statuses. Preserve simple status filtering.
- Empty state: no tests vs no matching filters must differ. No unnecessary metrics cards.
- Preserve delete controls, role restrictions, and `canDeleteTest` on terminal runs. Never move a destructive action so it competes visually with “Open report”.

### 8.2 Create test — `pages/runs/NewRunPage.tsx` (**458 lines; highest form priority**)

A redesign must preserve the existing complex safety and configuration contract. **Do not remove fields merely because they are hard to style.**

**Proposed form sequence:**

1. **Goal:** “What should a user be able to do?” with a concrete sample, test name optional/clearly labeled.
2. **Environment:** select only authorized targets returned by existing `getAuthorization` checks; if none, present a target authorization recovery path.
3. **Execution method:** plain language split between `Feature cases` (planned deterministic browser checks) and `Simulated journeys` (agent-guided persona flow). Keep existing backend mode values unchanged.
4. **Depth:** disclose that deeper modes can create more work and runtime. Explain current 3-persona cross-product limits accurately; no invented time/cost prediction.
5. **Optional context:** approved knowledge sets (actual attached/app-scoped and approved-only sets).
6. **Safety:** authentication verification, `runtimeHumanAssistance`, sensitive action approval, fixture approval and their actual constraints. **Must remain inspectable before draft creation**, not hidden in an unfindable settings drawer.
7. **Scope receipt:** show chosen target, approved origins, auth-only origins, relevant action safeguards, execution mode and depth before create.
8. Submit creates **draft**, then route to `/runs/:runId/overview`. Do not change this to immediate execution without a deliberate product/backend decision; Start is a separate action in `RunLayout`.

**Responsive:** main form with small supporting guidance rail on desktop; single column on mobile; no multi-page wizard unless back/forward preserves values and backend state properly. Collapsible advanced sections only for truly optional configuration.

**States/tests:** zero authorized targets, expired authorization, knowledge none, non-writer, invalid goal, conflicting auth verification settings, sensitive-approval enabled/disabled, fixture mode, network errors, duplicate-click guard, preserving entered values on submission error.

### 8.3 Shared Test layout — `layouts/RunLayout.tsx`

- Preserve fetching of run and results, five-second polling, `api.startRun` and draft lifecycle, redirect after Start to Live Execution.
- Title hierarchy: test name → target and mode → phase; one relevant CTA Start, Assist, Watch, or Review. Avoid showing a completed test as definitely “passed”.
- Tabs remain routable and accessible. Counts must describe **all findings** versus **verified findings** clearly; do not show raw count without label if mixed.
- Human-assistance banner should appear consistently when `awaiting_human`; send user to exact authorized assistance state.
- `HumanAssistanceHost` must remain one mounted source of lease truth across nested routes. Avoid creating a second controller in live view or a new sidebar.
- The right-side `RunFlowPanel` currently appears on most routes. Collapse it into `Advanced execution flow` or a side drawer, especially on report, findings and evidence detail where it competes with the inspector.
- Keep query scopes including user/workspace/run where needed, stale data labels, and prior result readiness semantics.

### 8.4 Test summary — `pages/runs/RunOverviewPage.tsx`

- First content: test question + **true current state**. For draft → “Start test”; running → “Watch execution”; awaiting human → “Continue test”; completed with results pending → “Evaluation in progress”; report ready → “Review verified results”.
- Existing lifecycle rail is useful; refine labels, never confuse `completed` run status with passed criteria.
- When results ready: lead with **verified product issues / unverified observations / execution problems** in separate groups, then coverage and top actionable record. The current `.slice(0,3)` top findings should **not** surface three near-identical timeouts before a meaningful product issue; first partition by classification.
- Move configuration snapshot and raw IDs to `Details`; retain copy ID and provenance.
- Fix status-specific copy: a run that has already completed should not show “Watch this test execute” as the default action; open historical journey or report instead.

### 8.5 Live Execution — `pages/runs/RunActivityPage.tsx`

- Preserve `api.getLiveExecution`, `api.getRunJourneys`, `api.listHumanActions`, pause/resume APIs, pagination cursor and existing polling.
- Use a **three-part workbench**: selected goal/tester on left (collapsible), actual authorized browser in center, recorded activity/selected step on right; mobile stacks browser → current action → timeline with a clear selector.
- Read-only observer must have no pointer affordances that imply input. Only the explicit protected human control viewer can send actions after lease.
- Show `Current task`, `Last persisted action`, `Waiting for human` and `Latest frame time` only from existing API data; no fabricated reasoning stream.
- Filter `All / Problems / Human assistance / Browser actions` and preserve existing selection after polling.
- When selected journey is historical, show its **saved steps/evidence** rather than another journey's live browser. After run closure, never imply a live session continues.
- Pause copy: `Requested → Waiting for safe boundary → Paused → Resume requested → Verifying continuation`; never claim instant interrupt or replay.
- Remove outdated line “Recorded session in next version” from base (already removed in draft PR #5). Preserve observer error/retry UI and policy gating.
- Test strict tenant/role/bound-generation behavior, missing frames, navigation while lease active, polling out-of-order and offline worker.

### 8.6 Read-only browser — `pages/runs/LiveBrowserObserver.tsx`

- This is an actual frame consumer, not a fake iframe. Keep `getLiveBrowserFrame` with its identity and abort logic.
- Add visible `Read-only observation`, observed timestamp, `Frame unavailable`/`Session ended` and frame staleness; never auto-reuse another session's old frame.
- If user lacks viewer permission, show a role-specific explanation rather than a broken preview.
- `aria-label` for screenshot conveys browser state and timestamp without falsely narrating visual content. Keyboard focus must not jump on every frame refresh.

### 8.7 Human assistance and sensitive approvals — `pages/runs/HumanActionPage.tsx`

- This is **not** a simple style change. Preserve lease claim, renewal, reconnect, release, skip, pending action approvals and role checks.
- Present a distinct sober **Action required** area when the run needs a person. Explain *which journey*, *why*, and *what the person is allowed to do*; link to exact requesting step.
- Clearly differentiate: `Claim control`, `Control active`, `Reconnect`, `Done — return control to agent`, `Skip this journey`, `Approve/Reject a sensitive action`. Do not use “Resume” when only a pause request was sent.
- Use separate visual language for protected login input vs read-only observation. Privacy: never repeat credentials, input values, cookies or bearer URLs in logs, screenshots, browser history or help text.
- The existing `HumanAssistanceHost` manages active control between tabs; do not mount a second host inside an independent modal.
- On expired lease/release failure, show truthful recovery and avoid pretending control is still valid. Require an explicit confirmation before Skip where current flow semantics justify it.
- Test 403, 404, 409, 410, expired lease, mid-flight logout, tab switches, verification failure and keyboard Escape.

### 8.8 Interactive protected browser — `pages/runs/HumanBrowserViewer.tsx`

- Keep WebSocket tickets, input authority, canvas/browser state, and secure reconnect handling.
- Visually distinguish **Captured live frame** from a normal web browser chrome; show focus help (“Click inside to control; use Leave control to return keyboard focus”).
- Keyboard focus trapping/escape for assistance must not prevent navigation outside the component; provide clearly named Leave control.
- Do not add Back/Forward/Refresh/Cut/Copy/Paste/New tab controls unless corresponding safe worker actions exist **and are separately authorized**. A frontend button that calls `page.goBack()` by a new unguarded path is not acceptable.
- Respect narrow viewports, text input composition/IME, zoom and touch; never echo secret content in debugging UI.

### 8.9 Journey index — `pages/runs/RunJourneysPage.tsx`

- Make **testing goal** the first grouping, then the persona who attempted it. In feature-case mode, organize by planned case and preserve the special discovery stage; don't call deterministic execution a simulated tester.
- Row shows execution status independently from outcome. For timeouts, show last saved activity if the API provides it; otherwise link “Inspect recorded steps”.
- Success criteria in nested disclosure with verified/unverified state; no generic stacked raw payload dictionary on first view.
- Preserve `api.getRunJourneys`, collection endpoint and all route links. Make step/evidence link the primary affordance.
- Tests: 9 journeys from Klaviyo sample; 3 inconclusive/5 timed out/1 policy-blocked; feature case mode; missing collection; late evaluation.

### 8.10 Journey detail — `pages/runs/JourneyDetailPage.tsx`

- Preserve **real** current pattern: paginated ordered steps, selected step, signed artifact viewer, linked findings.
- Make a clear three-part path: `Steps` list → selected `Browser evidence` → `Criterion and verification` (inspector or drawer). On compact screens, step selector above focused evidence.
- Use `?step=` (already referenced from Human Action links) to initialize selected step when valid; ensure pagination loads the relevant page, not merely first page.
- A failed step can have a screenshot, but an absent cited criterion must remain unverified. Show “Recorded step exists; not linked to a verified claim” when truthful.
- Preserve exact `execution_id`/attempt fencing and stale-attempt warning; no old attempt artifacts displayed for new attempt.
- Keyboard arrow semantics only if implemented accessibly; otherwise plain buttons/ordered list with correct `aria-pressed`.
- Test large step counts, truncation, missing screenshot, signed URL expiry, selected historical artifact, bad query step, rapid selection.

### 8.11 Findings overview — `pages/runs/RunFindingsPage.tsx`

**Current:** already has classified group sections with selected finding inspector. Preserve the core behavior; do not replace with report prose.

- Primary groups: **Verified product issues**, **Needs verification**, **Test execution problems**. Retain per-finding provenance, severity and real links.
- In the list, show severity only for product findings where it is meaningful; diagnostic severity is an internal operational priority, **not** a Klaviyo defect severity.
- Avoid near-duplicate unverified observations; present group count with expandable affected journeys but preserve every finding link and database record.
- Inspector shows supported short summary, criterion (if persisted), exact cited steps/artifacts, next action. If evidence missing, state which evidence is missing—not “no issues”.
- Optional URL query `?finding=` may help deep links, but only add if it doesn't change existing route identity.
- Tests: no findings, only diagnostics, only unverified, mix verified/unverified/diagnostics, missing evidence, long titles, read-only tenant.

### 8.12 Finding detail — `pages/runs/FindingDetailPage.tsx`

- A structured **issue record**: finding claim → verification classification → affected journeys → evidence preview → recommended next step.
- Expected versus observed requires **actual persisted criterion/assertion data**. If unavailable, use “Claim / Recorded observation / Verification limitations”; never infer an expected value from model text.
- Existing `ArtifactEvidence` must remain tenant/run scoped through the API; preserved links to journeys and signed image view.
- Make relevant screenshot caption and step metadata visible; on source expiry, show “Refresh artifact access”, not image from a different step.
- For non-product diagnostic, use a different document template: “Why this test couldn't complete” and recovery, not a red critical product bug report.

### 8.13 Evidence browser — `pages/runs/RunEvidencePage.tsx`

- Preserve existing journey selection and bounded metadata query. Add a compact filter or rail for journey, step and artifact type **only from existing response fields**.
- Users must see the connection `journey → step → artifact → finding` where supported.
- Respect `artifacts_truncated` and `next_after_step` flags; don't silently pretend the first page contains the entire evidence history. When pagination is not implemented, deep link to the journey detail that can show more.
- No screenshot carousel that mixes different journeys without clear identity. No publicly accessible presigned URL leaking in persistent markup or logs.

### 8.14 Evidence detail — `pages/runs/EvidenceDetailPage.tsx`

- **Not an empty placeholder.** Its `ArtifactEvidence` component already handles signed access.
- Surround it with a properly labeled evidence viewer: origin journey/step (only when retrievable), type, status, accessible image, download/open only with authenticated API grant.
- Replace generic “Back to evaluation” with contextual back to the evidence index and source step when available; preserve working evaluation back-link if necessary.
- Test missing/expired/foreign-tenant artifact, unsupported preview type, long captions and image containment on mobile.

### 8.15 Report — `pages/runs/RunReportPage.tsx`

**Pilot exists in draft PR #5; review and test it before making another implementation.** This source file on the base branch prints a generic summary and every finding, including five near-identical timeouts. The pilot introduces an evidence-first report with grouped diagnostics.

**Required structure:**

1. Verdict: **No verified product defects; coverage incomplete** (for the supplied Klaviyo fixture) — never “Passed”.
2. Justified figures: verified issues, normal execution completed/total, diagnostics; **count only what actual run data supports**.
3. Verified product problems, with exact evidence and actionable next step.
4. Unverified observations (pricing clarity, repeated controls, etc.) clearly labeled not confirmed.
5. Test reliability: grouped timeout / policy issues with individual original links preserved.
6. Coverage: what was attempted, completed, blocked, not established. Distinguish completion denominator and outcome denominator.
7. Assessment: model status completed/unavailable with truthful explanation; do not make generic model failure the main business conclusion.
8. Provenance: report ID, source run, mode, bounded scope, generated timestamp and limitations. Raw original summary available in a disclosure.

**Review draft PR #5 specifically for:** classification rules; regrouping of severity from `isConfirmedFinding`; contrast of the scoped light surface; long text; report `FeatureCases` mode; 0/0 division; dynamic `dateTime`; accessible `<details>` and copied summary; no duplicate `<h2>`; no fabricated evidence links; evaluator absence; React 19/TypeScript compile; responsive snapshots.

**Related files:** `lib/results.ts`, `components/markettwin/RunAssessmentView.tsx`, `FeatureCases.tsx`, `CopyButton.tsx`, `styles/evidence-ledger.css` (draft PR only), `styles/workspace.css`, `services/evaluation-worker/.../report_generator.py` (only when changing report payload, *not* for styling).

### 8.16 Evaluation — `pages/runs/RunEvaluationPage.tsx`

- Move technical model/runtime metadata behind an Advanced disclosure. Primary table: criterion → verification result → rationale → original reported result → linked screenshot(s)/steps.
- When the assessment model is unavailable, retain saved deterministic/visual checks; show “Narrative assessment unavailable” as one graceful state.
- Do not display generated model narrative as equal authority to observed evidence. Show verified status and evidence completeness prominently.
- Current `evaluation_records` and `evaluation-agents` endpoint are actual sources. If records absent, say no detailed visual checks were saved, not “all criteria passed”.

### 8.17 Simulated testers — `pages/runs/RunPerspectivesPage.tsx`

- Already functional: fetches journeys, groups by persona name, shows missions and execution/outcomes.
- Present each simulated tester as a *hypothetical testing perspective*, not real customer profile. Avatar/illustration unnecessary unless meaningfully explanatory.
- Keep project-specific context and link to the journey; express what perspective adds to the test instead of repeating generic metadata.
- In `deep_feature_v1`, preserve honest “Feature cases do not use simulated testers” state; link to cases.

### 8.18 Testing goals — `pages/runs/RunMissionsPage.tsx`

- Already functional: groups by mission and displays success criteria. Make it a compact **coverage matrix**, with each goal and its attempted testers, execution states, verified outcomes where backed.
- Keep criteria as actual planned text; do not magically mark them satisfied without evidence.
- Deep feature mode does not use persona missions; preserve correct alternative link to feature cases.

### 8.19 Agent settings and run inspector — `pages/runs/AgentPromptsPage.tsx`, `components/markettwin/ProjectAgentBrowser.tsx`, `AgentTree.tsx`

- `/agents` is the global advanced entry and `/runs/:runId/agents` is scoped to one run. Keep both URLs, but differentiate page headings and active selection.
- Default shows **simulated tester → goal → actual attempts/results**. Advanced section exposes model/YAML configuration, recorded runtime snapshots and prompt edits as currently allowed.
- Agent stage chart is technical context, not proof that each agent performed meaningful browser actions. Use actual snapshots and status rather than an animated “agent working” theater.
- Avoid editable-looking controls when prompt rerun contract is read-only or not available. Preserve validation and safety limits on YAML/model settings.

---

## 9. Page-by-page implementation instructions: settings, errors and global states

### 9.1 Settings layout — `layouts/SettingsLayout.tsx`

- Keep Profile / Workspace / Members / Security route paths. No duplicate global menu or unnecessary fixed sidebar.
- Plain text explanations for editable vs read-only and role limitations; current `PageHeader` description can be concise.
- On narrow screens use accessible horizontal scroll or a select/list; nav does not trap focus.

### 9.2 Profile — `pages/settings/ProfileSettingsPage.tsx`

- **Current read-only** name, email and user ID. Default shows name/email; hide user ID under technical details/copy-on-demand. Do not add Save or Profile Photo editing without API.

### 9.3 Workspace — `pages/settings/WorkspaceSettingsPage.tsx`

- **Current read-only** workspace name/status/role/ID. Present role in user-facing language. Workspace edit/delete remains unavailable; explain why only once, without visually presenting an editable form.

### 9.4 Members — `pages/settings/MembersSettingsPage.tsx`

- Explicit future stage. Design a clean unavailable-state description; **no functional Invite member table/button** without membership management APIs. If business prioritizes this, create a separately reviewed backend feature PR; not part of cosmetic rollout.

### 9.5 Security — `pages/settings/SecuritySettingsPage.tsx`

- Explicit future stage. Do not show password/SSO/MFA/session revocation toggles that do nothing. It may link to the real Target Authorization/Network Scope features as navigational information, but must not misrepresent those as account-level security settings.

### 9.6 Access denied — `pages/system/ForbiddenPage.tsx`

- Remove raw role jargon where possible; say resource access is restricted; return to Overview. Do not reveal hidden tenant names/IDs or attempt to call forbidden APIs to build suggestions.

### 9.7 Not found — `pages/system/NotFoundPage.tsx`

- Neutral “Page unavailable” rather than scary 404. Keep safe return. Don't distinguish forbidden foreign-tenant resources from nonexistent resources unless backend policy explicitly permits it.

### 9.8 Unexpected error — `pages/system/UnexpectedErrorPage.tsx`

- Contextual retry only if existing retry action is available; otherwise safe home link. Error page must not erase historical evidence or claim an async job failed unless backend says so.

### 9.9 Shared state matrix (all screens)

| State | User sees | Must not happen | Suggested implementation |
|---|---|---|---|
| Initial loading | Explicit context: Loading tests / Loading source | Fake result skeleton copy or false success | `StateViews.LoadingPanel`, `aria-busy` |
| Partial stale data | Existing content + “Refresh failed; showing prior values” | Silent stale state represented as live | React Query `isError` with retained `data` |
| Empty workspace | Add application or role explanation | “All tests passed” with zero tests | `EmptyState` + permission helper |
| Empty filtered list | Clear filters | Global create CTA replacing clear option | Query-aware empty pattern |
| Validation error | Field-level message and focus | Clearing form, vague error | Existing form state, `aria-describedby` |
| Forbidden | Lack of permission, safe navigation | Decorative disabled CTA implying later success | API-enforced permission, roles for rendering |
| Pending source | Durable entry ID + actual stage | 20/50% invented completion | `IngestionProgress` + polling |
| Source failed | Safe reason + retry when supported | Approval enabled | Backend exact state guard |
| Run queued | Queued, waiting for dispatch | “Browser is testing now” | `TestRun.status` |
| Run executing | Current approved browser + events if available | Fake browser video, fabricated agent thought | `LiveBrowserObserver` |
| Run awaiting human | Why + scoped handoff action | Duplicate controllers, unconditional Resume | `HumanActionPage` |
| Run completed; evaluator pending | “Execution finished; report pending” | “Passed” or empty completed report | `RunLayout.ResultsState` |
| Journey timed out | Last persisted action/step if present | Product defect classification | Journey detail + evaluator model |
| Browser policy blocked | Exact denied origin in safe diagnostic + request review | Auto-add denied origin | Target Scope route |
| Finding unverified | Observation and missing evidence | Critical verified issue badge | `findingClassification` |
| Evidence unavailable | Explicit missing artifact or citation | Another journey's image | `ArtifactEvidence` and scope checks |
| Long list / small screen | Controlled scroll/stack/pagination | Horizontal page overflow, clipped actions | `min-width:0`, wrap, responsive tables |

---
## 10. CSS and frontend architecture: exact files to modify

The current CSS entrypoint is `apps/web/src/styles.css` and currently imports, in order:

```css
@import "tailwindcss";
@import "./styles/tokens.css";
@import "./styles/legacy.css";
@import "./styles/base.css";
@import "./styles/workspace.css";
@import "./styles/signin.css";
@import "./styles/enterprise.css";
@import "./styles/agent-prompts.css";
@import "./styles/run-records.css";
@import "./styles/flow.css";
@import "./styles/public.css";
@import "./styles/journeys.css";
@import "./styles/product-theme.css";
@import "./styles/live-execution.css";
```

Draft PR #5 adds an import for `./styles/evidence-ledger.css` **after** these, and creates that stylesheet. The following instructions must respect cascading specificity and avoid a second inconsistent parallel design system.

| File | Existing responsibility | Concrete change | Regression risk |
|---|---|---|---|
| `styles/tokens.css` | Root palette, size, semantic aliases | Define documented light/dark semantic map **after** pilots; avoid immediate breaking `--page` / `--surface` | High: entire app |
| `styles/base.css` | Body, headings, forms, focus, global elements | Refine type scale, table overflow, focus tokens; preserve `:focus-visible` and skip-to-content | High: entire app |
| `styles/legacy.css` | Broad legacy forms/panels/badges/navigation | Inventory every selector; gradually replace duplicated tokens, never delete based on filename | High |
| `styles/workspace.css` | Workspace lists, runs, reports and application views | Split by page domain **only when useful**, normalize reading widths, compact rows and responsive details | High |
| `styles/enterprise.css` | App shell / enterprise layout | Refactor sidebar, topbar, drawer and breakpoints; preserve role/route behavior | High |
| `styles/product-theme.css` | Targeted product overrides | Remove obsolete specificity overrides after migration; use semantic variables | Medium |
| `styles/flow.css` | Agent/run flow rendering | Tighten technical inspector and make flow secondary | Medium |
| `styles/run-records.css` | Journeys, report assessment, HITL groups, finding inspector | Align actual step rows, evidence and contextual action surfaces | High |
| `styles/journeys.css` | Journey step/evidence panes | Responsive selector/screenshot/metadata, no clipped steps | High |
| `styles/live-execution.css` | Live workbench and browser stage | Responsive three-area layout, frame staleness, assistance alert and selected event | **Very high:** viewer and HITL |
| `styles/agent-prompts.css` | Advanced agent configuration | Grouped prompt editor and readable snapshots without affecting tester list | Medium |
| `styles/signin.css` | Public-to-private sign-in | Identity-consistent typography, form focus/error | Medium |
| `styles/public.css` | Landing/how pages | Evidence Ledger public narrative; scope styles to public root | Medium |
| `styles/evidence-ledger.css` | **New in draft PR #5**, report-only scoped pilot | Verify, then extract accepted semantic patterns; do not blindly replicate classes per page | Medium |
| `styles.css` | Global import manifest | Keep intentional precedence; add scoped phase CSS only as needed | High if order changes |

### 10.1 Specific CSS cleanup rules

- Never create another `global.css` that overrides every old selector by appending hundreds of `!important` rules. Migrate ownership class by class after confirming route dependencies.
- Use BEM-like domain roots (`.mt-report-*`, `.mt-knowledge-*`, `.mt-live-*`) or CSS Modules according to existing conventions; avoid global `section`, `article`, `h2` rules for domain-specific compositions.
- Remove obsolete `FutureStagePage` styling only if the component has zero remaining consumers. It currently has multiple consumers.
- Before removing `.panel`, `.study-row`, `.data-row`, `.status-badge`, `.run-record` or `.tab-link`, search their JSX usages and tests. Several domains share them.
- Reuse `fontsource` dependencies already installed. Do not download web fonts at runtime as a hidden dependency; preserve font licensing and do not redistribute font files.
- For reported browser image/canvas, use `object-fit: contain`, preserved aspect ratio, and genuine resize handling—not cropping the element to fill a pretty frame.
- Use `color-scheme` deliberately; the base repo is currently `dark`. A scoped warm report can coexist while forms and global app migrate in stages.
- Avoid `position: sticky` on panels that would cover focus targets or contain stale session-action controls at small heights.
- Scope animations and honor `prefers-reduced-motion`. No long-lived transforms around screenshot canvas or form input controls.

### 10.2 Component contracts and coding conventions

- Prefer typed data from `apps/web/src/lib/api.ts`; don't introduce `any` JSON parse of a backend payload merely for layout.
- Normalize display vocabulary via one utility in `lib/format.ts` or `lib/results.ts`; **do not duplicate** classification calculations in each screen.
- `Finding` classification must use `finding_kind`, `verification_status` and necessary persisted evidence, not simple severity text.
- Data requests should use existing `@tanstack/react-query`, scoped by authenticated user/workspace/run, and support abort/cancellation where feasible.
- React Router `Link`, `NavLink`, `useSearchParams` and nested `Outlet` remain. Do not replace with raw `window.location.href` navigation or hide route paths behind a custom state machine.
- Do not add decorative fake search, export, download or “Resolve issue” buttons unless the product has an actual operation and outcome confirmation. If exporting is unsupported, don't visually advertise Export.
- Buttons that trigger network mutations must show pending, success/failure and retry after safe idempotency consideration. The backend remains the source of authority.
- Each reusable component gets a focused `*.test.tsx` if interaction or classification is nontrivial.

---

## 11. Backend and data dependencies — unblock UI truth before polishing

**These are deliberately not “UI-only” changes.** The redesign must not mask known execution/reliability bugs behind prettier presentation.

| Dependency | Existing source | Failure shown to user | Correct change and UI implications | Priority |
|---|---|---|---|---|
| Queue-first link ingestion | `services/control-api/.../api/ingestion.py`, `knowledge/processor.py`, repository, storage, link crawler and schema migration | Link error prevents Processing route; request blocks while crawling | Persist durable ID and queue before crawl; frontend navigates on 202; truthful processing stages | P0 |
| Approval-state guard | `api/ingestion.py`, `knowledge/repository.py` | Failed/invalid asset may reach approval path if checks incomplete | Server require exact reviewable state and nonempty valid preview; UI mirrors actual ability | P0 |
| Research provenance | `knowledge/link_research.py`, Knowledge Worker input | Flattened source text obscures page-level failures/fallbacks | Keep source citations, observed-vs-fallback distinction and processing limitations; only surface persisted data | P1 |
| Reliable agent evidence after timeout | `workflow/journey_executor.py`, `workflow/report_validation.py`, `evaluation-worker/deterministic_evaluator.py` | Diagnostic says evidence unavailable despite potentially saved steps | Link safe already-persisted steps to diagnostic separately from criterion-verified evidence; never infer pass | P0 |
| Repetitive persona coverage | `agents/meta_agent.py`, planner, multi-persona executor | 3 personas × every mission can generate repetitive 9+ journeys | Benchmark actual value; any change to planner cardinality is **separate backend/product change**, not a frontend redesign | P1 |
| Browser repeated-control strategy | `browser/actions.py`, observations/controller, agent prompts | Duplicate “What's included” locators lead to ambiguity and wasted runtime | Bounded safe scope disambiguation and recovery, no arbitrary unsafe selectors; UI can expose this as execution diagnostic | P0 testing quality |
| Real browser network enforcement | `browser/controller.py`, network policy | Preflight DNS validation may not equal actual browser connection IP | Independent security gate; do not expose broader scope controls until connection-level enforcement is validated | P0 security |
| Kafka/outbox readiness | `services/control-api/.../config.py`, outbox relay, worker | Queued tests may not actually dispatch if relay off | Clear operational “Dispatch unavailable” status only when API can prove it; no fake running indicator | P0 ops |
| Evaluation fallback | `services/evaluation-worker/.../run_assessment.py` | Model unavailable → generic message | Preserve deterministic records; structured safe reason codes if backend added, no raw prompts/secrets | P1 |
| Report schema and grouping | `report_generator.py`, `RunReportPage.tsx`, `lib/results.ts` | Repeated technical issues dominate findings | Frontend grouping first, keep original IDs; schema changes only if frontend lacks required truth | P0 |
| Future edit/member/security APIs | `EditApplicationPage`, `EditTargetPage`, `MembersSettingsPage`, `SecuritySettingsPage` | Route looks editable despite no backend | Do not fake; separately scope backend CRUD/auth/audit before UI activation | Later |

### 11.1 Example: data truth hierarchy for reports

```
Target + authorization snapshot (backend authoritative)
  └─ Test plan/mission criteria (persisted)
       └─ Run execution status (persisted)
            └─ Browser steps and artifacts (persisted)
                 └─ Agent-reported claims (untrusted until validated)
                      └─ Deterministic/visual verification and findings
                           └─ Customer-facing report
```

The interface must never collapse these layers. In particular:

- A browser click succeeding is **not** a satisfied test criterion.
- A timed-out agent is **not** a confirmed site defect.
- Three personas saying the same thing is **not** independent factual verification.
- A completed Run is **not** a passed Run.
- A screenshot is **not** evidence for an unrelated test step.
- An approved scope revision request is not the same as an **authorized** scope until the backend says so.

---

## 12. Incremental implementation: proposed PR sequence

**Do not attempt a single giant frontend rewrite.** Small phases prevent regressions and make the design review meaningful. Each phase should be its own PR, with screenshots, tests and a product-quality checklist.

### PR 0 — inspect and finish the existing report pilot

**Source:** [draft PR #5](https://github.com/Sreenav14/Market-Twin/pull/5) targeting `feat/batch-1-aws-observability`.

- [ ] Fetch current PR diff, HEAD and checks. Do not assume the base is unchanged.
- [ ] Review its four changed files: `RunReportPage.tsx`, `RunActivityPage.tsx`, `styles.css`, `styles/evidence-ledger.css`.
- [ ] Run frontend typecheck/unit/build. Add explicit tests for confirmed/unverified/diagnostic grouping and preserving all original finding links.
- [ ] Test legacy-persona and feature-case reports, zero findings, assessment unavailable, long strings and missing evidence.
- [ ] Visual test 320/390/768/1024/1440 and keyboard/zoom/contrast.
- [ ] Only merge after all checks; otherwise repair draft PR in its branch.

**Deliverable:** coherent evidence-first Report screen, not a global theme migration. **Do not create another duplicate report PR unless intentionally replacing #5.**

### PR 1 — shared design-system foundation

**Touch:** `styles/tokens.css` *document/introduce scoped aliases*, `styles/base.css` *minimal adjustments*, `components/ui/{PageHeader,button,input,textarea,StatusBadge,StateViews,BrandMark}.tsx` and tests, plus `docs/design/FOUNDATIONS.md` (new).

- [ ] Add tokens for type, spacing, border, surface and semantic state.
- [ ] Create typography, buttons, fields, status, table row, empty/error/loading and focus fixtures.
- [ ] Ensure no global restyle breaks existing pages; prefer scoped changes.
- [ ] No new npm dependency unless justified by a concrete interaction deficiency.

**Gate:** contrast checks, keyboard all components, reduced motion, visual snapshots of old main shell.

### PR 2 — app navigation, onboarding and overview

**Touch:** `layouts/AppShell.tsx`, `app/App.tsx` only if needed, `pages/overview/OverviewPage.tsx`, `components/markettwin/CommandMenu.tsx`, `styles/enterprise.css`, `styles/workspace.css`, existing tests.

- [ ] Information architecture default: Overview, Applications, Tests, Knowledge; redundant Add Knowledge becomes contextual.
- [ ] User/task-oriented breadcrumb labels and mobile drawer.
- [ ] Overview attention queue and status explanation.
- [ ] First-run path to Add application; preserve read-only roles and multi-workspace isolation.

**Gate:** 320px drawer, command menu keyboard, switch workspaces while polling, 403 and logout.

### PR 3 — applications and scope/security flow

**Touch:** all `pages/applications/*.tsx`, all `pages/targets/*.tsx`, common list/receipt components, application/target CSS, routing tests.

- [ ] Cohesive add-application → add-target → authorize-scope → create-test path.
- [ ] Target status receipt and exact origins, pending vs authorized.
- [ ] Keep Edit Application/Edit Target future states honest; don't add unsupported forms.
- [ ] Reuse real target auth/revoke and revision-request APIs only.

**Gate:** authorization/revocation role matrix, denied origin, pending revision, inactive/expired target, mobile forms.

### PR 4 — goal-first test composer

**Touch:** `pages/runs/NewRunPage.tsx`, `components/markettwin/ScopeReceipt.tsx` (new, if useful), `styles/run-records.css` and focused tests.

- [ ] Goal and test name first; target authorization clear; execution modes explained.
- [ ] Preserve all current knowledge, auth, sensitive-action, fixture and assistance settings.
- [ ] Scope receipt before creating draft, with explicit target and permission boundaries.
- [ ] No hidden irreversible decisions and no fabricated runtime/credit estimate.

**Gate:** existing `NewRunPage.test.tsx`, all depth/mode/auth permutations, unauthorized target, 409 errors.

### PR 5 — Test shell and truthful run summary

**Touch:** `layouts/RunLayout.tsx`, `pages/runs/RunOverviewPage.tsx`, `components/markettwin/RunFlowPanel.tsx`, `components/ui/LifecyclePanel.tsx` as used, `styles/flow.css` and tests.

- [ ] One next action based on run/report stage, not an always-green Completed label.
- [ ] Technical run flow collapsible/secondary.
- [ ] Result summary partitions verified, unverified and execution problems.
- [ ] Preserve existing polling and `HumanAssistanceHost`.

**Gate:** draft/start; Kafka relay off; queued/running/awaiting-human/completed/report pending/failed.

### PR 6 — Live browser and human control workbench

**Touch:** `pages/runs/{RunActivityPage,LiveBrowserObserver,HumanActionPage,HumanBrowserViewer}.tsx`, `styles/live-execution.css`, existing protected-viewer tests, possibly read-only helper components.

- [ ] Task → real browser → real event timeline and step detail.
- [ ] Frame timestamp, closed/stale/permission states, historical evidence links.
- [ ] Single exclusive HITL lease owner, safe pause/resume semantics and clear input authority.
- [ ] No duplicate WebSocket or opportunistic iframe; no invented toolbar methods.

**Gate:** authenticated browser session, expired lease, reconnect, logout while owning control, UI-only observer cannot send input, no stale frame cross-journey leakage.

### PR 7 — Journey investigation and evidence explorer

**Touch:** `pages/runs/{RunJourneysPage,JourneyDetailPage,RunEvidencePage,EvidenceDetailPage}.tsx`, `styles/journeys.css`, `styles/run-records.css`, tests.

- [ ] Goal-first journey list, actual mode distinctions.
- [ ] Selected step and its true artifact, deep linking and pagination.
- [ ] Missing evidence / stale attempt / signed artifact error states.

**Gate:** 0/1/500 steps, `?step=`, no artifacts, truncated page, stored screenshots at mobile widths, foreign-tenant access never exposed.

### PR 8 — Findings and evaluation reading surfaces

**Touch:** `pages/runs/{RunFindingsPage,FindingDetailPage,RunEvaluationPage}.tsx`, `components/markettwin/{FindingListItem,RunAssessmentView}.tsx`, `lib/results.ts` (as needed), tests.

- [ ] Group by verification state, not mixed severity; any repeated diagnostics remain drillable.
- [ ] Distinct layouts for product issue versus testing issue.
- [ ] Criterion/evidence table, graceful model assessment unavailable state.

**Gate:** mixed-classification fixtures; strict evidence provenance; no false confirmed severity.

### PR 9 — queue-first link ingestion **backend dependency**

**Touch:** `services/control-api/.../api/ingestion.py`, `knowledge/{processor,repository,link_research,storage}.py`, DB models/migration, backend tests; then `pages/knowledge/IngestionPage.tsx` integration after new contract.

- [ ] 202 + durable ID before crawl; no request held open for link research.
- [ ] Background worker crashes/retries are durable; safe SSRF restrictions preserved.
- [ ] `needs_user_review` exact approval guard, no auto-approval.

**Gate:** direct Klaviyo URL request returns a processing record even when crawler later fails; verified background transitions and concurrency; file upload unaffected.

### PR 10 — knowledge UX + truthful processing

**Touch:** all `pages/knowledge/*.tsx`, domain CSS, tests.

- [ ] No fake percentages; real queued/researching/generating/ready/failed stages if backend provides them.
- [ ] Review and approve with original source references; attach only approved sets.
- [ ] Error/retry and permissions all explicit; support source signing failures.

**Gate:** link and file source variants, processing restart, failed retry, workspace changes, approval after stale data rejected by server.

### PR 11 — public story and sign-in

**Touch:** `pages/public/PublicPages.tsx`, `pages/auth/{LoginPage,AuthCallbackPage}.tsx`, `styles/public.css`, `styles/signin.css`, brand asset components, tests.

- [ ] Reuse one visual identity; interactive sample clearly marked illustrative.
- [ ] No empty marketing slogans, fake KPIs/clients, unsupported SSO.
- [ ] Accessible mobile story and form; real login feedback.

**Gate:** anonymous/public routing, focus order, no misleading calls to action, 5xx sign-in service message.

### PR 12 — secondary screens and system states

**Touch:** `pages/runs/{RunPerspectivesPage,RunMissionsPage,AgentPromptsPage}.tsx`, `ProjectAgentBrowser.tsx`, `AgentTree.tsx`, `layouts/SettingsLayout.tsx`, all settings/system pages and respective CSS/tests.

- [ ] Tester and goal views remain functional, mode-specific.
- [ ] Agent prompt diagnostics default collapsed, correct scope.
- [ ] Profile/workspace read-only; unsupported member/security/edit states clearly unavailable.
- [ ] 403/404/error design language unified without leaking foreign resources.

**Gate:** every original route still resolves, no fabricated settings, keyboard and role checks.

### PR 13 — cross-page visual & end-to-end verification

- [ ] Automated screenshot matrix and visual diff baseline for **every route family**, including happy, empty, error and permission states.
- [ ] Cypress or Playwright? **Use already installed Playwright**, not another browser automation framework.
- [ ] Automated axe checks plus **manual** keyboard/screen-reader and reduced-motion review.
- [ ] Full browser workflow smoke across app → target → authorization → test → activity → evidence → report and source → processing → approval.
- [ ] Reconcile duplicate CSS and unused components by verified search, then safely delete only demonstrated dead code.

---

## 13. Test strategy — hard release gates instead of assuming visual quality

### 13.1 Existing frontend commands (verified from `apps/web/package.json`)

```bash
cd apps/web
npm ci
npm run typecheck
npm run test
npm run build
npm run test:e2e
```

Run with the same package manager/lockfile used by the checkout. `test:e2e` needs the app/test fixture services configured for the chosen Playwright project; do not interpret failure to start services as a UI test failure. Backend changes must run the corresponding `uv`/Python lint, type checks and pytest suites configured in the repo; do not assume all database integration tests run by default (some are opt-in).

### 13.2 Viewport matrix

| Width | Main focus |
|---|---|
| 320 px | Minimum narrow content, no page-wide overflow, safe H/Back/Run controls |
| 390 px | Common mobile; login, test create, status, knowledge and report |
| 768 px | Tablet; navigation and inspector transitions |
| 1024 px | Laptop; workbench panel distribution and readable tables |
| 1280 px | Desktop; content width, hierarchy, no orphan sidebar |
| 1440 px | Large desktop; white space and stable reading width |
| 1920 px | Wide screen; no giant line lengths or huge empty cards |

Screen height matters too: include short-height laptop (e.g. 768px height), browser zoom at 200%, and viewport change during an active HITL session. Capture screenshots at first load, after data load and with expanded panels, not only pristine static pages.

### 13.3 State fixtures (must be executable test data, not invented product metrics)

Create test mocks or seeded local fixture records for:

| Fixture | Expected UI |
|---|---|
| Empty workspace | One appropriate Add application action or role-aware explanation |
| App created, no targets | Add environment, not Test now |
| Target pending authorization | Requires authorized review, no implicit allow |
| Target authorized with one origin | Scope receipt, create test enabled for writer |
| Target revision pending | New origin shown pending, blocked site still blocked |
| Knowledge document uploading | Durable queued/processing stage without fake percent |
| Link ingestion network failure | Processing entry still visible post-202 after backend fix, failed state + retry |
| Source ready for review | Source grounding, explicit checkbox and approval |
| Test draft | Start separate from draft creation |
| Test queued but dispatcher unhealthy | Distinguish saved job from browser running if status data proves it |
| Run awaiting human | Appropriate lease-control CTA and permissions |
| Run with read-only browser | Observer frame only, no input |
| Run with selected historical journey | Saved evidence, never another current live frame |
| Run results pending | Evaluation pending, not passed |
| Klaviyo example | 9 journeys: 3 inconclusive, 5 timed out, 1 policy blocked, 0 verified; no false pass |
| Verified assertion issue | Evidence-linked product issue and accurate source references |
| Evidence missing | Explicit unavailable state; no substituted artifact |
| Model assessment unavailable | Deterministic checks still visible |
| Workspace viewer role | No create/approve/lease controls beyond existing policy |
| Cross-workspace IDs | Unauthorized/nonexistent handling, no data leakage |
| 100+ rows / long name/URL | Density, truncation with accessible full context, stable layout |

### 13.4 Accessibility audit checklist (WCAG 2.2 AA target)

- [ ] Visible keyboard focus for buttons, text links, form controls, step rows and disclosures.
- [ ] Functional skip link and meaningful heading structure; one clear page H1/title context.
- [ ] Labels and `aria-describedby` for errors; submit errors announced and focus directed appropriately.
- [ ] Text contrast >= 4.5:1 (ordinary); meaningful UI contrast >= 3:1; status never color-only.
- [ ] Keyboard operable tabs, select, dialogs, resizable panels if added, browser viewer exit.
- [ ] No keyboard trap in human-browser interaction or mobile drawer; focus restore on dismiss.
- [ ] Reduced motion works with animations disabled and functionality intact.
- [ ] 200% zoom; 320 CSS-pixel reflow and no reliance on horizontal document scrolling.
- [ ] Touch targets meet WCAG 2.2 AA size/spacing criteria and sensible larger target for primary actions.
- [ ] Screen reader receives state changes without a live-event announcement storm.
- [ ] Screenshot accessible name and “not available” fallback are accurate (do not hallucinate screenshot contents in alt text).
- [ ] Tabs and expanded sections announce selected/expanded state; hidden content not focusable.

### 13.5 Permissions and security regression checklist

- [ ] Viewer cannot create/edit/delete/approve/authorize or claim browser lease through a styled control.
- [ ] Admin/owner scope mutation still enforces backend origin/CSRF/authorization checks.
- [ ] Network scope revision request cannot silently become approved.
- [ ] Human viewer tickets, session IDs, auth cookies and typed credentials are never pasted into analytics, logs, copy-to-clipboard success messages or permanent screenshot descriptions.
- [ ] Actual `LiveBrowserObserver` remains read-only; the interactive `HumanBrowserViewer` requires valid control.
- [ ] Signed S3 artifact access remains short-lived and run/workspace scoped.
- [ ] Source/knowledge approval remains explicit; no default checked consent.
- [ ] Data from previous workspaces/runs is cleared when context changes.
- [ ] Report never calls a diagnostic a verified app defect simply because its severity is high.

---

## 14. Screen-by-screen quality acceptance matrix

This is the tracking grid for design reviews. Each row should receive a screenshot or short recording for the relevant scenarios before sign-off.

| Screen / route family | User's first answer | One primary action | Required failure or edge case | Reviewer sign-off |
|---|---|---|---|---|
| Public `/` | What MarketTwin does, correctly | Log in | Demo labeled illustration | [ ] |
| Public `/how-it-works` | How goal → evidence works | Open workspace | Caveats readable | [ ] |
| Login | How to access current workspace | Sign in | Unapproved identity / 5xx | [ ] |
| Auth callback | Supported or unsupported auth state | Back/log in where relevant | No fake SSO | [ ] |
| Overview | What needs attention | Assist/watch/review or add app | Empty workspace + stale refresh | [ ] |
| Applications list | Which applications exist | Open or add app | No results / role reader | [ ] |
| Add application | What is being created | Create | Validation + redirect | [ ] |
| Application overview | Target ready? What next? | Authorize or create test | No target or runs | [ ] |
| Edit application | Backend unavailable | Back | No fake save | [ ] |
| Application runs | Which tests belong here | Open test | Empty / failed API | [ ] |
| Target list | Which environments are approved | Open/add target | Revoked/inactive | [ ] |
| Add target | Authorization is separate | Create target | Bad URL / no permission | [ ] |
| Target overview | Exact current scope | Authorize/view scope | Expired or denied | [ ] |
| Authorization | What is being approved | Authorize/revoke | Role/confirmation races | [ ] |
| Network policy | Which origins are allowed | Request revision | Pending != authorized | [ ] |
| Edit target | Changing URL not supported | Back/review scope | No fake editing | [ ] |
| Ingestion form | Which source will be researched | Save source | Link crawl later fails | [ ] |
| Knowledge library | Which sources need review | Review/add source | Filters and long names | [ ] |
| Knowledge detail | Evidence, draft and decision | Approve/retry/attach | Missing source, failed processing | [ ] |
| Tests list | Current statuses and next tasks | Open/create test | Filter zero, role reader | [ ] |
| New test | Goal, target, safety | Create draft | No authorization, 409 | [ ] |
| Run shell | Test/target/current phase | Start/assist/review | Results pending | [ ] |
| Run summary | What happened at this stage | Relevant next action | Completed ≠ passed | [ ] |
| Live execution | Which actual browser is active | Observe/assist as allowed | Stale/no frame | [ ] |
| Protected viewer | Who controls browser | Explicit done/skip | Lease expire/reconnect | [ ] |
| Journeys index | Which goals were attempted | Inspect steps | Feature/persona distinctions | [ ] |
| Journey detail | What exactly happened at a step | Inspect screenshot/evidence | Missing/stale/truncated | [ ] |
| Findings index | Which issues are verified | Inspect finding | 5 similar timeouts | [ ] |
| Finding detail | Claim and exact supporting evidence | Inspect step | Missing artifact | [ ] |
| Evidence index | How artifacts map to steps | Open artifact | Truncated list | [ ] |
| Evidence detail | Artifact and permitted context | Back to source | Expired/foreign artifact | [ ] |
| Report | Trustworthy conclusion | Inspect priority issue | 9-journey Klaviyo fixture | [ ] |
| Evaluation | How criteria were checked | Inspect linked result | Model unavailable | [ ] |
| Goals | What missions were planned | Inspect affected journey | Deep mode fallback | [ ] |
| Testers | Who simulated each task | Inspect journey | Not human research | [ ] |
| Agent settings | Actual agents vs advanced config | Open run/advanced | Invalid YAML/read-only | [ ] |
| Profile | Current identity | None if read-only | Long email | [ ] |
| Workspace settings | Current role | None if read-only | No edit API | [ ] |
| Members settings | Not yet supported | Back | No fake invites | [ ] |
| Security settings | Not yet supported | Back | No fake MFA/SSO | [ ] |
| 403 | Why access is denied | Go to overview | No tenant info leak | [ ] |
| 404 | Resource unavailable | Go to overview | Foreign resource ambiguous | [ ] |
| Error | Recovery path | Safe navigation/retry | No phantom success | [ ] |

---

## 15. Common missteps to explicitly prohibit

1. **Do not create a “beautiful version” alongside the actual application** and call it implemented if it has disconnected demo buttons and fake test data.
2. **Do not switch all root CSS tokens in a single commit.** The current app has a dark baseline and many shared selectors.
3. **Do not use one repeated card component for every screen.** Reports read like editorial documents; runs like operations lists; browser inspection like a split workbench; security decisions like approval receipts.
4. **Do not turn server truth into animation.** A 50% progress bar based on `status === 'processing'` is not progress measurement.
5. **Do not convert “0 verified defects” into a successful product test.** The Klaviyo fixture demonstrates why.
6. **Do not use AI-agent portraits, fake reasoning streams, synthetic customer quotes or fictional organizations.** Personas are not actual research participants.
7. **Do not replace actual browser evidence with a prettier image or generic screenshot.** Frame/step/tenant identity must match.
8. **Do not remove exact origin safety policies, authorization confirmations, lease fencing or sensitive-action checks.** These are defining protections.
9. **Do not hide unsupported backend features behind form fields.** App edit, target edit, members and security settings remain unsupported in the inspected branch.
10. **Do not treat a generated Playwright/Vitest pass as a complete design audit.** Inspect actual rendered pages, keyboard focus, difficult data and user comprehension.
11. **Do not add libraries only because the reference galleries look appealing.** If a Bencho/EasyUI component is used, audit its keyboard/ARIA, performance and maintenance impact.
12. **Do not delete a page purely to reduce navigation count.** Reduce cognitive burden through regrouping; preserve existing URLs and stored references.
13. **Do not advertise “real-time” when the screen is polling snapshots.** Use actual freshness and timestamps.
14. **Do not generalize permissions by workspace role alone** if the backend also requires target/run authority and lease identity.
15. **Do not conflate application defects with MarketTwin execution defects** in severity dashboards or report narratives.

---

## 16. Suggested working procedure for the next coding agent/developer

Follow this contract on **every PR**:

1. Inspect `git status`, current branch/HEAD and existing PRs. Do not reset, overwrite or cherry-pick blindly.
2. Read the target page, its parent layout, shared components, route, API type, existing tests, and CSS selectors before editing.
3. Write a one-paragraph **source-truth contract** for the page: available real data, permission model, mutations, backend limitations and failure states.
4. Build the UI with typed existing data; use a new reusable component only after checking for a suitable existing one.
5. Keep **one primary action** visually obvious while preserving all security-critical controls.
6. Run typecheck/unit/build. For backend-touching changes, run backend tests and any opt-in integration fixture available.
7. Start the actual app with representative local fixture data and capture desktop/mobile screenshots. Visually inspect contrast, density, row wrapping, scroll, hover, focus and errors.
8. Run one keyboard-only pass and an automated accessibility scan; repair failures.
9. Verify every old link and permission state relevant to the changed surface.
10. Update documentation and PR description with before/after images, known limitations, exact files touched and tests run. If untested, say **untested**.
11. Only then move to the next PR; avoid expanding scope to unrelated backend architecture unless required for truthful UX.

### Per-PR description template

```markdown
## User problem
Describe what users could not understand or complete.

## Files changed
List exact paths and why each changed.

## Existing behavior preserved
List API routes, authorization, HITL and evidence contracts retained.

## New behavior
Give UI states and exact labels for happy, empty, pending, error and role-limited cases.

## Source-backed changes
Separate directly implemented UI from backend prerequisites or recommendations.

## Verification
- TypeScript: [command + pass/fail]
- Unit: [command + pass/fail]
- Browser: [viewports + screenshots + pass/fail]
- Accessibility: [automated/manual + findings]
- Security/roles: [matrix + pass/fail]

## Known limitations
Explicit list. No production-ready assertion until verified.
```

---

## 17. Definition of Done for the *whole* MarketTwin redesign

The project should **not** be called finished until the following are true:

- [ ] All existing routes in Section 2 were reviewed; active pages use one cohesive Evidence Ledger design language, and intentionally unsupported pages communicate that clearly.
- [ ] A first-time authorized user can navigate: create app → create/authorize target → create draft test → start → observe → review findings/evidence/report **without developer help** in controlled usability testing.
- [ ] Knowledge ingestion supports durable processing identity on public-link errors after the backend lifecycle fix; status copy is factual.
- [ ] Human control still works under a single exact authorized lease; no input path is added to read-only observation.
- [ ] Actual criterion verification and evidence provenance remain intact; report language never converts an unsupported claim into a confirmed product defect.
- [ ] Every route has documented loading, empty, failure, permission, mobile and long-data behavior.
- [ ] Visual review at 320/390/768/1024/1440/1920 and 200% zoom was performed on **the real integrated React app**.
- [ ] TypeScript, unit, build and relevant Playwright tests pass; backend tests pass where affected, including the opt-in database/browser suites needed for correctness.
- [ ] WCAG 2.2 AA issues identified by automation **and manual review** are addressed.
- [ ] CSS is maintainable: shared tokens, isolated component responsibilities, no uncontrolled specificity layering.
- [ ] Every interactive control is real and backed by documented user intent/API action.
- [ ] Key UX concepts are understood by representative QA, developer and product participants. Test the ability to distinguish incomplete run, product defect, unverified observation and authorization block.
- [ ] No invented integrations, savings, benchmarks, testimonials, metrics, result content or feature capability.

### Suggested comprehension task for design testing

Give participants the **labeled** Klaviyo example run (9 planned journeys; 3 completed inconclusive; 5 timed out; 1 origin blocked; zero verified issues; model assessment unavailable). Ask them, without coaching:

1. “Did Klaviyo pass MarketTwin's test?” Correct: **No overall passing outcome was established**.
2. “Did MarketTwin find a verified Klaviyo defect?” Correct: **No**.
3. “What should happen next?” Correct: **Investigate execution and evidence problems; request authorization only if legitimately permitted; rerun focused checks**.
4. “Find the evidence for the pricing observation.” Correct: open the relevant journey/step evidence; if none is cited, explicitly recognize **unverified**.
5. “What is the difference between Live Execution and Human Assistance?” Correct: passive observation versus strictly authorized exclusive control.

The redesigned interface should make these answers discoverable without reading a long manual.

---

## 18. Reference and handoff links

- Existing design/research plan in this conversation: `MARKETTWIN_PRODUCT_REDESIGN_RESEARCH_AND_IMPLEMENTATION_SPEC_2026-10-18.md` (research, prior mockup and design tokens). Treat it as creative background, not evidence that React integration works.
- Existing repository audit in this conversation: `MARKETTWIN_REPOSITORY_AUDIT_2026-10-18.md` (broader technical risks; not full-runtime certification).
- Existing interactive prototype in this conversation: `markettwin_design/evidence_ledger_prototype.html` (a standalone HTML concept, not a connected app).
- **Actual draft implementation:** https://github.com/Sreenav14/Market-Twin/pull/5
- **Actual inspected branch:** https://github.com/Sreenav14/Market-Twin/tree/feat/batch-1-aws-observability
- **Original reference inspiration:** https://easyui.site/components and https://bencho.dev/
- Product structure and WCAG sources appear in Section 1.

## Final decision

**Redesign the entire MarketTwin application in an incremental, route-aware way—not by changing its architecture or painting every screen with the same dashboard cards.** Prioritize test comprehension, trustworthy evidence, meaningful next actions and secure human control. Use **Evidence Ledger** as the visual system, keep the real domain/API contracts, respect intentionally unsupported pages, prove each screen in the running app and let the final report be a consequence of better testing—not a cover for weak execution.
