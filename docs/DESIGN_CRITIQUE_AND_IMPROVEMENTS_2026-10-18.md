# Independent product design critique and improvements

This review covers the current local code, interaction regressions, and isolated
Chromium renders with synthetic data. It is a critical product review, not an award
endorsement or evidence of user research. The connected browser surface was
unavailable; the application's browser-test setup provided current rendered checks.

The largest weakness was incoherence: dark workspace surfaces, a cream report and
public-page palette, serif promotional headings, and competing gutter rules made
routes feel like separate products. Report ornament also displaced evidence while
some verdicts sounded more certain than their data justified. A distinctive testing
product should make its evidence unusually easy to find and understand.

## Ten improvements, ordered by user impact

| Priority | Problem and consequence | Action and status |
| --- | --- | --- |
| 1 | Routes change palette, fonts and horizontal alignment; users lose their sense of place. | Implemented one shared dark palette and Instrument Sans for UI headings/body, monospace for code/data. Removed light-theme overrides, public variable cycles and hardcoded white surfaces. Main content/topbar share gutter rules; report occupies the same frame width. |
| 2 | Reports can imply a clean product when coverage is zero, unknown or incomplete. | Implemented one evidence-aware verdict model. Unknown coverage means insufficient evidence, unresolved observations require review, and verification language reflects the recorded method. |
| 3 | A finding's evidence link can land on a step that is not loaded. | Implemented automatic bounded pagination to the linked step, missing-step feedback, retry without discarding loaded evidence, and URL/history updates when choosing steps. |
| 4 | Authorization outages look like missing permission; loading looks like an empty application. | Implemented distinct loading, unavailable, unauthorized and ready states with retry. Reauthorization is offered only when absence is known. |
| 5 | Remote-browser controls trap Tab while offline; source tabs have incomplete keyboard behavior. | Implemented ordinary Tab navigation before readiness/after disconnect, associated escape instructions, proper source-tab arrows/Home/End and a single tab stop. |
| 6 | The report repeats a TOC, hero, verdict and KPI cards before evidence. | Implemented a compact result header/count links, removed the redundant rail/hero/KPI row and collapsed method/provenance. Evidence links and substantive sections remain. |
| 7 | Cancelling or leaving a saving form can trigger a later unexpected redirect. | Implemented disabled pending controls and mounted-navigation guards for application/target creation; late completion cannot hijack a later route. |
| 8 | Creating a test exposes owner policy JSON and reports some policy errors against the task brief. | Recommended next: replace handwritten policy JSON with validated action/resource/reset fields and local errors; disclose advanced controls progressively. This review did not change the authorization contract. |
| 9 | SPA navigation can silently discard an unfinished test brief. | Recommended next: accessible discard confirmation or a scoped, recoverable draft. The existing beforeunload handler only covers document navigation. |
| 10 | Presentation language and entrance effects advertise the interface rather than help the task. | Partially implemented: plain task-oriented test-list copy and stable, fully opaque public content. Removed entrance fades after real contrast checks caught unreadable text mid-transition. Further task-copy editing remains. |

## Assessment

- **Originality:** the evidence trail is a useful product distinction. Repeated
  cards, numbered marketing-style introductions and "ledger" language add little
  originality by themselves. Make observed results and their provenance the identity.
- **Craftsmanship:** coherent typography, spacing and states matter more than a new
  page-specific theme. The shared foundation now replaces the competing palettes.
- **Usability:** locating proof, recovering from an unavailable service and retaining
  keyboard control are more consequential than attractive empty states. Those paths
  received executable interaction regressions.
- **Product clarity:** distinguish test completion, verified issues, observations
  and missing coverage. A completed process cannot establish a defect-free product.
- **Accessibility:** keyboard repairs and automated contrast/reflow checks improve
  the tested paths. They do not substitute for a manual assistive-technology audit.
- **Consistency:** public, sign-in, report and workspace now share semantic tokens.
  Layout may vary with the task while retaining a common frame and type hierarchy.

The comparison standard is interaction quality, not copied appearance: Linear's
[documented navigation/search model](https://linear.app/docs/search) demonstrates
attention to repeated workflows; GOV.UK's
[interface writing guidance](https://www.gov.uk/service-manual/design/writing-for-user-interfaces)
emphasizes clear task language and interfaces that require little explanation.
These are reference principles, not claims that this product has reached their quality.

## Verification

- Report model/page: 20 focused tests passed.
- Journey evidence pagination/history/error recovery: four interaction tests passed.
- Source tabs/remote viewer: 23 focused tests passed.
- Application readiness/save navigation: six focused tests passed.
- TypeScript checks passed during these tracks; final integrated build and unit
  results are recorded in SESSION_HANDOFF.md.
- Desktop/phone Chromium checks cover shared frame alignment, fonts, colors,
  document overflow and WCAG-tagged axe rules. Synthetic current renders are stored
  under `.local/design-consistency/`; these are not live target/model tests.
- The first public-page check caught contrast failures during text-fading entrance
  animation. The animation was removed rather than weakening the accessibility rule.

The final consistency checks passed for ten routes at two sizes (20 views). The full
frontend checkpoint passed 137 tests. User's subsequent live-browser priority was
also implemented: full-width viewer, preserved frame aspect ratio, internal scroll
controls and a custom macOS-style arrow with native fallback. A Chromium synthetic
frame test passes width/ratio/cursor checks and proves wheel input does not scroll
the workspace while ordinary scrolling outside still works. Latest viewer and
HumanAction unit batch: 23 passed. No real target browser or credentials were used.
Final TypeScript and production build passed after the viewer changes. The existing
bundle-size warning remains. The owned isolated Vite5199 was stopped afterward.
