# MarketTwin — Evidence-First Product UI Redesign
## Research, independent design review, exact React/TypeScript implementation plan, and deep end-to-end acceptance contract

**Prepared:** 2026-10-15  
**Intended recipient:** Codex, working in the existing MarketTwin repository  
**Repository:** `Sreenav14/Market-Twin`  
**Audited remote branch:** `feat/batch-1-aws-observability`, **HEAD `339a4b30326ed4cf0c47c7238e63e4387c6d0fac`** at the time of this audit  
**Scope:** Design and frontend implementation, plus deep local end-to-end validation of the application and already-implemented HITL integration. **Not** a backend feature rewrite.  
**Status:** **Implementation specification, not an implemented redesign or a passing live E2E result.** Source files and published product documentation were reviewed; this document does not claim the running MarketTwin browser was inspected or tested in this session. Codex must inspect the CURRENT local checkout, which may be newer or uncommitted.

---

# 0. Executive design decision

Choose **Quiet Precision**, an evidence-first research workbench with an **optional dark mode**, rather than cloning Perplexity or imposing a generic black AI dashboard. Preserve the exact existing font families:

- **Instrument Sans Variable** (`@fontsource-variable/instrument-sans`) for the UI, paragraphs, buttons, navigation, headings.
- **IBM Plex Mono** (`@fontsource/ibm-plex-mono`) only for execution IDs, timestamps, step indices, tiny technical metadata, code, diagnostics and bounded values.

**Identity statement:** *A deliberate instrument for investigating how software behaves.* MarketTwin should feel precise, calm, trustworthy and technically capable. It must look like one coherent product across onboarding, target authorization, test creation, live runs, HITL, evidence, findings, knowledge review and reports.

**High-level composition:**

1. **Quiet navigation rail** (persistent on desktop, properly operable drawer on small screens).
2. **Purposeful content canvas** (content-centered on creation and reading surfaces; fluid width for tabular and investigative surfaces).
3. **Persistent run context and status** (current target, mode, status, and one truthful next action).
4. **Optional evidence inspector** (steps / finding / screenshot / source with a controlled resize/collapse; not a decorative AI-chat column).
5. **Human-assistance interrupt state** treated as a first-class active task; safe browser viewer gets a high-visibility, uncluttered area.

**Avoid:** broad gradients, animated orbs, glassmorphism, cyber-neon borders, giant glowing buttons, equally weighted cards, 12-pixel gray text on gray, endless empty cards, auto-playing decorative animations, terminal cosplay, fake agent-thinking animations, fake graphs, invented metrics, invented coverage, chatbot-first UX for a testing product, cloning Perplexity icons/copy/layout exactly.

**Non-negotiable:** Visual changes must **not** change API authorization, browser control, lease/token secrecy, evidence attribution, testing truth semantics, Kafka workflows, Playwright runtime or existing backend contracts. Do not create a "nice-looking demo" that bypasses production components.

---

# 1. Research methodology, evidence and limits

## 1.1 Actual product research, not imagined visual facts

### Perplexity — WHAT to borrow

- The product publicly documents **streamlined threads, universal content tabs, and contextual navigation**. Its updated side menu emphasizes Library, recents and configurable shortcuts. Earlier updates describe a cleaner sidebar, fast hover access and shortcuts.
- **Takeaway for MarketTwin:** maintain user focus, preserve readable space, make navigation predictable, and use a single primary action on creation surfaces.
- **Do not borrow:** a conversational model pretending run artifacts are chat messages; arbitrary "Sources" badges; product-identical logos, copy, icon arrangements or trade dress.

Evidence: [Perplexity product changelog — streamlined UI](https://www.perplexity.ai/changelog/what-we-shipped---december-5th), [redesigned sidebar](https://www.perplexity.ai/changelog/what-we-shipped-may-2nd). Screenshot galleries are supplemental; version-specific imagery is not a design authority.

### Arize AX / Phoenix — WHAT to borrow

- Arize's official trace docs show **project-level trace lists, nested trace/span inspection, evaluations, filters, configurable columns, and drill-down**. Product screenshots demonstrate compact, high-information-density views with contextual side panels.
- Arize's documented January 2026 UI changes emphasize expandable trace hierarchy, resizable slideovers, time persistence, and reducing unnecessary initial table load. Treat published performance claims as Arize's claims, not measurements for MarketTwin.
- **Takeaway for MarketTwin:** two-stage investigation (select record -> inspect source evidence), meaningful metadata, dense readable rows, trace-like case/step hierarchy, progressive detail.
- **Do not borrow:** Arize's exact trace vocabulary for MarketTwin's different data model; a wall of unlabeled widgets; claims that deterministic cases are autonomous agent traces.

Evidence: [Arize Explore traces](https://arize.com/docs/ax/observe), [Arize run evals on traces](https://arize.com/docs/ax/evaluate/online-evals/log-evals-to-traces), [Arize January 2026 product updates](https://arize.com/blog/new-in-arize-ax-january-2026-updates/), [Arize Phoenix overview](https://arize.com/phoenix).

### Neatlogs — WHAT to borrow

- Neatlogs' own dashboard introduction describes **Investigate, Traces, Detections, Analytics, Fixes and Evals**. Its trace documentation explains span trees, sequence/parallel timelines, evidence detail on selection, and cost/latency context.
- **Takeaway for MarketTwin:** make sequential actions, branch structure, and selected-step details easy to scan; preserve the distinction between what happened and an interpretation of what happened.
- **Do not borrow:** token/cost fields where MarketTwin has no measured data; "AI fix" calls to action if no safe corresponding feature exists; stylized terminal UI as default.

Evidence: [Neatlogs dashboard overview](https://docs.neatlogs.com/docs/quickstart/explore-dashboard), [Neatlogs trace detail](https://docs.neatlogs.com/docs/features/traces).

### Usability, accessibility, performance

- Use Nielsen Norman Group's **visibility of system status**, recognition over recall, consistency, error recovery and progressive disclosure. Long-running complex operations need explicit progress and uncertainty, not just spinners: [NN/g general heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/), [complex-application heuristics](https://www.nngroup.com/articles/usability-heuristics-complex-applications/).
- Use **WCAG 2.2 AA** as the acceptance standard. Normal text contrast >=4.5:1; large text and non-text state/focus graphics as applicable >=3:1; keyboard order, keyboard-only completion, dialog semantics, visible focus, viewport reflow and 200% text scaling. W3C: [WCAG 2.2](https://www.w3.org/TR/WCAG22/), [what is new in 2.2](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/).
- Use web.dev Core Web Vitals for **field measurement targets**, not as magically guaranteed local lab results: **LCP <=2.5 seconds, INP <=200ms, CLS <=0.1** at p75 when meaningful usage data exists. [Core Web Vitals](https://web.dev/articles/vitals), [threshold methodology](https://web.dev/articles/defining-core-web-vitals-thresholds/). Lab E2E should additionally measure pages with data-heavy records.

## 1.2 Source-of-truth hierarchy

1. **Current local repository and actually running app** outrank the pinned remote baseline. Inspect git status/HEAD and existing uncommitted changes first.
2. Existing **product semantics/API/evaluator/HITL policy** outrank visual preference. Never invent capabilities.
3. Published product docs above support pattern comparisons, **not** exact current competitor screen geometry.
4. This document's color/layout values are **design proposals** and must pass a browser-based visual/accessibility critique before broad rollout.
5. Any reference screenshot is inspiration, **not** permission to copy a screen or include external brand assets.

---

# 2. Verified current MarketTwin frontend inventory

**Audited code, not speculative:**

| Area | Current repository fact | Consequence for design |
|---|---|---|
| Stack | React 19.1.1, TypeScript, Vite 8.2.2, React Router 7.18.2 | Keep architecture; no Next.js rewrite. |
| Components | Existing reusable UI, Lucide, Radix Dialog/Tooltip, class-variance-authority, Tailwind v4 | Extend existing components; no shadcn mass reinstall or component library swap. |
| Data | TanStack React Query 5.102.8, `lib/api.ts`, existing hooks | Preserve query keys, cache correctness, errors, polling, mutations and authorization. |
| Fonts | `@fontsource-variable/instrument-sans` and `@fontsource/ibm-plex-mono` already installed | No font package change or new display font. |
| Shell | `layouts/AppShell.tsx` has permanent sidebar, workspace selector, breadcrumbs, command menu, account footer | Redesign shell and responsive controls incrementally. |
| Run shell | `layouts/RunLayout.tsx` has Summary/Journeys/Findings/Report tabs and `RunFlowPanel` | Expose Human Assistance and Evidence without breaking existing routes. |
| Run types | `legacy_persona` and `deep_feature_v1`; UI's FeatureCases already distinguishes deterministic execution | Preserve transparent execution type. |
| HITL | `HumanActionPage.tsx` and `HumanBrowserViewer.tsx`; local pilot, claim/renew/reconnect/release/approval | Priority screen: cannot obscure live browser, lease expiry, denial, reconnect or secret-entry rules. |
| Router | `app/router.tsx` contains routes for applications, targets, network/authorization, knowledge, all run detail, settings, errors and public pages | No deleting or silently redirecting existing routes. |
| CSS | `styles.css` imports tokens + `legacy.css`, `base.css`, `workspace.css` (~1397 lines), `enterprise.css`, `product-theme.css`, and others | **High cascade/dead CSS risk**: refactor cautiously; avoid piling more global overrides. |
| Palette | `styles/tokens.css` currently has off-white/green colors (`--page`, `--surface`, `--primary`) | Existing theme is already close to a warm, calm aesthetic; improve instead of replacing wholesale. |
| Test tooling | Vitest, Testing Library, Playwright E2E (Chromium and Pixel 7), axe Playwright integration | Reuse. Tests must target actual current app and use synthetic fixtures for protected paths. |
| Documentation | `docs/hitl/README.md` is HITL source of truth; latest remote commit `339a4b30` | Preserve local-pilot/NO-GO distinction and manual testing guide. |

## 2.1 Current page/route audit list

Read `apps/web/src/app/router.tsx` as the live map. Audit all listed pages, not merely the overview:

- Public: `/`, `/how-it-works`; account: `/login`, `/auth/callback`.
- Workspace: `/overview`, `/applications`, `/applications/new`, `/applications/:applicationId`, edit, application runs and targets.
- Target: `/targets/:targetId`, `/authorization`, `/network`, `/edit`, application-specific new-target flow.
- Knowledge: `/ingestion`, `/knowledge/review`, `/knowledge/review/:entryId`.
- Tests: `/runs`, `/applications/:applicationId/runs/new`; `/runs/:runId/{overview,agents,perspectives,missions,journeys,evaluation,activity,findings,evidence,report,human-action}` and child finding/evidence/journey detail routes.
- Agents: `/agents`.
- Settings: `/settings/{profile,workspace,members,security}`; system `/403`, `/error`, unknown-route 404.

For each route, record: **purpose**, primary decision, primary action, permission required, source data, loading state, empty state, error state, destructive action, small-screen behavior, current CSS dependencies. Produce a concise route inventory in `docs/ui/ROUTE_INVENTORY.md` if no equivalent exists.

## 2.2 Observed defects/risks to solve (from static inspection, not live bug claims)

1. `RunLayout.tsx` primary tabs hide the already-implemented `/human-action` path. Users with `awaiting_human` need an unmistakable action and way back to the original run state.
2. `RunFlowPanel.tsx` occupies a separate right column and can add permanent density. It should be collapsible, context-aware, and not compete with the evidence inspector at medium widths.
3. `FeatureCases.tsx` shows important coverage/source/recorded-versus-evaluated concepts as long paragraphs and repeated panels. It needs an accessible table/list hierarchy, drill-down and status separation, **without** changing data meaning.
4. `HumanBrowserViewer.tsx` uses canvas and hidden password input for transient input. Repositioning/reflow must preserve coordinate mapping and browser focus; **never** make a thumbnail-sized browser viewer for aesthetics.
5. `HumanActionPage.tsx` polls requests and approvals and manages active lease and renewal. Cosmetic refactors could unmount the viewer or reset tokens and affect lease lifecycle. Keep state and actions stable.
6. `NewRunPage.tsx` contains numerous auth, approval, environment and scope controls. Hiding all controls under inaccessible visual flourishes would make safe run setup harder.
7. Many global CSS classes live in `workspace.css` and `product-theme.css` overrides. Adding a second huge generic stylesheet would compound specificity debt and regress cross-page surfaces.
8. E2E config can save Playwright traces/screenshots on failure; protected/HITL screens must use safe fixture values and **disable diagnostic content capture during secret entry**, even though test credentials are synthetic.
9. Current `OverviewPage` renders a four-step process and summary metrics; these are useful information, but visual emphasis should shift toward relevant user actions and actual recent runs.
10. Existing status names may not cover every step-level meaning in a single badge. Do not conflate `failed` execution, `failed_assertion`, `blocked`, `inconclusive`, `not_run`, `awaiting_human` and `evaluation_pending`.

These are source-derived **design integration risks**. Treat their runtime impact as unverified until measured.

---

# 3. Three candidate design directions, evaluated before selection

Score 1–5 based on suitability for MarketTwin, **judgment not user testing**.

| Criterion (importance) | A: All-dark observability clone | B: Chat-first Perplexity clone | C: Quiet Precision workbench |
|---|---:|---:|---:|
| Information hierarchy (high) | 4 | 3 | **5** |
| Complex-case inspection (high) | 5 | 2 | **5** |
| HITL interaction clarity (critical) | 3 | 2 | **5** |
| Existing CSS reuse (high) | 2 | 2 | **5** |
| Distinct MarketTwin identity (high) | 2 | 2 | **5** |
| Light-mode legibility (high) | 2 | 4 | **5** |
| Risk of "AI slop" (inverted; 5 = least risk) | 2 | 2 | **5** |
| Incremental delivery (high) | 2 | 2 | **5** |

**Decision: C.** A dark interface is attractive for dense traces, and a centered composer is ideal for one action, but *making everything* dark or *everything* chat-like would lose testing-specific affordances. Use a calm, editorial surface for setup and reading, and a compact, forensic hierarchy for execution and evidence. A charcoal dark theme is a secondary enhancement rather than a release blocker; ship it only after complete contrast and interaction verification. The default light presentation must already be excellent.

---

# 4. Detailed visual language and design tokens

## 4.1 The palette — candidate values with calculated contrast

**Light / default (warm neutral, not beige AI-template):**

```css
:root {
  color-scheme: light;
  --mt-canvas: #f8f9f7;
  --mt-surface: #ffffff;
  --mt-surface-subtle: #f1f4f1;
  --mt-surface-hover: #e9efeb;
  --mt-ink: #172422;
  --mt-ink-secondary: #52615e;
  --mt-ink-tertiary: #647370;
  --mt-border: #dde4e0;
  --mt-border-strong: #bac9c2;
  --mt-accent: #0c625d;
  --mt-accent-hover: #084d49;
  --mt-accent-foreground: #ffffff;
  --mt-accent-subtle: #e7f3f0;
  --mt-success: #1c6b4c;
  --mt-danger: #ae2b40;
  --mt-warning: #8c4b00;
  --mt-info: #1f5d86;
  --mt-focus: #0c625d;
  --mt-shadow: 0 2px 10px rgb(15 32 25 / 5%);
  --mt-radius-xs: 4px;
  --mt-radius-sm: 7px;
  --mt-radius-md: 10px;
  --mt-radius-lg: 14px;
}
```

**Dark (under explicit user preference, not inferred from time of day):**

```css
[data-theme="dark"] {
  color-scheme: dark;
  --mt-canvas: #0f1516;
  --mt-surface: #161f20;
  --mt-surface-subtle: #1c2829;
  --mt-surface-hover: #243233;
  --mt-ink: #edf3ef;
  --mt-ink-secondary: #afc0bb;
  --mt-ink-tertiary: #96aaa5;
  --mt-border: #304341;
  --mt-border-strong: #527067;
  --mt-accent: #8ee1d0;
  --mt-accent-hover: #b1f1e1;
  --mt-accent-foreground: #072321;
  --mt-accent-subtle: #193c37;
  --mt-success: #80d4a9;
  --mt-danger: #ff9eaf;
  --mt-warning: #ffc580;
  --mt-info: #8dbde1;
  --mt-focus: #8ee1d0;
  --mt-shadow: none;
}
```

**Calculated pairwise contrast** (simple sRGB WCAG ratio, verified programmatically; still inspect actual UI layers):

| Pair | Calculated ratio | Assessment |
|---|---:|---|
| Light ink `#172422` on canvas `#f8f9f7` | 15.16:1 | Strong |
| Light secondary `#52615e` on canvas | 6.16:1 | >= 4.5 |
| Light tertiary `#647370` on white surface | 4.97:1 | >= 4.5 |
| Light white on accent `#0c625d` | 7.19:1 | Strong |
| Light danger `#ae2b40` on white | 6.52:1 | >= 4.5 |
| Light warning `#8c4b00` on white | 6.73:1 | >= 4.5 |
| Dark ink `#edf3ef` on canvas `#0f1516` | 16.39:1 | Strong |
| Dark secondary `#afc0bb` on canvas | 9.73:1 | Strong |
| Dark tertiary `#96aaa5` on surface `#161f20` | 6.87:1 | >= 4.5 |
| Dark deep text `#072321` on accent `#8ee1d0` | 10.88:1 | Strong |

**Implementation rule:** Keep **existing semantic variable names** (`--page`, `--surface`, `--text`, `--text-2`, `--text-3`, `--primary`, `--danger`, etc.) and map them onto approved new `--mt-*` values first; do NOT indiscriminately rename thousands of selectors. Apply theme on a stable document root, and ensure portals/dialogs inherit it. Maintain `@theme inline` Tailwind mappings. Never use status *color alone*; use icons/text/state labels. UI dark theme must be audited screen by screen, including charts, HTML select controls, focus rings and screenshot overlays.

## 4.2 Typography (do not install or distribute any other fonts)

- Headings: **Instrument Sans Variable**, normal-to-semibold (500–650). Big headings 28–34px on reading surfaces; run titles 24–30px; section headings 17–21px; dense headings 15–17px.
- Body: 14px on dense technical tables, 15–16px on content; line-height 1.45–1.65. Never use 11px default for general copy.
- Labels: 12–13px, weight 550–650; do not make all labels uppercase letter-spaced microtype.
- Metadata / IDs / durations / evidence hashes: **IBM Plex Mono**, 11–12px minimum when legible, `font-variant-numeric: tabular-nums;`.
- Headings should be compact, never giant 60–80px hero text within authenticated product pages. Public marketing pages may have a separate editorial scale.
- Avoid changing user-specific characters, localization, or making code lines horizontal-scroll the whole page; use bounded overflow in code containers.

## 4.3 Spacing, lines, icons, surfaces

- Base spacing steps: **4, 8, 12, 16, 20, 24, 32, 40, 48px**; use tokens and layout primitives rather than random values.
- Page max width: **1200–1360px** for most work; ~**860px** for content-heavy configuration and reading; investigative pages may use viewport width with side inspector.
- Sidebar width target: **228–248px** desktop; compact collapsed mode **64–72px** only if labels are accessible; hidden in overlay drawer under small viewport.
- Header: ~**56–64px**; height remains consistent.
- Cards are for distinct objects/tasks, **not** every heading. Prefer 1px boundaries and whitespace. Shadows subtle or absent.
- Icons: reuse **Lucide**; 16–18px controls, ~20px feature callouts; never add emojis to product navigation or gradient icon tiles.
- Radius: 7–14px, not bubbly 24–40px controls. Buttons need distinct primary/secondary/ghost/destructive semantics, not gradient CTA branding.
- Reduce repeated badges to meaningful states. Secondary metadata should read like metadata; not every label gets a pill.

## 4.4 Motion and interaction polish

- Short transitions **120–180ms** for hover/pressed/collapse only. Honor `prefers-reduced-motion: reduce`; transitions should not block task completion.
- No skeleton layout shifts: reserve space, use stable placeholders, preserve table headers.
- No animated agent-status theatre. Show last timestamp, known stage, truthful actual event and manual refresh.
- All dialogs get accessible titles, descriptive text, Escape/cancel paths, focus trap/restore and no accidental destructive submit on Enter.

---

# 5. Design anatomy and wireframes (descriptive, not production JSX)

## 5.1 Desktop navigation and contextual workbench

```text
┌─────────────────────┬───────────────────────────────────────────────────────────────┐
│ MARKETTWIN          │ Workspace  /  Applications  /  Test                           │
│ [Workspace switch]  │───────────────────────────────────────────────────────────────│
│                     │                                                               │
│ ◈ Overview          │ [Context / title / status]                [contextual actions] │
│ ◉ Applications      │                                                               │
│ ▤ Tests             │ [Task-focused main column]             [Inspector only when   │
│ ◷ Knowledge         │                                         investigating a run]  │
│ ⌘ Agents            │                                                               │
│                     │  All important records are real data, not dashboard filler   │
│ ──────────────────  │                                                               │
│ Settings            │                                                               │
│ [Avatar/account]    │                                                               │
└─────────────────────┴───────────────────────────────────────────────────────────────┘
```

Navigation never includes nonexistent features. A `Needs you` indicator appears **only** for actual accessible pending human requests/approval events; don't fake unread numbers. Active route has low-key background + left ink/accent indicator, not a big gradient.

## 5.2 Run overview (a forensic timeline, not chatbot)

```text
Tests / Checkout form regression                              Completed [•••]
Target: approved staging · Deep-feature deterministic cases   Run #a2b4c3
────────────────────────────────────────────────────────────────────────────
[Summary] [Cases/Journeys] [Findings] [Evidence] [Report] [More ▾]

  8 planned  ·  6 executed  ·  1 blocked  ·  1 inconclusive
  Evidence status: evaluation complete        [Open report]

  Execution timeline                      │ Selected case / step inspector
  ├── Plan created                        │ Case 04 / submit validation
  ├── Human authentication [verified]     │ Expected ... / observed ...
  ├── Case 01 [passed]                    │ Source: approved requirement
  ├── Case 02 [blocked]                   │ [Screenshot thumbnail][Open securely]
  ├── Case 03 [inconclusive]              │ Evidence ID · execution step ID
  └── Evaluation complete                 │ [Next step / Previous step]
```

Run navigation must preserve existing `/runs/:runId/{overview,journeys,findings,evidence,report}` and other existing URLs. The tab names may be *display labels*; URLs remain stable. **Human assistance is visible in both run header and relevant route navigation** whenever relevant. `RunFlowPanel` should transform into a compact, collapsible **Execution** inspector or timeline, preserving actual mode labels.

## 5.3 HITL takeover view (prioritize safety over decoration)

```text
ACTION REQUIRED                                  Test: protected dashboard
The agent is paused. Complete sign-in in the isolated test browser.

┌────────────────────────────────────────────────────────────────────────────┐
│ Secure browser · test origin                                   Lease 00:29 │
│ ┌────────────────────────────────────────────────────────────────────────┐ │
│ │                                                                        │ │
│ │              LIVE BROWSER VIEWER (large and readable)                │ │
│ │                                                                        │ │
│ └────────────────────────────────────────────────────────────────────────┘ │
│ [Connect/Reconnect] [Secure input help]  [Release for verification]         │
└────────────────────────────────────────────────────────────────────────────┘

One operator controls the browser. Agent actions and capture are paused.
If the viewer disconnects, reconnect while lease is valid. Disconnect ≠ Release.
```

- The browser viewport must have a sensible min-height and can enlarge into a **dedicated viewer focus mode**. For small screens, use carefully supported scaling with correct pointer coordinate mapping; do not implement an unverified fullscreen API shortcut.
- Show exact lease expiry as an accessible text and announce key status changes; do not show false seconds if the clock isn't synchronized.
- **Never** place secret values in React global store, logs, query cache or error toasts; existing transient ticket/token state remains scoped to owner component.
- Approval decisions are a separate purpose-built panel with exact action summary and evidence link. "Approve once" and "Reject" are clear; never merge them with a login "Done" button.

---

# 6. Information architecture and exact screen-by-screen behavior

## 6.1 Overview (`OverviewPage.tsx`)

**Purpose:** answer "What needs attention?" and "What should I do next?" within 10 seconds.

1. Strong single `New test` action, obey existing role permission checks; no custom giant prompt input on an account that lacks target authorization.
2. A restrained **Requires attention** section only when real data supports it (HITL pending, pending action approval, errored run). Existing API permissions must be respected. It is not a notification engine; don't invent a system-wide count if not supported.
3. **Recent runs** with actual target, execution mode, status, date; first 5–8 items; real links. If no runs, focus on onboarding CTA, not empty charts.
4. Small numerical overview from actual query results; avoid meaningless 4-card KPI dashboards if zero values repeat.
5. Existing "How a test runs" guidance can become a discreet collapsed "How testing works" link; do not dominate returning-user landing page.
6. Do not make `completed` imply evaluation/report ready; show `awaiting report` if known by source state.

**Acceptance:** at desktop and mobile, pending action is visible near top; empty/loading/error states are distinct; no additional backend call per list row; all actions permission-gated.

## 6.2 Applications and targets

- Applications list: one dense, well-spaced line per app, with target/environment count only if truly available; no fake health scores. Each row offers navigation to details. Account for long application names.
- Application details: purposeful sections for **Targets**, **Tests**, **Knowledge** and editing. Deletion/settings remain explicit; admin-only actions do not become client-only hidden security.
- Target overview: environment, base URL, exact authorized origins, `requires_auth`, network policy, owner/expiry and authorization status. **Clear visual separation between target configuration and authorization approval**.
- Network/security: preserve exact policy wording; do not replace caution language with reassuring green cards.
- Destructive controls: secondary, confirm with actual target name (existing `DeleteAction`), never icon-only with no accessible name.

## 6.3 Test creation (`NewRunPage.tsx`) — most important form redesign

This is **not** a consumer chatbot. It is a structured test request with a primary brief input and clearly defined policy controls.

**Three explicit zones:**

A. **What to test:** approved target and user-owned goal/brief in a restrained large textarea (Instrument Sans, no rainbow border); example suggestions grounded in test intent, not fake generated AI content. Keep existing minimum brief validation.

B. **How to execute:** explicit `legacy_persona` vs `deep_feature_v1`; explain model planning versus deterministic case steps truthfully; test depth; knowledge sources; any advanced settings under accessible disclosure.

C. **Security/authorization:** expanded whenever `requires_auth` or action approvals are requested. Show origin, exact marker, role, account reference, auth-only origins and why they matter; show synthetic/staging scope and explicit action rule conditions. Never bury approvals behind an unlabelled icon or choose an unsafe default.

**Essential cases:** no authorized target; expired authorization; auth required without verifier; unsaved brief; owner versus viewer; mobile keyboard; browser history back; failed submission preserves text and nonsecret selections; no confidential values in URL.

**Acceptance:** same API payload contract and safe defaults; original validation retained; one action submits once (avoid double-run); route remains `/applications/:applicationId/runs/new`.

## 6.4 Tests list (`RunsPage.tsx`)

- Compact table/list, left-aligned headings, filter/search bar, status clearly labeled, environment/mode/date if the API exposes them; no invented values.
- Retain query URL parameters (`q`, `status`) and existing filtered deep-link behavior; do not reset on rerender.
- Empty filter results differ from no tests; maintain Clear filters.
- Status `awaiting_human` clearly distinguishable and row links directly to relevant run/Human Assistance if permitted, but avoid exposing cross-user request details.
- On mobile collapse lower-priority columns into secondary lines, do not create page-wide horizontal scrolling.

## 6.5 Run shell (`RunLayout.tsx`) and status hierarchy

- Unified run header showing run title, actual target/env, **execution mode**, lifecycle status, refresh and permission-gated Start/Delete.
- Keep relevant existing run routes working. Recommended *visible* primary tabs: **Summary, Cases/Journeys, Findings, Evidence, Report**; additional existing Activity, Evaluation, Missions, Perspectives, Agents under accessible **More** menu or contextual links. Preserve route support and deep-link URLs.
- When `run.status === "awaiting_human"`, show **action-required callout and direct `/runs/:runId/human-action` link** with unique accessible label; don't automatically navigate while the user is inspecting past evidence.
- Even without `awaiting_human`, provide Human Assistance in run navigation or overflow, because pending approvals/request info may exist and is operator-critical.
- `RunFlowPanel`: show **Feature cases / deterministic execution** for deep mode, not `Sequential Agent`. Legacy journey flow retains true labels. Avoid decorative agent avatars and fake live typing.
- Run-status semantics must come from backend results (including evaluation pending).

## 6.6 Cases and journeys (`FeatureCases.tsx`, journey pages)

- Dense two-column **case list + selected evidence detail** on wide screens; one-column stacked/accordion on small screens.
- Each case line: name, kind, execution status, assertion count, grounded/inferred classification, optional supporting step link.
- Case detail: exact expected, observed, assertion status, source/origin, supporting artifact and step link. Inferred mismatches must not display as "confirmed bugs".
- Distinguish `not_run`, `blocked`, `inconclusive`, `evaluation_pending`, `recorded failed assertion`, `confirmed finding` without relying only on color.
- `ArtifactEvidence` remains an authenticated artifact fetch; never make its URL globally cached or directly embed unapproved screenshots.
- Large case collections: paginate or virtualize only if justified by measurement and preserve keyboard navigation and test IDs. Do NOT introduce a virtualization library for eight cases.

## 6.7 Findings and evidence

**Findings:** master-detail view on desktop, titled list on mobile. Group by actionable severity/status only when grounded backend field exists; show provenance and evidence availability. Separate "needs verification" from confirmed findings. No auto-counted "critical" by color alone.

**Evidence:** bounded image preview with artifact metadata and links; no infinite images rendered in lists. Provide unambiguous artifact ID, source step, time and access error state. If binary downloads require signed fetch, use existing API and avoid accidental public blob URLs.

**Detail:** preserve screenshot natural dimensions, zoom/pan and keyboard support. Sensitive masking already done on backend; UI must not pretend a screenshot is verified or declassified just because it renders. Avoid `innerHTML` for ARIA or logs.

## 6.8 Agent flow, activity, observability

Borrow Arize/Neatlogs **navigation models**, not their exact terminology. Use:

- "Planned" → "Executing" → "Evaluating" → "Completed/Blocked" only when backed by saved events.
- Nested rows with meaningful durations and statuses; elapsed time only if measured.
- Expand details on demand; avoid rendering every step's full payload at once.
- Show explicitly whether event is from a human operation, deterministic browser action, model planning step or independent evaluation.
- Empty "awaiting evaluation" is not a software defect; source evidence is not model output.

## 6.9 Human assistance (`HumanActionPage.tsx`, `HumanBrowserViewer.tsx`)

Treat as a safety-critical transaction with user attention and clearly divided control types:

1. **Login takeover**: pending request, one exclusive lease, high-visibility viewer, connect/reconnect, secure ephemeral input and explicit Release for verification.
2. **Approval**: exact action summary, safe prior step/evidence, environment, expiry and distinct Reject / Approve once.
3. **Blocked/expired**: informative status without offering bypass. Releasing the viewer doesn't prove login or resume.

**Important:** Do not change underlying lease timer, reconnect API, generation fencing, transient ticket handling, WebSocket input protocol or event capture behavior for CSS simplification. No automatic reconnect loop that might reuse tickets. If user leaves viewer, maintain backend control semantics: disconnect ≠ Release. Do not persist the last browser frame to state or caches. Preserve focus in live canvas/input UI.

**Responsive:** browser is *usable* above fold when possible; high-priority control and lease status remain accessible; no iframe to target outside the trusted viewer. If 320px viewport cannot safely support pixel-perfect canvas input, offer clearly explained "Open on desktop" with cancel/release rather than secretly altering click coordinates.

## 6.10 Knowledge, settings, authentication and error pages

- Knowledge ingestion/review must prioritize source, evidence, approval state and provenance. A generated draft is not approved simply because of a green accent.
- Settings retain subnav role access. Clear account/organization distinction. Auth callback stays intact.
- Login should be minimal and recognizable, match typography and controls; avoid reimplementing OAuth/session logic.
- 403 and 404 pages offer safe back navigation; 500/error shows retry plus nonsecret error. No mock success pages.
- Public marketing `/` and `/how-it-works` can share tokens but should not inherit workspace dense layout; audit separately. Avoid a complete marketing rewrite unless the current design makes typography/colors contradictory.

---

# 7. Technical implementation strategy: incremental, efficient and reversible

## 7.1 Do NOT rewrite global CSS indiscriminately

Proposed minimum-change evolution:

```text
apps/web/src/styles/
  tokens.css              # update existing semantic variables, theme maps
  base.css                # shared type, focus, form/input primitives
  workspace.css           # progressively reduce duplication, do not shotgun rewrite
  enterprise.css          # existing product sections retained until migrated
  product-theme.css       # shrink/remove obsolete overrides once routes migrate
  [optional] workbench.css  # ONLY genuinely new layout primitives, ~small focused file
  [optional] hitl.css       # isolated critical viewer/layout styles if justified
```

Prefer **one token definition for each purpose** and semantic utility components. Do not create `theme2.css`, `redesign-final.css`, `new-override-2.css`. Use simple scoped classes (e.g. `.mt-run-layout`, `.mt-evidence-inspector`) or CSS modules if the existing setup supports them. Protect unrelated selectors with migration. CSS cascade complexity must go **down**, not up.

Check the import order in `apps/web/src/styles.css` before editing. `product-theme.css` currently imports last; update/remove conflicting overrides so token-level changes actually apply. Any new layout stylesheet belongs in an intentional position, not endlessly appended over earlier rules.

## 7.2 Proposed reusable components — add only if reused

Keep current Button, PageHeader, StateViews, StatusBadge, BrandMark, DeleteAction and form primitives. Potential focused components:

- `WorkspacePageFrame` — consistent title, subtitle, actions, content width only if >=3 pages need it.
- `StatusContext` — lifecycle + execution + evaluation labels without collapsing them into "passed/failed"; can be composed with existing status badges.
- `InspectorSplitView` — case/step source list and selected detail; create only when used in multiple views (e.g. Journey + Findings).
- `AttentionBanner` — exact pending human action/status, no generic AI alerts.
- `EmptyStateAction` — reuse/extend existing `EmptyState`, not duplicate.
- `MetadataLine` — ID, role, environment, timestamps in compact form.
- `ThemeToggle` — optional `light/dark/system` with a11y, flash prevention and persisted user choice only if acceptable; don't install theme libraries.

Do not create a dozen generic card components. Reuse existing branded components and maintain obvious DOM semantics; real links for navigation, buttons for action.

## 7.3 Component state and data rules

- Keep `api.ts` contracts unchanged for purely visual tasks.
- Existing TanStack Query cache keys must preserve **user and run identity**. Never cache browser frames or lease tokens in shared global stores.
- Avoid `useEffect` loops for derived state; prefer props, selectors and CSS.
- Use `useMemo` only for measured expensive transforms; avoid setting state for every simple derived value.
- Preserve React Router Outlet context contract and current run loading/errors.
- Poll critical HITL states only when relevant; preserve retry behavior; avoid refetch storms on every frame.
- Render bounded lists; lazy-load inspector detail and images rather than fetching all evidence for every case.
- Screens and UI demos use **existing local mock fixtures**; no fake backend data in the real app.

---

# 8. Implementation work packages with hard acceptance gates

**Core rule:** Codex may continue autonomously through normal implementation tasks, but must first understand local changes. Make reviewable commits ONLY if user has authorized commits; **do not push without permission**. The user wants one coherent redesign and a deep end-to-end test, not hand-wavy estimates.

## UI-00 — Inventory, baseline and snapshot truth

Files to inspect: `AGENTS.md`, `MKT.md`, `docs/CURRENT_STATE.md`, `docs/hitl/README.md`, `apps/web/src/app/router.tsx`, `styles.css`, all imported styles and layout components, current e2e specs. Inspect `git status --short` and newer HEAD before edits.

Deliverable: route/component inventory, computed style issues, current screenshots on **local synthetic/demo only** at desktop/tablet/mobile, tracked functionality checklist, list of existing failing tests. If environment unavailable, mark unverified and do not invent baseline pictures.

**Gate:** No lost uncommitted changes; agreed list of critical routes/states; baseline exists or blocker recorded.

## UI-01 — Foundation and design system

Edit `tokens.css`, `base.css`, `product-theme.css` as needed, preserving CSS variable aliases, fonts, focus styles and existing components. Add theme only after inheritance and portals tested. Update UI primitives rather than every consumer.

**Gate:** new palette contrast audited on sign-in, forms, tables, dialogs and status labels; no invalid vars/contrast regressions; existing frontend build/typecheck green. If dark mode is implemented, verify all those surfaces in both themes.

## UI-02 — Workspace shell and navigation

Edit `layouts/AppShell.tsx`, `styles/workspace.css`, command menu if needed. Compact sidebar, active states, workspace switcher, breadcrumb, readable header, account actions, mobile drawer with focus trap/Escape/scroll lock/focus return. All existing routes and permissions unchanged.

**Gate:** keyboard traverse; desktop/mobile no horizontal overflow; workspace switch keeps cache/user isolation; direct links still work; logout button functional.

## UI-03 — Overview, application and target views

Edit `OverviewPage.tsx`, applications and target pages and their scoped CSS only after inspecting each component. Keep real data and authorization labels prominent; meaningful onboarding empty state.

**Gate:** new/empty/populated/error, correct owner/viewer actions, nonsecret target policy visible, no fake status.

## UI-04 — Test creation: prominent composer, exact safety options

Edit `NewRunPage.tsx` and scoped styles. Organize primary brief and target + progressive advanced controls. Safety/auth verifier/approval options stay explicit and visible when required. No backend changes unless fixing a proven API/UI mismatch.

**Gate:** create draft payload equivalent before/after; no silent auth weakening; cannot submit unauthorized target; no duplicated run creation; keyboard/form screenreader pass.

## UI-05 — Run, case, evidence and findings workbench

Edit `RunLayout.tsx`, `RunFlowPanel.tsx`, `FeatureCases.tsx`, run overview, journey detail, findings/evidence/report pages and styles in reviewable passes. Preserve statuses, source provenance, evidence URLs and all routes. Use compact run subnav and contextual inspector.

**Gate:** deterministic versus legacy accurately represented; evaluation pending/inferred mismatch/blocked statuses correct; opening supporting step/evidence works; counts reconcile with backend fixtures; mobile usable.

## UI-06 — HITL priority interrupt, safe takeover and approval

Edit `HumanActionPage.tsx`, `HumanBrowserViewer.tsx` **presentation only**. Add prominent awaiting-human affordance in `RunLayout`. Separate approval workflow from browser takeover. Preserve and test claim, connect, reconnect, renew, Release retry, cancel, approve, reject and expiry states.

**Gate:** no exposure of tickets/passwords; no duplicate mutation; browser pointer mapping exact after responsive resize; keyboard focus accessible; disconnection doesn't imply Release; hard failure shown as failure, never success.

## UI-07 — Knowledge/settings/auth/public visual consistency

Edit scoped pages where necessary. Font and palette consistency; correct accessible form/error states. No functionality rewrite.

**Gate:** route coverage and permission checks, no broken forms or OAuth redirects.

## UI-08 — Design adversarial critique and second independent review

Before large-scale finish, take visual screenshots of representative **actual rendered routes** in two themes and at multiple widths. Evaluate section 9. Resolve all critical failures, iterate, then rerun independent review with a new critical checklist.

**Gate:** every P0/P1 issue resolved; findings documented with before/after and proof; no invented screenshots.

## UI-09 — Deep local E2E and regression validation

Run the real React UI + API + local infrastructure + workers with synthetic controlled target and fixture. Follow section 10. Preserve separate categories: **frontend integration**, **HITL feature integration**, **application testing engine results**, **security safety**.

**Gate:** complete supported path verified or exact blocker documented; no "all tests passed" if Kafka/model provider not available.

---

# 9. Mandatory DOUBLE-REVIEW of design before accepting it

**The original design idea is NOT final until two reviews happen.** One review challenges aesthetics/function before implementation; the second reviews *actual running screens* after implementation.

## 9.1 First pass — falsify the design proposal

Ask a critical reviewer/agent (or have Codex critically review independently):

1. Does MarketTwin still look like a recognizable testing/evidence product, not a generic assistant?
2. Can a user tell within 5 seconds whether a run is **waiting for their input**?
3. Is there only one primary CTA per task surface, with approval distinctly secondary/critical?
4. Can a reviewer identify whether a failed assertion is **inferred** or grounded in an approved requirement?
5. Can a user go from a case verdict to the exact step, screenshot and source with at most two meaningful navigations?
6. Are high-risk target authorization and `requires_auth` controls genuinely understandable, not hidden as minimalist art?
7. Does the interface survive long names, large IDs, 100+ cases, invalid API responses, zero data and evaluation pending?
8. Can a keyboard-only operator claim, use and release HITL without accidental duplicate action?
9. Is the layout readable at 320, 375, 768, 1024 and 1440 CSS px, **and** at 200% zoom?
10. Are tokens and UI states distinguishable using more than color? Are theme contrast claims accurate on real surfaces?
11. Is a right inspector stealing necessary width from a browser viewer or report reading view?
12. Is there any "AI slop": needless orbital graphics, confusing glow, same-size widget grid, too many pills, fake activity or unhelpful jargon?
13. Is the CSS implementation smaller/simpler than a redesign that just adds more overrides?
14. Does the update preserve every current route, permission, API mutation and deep link?
15. If the UI is beautiful but user can't resolve a blocked run, **reject** it.

**Pass criterion:** write specific deficiencies and amendments, not "looks great." Scores are subjective, not usability-study evidence.

## 9.2 Second pass — test real rendered UI after changes

- Capture real screenshots from local seeded fixture under current working commit, not design-tool mockups masquerading as production.
- Compare desktop 1440x900 and 1280x800, tablet 768x1024, mobile 390x844 and 320x700, light and dark; browser zoom 200%.
- Review content hierarchy, affordances, typography, responsive cropping, scroll, contrast, keyboard, screenreader names, mouse/pointer mapping.
- Inspect HITL takeover, approval pending/rejected, network disconnect, evidence detail, loading, empty, API error, denied role, waiting for evaluation, 100-case synthetic list, long names.
- Run `axe-core` and Playwright keyboard paths. Review false positives manually; automated checker alone is not WCAG certification.
- Conduct a deliberate **AI-slop elimination pass**: remove any ornament that doesn't identify context, state, evidence or a useful action.
- Record defects **and rerun** the same checks after repairs. Do not stop at a marketing screenshot.

---

# 10. Deep end-to-end testing plan AFTER UI implementation

The user requested deep E2E rather than just a static redesign. **This plan authorizes only controlled local synthetic tests and existing expressly approved target permissions**; no real customer secrets, external sites, payments or unauthorized effects.

## 10.1 Test topology and truthful reporting

```text
React/Vite UI → FastAPI Control API → PostgreSQL → Outbox/Kafka → execution worker
       ↕                 ↕                                   ↕
  HITL viewer ← signed worker handoff ← process-local live Playwright context
                                                  ↓
                                       S3/MinIO evidence artifacts
                                                  ↓
                                         evaluation worker/report
```

Before tests verify each dependency is reachable. DB migration readiness must be checked; **do not blindly upgrade a database that contains valuable user data**. The HITL guide documents the local migration chain and required environment. Existing API provider HTTP 401 / missing Kafka / model calls are distinct service blockers, not proof the redesign failed. Never manufacture model autonomy from deterministic fixtures.

Every E2E record must show: test ID, exact route, precondition, persona/role, action, expected observable state, observed actual state, screenshots/evidence *only when safe*, outcome PASS/FAIL/BLOCKED/NOT_EXECUTED, and source commit.

## 10.2 UI route and role matrix

| ID | Scenario | Acceptance |
|---|---|---|
| E01 | Anonymous public routes | `/`, `/how-it-works` load, useful navigation, branding readable. |
| E02 | Login / logout | Only real account workflow; no mock bypass; session redirects persist. |
| E03 | 403 + unauthorized deep link | Cannot see unauthorized workspace or artifact; no secret response in UI. |
| E04 | Desktop/phone nav | Workspace rail/drawer operable, focus return, navigation stable, no page overflow. |
| E05 | Workspace switch | Routes and query caches move to authorized workspace; cross-workspace info not retained. |
| E06 | Applications list/create/edit | Permissions, forms, empty, errors, long names, duplicate prevention. |
| E07 | Target create/authorization | Exact origins and network policies accessible; dangerous configuration not hidden. |
| E08 | Knowledge ingestion/review | Pending/approved/rejected states and source evidence retain meaning. |
| E09 | Tests list | Search/status query persisted; status truth and mobile rows correct. |
| E10 | New test | Target, brief, depth, legacy/deep mode, knowledge, auth and approval payload unchanged. |
| E11 | Run start/refresh | Draft start once, Kafka unavailable state visible, authorized roles only. |
| E12 | Run complete/evaluating | Evaluation pending is not shown as passed or final report. |
| E13 | Run details | Overview/cases/journeys/evidence/findings/report, existing deep links work. |
| E14 | Findings provenance | Inferred mismatch never displayed as confirmed issue; grounded evidence link works. |
| E15 | Screenshot retrieval | Exact authorized artifact loads; cross-user retrieval denied; no broken image swallowing error. |
| E16 | Settings | Profile/workspace/members/security role guards, accessible confirmation. |
| E17 | Unexpected errors | Error/timeout/empty/404 states show recovery paths; no fake success. |

## 10.3 HITL end-to-end matrix (synthetic fixture only)

| ID | Test | Expected outcome |
|---|---|---|
| H-E01 | Authorized protected target triggers login | Run enters truthful `awaiting_human`, agent input/capture fenced. |
| H-E02 | Claim from authorized owner | Single exclusive lease, secure viewer grants scoped to run/browser. |
| H-E03 | Second tab/operator claim | Lease conflict, no second input source. |
| H-E04 | Connect viewer | Same Playwright page/context, not an unrelated user browser. |
| H-E05 | Synthetic login + OTP | Values only through transient viewer; no real credentials anywhere. |
| H-E06 | Release before successful login | Identity not verified, case blocked; not silently resumed. |
| H-E07 | Correct login → Release | Auth role verified, resume with original target limits. |
| H-E08 | Disconnect before Release | No generation mismatch, no accidental resume. |
| H-E09 | Reconnect with fresh ticket | Valid lease resumes viewer input, old ticket denied. |
| H-E10 | Release with viewer still connected | Inputs revoked, verification/resume path works. |
| H-E11 | Release delivery temporary failure | Error shown; same lease can retry safely; no double control. |
| H-E12 | Expired lease | No stale viewer or API authorization; fail closed. |
| H-E13 | Cancel/deny | Honest cancelled/blocked outcome and correct UI. |
| H-E14 | Nonproduction approved synthetic Save | Exact approval required, one dispatch receipt, visible result. |
| H-E15 | Reject Save | No side effect; denial recorded without false product defect. |
| H-E16 | Tampered page/form/generation | Old approval not reusable. |
| H-E17 | Duplicate submit/release/Kafka replay | No duplicated mutation or invented successful run. |
| H-E18 | Worker/browser interruption | Browser lost, run marked blocked/failed with uncertain action protected; no fake resume. |
| H-E19 | Auth reuse across separate cases | Scoped role verified per case; fallback on stale state. |
| H-E20 | Wrong-role user, unapproved IdP | Blocked; no unauthorized navigation. |
| H-E21 | Authenticated evidence privacy | No synthetic canary values in DB logs, artifacts, browser traces, Kafka, API logs, UI toasts, test reports. |
| H-E22 | Viewer responsive interaction | Canvas/pointer mapping correct after resize/scaling; keyboard reliable. |

**Sensitive test runner note:** The existing Playwright e2e configuration uses failure trace/screenshot capture. Configure HITL test fixtures to **disable capture on credential-bearing phases**, and inspect any generated diagnostic artifacts. Do not run external real login flows in visual regressions.

## 10.4 UI performance, resilience and accessibility

| ID | Concern | Test and target |
|---|---|---|
| P01 | Layout | At 320/390/768/1024/1440 widths `scrollWidth <= clientWidth + 1` except intentional bounded tables. |
| P02 | Long data | 120-char names, long origins/IDs, 100-case fixture; text wraps/truncates with a recoverable full value. |
| P03 | Navigation | Deep links, Back/Forward, direct refresh and non-admin route restrictions. |
| P04 | Focus | Skip link, drawer, dialog, tab order, focus restore, focus not obscured. |
| P05 | Screen readers | All primary controls accessible name; status updates have appropriate live region. |
| P06 | Color | Light/dark contrast with actual rendered surfaces; no color-only classification. |
| P07 | Reduced motion | `prefers-reduced-motion` honored; no focus-losing animation. |
| P08 | Polling | No duplicate React Query requests or runaway refetch while HITL open. |
| P09 | Bundles | Track build output delta, route-specific chunks, unused CSS; avoid gratuitous dependencies. |
| P10 | LCP/INP/CLS | Lab measure key pages under repeatable throttling, then use p75 Core Web Vitals for real traffic when available. Targets: <=2.5s / <=200ms / <=0.1; report measured values, not assumed passes. |
| P11 | Dark mode | No unthemed modal portal, tooltip, select, chart or browser overlay. |
| P12 | Repeated action | No double-submit, no double approvals, no inadvertent run restart on navigation. |

## 10.5 Negative/abuse cases

- Unauthenticated client attempts viewer WS and approval API; deny.
- Tampered viewer ticket, lease ID, generation, expired state and Origin header; deny.
- Browser goes offline between claim and Release; fail closed with error and retry policy.
- Viewer loses network while user is typing; disconnected input should not queue/replay in another session.
- User switches workspace during an active view; ensure lease access is revoked or clearly handled, no leaked run information.
- Authorizing synthetic approval does not expand target network permissions or allow payments, destructive actions, real emails/messages.
- Backend returns no evaluated report yet; UI displays "Evaluation pending" not "Pass".
- API 401/403/404/409/500 error handlers preserve truthful status and clear next action.
- Malformed/escaped text in application names, knowledge snippets, reports, logs and titles never executes as HTML.
- Expensive case/event lists cannot freeze the main UI or destroy browser control responsiveness.

---

# 11. Exact repo commands / test protocol for Codex

Adapt to local platform and `AGENTS.md`; these commands are proposed, **not executed by this document author**.

```powershell
# Baseline, no file loss
pwd
git branch --show-current
git rev-parse HEAD
git status --short

# Frontend ordinary checks
npm --workspace @markettwin/web run typecheck
npm --workspace @markettwin/web run test
npm --workspace @markettwin/web run build

# Browser E2E: only after local services and synthetic test accounts exist
npm --workspace @markettwin/web run test:e2e -- --project=chromium
npm --workspace @markettwin/web run test:e2e -- --project=mobile-chromium

# Existing HITL local setup and scripts: see docs/hitl/README.md
# Check migrations before altering a local database containing data.
# Avoid external application testing unless user separately reauthorizes it.
```

**Playwright e2e file placement:** `apps/web/e2e/` already exists and contains `smoke.spec.ts`, `ui-workflow.spec.ts`, `run-records.spec.ts`, `run-flow.spec.ts`, `route-protection.spec.ts`, `knowledge-workflow.spec.ts`, `public-pages.spec.ts`, `agent-prompts.spec.ts`. Extend them or add focused `design-regression.spec.ts`, `hitl-visual-safety.spec.ts` where justified. Add screenshot baselines only with stable fixture data and explicit user-friendly update procedure; no secret-bearing artifacts.

**Before full E2E:** run the app from existing README/development commands with Postgres, Kafka, MinIO, Control API, execution worker, evaluation worker and React. Inspect environment readiness and health individually. If a dependency is unavailable, mark relevant scenarios **NOT_EXECUTED**, not PASS. If model provider returns 401, record provider-auth blocker separately from UI/HITL failures.

---

# 12. Release criteria and review report (do not game them)

## 12.1 Required for "UI redesign complete"

- [ ] Every route inventory row reviewed; no intentional route or feature lost.
- [ ] Light/dark theme or explicitly approved single-theme alternative coherent; exact existing fonts preserved.
- [ ] No generic AI-template decorations, fake KPIs or chat-first misrepresentation.
- [ ] Desktop/tablet/mobile layouts verified, with graceful 320px/200% text scaling.
- [ ] WCAG 2.2 AA issues in affected workflow resolved or documented blocker.
- [ ] No contrast or focus regressions; semantic accessible controls.
- [ ] Run mode and result/evidence/HITL semantic truth preserved.
- [ ] React/TypeScript build, focused unit tests and visual smoke suite green.
- [ ] CSS specificity/dead style burden tracked; no unsupported dependency added.

## 12.2 Required for "deep E2E validated"

- [ ] UI → API → Postgres → Kafka/outbox → execution worker → Playwright → evaluator → report verified with actual synthetic evidence.
- [ ] HITL takeover → login → release → verifier → protected cases verified end to end.
- [ ] Approval/deny, reconnect/disconnect, stale leases and duplicate effects exercised.
- [ ] Actual screenshots/artifacts reviewed **without secret-bearing content**.
- [ ] All test outcomes enumerated PASS/FAIL/BLOCKED/NOT_EXECUTED with reproducible steps and run IDs.
- [ ] H12 separate release/security checklist acknowledged. **Local E2E green != production certification.**

## 12.3 Standard Codex completion report

```text
BASELINE: branch, HEAD, dirty-file preservation
DESIGN: selected direction, changes after first and second critique
CODE: exact files created/modified, tokens/components/routes, unchanged backend contracts
VISUAL: real tested viewport/theme matrix, screenshot artifact paths, major defects/fixes
QUALITY: commands and exact pass/fail counts, lint/types/build/a11y findings
E2E: case-by-case outcome with env/service conditions; HITL step-by-step evidence
SECURITY: viewer privacy and action-control regression results, remaining limitations
UNVERIFIED: honest list of blocked cases and reasons
NEXT: exact remaining steps to user verification; no guessed ETA
```

If tests are not executable because of shell/model capacity, do not fabricate success. Preserve work, diagnose the environment and prepare reproducible commands for the next session.

---

# 13. Independent final red-team review: known tradeoffs and chosen mitigations

This is the *second* conceptual review of the proposed design, after competing directions were evaluated. It is **not** a substitute for reviewing live rendered screens.

| Counterargument / issue | Why it matters | Final correction |
|---|---|---|
| Light UI might feel too consumer for observability | Arize/Neatlogs are dense and technical | Keep technical inner inspectors dense and structured, with selectable dark mode; not fake terminal chrome. |
| Too much minimalism can hide critical actions | HITL approval/login and auth policy are safety-critical | Use explicit contextual interrupt/action; never rely on sidebar-only link. |
| Large main column may waste desktop space | Evidence debugging needs side-by-side comparison | Use a responsive inspector for investigative routes, not all routes. |
| Permanent right inspector can squeeze browser canvas | Pixel mapping and sign-in readability suffer | HITL viewer uses dedicated large surface; inspector collapses. |
| Reusing existing token names might preserve old visual glitches | Existing CSS has many overrides | Map aliases, audit import cascade and migrate route-by-route, remove redundant rules after verifying. |
| Dark mode can double implementation time and bugs | Complex components and portals inherit theme inconsistently | Build coherent light foundation first; deliver dark only after real contrast/regression verification. |
| “One primary action” can imply hiding permissions | Test creation needs safety visibility | Advanced UI only for optional complexity; auth/approvals always visible when applicable. |
| Dense rows might be inaccessible on mobile | Small hit targets/text, horizontal overflow | Use adaptive stacked row/detail, >=44px practical touch targets where possible, readable text. |
| Hover-only actions mimic Perplexity but harm access | Touch/keyboard cannot hover | Every hover affordance has visible keyboard/touch alternative. |
| Agent observability metaphors can mislead | Deep mode currently executes deterministic cases | Explicitly show execution mode and source evidence; no misleading animated "thinking". |
| No new backend means some UX metrics are missing | Can't truthfully show unmeasured health/latency | Omit metric until sourced, rather than add invented API or hardcoded numbers. |
| Local E2E results might exaggerate release readiness | HITL production security/IdP compatibility still unverified | Label local pilot and individual blocked scenarios; hosted NO-GO until separate release assessment. |

**Final recommended direction after critique:** *Quiet Precision* with a **light-first neutral canvas**, quiet teal only as an accent/interactive signal, Instrument Sans + IBM Plex Mono, compact developer-grade inspectors, meaningful states, explicit HITL affordance, source-anchored findings, and measured performance. This is a *deliberate MarketTwin identity*, not a direct clone of Perplexity, Arize or Neatlogs.

---

# 14. Paste-ready Codex implementation instruction

> You are implementing a real frontend redesign in the existing MarketTwin repository, **not** generating a mock screenshot or building a clone of another company's UI. Treat this attached Markdown document as the design/research and E2E acceptance specification.
>
> First inspect the latest local branch/HEAD/status and preserve every user change. Read `AGENTS.md`, `MKT.md`, `docs/CURRENT_STATE.md`, `docs/hitl/README.md`, the current router, layouts, CSS import cascade, existing font imports, tests and role guards. The audited remote commit `339a4b30` may be older than local HEAD.
>
> Implement the selected **Quiet Precision** evidence-first workbench, keeping current **Instrument Sans Variable** and **IBM Plex Mono**. Draw structural inspiration from Perplexity's clarity and sidebar, Arize's trace/evaluation inspection and Neatlogs' timelines, but create a distinct MarketTwin design. Avoid AI slop: no gradients/orbs/glass/cards everywhere/fake KPIs/generic chatbox/fake progress. No broad redesign of backend or framework replacement.
>
> Follow packages UI-00 through UI-09 in dependency order; work autonomously through ordinary coding/testing. Preserve all routes, React Query semantics, user permissions, protected artifact access, HITL security, browser viewer coordinate mapping, lease/reconnect/release controls, source-grounded assertion meaning, and deterministic-versus-model-driven labels. Do not silently change API schemas or current authorized targets.
>
> **Double-review the design:** first critique the proposal against task hierarchy, evidence depth, anti-slop and security; then inspect **actual local rendered screenshots** in multiple viewports/themes/states and resolve issues. An attractive landing page alone is not acceptance. Improve accessibility, empty/loading/error states, 200% zoom and responsive behavior. Keep code lean and shared CSS simpler, not larger.
>
> After UI implementation, execute real safe local E2E through React, Control API, database, Kafka, worker, Playwright, evidence and evaluation, using only existing local synthetic fixtures and accounts. Include HITL takeover, synthetic MFA, role verification, reconnect/disconnect, approval/rejection and accurate report. Do not capture secrets in debug traces or screenshots. Distinguish actual PASS from BLOCKED/NOT_EXECUTED; don't claim that deterministic direct fixtures prove autonomous model quality or that local pilot testing proves production security.
>
> Run typecheck, frontend unit tests, build, Playwright desktop/mobile, axe checks, and relevant focused backend regressions; fix observed failures. Report exact modifications, test commands, results and remaining blockers. If services or execution tools fail, diagnose and record missing E2E evidence; do not fabricate success.
>
> **No push/deploy, new paid services, real customer credentials, unauthorized external targets or irreversible DB changes without explicit user permission.** Continue implementation without artificial phase-by-phase approval requests for routine work. At the end, give the user precise local setup and manual verification steps.

---

# 15. Reference list and evidence provenance

All competitor observations above are sourced to their **product or official docs** except where explicitly described as design interpretation. These sources establish **patterns and capabilities, not permission to replicate copyrighted UI**:

1. [Perplexity — 2025/2026 streamlined messages and sidebar](https://www.perplexity.ai/changelog/what-we-shipped---december-5th)
2. [Perplexity — redesigned sidebar](https://www.perplexity.ai/changelog/what-we-shipped-may-2nd)
3. [Arize AX — explore traces, spans, sessions](https://arize.com/docs/ax/observe)
4. [Arize AX — evaluations on traces](https://arize.com/docs/ax/evaluate/online-evals/log-evals-to-traces)
5. [Arize AX — January 2026 UI improvements](https://arize.com/blog/new-in-arize-ax-january-2026-updates/)
6. [Arize Phoenix overview](https://arize.com/phoenix)
7. [Neatlogs — dashboard overview](https://docs.neatlogs.com/docs/quickstart/explore-dashboard)
8. [Neatlogs — tracing and span detail](https://docs.neatlogs.com/docs/features/traces)
9. [Nielsen Norman Group — 10 usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/)
10. [NN/g — complex application heuristics](https://www.nngroup.com/articles/usability-heuristics-complex-applications/)
11. [W3C — WCAG 2.2](https://www.w3.org/TR/WCAG22/)
12. [W3C — WCAG 2.2 new requirements](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/)
13. [web.dev — Web Vitals](https://web.dev/articles/vitals)
14. [web.dev — threshold methodology](https://web.dev/articles/defining-core-web-vitals-thresholds/)
15. **Repository code**: audited from authenticated GitHub connector under branch `feat/batch-1-aws-observability`, commit `339a4b30326ed4cf0c47c7238e63e4387c6d0fac`; key paths specified in §2. These code findings are not statements about a later uncommitted local workspace.

## Final boundary

This plan provides a comprehensive **researched design and implementation contract**, with an independent conceptual critique. **It does not mean the UI has been changed**, nor that the complete MarketTwin end-to-end test has been executed. Codex must perform implementation, live visual validation and real local E2E, and report the observed evidence precisely.
