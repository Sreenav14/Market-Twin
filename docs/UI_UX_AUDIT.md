# MarketTwin UI audit and implementation direction

Audit date: 2026-09-10. Scope: `apps/web`, the supplied UI/UX specification, Control API results contracts, and the deterministic report generator. This is a code and interaction audit, not a study with representative customers. Product recommendations remain hypotheses to validate with users.

## What the app actually contains

The frontend is an existing React 19 / strict TypeScript / Vite application with React Router and Tailwind 4. `app/App.tsx` resolves the authenticated session. `app/router.tsx` maps application, target, study, and settings routes. `AppShell` provides workspace context; `RunLayout` provides the selected study. `lib/api.ts` talks to the real cookie-authenticated Control API. Existing application and target creation and authorization workflows must remain intact.

The shared SQLAlchemy models and worker pipeline now support far more than the original frontend exposes. `api/test_run_results.py` returns an authorized user's completed report and findings, with linked journey IDs, step IDs and artifact IDs. `report_generator.py` produces journey status/outcome counts and finding severity/category counts. These are usable today. It does not return screenshot download URLs, detailed journey steps, live event streams, persona definitions, or a human-control session. An ORM table existing is not the same as a browser-facing API existing.

## Findings from the current implementation

| Priority | Evidence | User impact | Implementation response |
|---|---|---|---|
| Critical | `RunLayout.tsx` disables seven sections; `RunOverviewPage.tsx` says planning is not connected | Users cannot reach results that already exist | Connect the results API and enable Overview, Findings and Report |
| High | `NewRunPage.tsx` tests `authLoading` before a target-fetch error; `RunsPage.tsx` similarly waits for a dependent loader | Failed requests can become permanent loading screens | Resolve upstream errors explicitly and use a shared query lifecycle |
| High | Results are absent from the API client | No completed-study workflow | Typed result contract; distinguish 409 waiting from 403/404/transport failure |
| High | Breadcrumbs are raw path segments | UUIDs and implementation paths replace meaningful orientation | Route-aware labels and navigable parent links |
| High | No skip link; tablet navigation hides text without explicit accessible labels | Keyboard and assistive-technology navigation becomes difficult | Skip-to-content, focus management, labeled controls and responsive navigation |
| High | Most control text is 10–12px; narrow states are dense | Scanning and touch use are harder than necessary | 14px controls, 15–16px reading text, larger touch targets and explicit focus |
| Medium | One compressed global stylesheet mixes tokens, layout and page styling | Changes are difficult to review and maintain | Separate semantic tokens, shared base styling and product layouts |
| Medium | Repeated manual effects and no shared result cache | Duplicate work, lost loading context, stale run state | Query caching scoped to the session, abort support and visibility-aware polling |
| Medium | Identical card treatment for unrelated tasks | Weak information hierarchy | Findings as triage rows, report as a reading surface, study creation as a focused form |
| Medium | Status mapping covers only a subset of states | Timeouts, policy blocks and human action are ambiguous | Explicit lifecycle, outcome and severity semantics |

## Design decisions

Follow the supplied “Evidence Lab” direction: graphite navigation, a bright neutral canvas, cobalt actions, teal evidence references and semantic amber/red states. Instrument Sans carries interface and reading text; IBM Plex Mono is reserved for identifiers. The visual signature is the connection between a study, its findings, and the evidence references behind them. No decorative metrics, stock photography, simulated progress, shaders in working screens, or repeated AI labels.

Use a compact sidebar with a persistent study entry point. Keep the main reading width comfortable. Page titles should identify the current task, not advertise the product. Distinguish three separate meanings: execution status, journey outcome, and finding severity. A completed execution does not mean that the product passed. “No findings” is not proof of usability. Evidence references are not the same as accessible or independently verified artifact contents.

### Primary workflows

1. Choose an application → choose an authorized target → describe a study goal → create study.
2. Open study → understand lifecycle → inspect highest-priority findings → read recommendation and provenance.
3. Open report → read executive summary → inspect journey outcomes and finding distribution → copy a useful summary.

Keep advanced evidence, planning, realtime and takeover surfaces honest until their contracts exist. Preserve their URLs for future integration, but avoid a navigation bar full of dead controls. Never invent a coverage percentage, confidence score or detailed journey from aggregate counts.

## Skills and research applied

The [LinklyAI index](https://github.com/LinklyAI/best-skills) is a discovery/ranking source, not a design specification. Relevant guidance was read at its original source rather than installing the entire ranked catalog:

- [Anthropic frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md): domain-led visual direction, deliberate typography, meaningful composition and a critique pass.
- [Vercel React best practices](https://github.com/vercel-labs/agent-skills/blob/main/skills/react-best-practices/SKILL.md): parallel independent requests, deduplicated client data, modest bundle size, stable effects and responsive inputs. Next.js/server-component rules do not apply to this Vite client.
- [Vercel web-design-guidelines](https://github.com/vercel-labs/agent-skills/blob/main/skills/web-design-guidelines/SKILL.md) and [current interface checklist](https://github.com/vercel-labs/web-interface-guidelines/blob/main/command.md): meaningful controls, visible focus, URL-based filters, recoverable errors, long-text handling and reduced motion. The product spec's sentence case takes precedence over stylistic title-case advice.
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/): accessibility is evaluated through contrast, keyboard use, reflow, accessible naming and focus visibility, not an automated score alone.
- [Playwright trace viewer](https://playwright.dev/docs/trace-viewer): a useful precedent for evidence inspection tied to an action. This does not justify embedding a trace viewer before secure artifact delivery exists.

## Delivery order and boundaries

Implement the spec's UI-1 through UI-6: shared primitives and tokens, shell, New Study, real results, findings and report. UI-7 through UI-10 require the richer APIs explicitly identified as future work in the spec. This frontend update does not create those backend contracts or weaken authorization to make a screen appear complete.

## Validation plan

- Typecheck and production build; inspect bundle output.
- Component tests for result parsing, status semantics and expected waiting/error states.
- End-to-end tests with explicit API fixtures for completed results, waiting evaluation, empty results, failures, readonly permissions, filters and navigation.
- Desktop and mobile checks for overflow, keyboard focus, accessible dialogs, reduced motion and contrast.
- Use fixture data only inside tests, never as a production fallback. Clearly distinguish rendered fixture validation from a live backend integration test.
- Next user-research step: observe product managers and engineers creating a study, finding the most important issue, checking its supporting references, and sharing the report. Measure task completion, time to first useful finding, misunderstanding of simulated-user conclusions and recovery from missing evidence. Avoid claiming usability is proven by code tests.
