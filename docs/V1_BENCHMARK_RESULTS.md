# Controlled benchmark — TASK 04

Status: real-pipeline measurement in progress. No precision, detection, or
production-readiness claim is established by the unit tests.

The fixture is `services/execution-orchestrator/tests/fixtures/v1_benchmark/index.html`.
It runs on loopback port 5191. A deliberately restricted destination uses port
5192, outside the sole allowed origin. No action sends user data or makes a
purchase; the form changes only the local page.

The harness `services/execution-orchestrator/scripts/run_v1_benchmark.py` creates
a distinct authorized local target and TestRun in the existing development
workspace. It calls the actual Meta Agent, browser/persona execution, evaluation,
and report pipeline. It explicitly selects `local_development` for this request;
production defaults and network restrictions remain unchanged. It refuses
non-loopback database or artifact storage endpoints.

| Test case | Expected | Actual | Evidence valid? | Result |
|---|---|---|---|---|
| Working link | Correct Help guide destination | Repeat: all 3 passed; no validation errors | 66/66 repeat objects present | Repeat passed |
| Working form | Display name saved successfully | Repeat: all 3 passed; no validation errors | 66/66 repeat objects present | Repeat passed |
| Disabled primary button | Observable disabled control | Focused repeat: 3 visual confirmations | Exact screenshots 930, 967, 988 manually reviewed; 234/234 run artifacts | Demonstrated for this fixture |
| Missing validation | Required message absent after empty submission | Visual check unverified; no confirmed finding | Relevant image exists but action context not established by image alone | Inconclusive |
| Incorrect navigation | Profile settings instead of Billing settings | One stored visual finding; manual review rejects its sufficiency | Step 768 shows the top viewport, not the destination section | Evidence quality gate failed |
| Missing confirmation | Preview ready absent after Generate preview | Visual check unverified; no confirmed finding | Relevant image exists but transition context insufficient | Inconclusive |
| Ambiguous service state | Inconclusive; no confirmed defect | Second corrected repeat: all 3 inconclusive, zero confirmed defects | 46/46 objects present | Repeat passed |
| Restricted destination | Policy blocked; no confirmed defect | Repeat: all 3 policy_blocked, no product outcomes, only execution diagnostics | 18/18 repeat objects present | Repeat passed |

Start with raw case counts. Review real plans, execution events, physical artifact
objects, exact evidence ownership, journey outcomes, and final report before
changing a row to measured. Repeat relevant cases to assess consistency.

Example commands from the workspace root, using its existing environment:

```powershell
.venv\Scripts\python.exe services/execution-orchestrator/scripts/run_v1_benchmark.py working
.venv\Scripts\python.exe services/execution-orchestrator/scripts/run_v1_benchmark.py broken
.venv\Scripts\python.exe services/execution-orchestrator/scripts/run_v1_benchmark.py ambiguous
.venv\Scripts\python.exe services/execution-orchestrator/scripts/run_v1_benchmark.py policy
```

The first working-case run is `9299d697-d52d-4cd9-abf5-57c47a9f4184`.

It terminated with completed report `b1011bee-6cac-4b5a-9ef1-7903e2e74a21`:
3 personas, 2 missions, 6 completed executions, 21 steps, and 66 artifacts.
All 66 storage objects physically exist with matching recorded sizes. Five
journey outcomes passed. One navigation journey paraphrased an assigned criterion;
the validator retained its original report but correctly made its checked outcome
inconclusive. The sole resulting finding is informational and unverified. There
were no confirmed product findings. The fixture's successful page behavior does
not erase the report contract problem; this needs a repeat measurement.

## Initial broken-case measurement

Run `ef725d32-45ac-4456-bf75-e1ed00c6d8f8` terminated with report
`8c1505f2-459a-4582-a449-4d0973cacae4`: 3 personas, 4 missions,
12 completed executions, 68 steps, and 185 physical artifacts with matching sizes.
Ten outcomes were inconclusive, one partial, and one failed. Its report contains
15 unverified observations and one stored visual issue. Repeated claims are
informational observations, separately classified from the visual issue.

Manual review of that issue's exact image (step 768) found it insufficient: the
viewport does not show the destination region. The seeded wrong destination is
real, but this image does not establish it. Treat the stored confirmation as a
benchmark evidence-quality failure; do not count it as a manually validated
detection. Historical benchmark rows have not been rewritten to conceal this.

The first ambiguous run `ef9bab44-953b-4c96-b621-7f1bfc82c8bf` produced report
`21507862-a3c1-404b-b60f-d2b619dcd5d7`, with 3 completed journeys and 35 physical
artifacts. All outcomes passed and no findings were created. Its planner tested
recognition of uncertainty rather than the product's final delivery requirement,
so it does not satisfy the intended inconclusive-case test. The harness goal now
states that product requirement explicitly; repeat measurement is still needed.

## Small corrections driven by these measurements

- Persona criteria are presented as separate JSON strings and repeated at the
  final-response boundary, to reduce renaming or replacing them with objectives.
- Planner criteria must describe product behavior, not agent reporting rules.
- Suspected missing/wrong visible states should be captured in the relevant
  viewport region, with the exact capture and action steps cited.
- The visual verifier explicitly treats unseen page regions and missing action
  or transition context as unverified.

These instruction changes do not prove improved accuracy. Repeat the working,
broken, and ambiguous cases before assessing the quality gates. TASK 04 remains
incomplete; production readiness has not been established.

## Initial policy measurement and correction

Run `11fecf58-7e65-4c83-9c37-a5a016bf4f1f` produced completed report
`7211e5ed-05a9-4518-bcf2-b5b52d22e8e7`, three passed journeys, no findings,
19 steps, and 40/40 physical artifacts. The network guard blocked the destination,
but the click did not raise a policy error, so no step or journey was marked blocked.
The generated mission also treated observing the block as success. This does not
meet the intended execution-status case.

A real Chromium regression reproduced the missing policy exception. HTTP(S)
link destinations now undergo the existing origin policy check before clicking;
policy errors propagate to the existing recorder. This leaves the original page
intact, does not fetch the restricted destination, and preserves all network guards.
The regression and browser-tool suite passed (16 tests). A full policy repeat is
completed with the intended statuses.

Policy repeat `7e2e0079-8e6f-41fa-bd95-4b1ff35ebeb2` produced report
`78ce3c3e-0b5a-4a26-8b32-963c0b290f10`: all three journey statuses are
`policy_blocked`, product outcomes are null, and all three findings are execution
diagnostics. There are zero confirmed product findings or unverified product
observations. All 18 artifacts physically exist with matching sizes.

A direct repeat of the visual verifier on the rejected step-768 screenshot after
the stricter sufficiency rules returned `unverified`: it could not establish
whether Billing settings appeared elsewhere. This single repeat supports the
specific correction, but does not establish general visual-verifier precision.

## Conditional prerequisite failure

Corrected ambiguous run `a4aeadb9-dcb7-4706-860b-0316be0cf1b9` kept all three
journey outcomes inconclusive and produced 41/41 physical artifacts. Nevertheless,
visual evaluation confirmed three issues for a requirement starting "When final
delivery evidence is present ...", even though the image explicitly says no final
evidence is available. These are false confirmations, not seeded defects.

The existing visual JSON response now requests `preconditions_met`. An unsatisfied
result cannot promote a finding unless that value is strictly true. Absent, false,
unknown, or malformed prerequisite attestations keep it unverified. This reuses
the same verifier/result model and adds no model call or migration. Three failing
regressions reproduced the missing guard; the focused visual suite passed after
the fix. Real repeat `bc1f4a68-5f97-49c2-981f-a4d3654f9764` completed with report
`90ce69b5-aece-4c96-bb8e-f7b499cd7e0e`: all three journeys are inconclusive,
all conditional visual checks unverified, three unverified journey observations,
and zero confirmed issues. All 46 artifacts physically exist with matching sizes.
This repeat meets the intended ambiguous-case check. Working and broken repeats
remain necessary before concluding overall benchmark quality.

## Working repeat and evaluation recovery

Run `13158b2b-4910-4db3-8b47-bcc387c749ee` completed all six journeys with passed
outcomes and no report-validation errors. All 66 artifacts physically exist with
matching sizes. Its initial evaluation attempt failed with S3 HeadObject 403.
Retrying evaluation only under the current development environment recovered:
report `48440812-efb2-406c-8018-69ae385c57d7` completed with zero confirmed
product issues, unverified observations, or execution diagnostics. The same saved
execution evidence was reused. The exact cause of the earlier permission failure
has not been established; this demonstrates recovery, not permanent storage reliability.

## Broken repeat and evidence capture correction

Run `60e65ca1-c914-4950-bfcb-85a5e433d480` completed report
`e28085fd-3f64-4dd3-b60d-02b371c5146c`: twelve completed executions,
64 steps, eight inconclusive and four failed outcomes. All 179 artifacts physically
exist with matching sizes. Evaluation stored one confirmed missing-validation
finding and thirteen unverified observations. Disabled action, wrong destination,
and missing preview were not confirmed. This does not pass the detection gate.

Manual review of step 919 shows the entire empty validation form and no inline
message. The preceding recorded click completed. The screenshot alone cannot
identify the clicked element. Direct diagnostic rechecks of saved validation
images with only owned cited action types/statuses were inconsistent: steps 877
and 919 remained unverified, while 900 returned unsatisfied. Historical reports
were not altered and these diagnostic results do not establish repeatable detection.

The verifier now receives only cited execution step IDs, action types and statuses,
up to the selected screenshot. Failed statuses remain failed and future steps
are excluded. These facts establish action sequence, not clicked target identity
or product success; visual state still comes from pixels. Regression coverage
checks the context boundary. No additional model call or history store was added.

A real Chromium regression reproduced focused capture rejecting a rendered
destination below the viewport. Explicit focused capture now scrolls the requested
rendered element into view, then saves the viewport and its crop. Hidden elements
remain rejected and the crop still derives from the exact viewport, with existing
ownership and network guards. This follows Playwright's documented
[scroll-into-view behavior](https://playwright.dev/python/docs/api/class-locator#locator-scroll-into-view-if-needed).

Focused-capture repeat `87922cc8-56ce-45c0-8353-9d9436162906` completed report
`7ac1b7d5-e784-4756-bef5-22c5bd81ff2f`: twelve executions, 90 steps,
234/234 physical artifacts, three visual confirmations of the disabled control
and fourteen unverified observations. Its brief explicitly requires the primary
action to be enabled and activatable and requests the actual result region.
Disabled-control confirmations agree with fixture ground truth; the other seeded
defects remain unverified. This does not pass the overall detection gate.

The next minimal correction preserves the bounded semantic click target in the
existing ExecutionStep.action_summary. Each locator field is limited to 160
characters; longer targets retain the generic summary, and filled values remain
excluded. The verifier receives this target only for cited owned click steps,
with their actual statuses, before the selected screenshot. Target labels are
untrusted data, not instructions or visual product truth. Failed actions stay
failed. Old generic records cannot establish target identity and are not rewritten.
Regression coverage includes target recording, bounded summaries, excluded filled
values and failed/future-step context. Complete suites pass 232 tests; Ruff and
strict Pyright pass.

Target-context repeat `3d0be5e4-2d8c-40cf-80aa-a033011845b9` completed report
`30624052-db57-46e9-be47-b84330ed5328`: twelve executions, 84 steps,
220/220 physical artifacts, eight inconclusive/four failed outcomes. Four visual
findings were stored (two disabled-control, two billing) and fourteen observations
remain unverified. Manual review rejects billing steps 1065 and 1095 as sufficient
proof of destination mismatch: the relevant destination region is absent. These
are evidence-quality failures, not valid detections. Historical records stay intact.

## Conservative viewport confirmation boundary

Prompt instructions and exact click context did not reliably prevent false
confirmation from a general viewport. A failing regression reproduced this
boundary. The evaluator now downgrades an unsatisfied visual judgment to unverified
when no focused element crop is linked to the selected viewport. It preserves the
observed details, exact references and model explanation with a sufficiency note.
Passing judgments are unchanged; focused evidence still undergoes the existing
visual and prerequisite checks. A crop is a required evidence boundary, not proof
of relevance or correctness by itself. This deliberately reduces detection until
the relevant region is captured; it does not force uncertain absence into a defect.
Complete execution/evaluation suites pass 236 tests, Ruff and strict Pyright pass.

A read-only replay of the target-context run completed in
`.local/v1-visual-boundary-replay.json`, using the real repository/storage/verifier:
thirteen checks, one unsatisfied disabled-control result (step 1023), twelve
unverified. Both rejected billing cases remain unverified. It does not rewrite
reports or create findings and is not a new full-pipeline run.
TASK 04 and the overall detection release gate remain open. User explicitly chose
**continue detection work before UI**. New full region-capture repeat
`ae957cff-0b52-4987-89ab-d43b42b8bd34` is running in shell 21738,
`.local/v1-benchmark-broken-region.log`. Persona instructions capture existing
result containers/controls after the action, not missing expected text, and the
actual destination heading after navigation, not page-top headings/original links.
Brief scopes validation beside the field and preview feedback to its section.
Prompt-construction test and Ruff pass. Actual results remain unreviewed.

Region-capture repeat completed report `c1c27372-d307-44e8-821b-84d899db07d6`:
75 steps, 212/212 physical artifacts, seven inconclusive/five failed outcomes,
four visual confirmations (two disabled-control/two missing inline validation)
and sixteen unverified observations. Validation images 1115/1162 show the full
adjacent field area without feedback after the exact recorded button click.
Navigation images now show Profile settings, but the verifier treats this as an
inline source-page region rather than an established destination. Navigation and
preview checks remain unverified. Overall detection is still insufficient.

After that run finished, the fixture's help/profile navigation was changed to
standalone destination views, preserving the good guide and deliberately wrong
Profile destination. This makes the navigation ground truth resemble normal page
navigation and removes ambiguity from a destination hidden inside the source page.
Two real Chromium ground-truth regressions failed before and pass after this change.
All 238 execution/evaluation tests pass; changed test/harness Ruff/Pyright pass.
Older benchmark failures remain recorded; they used the earlier fixture.
Future runs record fixture SHA256 in the existing configuration snapshot.
Working repeat `b9c94c59-d47b-4988-9037-abf5d6c443dd` is running in shell71677,
`.local/v1-benchmark-working-destination.log`; verify it before the next broken run.
