# Results, evaluation records, and evidence review

Date: 2026-10-04

## Problem studied

A completed browser execution and a completed evaluation are different events. Previously, reviewing a run largely depended on the final report being available. That made a completed run with an evaluation still in progress appear to have no useful output. It also made it difficult to distinguish a browser/runtime failure from a product capability that did not meet its success criteria.

The review examined `RunLayout`, the new journey and evaluation pages, `ResultsBoundary`, artifact access/preview rendering, the saved Persona result contract, and report payloads. The implementation uses the existing run navigation and saved data rather than introducing another workspace results library or generating client-side conclusions.

## Design rationale

[NN/g's visibility-of-system-status guidance](https://www.nngroup.com/articles/visibility-system-status/) supports explaining which stage has completed and what is still happening. The interface separates execution completion, supervisor collection, and report availability, so a waiting evaluation does not hide recorded journeys.

[NN/g's recognition-versus-recall guidance](https://www.nngroup.com/articles/recognition-and-recall/) supports keeping criteria, reported outcomes, evaluator rationales, and their evidence together. Users can inspect a decision's basis without memorizing artifact identifiers or inferring it from an aggregate report.

[WCAG's use-of-color guidance](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html) requires meaningful information to have cues beyond color. Execution, product outcome, and verification status have explicit labels. The existing light theme and semantic status colors provide supporting emphasis.

These are design references and an expert implementation review, not formal user research. Browser checks validate specific rendered workflows; they do not establish that every possible report is usable.

## Workflow and responsibilities

The workspace **Tests** navigation remains the entry point. Each run has **Overview**, **Results**, **Evaluation**, **Findings**, **Report**, and **Agents** tabs.

| View | Information shown | Reason for keeping it distinct |
| --- | --- | --- |
| Results | Planned journeys; execution status; product outcome; summary; runtime error; criteria; actions, observations, friction and blockers; saved supervisor-collection notice. | Recorded execution can be inspected before the final evaluation exists. A completed execution can have a failed product outcome. |
| Evaluation | Execution/outcome-check context and saved visual-verification records, with criterion, status, rationale, original Persona report, observed details, step IDs and artifact links. | Shows what the evaluator checked and why, without presenting a Persona's assertion as independently verified. |
| Findings | Evaluator conclusions and supporting references. | Keeps individual findings separate from the raw journeys and individual visual checks. |
| Report | Saved report summary and aggregate results. | Gives a reviewable summary once evaluation is persisted. |
| Evidence detail | Exact artifact identity and an explicit request for a temporary, authorized preview. | Makes provenance inspectable while retaining server-side access checks. |

The `Results` tab uses the `/journeys` route and its dedicated endpoint. It does not require the `/results` report request to succeed. A `409` report response presents **Preparing evaluation** on evaluation/report views. The copy explains that execution has completed, evaluation is separate, and the page checks again automatically. **Check again** also refreshes the report request.

The UI reads saved results; it does not rerun agents when a user visits Results or Evaluation. Starting execution remains an explicit action on a draft test.

## Honest result semantics

| Recorded state | Display | Interpretation |
| --- | --- | --- |
| Journey execution completed, product outcome failed | Execution **completed**, Outcome **failed** | The browser/runtime finished its work; the product did not meet the mission outcome. |
| Journey runtime failed, no outcome | Execution **failed**, Outcome **not recorded**, runtime error shown | The failure is available for inspection without inventing a product verdict. |
| Planned journey has no execution | Execution **not started**, Outcome **not recorded** | The UI does not convert missing execution into a pass or product failure. |
| Visual check `satisfied` | **passed** | The saved evaluator record says the criterion was satisfied. |
| Visual check `unsatisfied` | **failed** | The saved evaluator record says the criterion was not satisfied. |
| Visual check `unverified` | **unverified** | The record lacks verification; it is not treated as a pass. |
| Historical report has no `evaluation_records` field | Detailed checks were not recorded for this report version. | Existing findings and report remain readable, but detailed checks cannot be reconstructed from absent data. |
| Report has an empty `evaluation_records` array | No visual criteria were selected for verification; this does not indicate every criterion passed. | An empty check list is distinct from a historical payload that never recorded this field. |

The visual-check fixture deliberately includes a Persona reporting a criterion as satisfied while the evaluator records it as unsatisfied. Both statements remain visible beside the rationale and exact evidence steps. This verifies that the interface does not silently substitute one judgment for the other.

## Simple agent flow map

Each run view now has an **Agent flow** panel. It presents the saved Meta Agent, the actual planned journey agents, supervisor collection, evaluation, and report in execution order. Connections come from the endpoint's directed edges, and status labels come from saved run data. Visiting the map does not create agents or change the workflow.

The panel is a compact column beside the run content on desktop. On narrower screens it becomes a disclosure above the tabs and starts collapsed, so results remain the main reading area. Journey agents form one phase with individually named Persona/mission nodes inside a list that starts collapsed. Users can expand the phase to inspect each agent's state. This keeps the five-phase map visible without removing access to individual agents, including plans with many journeys.

The browser-tool caption uses **Browser tools · Playwright**. It describes the actual controlled browser implementation without claiming that every historical run used an MCP transport.

The flow request refreshes every five seconds while execution is active, or while a completed execution is still awaiting a saved report. Polling stops for idle drafts, stopped executions and completed runs with a ready report. A change in run status or report availability also triggers a fresh flow query; otherwise stopping polling immediately after a report arrives could leave the map stuck on an older pending-report state. No graph editor, drag-and-drop behavior, or additional graph dependency was introduced.

`apps/web/e2e/run-flow.spec.ts` verifies that a zero-journey planning map updates to two actual journey agents, displays their separate completed/running states, then updates to four agents with the compact disclosure behavior. It checks five high-level phases, directed connectors, mobile default collapse, desktop/mobile reflow, accessibility, and that inspection never requests execution startup.

## Evidence behavior and issue corrected

Evidence detail identifies the full artifact ID and requests access only after **View evidence**. An image preview uses the returned access URL and includes descriptive alternative text. **Back to evaluation** returns to the saved checks.

The review identified that an old successful preview could remain visible if a subsequent refresh of artifact access failed. `ArtifactEvidence` now clears the previous access state before requesting a new preview. An access-denied response therefore displays its error without retaining a stale image or preview link. This is a UI-state fix; the backend remains responsible for authorizing artifacts and issuing access URLs.

The journey view's actions section uses the actual persisted `actions` field from `PersonaReport`/`MultiPersonaExecutor`. An early test fixture used `actions_taken`; comparing it with the source contract exposed the mismatch, and the fixture was corrected before final verification.

## Overall and individual model assessment

Evaluation and Report also display the saved model assessment. Its overall testing-goal verdict, ease-of-use assessment, summary, recommendations, supporting journeys and scope limitations remain separate from the individual visual-check records. The runtime note identifies the configured model and elapsed duration. A historical report without this assessment retains an explicit missing-assessment explanation.

The additional browser fixture deliberately combines a **partial** overall testing-goal result with **difficult** ease of use and an **inconclusive** individual journey. It checks that the summary does not hide uncertainty, that untested flows retain an explicit scope limitation, and that opening **Inspect recorded journey** navigates to the actual saved journey and its runtime error. The same assessment remains accessible in Report.

Visual review caught an identity bug: numbering assessment entries by their array index labeled a partial result for planned Journey 2 as Journey 1. Individual headings now use the recorded Persona/mission names, with the actual journey ID as the historical fallback. The test checks the exact heading and source link together. Scoped assessment spacing also separates the summary, recommendations, limitations and individual details without changing other report sections.

The flow API uses **awaiting report** for an evaluation stage whose completed execution has no saved final report. This avoids claiming the evaluation worker has not started when the UI does not have a durable record of its activity.

## Prompt editor within the flow layout

Adding the side map reduces the width available to per-run content. The prompt editor's old screen-width-only breakpoint could leave its YAML field cramped on an intermediate desktop viewport. Run content now establishes a CSS size container, and the prompt selection/editor layout stacks when that content is at most 680px wide. Selection remains accessible above the full-width editor, including its date filters; larger content areas keep the two-column layout. The existing mobile behavior remains in place.

The existing agent-prompt browser workflow now also runs at a 1100px desktop viewport and verifies the YAML editor is wider than 340px, while retaining Save, persisted edits, filters, validation and rerun-draft checks. Both desktop and mobile workflows were verified. The desktop-width criterion applies only to desktop; a mobile field appropriately follows its narrower screen.

## Verification

The durable browser coverage is `apps/web/e2e/run-records.spec.ts`. It renders the real React application with authenticated API responses mocked at the HTTP boundary. Both desktop Chromium and Pixel 7 Chromium run the same six scenarios:

1. Journey outputs remain visible with report `409`, including completed/product-failed, runtime-failed, and not-started states; expanded details show actual actions and observations. Evaluation transitions from pending to saved through **Check again**.
2. Three visual-check statuses retain exact rationales, Persona assertions, observed details, step IDs and artifact links. The exact evidence link opens the correct artifact, requests access explicitly, renders an actual image, and returns to Evaluation.
3. Historical reports show the missing-records explanation and keep their report accessible.
4. An evaluation with no visual checks displays the explicit scope limitation and keeps its report accessible.
5. Evidence denial displays a clear error with no preview, including denial after an earlier successful preview.
6. A completed model assessment preserves the overall verdict, ease-of-use conclusion, recommendations, scope limitation and configured-model runtime; its individual disclosure links to the exact source journey, and the saved assessment also appears in Report.

Each scenario checks that no execution-start request occurred. Accessibility checks use axe WCAG 2 A/AA and 2.1 AA tags. Reflow checks detect document overflow at desktop and mobile viewport sizes. The Results, Evaluation and evidence preview screens are captured for visual inspection.

Verification completed as follows:

| Check | Result |
| --- | --- |
| Initial Results/Evaluation suite | 10 desktop/mobile cases passed in 1.3 minutes. |
| Combined suite after the flow layout | 11 of 12 passed; the pending-report test raced automatic polling and attempted to click a waiting-view button after that view was replaced. The test now checks **Check again** while still pending, then uses the persistent **Refresh test** action after the fixture becomes ready. |
| Confirmation of flow and pending-report workflows | All four desktop/mobile cases passed in 1.2 minutes. |
| Final compact-map disclosure behavior | Both desktop/mobile cases passed in 33.3 seconds. |
| Final report/graph completion transition | Both desktop/mobile cases passed in 28.1 seconds, including the Report node changing to completed when report polling stops. |
| Completed model-assessment scenario | Mobile passed in 17.7 seconds; desktop focused rerun passed in 14.5 seconds. Evaluation and Report accessibility/reflow checks passed, including exact source-journey navigation. |
| Final model-assessment identity regression | Both desktop/mobile cases passed, in 8.9 and 11.7 seconds, with the exact saved Persona/mission heading and correct source journey. |
| Prompt editor with side map | Desktop at 1100px passed in 13.0 seconds; mobile confirmation passed in 19.3 seconds. Save, date/order filters, persistence, rerun-draft creation, axe and reflow remain covered. An initial test-only desktop width threshold was corrected to apply only to desktop, rather than incorrectly requiring a mobile field to be over 340px. |
| TypeScript | Passed after adding the flow component and its typed run status. |
| Diff whitespace check | Passed. |

Intermediate desktop evidence and model-assessment runs timed out while the application remained at its boot/workspace-loading screen during unusually long browser intervals. Their focused reruns passed without changing the production behavior. This was not treated as proof of a production execution or model problem. The two browser files now cover **14 desktop/mobile cases** in total; all scenarios have passing executions, with the timing corrections and focused reruns reported above rather than represented as one uninterrupted clean run.

Desktop and mobile screenshots were visually inspected for readable phase order, meaningful status labels, criterion/rationale hierarchy, exact evidence preview, and absence of clipped horizontal content. The final compact desktop map shows all five phases within its viewport; journey details can scroll when expanded. All temporary output folders created for these results, flow, assessment and editor checks were removed after coordinated visual review. The durable test fixtures contain only in-memory mocked evidence, not downloaded source files. Application evidence storage and evidence functionality were not removed.

These checks do not execute production agents, evaluate a live model, verify real object-storage permissions, or assert screenshot pixel stability. Those concerns are covered by backend/runtime checks and operational verification separately.

## Relevant files

- `apps/web/src/layouts/RunLayout.tsx`: run tabs, independent run/report state and refresh behavior.
- `apps/web/src/pages/runs/RunJourneysPage.tsx`: persisted journey outputs and supervisor collection.
- `apps/web/src/pages/runs/RunEvaluationPage.tsx`: saved evaluation records and truthful missing/empty states.
- `apps/web/src/pages/runs/EvidenceDetailPage.tsx`: exact artifact inspection route.
- `apps/web/src/pages/runs/FindingDetailPage.tsx`: shared authorized artifact preview and stale-preview clearing.
- `apps/web/src/components/markettwin/ResultsBoundary.tsx`: distinct pending/stopped/error/report states.
- `apps/web/src/styles/run-records.css`: responsive presentation of records and evidence links.
- `apps/web/e2e/run-records.spec.ts`: desktop/mobile regressions for these contracts.
- `apps/web/src/components/markettwin/RunFlowPanel.tsx`: read-only, API-backed agent map and bounded polling.
- `apps/web/src/styles/flow.css`: responsive flow panel and directed connections.
- `apps/web/e2e/run-flow.spec.ts`: dynamic-plan, disclosure, status and layout regressions.
- `apps/web/src/styles/agent-prompts.css`: container-width breakpoint for the prompt editor beside the flow panel.
- `apps/web/e2e/agent-prompts.spec.ts`: existing Save/rerun workflow with intermediate desktop-width verification.
