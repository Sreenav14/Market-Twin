# Light theme and workflow clarity

Date: 2026-10-04

## Study

The latest UI request supersedes the earlier dark-theme preference. This change makes the existing application light by default; it does not introduce another theme configuration system.

The audit reviewed the shared color tokens, all hard-coded color references, overview/knowledge screens, sign-in styles, existing accessibility workflows, and the prior enterprise UI findings. The color scan found that application colors already came from one token file. That makes a consistent conversion possible without replacing components or scattering page-specific colors.

The underlying comprehension problem was separate from color: users had to infer what creates a draft, what starts execution, where generated knowledge becomes approved, and why completed execution does not immediately imply a saved evaluation. The implementation therefore clarifies these boundaries in the product rather than claiming a palette alone fixes usability.

## Research

[Carbon's theme guidance](https://www.carbondesignsystem.com/building-blocks/foundations/themes/overview) describes preserving semantic token roles across themes. Its [color/layering guidance](https://www.carbondesignsystem.com/building-blocks/foundations/color/overview) distinguishes light page backgrounds from component layers. MarketTwin keeps its existing semantic roles and uses a pale neutral workspace background, white surfaces, and restrained slate/blue controls.

[WCAG contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) requires sufficient contrast for normal text, including placeholder and hover text. The palette was checked numerically before browser accessibility testing. Meaningful statuses continue to have text labels as well as color.

[NN/g's recognition-versus-recall guidance](https://www.nngroup.com/articles/recognition-and-recall/) supports making relevant context visible where users need it. The overview now explains the execution stages, and ingestion/review copy spells out approval and application selection instead of requiring users to remember the architecture.

These sources inform an expert review; this is not a claim of formal user research or that all users prefer light interfaces.

## Changes and reasons

| Area | Change | Reason |
| --- | --- | --- |
| Shared theme | Light native controls; gray page, white surfaces, slate text, blue actions; status-specific light backgrounds. | Consistent readable surfaces across workspace, dialogs, source review, forms, and sign-in. |
| Boundaries | Add a quiet sidebar/content divider and retain stronger borders on interactive inputs. | Users can distinguish navigation, document content, and editable controls. |
| Overview | Explain Plan → Execute → Supervisor collection → Evaluate. | Make the workflow visible without exposing framework internals or inventing live progress. |
| Starting tests | State that creating a test saves a draft and Start runs its agents. | Distinguish configuration from execution. |
| Completion count | Rename the overview count to Execution completed. | Avoid implying that every completed execution already has an evaluation report. |
| Knowledge entry points | Mark knowledge optional and explain ingest → review/approve → attach → select. | Clarify that knowledge is workspace material whose use is explicitly selected for an application/test. |
| Ingestion | Explain draft generation and background processing after upload. | Make upload completion and model processing distinguishable. |
| Generated categories | Add concise explanations for application knowledge, artifacts, Skills, and evidence. | Explain the purpose of each output without forcing every source to generate every category. |
| Processing text | Correct the progress label's undefined color token to the existing muted-text token. | Keep status text readable and consistently themed. |

## Palette checks

Representative computed contrast ratios:

| Pair | Ratio |
| --- | ---: |
| Primary body text / white surface | 15.75:1 |
| Secondary text / white surface | 7.84:1 |
| Muted text / sidebar | 4.90:1 |
| White label / primary button | 7.23:1 |
| Success label / success background | 5.72:1 |
| Failure label / failure background | 5.88:1 |
| Warning label / warning background | 6.13:1 |
| Information label / information background | 6.41:1 |
| Interactive input border / white surface | 3.65:1 |

Decorative separators use a lighter border; editable controls and focus indicators use stronger colors. Existing fonts, touch sizes, responsive behavior, keyboard focus, and reduced-motion behavior remain in use.

## Changed files

- `apps/web/src/styles/tokens.css`: light semantic palette and native color scheme.
- `apps/web/src/styles/base.css`: correct the processing-label text token.
- `apps/web/src/styles/workspace.css`: restore the sidebar/content divider.
- `apps/web/src/styles/enterprise.css`: responsive process explanation, generated-category descriptions, and spaced knowledge utility links.
- `apps/web/src/pages/overview/OverviewPage.tsx`: workflow explanation, draft/Start distinction, optional knowledge path, and execution-completed count.
- `apps/web/src/pages/knowledge/IngestionPage.tsx`: distinguish uploading, background generation, and draft knowledge.
- `apps/web/src/pages/knowledge/ReviewKnowledgePage.tsx`: explain approval, application attachment, and test selection.
- `apps/web/src/pages/knowledge/KnowledgeResult.tsx`: explain the role of each generated output category.

## Verification

Rendered knowledge and sign-in workflows passed on desktop and Pixel 7 mobile: **4 tests passed**. The knowledge flow includes seven WCAG/reflow checks per device, upload/background processing, evidence review, explicit approval, application attachment, search/filter/reset, and approved-only test selection. Desktop knowledge review, desktop sign-in, and mobile knowledge-library screenshots were inspected. The light palette remains consistent across native inputs, disabled controls, semantic statuses, source disclosures, and navigation.

TypeScript passed after the overview change, and changed files passed `git diff --check`. The initial browser run caught an incorrectly placed Overview JSX block before release; it was moved inside the page fragment before the passing knowledge/sign-in run.

Overview verification passed **8 desktop/mobile cases** covering keyboard/quick navigation, empty workspaces/tests, 320px long-content reflow, and reduced-motion behavior. Screenshot inspection then caught adjacent knowledge utility links with no spacing rule. After adding scoped flex spacing/wrapping, the final navigation and 320px checks passed again: **4 cases in 33.3 seconds**. Desktop and mobile workspace screenshots were inspected.

An intermediate Overview run stopped at Vite's missing-import overlay while the parallel per-test Evaluation page was being created; it did not test the Overview's rendered behavior. The passing runs occurred after that import resolved. A focused Vitest attempt hit the local 60-second worker-startup timeout and ran zero tests; this is distinct from a failing assertion. Final combined unit/build results belong to the integration verification.

## Scope

The light-theme and knowledge-copy changes do not alter source parsing, approval rules, workspace permissions, saved knowledge snapshots, application attachment, or execution/evaluation data. Results and evaluation remain separate per-test views, with workflow implementation documented separately. Temporary verification screenshots are inspected and removed after the checks; stored application evidence is preserved.

## Temporary-file cleanup

After visual inspection, removed `.tmp_light_ui`, `.tmp_light_overview`, and `.tmp_light_overview_final`: 20 generated PNG screenshots and three Playwright result JSON files. Each resolved directory was checked to remain inside the workspace and not be a linked directory before native PowerShell recursive deletion. The three directories no longer exist. No object-storage originals, application evidence, or durable tests were removed.
