# MarketTwin UI review and change record

Review date: 2026-09-30. Scope: the current React workspace, sign-in, application
and test lists, test creation, execution status, findings, reports, shared controls,
and responsive shell. This review uses source inspection, rendered browser
screenshots, usability research, and automated checks. It is not a study with
representative customers, and it cannot certify that a product has no defects.

## What “AI slop” means in this review

The term is subjective, not a technical diagnosis. Here it means presentation
that looks interchangeable or polished while paying too little attention to the
actual task: repetitive slogans, decorative status signals, exaggerated type,
arbitrary spacing, and incorrect or incomplete states. A sans-serif font, a
component library, or a restrained palette is not itself a defect.

MarketTwin is a working tool. Its central tasks are to choose an application and
authorized target, create a draft, start execution, track progress, inspect
findings/evidence, and manage finished tests. The design should make those steps
clear and keep system status truthful. The UI should not imply that broker
connectivity proves worker availability or that creating a draft starts execution.

## Research and reference products

There is no objectively “best UI” for every application. The reference choices
below fit an operational workspace with lists, forms, status, and evidence.

| Source | Evidence or principle | Decision for MarketTwin |
| --- | --- | --- |
| [NN/g: AI prototyping in real design contexts](https://www.nngroup.com/articles/ai-prototyping/) | Its evaluation found generic styling, inappropriate patterns, weak grouping, excessive color, contrast problems, and inconsistent spacing in generated prototypes. Specific product context improved outputs. | Evaluate each screen against the actual testing workflow; treat generic copy and misleading states as concrete findings rather than trying to avoid a particular font or library. |
| [NN/g: ten usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/) | Visible system status, consistency, error prevention, user control, and focused content are useful evaluation criteria. | Keep status labels accurate, preserve deletion confirmation and permissions, provide recovery actions, and remove copy that competes with the task. |
| [NN/g: aesthetic-usability effect](https://www.nngroup.com/articles/aesthetic-usability-effect/) | Attractive presentation can make people overlook interaction difficulties. | Validate task completion and errors separately from screenshot appearance. A calmer palette is a design choice, not proof of reliability. |
| [Linear: interface redesign](https://linear.app/now/how-we-redesigned-the-linear-ui) | Linear describes reducing visual noise and aligning sidebar, tabs, headers, and panels to improve hierarchy and navigation density. | Retain familiar navigation, shorten the topbar, reduce oversized headers, align controls, and prioritize test activity over promotional content. Do not copy Linear's entire visual identity. |
| [GitHub Primer: accessibility design guidance](https://primer.style/accessibility/design-guidance/) | Product controls need meaningful semantics, visible focus, usable text sizing, and deliberate interactions. | Keep labeled buttons and links, keyboard navigation, focus restoration in dialogs, and explicit destructive-action confirmation. |
| [Primer: motion and animation](https://primer.style/accessibility/design-guidance/motion-and-animation/) | Motion should serve a purpose and respect reduced-motion preferences. | Use brief color/background transitions, retain reduced-motion overrides, and avoid decorative animation or forced smooth scrolling. |
| [W3C: reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) | Ordinary vertically read content should reflow at a width equivalent to 320 CSS pixels. | Check narrow widths and long content for horizontal overflow and hidden controls; allow form and header actions to wrap. |
| [W3C: target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) | WCAG 2.2 defines a 24 CSS pixel minimum target, with specific exceptions. | Preserve larger touch controls in the mobile shell and test forms instead of reducing hit areas while tightening visual spacing. |

## Findings and decisions

The following are observations and judgments about this repository, not claims
that the cited sources reviewed MarketTwin.

| Finding | Consequence | Change / reason |
| --- | --- | --- |
| The sidebar repeats “Different perspectives” and “Evidence you can inspect.” | Permanent navigation space is used for a slogan without helping navigation. | Remove the slogan and its orphaned CSS/import. Keep Settings at the foot of the sidebar. |
| Workspace, tests, application and sign-in copy repeatedly promises insight or value. | Screens read like marketing instead of explaining the next action. | Replace it with direct descriptions of applications, targets, execution and findings. |
| The sign-in headline promises to build an app people want. | It describes a broad outcome rather than what MarketTwin does. | Describe testing user journeys and reviewing evidence; make the form heading explicitly say sign in. |
| Page headings, the topbar and row spacing dominate small datasets. | More scrolling and weaker hierarchy on narrow screens. | Reduce shared heading sizes, topbar height and list/header spacing without reducing touch targets. |
| The new-test textarea uses 20px text and the guidance uses a decorative lightbulb and a large slogan. | Ordinary input and secondary advice compete with the main task. | Use 16px input text, a concise guidance heading and a compact form layout. |
| The draft-creation footer says perspectives and missions are generated. | It can imply execution happens when the draft is saved. | Explain that creation saves a draft and Start is a separate action. |
| An active-status dot is shown with zero active tests. | A visual signal contradicts the count. | Only show the signal when active tests exist. |
| Every Delete action is bright red even at rest. | Repeated destructive accents compete with the primary workflow. | Use a neutral resting treatment and danger color on hover; keep text, accessible labels and confirmation. |
| Header action groups cannot wrap. | Status, Start, Delete and Refresh compete on small screens or long content. | Permit wrapping for page actions; keep the compact topbar group together. |
| Long mobile breadcrumb trails compete with the topbar controls at 320px. | Content extends beyond the viewport. | Show the current breadcrumb on mobile and retain the complete desktop trail; allow the current label to truncate if needed. |
| Kafka status is displayed everywhere, although it mainly helps when starting execution. | An operational indicator competes with unrelated workspace tasks. | At the user's request, show the badge only with the draft run's Start test controls. It disappears after starting. |
| The mobile header CSS gives every primary button full width. | Start test becomes wider than Delete and Refresh. | Override width only for Start test; preserve the shared button heights and padding. Check actual rendered dimensions on desktop, mobile, and at 320px. |
| Queued runs are treated like running runs by the lifecycle rail. | Planning is presented as completed before the worker has started it. | Keep queued and planning runs at the planning stage; only running advances to execution. |
| Workspace run lists fetch without an interval. | A run can stay visually active until focus/navigation triggers another fetch. | Poll at five seconds while queued/planning/running tests exist and stop when all runs are inactive. |
| Background refresh errors replace previously loaded workspace/test content with an error view. | A temporary outage makes the list disappear and interrupts the task. | Keep the cached rows, explicitly say they could not be refreshed, and provide a retry action. |
| A failed Kafka status request is labeled Kafka unavailable. | An API/network error does not establish that the broker is down. | Display unknown status when the request fails; retain unavailable only when the probe reports it. |
| The user's running Control API returns 404 for the new Kafka health endpoint while `/health` returns 200. | The browser cannot check the broker through that older API process. | Explain missing-endpoint failures in the badge's description. The running Control API must be restarted to load the endpoint already present in source. A 404 does not imply a Kafka outage. |
| An expired target authorization is displayed as authorized on the target overview. | Its New test action conflicts with the creation screen, which excludes expired authorizations. | Check expiration consistently before offering authorized-target actions. |

## Visual decisions

Keep Instrument Sans and IBM Plex Mono, the existing navigation and evidence
layout, and a small set of shared surface/border/status treatments. Use a muted
blue primary action rather than saturated indigo to lower competition with
findings and execution status. This palette decision is a contextual design
judgment; the contrast and interaction tests provide the supporting verification.

Use 26–32px shared page titles, 16px form input, restrained 14px explanatory text,
and 140ms color/background transitions. Keep the existing reduced-motion support.
Do not add simulated activity, invented metrics, decorative charts, or automatic
animations to suggest work that the backend has not reported.

## Files and responsibilities

- `src/styles/tokens.css`: shared page and primary-action palette.
- `src/styles/base.css`: shared heading scale, spacing, empty states and link feedback.
- `src/styles/workspace.css`: sidebar spacing, header and list density, form sizing,
  destructive-action feedback and responsive action wrapping.
- `src/layouts/AppShell.tsx`: remove the slogan and simplify the brand subtitle.
  Remove the global Kafka badge.
- `src/layouts/RunLayout.tsx`: place Kafka status beside Start test for manageable draft runs;
  use the standard-size Start button with a targeted width override.
- `src/pages/auth/LoginPage.tsx`: product-accurate sign-in copy.
- `src/pages/overview/OverviewPage.tsx`: direct copy and conditional activity signal.
- `src/pages/applications/ApplicationsPage.tsx`: direct application-list copy.
- `src/pages/runs/RunsPage.tsx`: direct test-list/empty-state copy.
- `src/pages/runs/NewRunPage.tsx`: concise guidance and truthful draft-creation copy.
  Link brief-validation errors to the field through `aria-describedby`.
- `src/pages/runs/RunOverviewPage.tsx`: correct queued lifecycle stage.
- `src/lib/useWorkspaceTests.ts`: refresh active runs while preserving cached content.
- `src/components/markettwin/KafkaStatusBadge.tsx`: distinguish unavailable from unknown.
- `src/pages/targets/TargetOverviewPage.tsx`: honor authorization expiration.
- `e2e/*.spec.ts` and the badge test: validate the rendered product and regression cases.

Paths above are relative to `apps/web`. The completed-test deletion fix predates
this visual review and is verified as part of regression coverage; it also changed
the API lifecycle rule and its tests. No actual user records are deleted by the
browser tests, which intercept requests with test fixtures.

## Verification record

The final browser suite passed in two complementary passes: **18 focused edge-case
checks and 40 remaining workflow checks**, covering all 58 tests across desktop
Chromium and mobile Chromium. The first expanded pass found one real 320px
breadcrumb overflow defect and a reduced-motion test that incorrectly attempted
to inspect a background control hidden by an accessible modal. The layout defect
and test were corrected and their cases rerun successfully.

| Check | Final result | Scope |
| --- | --- | --- |
| TypeScript typecheck | Passed | Frontend source |
| Vitest | 14 passed | Existing component/utility cases plus Kafka unknown/404 regression |
| Production build | Passed | Vite compiled the application |
| Focused Playwright pass | 18 passed | Start and status polling, equal button heights, 320px layouts with long content, reduced motion, cached-data error/retry recovery |
| Remaining Playwright pass | 40 passed | Sign-in entry, route protection, test creation, navigation, evaluation waiting/error states, findings, report, deletion confirmation, permissions, active-list polling, queued lifecycle, authorization expiration and empty states |
| Automated accessibility | Passed for audited states | Axe checks on rendered fixture screens; WCAG 2 A/AA and 2.1 AA tags in workflow tests; serious/critical checks on sign-in |
| Visual review | Inspected desktop/mobile renders | Workspace, creation, sign-in, completed run, findings and report; inspected narrow draft controls and the failed overflow screenshot before fixing it |
| Diff whitespace check | Passed | No whitespace errors |
| Running local API diagnostic | `/health`: 200; Kafka health route: 404 | The current API process needs a restart; no broker health inference is possible from that 404 |

For the preceding completed-test deletion fix, 16 backend lifecycle tests passed;
two PostgreSQL integration cases were skipped because the opt-in test database
was not enabled. This visual pass did not change the API or database schema.

### Screenshot cleanup

Screenshots contain controlled fixture data, not live customer records. A
“Kafka connected” badge in a test screenshot is a fixture response, not proof of
the user's broker health. Full-page mobile screenshots composite a scrolling
page while the bottom navigation remains fixed at the viewport boundary; that
bar can appear partway down the image. Runtime layout and scroll checks are
performed separately.

The reviewed screenshots were removed at the user's request. Written findings
and check results remain. Browser tests now save captures with
`testInfo.outputPath()` in the ignored Playwright results directory, preventing
future runs from adding generated PNG files to the documentation folder.
Removed 14 documentation captures and two temporary browser captures. Both
desktop/mobile smoke checks passed with the new output paths. This cleanup did
not delete MarketTwin test-run evidence or change application screenshot capture.

### Practical limits and handoff

Refresh the running frontend to load the changes. Restart the Control API to load
`/api/v1/health/kafka`; its existing `/health` is intentionally independent of
Kafka. The badge appears only with Start test for a draft run that the user can
manage. Start uses the same shared button height as Delete/Refresh and no longer
inherits the mobile full-width primary-action rule.

Browser tests intercept the API and do not establish live Kafka, worker, database,
model-provider or storage reliability. No live browser execution was started and
no real test was deleted. Firefox/Safari, every possible text-zoom combination,
screen-reader user testing and performance under production load are outside the
verified scope. The application-specific test list still uses its pre-existing
fetch-on-entry flow; continuous polling added here applies to the workspace
overview and main Tests list. These limits are recorded rather than claiming
that visual polish or passing automated checks guarantees a defect-free product.

## Execution review follow-up

- The one-command diagnostic now calls the persistent worker's `process_command()`.
  Both commit offsets only after that processing returns. The diagnostic keeps
  Kafka connected through processing, shares the worker's long poll interval,
  and closes Kafka/database resources in `finally`. A processing error or
  cancellation does not commit the offset.
- A connected broker with `outbox_relay_enabled=false` now displays
  `Kafka connected · relay off` with the warning tone. Green is reserved for a
  connected broker with the relay enabled; it still does not establish worker
  readiness. Worker-health instrumentation is deferred.
- V1 recovery assumes exactly one active execution consumer. The README and
  recovery comment explicitly state that concurrent workers, including running
  the diagnostic alongside the persistent process, are unsafe without ownership
  leases. Lease/attempt-owner recovery must precede horizontal scaling. No
  horizontal-scaling guarantee is made.
- Regression coverage exercises diagnostic commit ordering and cleanup on success,
  processing failure and cancellation, plus the connected/relay-off warning.
- Verification: all 9 worker/diagnostic tests and all 5 Kafka badge tests passed.
  Frontend TypeScript checking, Pyright for the changed Python files, Ruff, and
  `git diff --check` passed. These checks use mocks and do not execute a live run.

## Dark theme follow-up

The application now uses a consistent charcoal theme with soft light text and a
restrained blue accent. Hardcoded light colors in legacy screens, forms, dialogs,
status badges and hover states were replaced with shared semantic tokens. See
[the dark theme review](DARK_THEME.md) for research sources, the palette, reasons
for each changed file, contrast measurements and verification results. The
screenshots were reviewed in the dark theme and then removed as requested.

## Local queued-run diagnosis

The local database contained three queued runs with successfully published
`run.requested` outbox events and no worker acceptance records. Process inspection
found the Control API running but no execution worker. The Kafka connection check
succeeded, with a transient SSL warning; the absence of a worker explained this
queue backlog.

Started one persistent execution worker using the existing `.env` configuration.
It authenticated, joined the execution consumer group, accepted the oldest queued
command and moved that run to `running`. The remaining commands wait for sequential
execution. This confirms dispatch into execution, not successful completion of all
journeys or the remaining tests.

The running Control API still returned 404 for `/api/v1/health/kafka`. Restarted
its verified process tree with the same host and port to load the current code.
Verified `/health` returns 200 and the separate Kafka endpoint returns 200 with
`status=connected` and `outbox_relay_enabled=true`. The API and worker are left
running as separate local processes; no operating-system autostart service was
installed.

The worker subsequently finished the oldest queued run and began the next.
Execution logs also reported model-provider HTTP 429 token-rate limits during
some journeys. Those are separate from Kafka dispatch and remain a provider
capacity limitation; completion of a run does not imply every journey passed.
