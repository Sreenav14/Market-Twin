# Enterprise UI review and repository cleanup

Date: 2026-10-04

## Scope and method

This review concerns the existing MarketTwin workspace interface, especially the path from ingestion to review, approval, application attachment, and test creation. The implementation preserves the existing dark palette, fonts, permission checks, processing lifecycle, and approved knowledge snapshots. It does not add a second design system or change the knowledge model's output.

The audit combines a source-level workflow review, published design guidance, browser-rendered desktop/mobile checks, and accessibility checks. It is an expert review, not a claim that users have completed a formal usability study or that one visual style is universally best.

## Research and decisions

[Carbon's data-table guidance](https://www.carbondesignsystem.com/building-blocks/core/components/data-table/guidelines) recommends predictable resource lists with nearby search and filter controls, consistent density, visible actions, and expandable supplementary information. MarketTwin's knowledge library therefore reuses the existing Tests search/filter pattern. Evidence gets native expandable rows rather than a new modal or a deeply nested card layout. Multi-line knowledge rows retain enough room for names and source metadata.

[Nielsen Norman Group's complex-application guidance](https://www.nngroup.com/articles/complex-application-design/) supports keeping important work prominent and making supporting information accessible without leaving the task. This informed the review action rail, linked provenance, and compact empty output categories. The overview now leads with actual test activity and application counts; the knowledge entry points remain available in a smaller utility section.

[NN/g's consistency guidance](https://www.nngroup.com/articles/consistency-and-standards/) distinguishes internal product consistency from common platform conventions. The changes reuse existing buttons, list controls, statuses, routing patterns, and theme tokens. Native links and disclosures provide familiar keyboard behavior. No decorative charts, fabricated statistics, gradients, or additional brand artwork were introduced.

## Findings and implementation

| Finding | Change | Why it helps |
| --- | --- | --- |
| Review knowledge lacked search and status filtering. | Add URL-backed search by knowledge name/source name and filters for needs review, approved, in progress, and failed. | Users can find the set they need and return to the same filtered view. |
| Filtering could leave users with an unexplained empty list. | Add matching/total counts and a clear-filters empty state. | An empty search result is distinguishable from an empty knowledge library. |
| Background list refresh failure replaced already loaded content. | Keep cached library contents visible with a retry message. | A temporary refresh problem does not interrupt review navigation. |
| Generated items appeared as repeated bordered cards, while approval followed the entire result. | Flatten generated items into divided sections and put approval/application controls in a desktop action rail. | Content is easier to scan, and the next action stays near the work. Below 1100px, the rail becomes an ordinary full-width section. |
| Evidence ordinals were plain text and evidence rows exposed only location metadata. | Link each generated item to its evidence row; opening the link expands extracted text or structured JSON. Preserve the original-source link for image/video regions. | Reviewers can inspect the actual grounding without guessing what an ordinal means. |
| Confidence labels could be read as independent verification. | Label these values explicitly as model confidence. | Generated confidence remains distinct from human approval. |
| Skills combined multiple conditions into semicolon-heavy paragraphs. | Render nonempty preconditions, inputs, constraints, outcomes, and failure signals as labelled lists. | Reviewers can check each individual condition while keeping the shared Skill contract intact. |
| Categories with no generated items consumed the same visual space as populated sections. | Keep their absence explicit but use compact empty-category spacing. | Zero Skills remains a valid visible result; the interface does not imply that every source must produce a Skill. |
| Approved knowledge displayed a duplicate availability panel before application attachment. | Use one availability status beside the Applications controls. | The attachment task stays clear without repeating instructions. |
| Overview promoted knowledge preparation before showing actual workspace activity. | Move knowledge entry points into a quiet utility section after the workspace content. | Active tests and applications remain the primary purpose of the overview. |
| The entire generated result was a live announcement region. | Remove the broad live region; retain focused live processing status and library count feedback. | Screen readers are not asked to announce the full generated document after a render. |
| Phone layouts stacked every row action vertically and made source controls full width. | Put library metadata above a horizontal action row, keep pending progress full width, and allow source/Rename/Delete controls to wrap together. | Names remain readable and repeated controls take less vertical space without hiding actions. |

## Changed files

- `apps/web/src/pages/knowledge/ReviewKnowledgePage.tsx`: searchable, filterable library and cached-data refresh behavior.
- `apps/web/src/pages/knowledge/KnowledgeResult.tsx`: section navigation, linked expandable provenance, flatter items, and structured Skill fields.
- `apps/web/src/pages/knowledge/KnowledgeReviewPage.tsx`: approval/application rail and single approved-state indicator.
- `apps/web/src/pages/overview/OverviewPage.tsx`: quieter knowledge entry points.
- `apps/web/src/styles/enterprise.css`: scoped knowledge/overview layout rules using the existing tokens.
- `apps/web/src/styles.css`: imports the scoped stylesheet after existing styles.
- `apps/web/e2e/knowledge-workflow.spec.ts`: extends the real browser workflow to exercise source evidence, status filtering, search, and filter reset.

## Verification

The complete knowledge browser workflow passed on desktop and Pixel 7 mobile: **2 passed** (27.1s and 28.1s). After the final phone density/control refinement, the mobile workflow passed again in **25.3s**. Each workflow checks seven screens for horizontal overflow and WCAG 2 A/AA and WCAG 2.1 AA violations; all checks passed.

The workflow covers source upload, immediate processing status, navigation away and back, linked evidence content, explicit approval confirmation, application attachment, approved-only test selection, search/status filtering, filter reset, and submitted test selection. Desktop review and mobile review/library screenshots were inspected. The added assertions check behavior rather than mirroring CSS implementation details.

The focused knowledge component suite passed: **7 tests** with `npm.cmd run test -- src/pages/knowledge/IngestionPage.test.tsx --pool=threads --maxWorkers=1`. An earlier fork-pool attempt timed out before its worker started and ran no tests; the sequential thread-pool run completed successfully. The knowledge changes passed TypeScript checking, and the changed files passed `git diff --check`. Final combined application build/test results are recorded after integration with the parallel agent/evaluation work.

Browser verification caught an evidence metadata container that became too narrow after conversion to disclosure rows. The container now fills the available width, and the existing width assertion passes. Later intermediate runs also exposed a temporary in-flight route import and an ambiguous test selector after adding title links; both were corrected before the passing runs.

## Boundaries and remaining limitations

The knowledge UI changes do not alter extraction accuracy, model selection, supported media transport, storage retention, evaluation execution, or test evidence. Image/video evidence is reviewed through the original source rather than an invented textual transcript. Approval still requires a nonempty result, write permission, and explicit review confirmation. Search currently operates on the library entries returned by the existing API; server-side pagination remains a separate scale concern.

## Repository cleanup

Removed the following repository-root sample files: `1_PB7v7MmW9NpdNn-_mfTj_A.png`, `dsd-netflix-3.png`, `image.png`, `screenshot.png`, and `numpy.docx`. The four images have no runtime asset references. The DOCX was used by an extraction regression; that regression now generates a generic document with 79 meaningful paragraphs/table parts in pytest's temporary directory, verifies complete extraction, and does not depend on a user-specific binary in the repository root. The first combined test pass caught this dependency before cleanup was considered complete.

Removed nine old `.local/pytest-*` ingestion/architecture directories, seven `.local/knowledge-*-smoke*.json` outputs, `.local/knowledge-test-results.txt`, the obsolete `.playwright-mcp` console log, and three old `tmp/pyright-*.json` diagnostic outputs. Also removed this change's temporary Python/E2E output directories after inspecting their screenshots. Deletion used native PowerShell and verified each resolved target stayed inside its named repository directory; runtime directories and symbolic links were not broadly swept.

Uploaded originals in object storage, application screenshots/videos/traces, execution evidence, runtime artifact storage, Kafka local data, dependencies, useful automated tests, and user-authored architecture documents remain intact. Removed `.knowledge-intro` CSS rules became unused when this change replaced the overview promotion with the compact knowledge utility row.

## Combined integration checks

- Full ordinary Python suite: **345 passed, 12 skipped**. Skips are explicit model-call or local database opt-in checks. Test tracing was disabled for the combined run; the observability regression still uses its own in-memory exporter to verify a model span. An earlier run with globally initialized tracing collided with that test's instrumentor; the isolated and correctly configured combined runs pass.
- Frontend: **23 unit tests passed**, TypeScript passed, and production build passed.
- Browser workflows: knowledge review desktop/mobile, agent YAML editing/new draft desktop/mobile, and test coverage selection/evaluation polling desktop/mobile passed. These use controlled API fixtures and rendered Chromium screens; they do not claim a new real application run was executed.
- Actual environment: all five completed runs inspected had saved evaluation reports. The latest report arrived **31.141 seconds** after execution. The updated API exposes both agent endpoints and retains independent process `/health`. API and idle execution/evaluation workers were reloaded after verifying zero active runs.
- Remaining infrastructure issue: Kafka broker 1 still returns a TLS record-layer error. The execution consumer connected through broker 2. The relay can still be delayed by the broker problem; application health and evaluation availability do not establish that every Kafka broker or the outbox producer is healthy.

Companion implementation notes: [agent prompts and reruns](../AGENT_PROMPTS_AND_RERUNS.md), [evaluation and testing depth](../EVALUATION_READINESS_AND_RUN_SETTINGS.md), and [Persona structured report reliability](../PERSONA_STRUCTURED_REPORT_FIX.md).
