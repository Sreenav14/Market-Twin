# MarketTwin efficiency: adversarial validation and implementation decision

September 20, 2026. This follow-up tests the [proposed algorithm](ALGORITHM.md) against counterexamples and the installed MarketTwin/ADK code. It supersedes any impression that the original single synthetic selector example established optimal selection or unchanged output quality.

**Decision: proceed first with reversible observation encoding, usage accounting, and better evidence capture. Do not enable lossy selection or history masking by default yet.** The sample demonstrated meaningful transport savings, but also exposed evidence gaps in the existing collector and limitations of the selection objective. No real model quality claim is justified by these offline runs.

## What actually ran

- Four pages rendered in local headless Chromium, with browser network requests blocked. The application's actual `build_observation` and `BrowserActionResult.to_dict` generated the observations.
- Four real ADK runner executions: dense baseline, dense encoded, tiny baseline, tiny guarded encoding. Each used three tool calls and four scripted model turns, the application persona-agent builder and prompt, and the installed LiteLLM adapter's request conversion.
- A deterministic scripted `BaseLlm` replaced inference. No model endpoint was called, and its final text deliberately states an inconclusive scripted outcome. It does not validate a real persona's decisions or a report.
- 250 seeded small evidence-selection instances compared with exhaustive optimization of the same scoring objective.
- 22 research tests and 15 existing observation/tool/persona tests passed. Ruff passed for the research directory. Dependency deprecation/experimental warnings were emitted; no test failed.

Reproduce with [validation_run.py](validation_run.py). Full machine-readable results are in [validation-results.json](validation-results.json). These are integration and adversarial fixtures, not a production TestRun or a statistical sample of real websites.

## Measured results

| Measurement | Original | Candidate | Interpretation |
|---|---:|---:|---|
| Dense observation tool-result text | 5,830 tokens | 3,395 tokens | 41.77% smaller; every original payload value round-tripped. |
| Sum of four serialized ADK request measurements, dense fixture | 42,703 | 27,766 | 34.98% smaller including the table explanation and tool declaration in this sample. |
| Tiny observation text, unconditional encoding | 205 | 219 | Encoding increased size by 6.83%; table headers have overhead. |
| Sum of four serialized request measurements, tiny fixture with guard | 7,291 | 7,291 | The guard retained the original format. |
| Exact scoring optimum matched | — | 166 / 250 cases | Greedy selection is not always optimal. |
| Mean relative scoring gap | — | 1.69% | Averaged across this synthetic distribution, including exact matches. |
| Worst relative scoring gap | — | 34.96% | A low mean must not obscure bad individual cases. |
| Budget/dependency/required-item violations | — | 0 / 250 | Mechanical constraints held; this does not establish evidence sufficiency. |

Tokens use `o200k_base`. The request metric tokenizes a JSON representation of the adapter-produced messages and tools; it is a repeatable serialization measure, **not the provider's exact prompt-token accounting or a dollar estimate**. It includes JSON framing/escaping, omits provider-internal framing, and has no image or real output tokens. The tool-result metric tokenizes the actual text produced by the adapter. A production percentage still requires returned usage and invoices where applicable.

The fixed scripted action sequence ensures both formats receive the same work, but also prevents the test from revealing changed model behavior. Identical scripted final text is not evidence of equal language-model performance. The sample uses one fixture tool, not the full production tool suite or database/evaluation-worker flow.

## Three findings that change the rollout plan

### 1. The current collector can omit important visible evidence

The dense fixtures place 90 navigation links above content within a 1280×900 viewport. The current collector sorts candidates by position and takes the first 80. The remaining heading is visible in the browser but absent from `visible_elements`. The full accessibility snapshot contains the later content, but its first 2,000 characters do not.

Consequently the model payload omitted:

- A visible Software testing heading.
- A visible pricing paragraph containing an annual-billing condition and cancellation fee.
- An alert overlay covering part of the heading in the overlap fixture.

Full accessibility text contained the qualifier and alert. The overlay also intercepted a test point in the heading, confirming the fixture's intended overlap. That hit test is a fixture check, not a general visual correctness oracle.

Code locations: [observation cap](C:/Users/sreen/OneDrive/Desktop/MarketTwin/services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/observations.py:295) and [ARIA truncation](C:/Users/sreen/OneDrive/Desktop/MarketTwin/services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/contracts.py:107).

This means matching the current model payload cannot by itself satisfy the user's quality requirement. The baseline has an evidence blind spot. Fix capture coverage before assuming pruning is harmless. Preserve a complete canonical inventory, explicit truncation metadata, and a way to retrieve omitted visible regions. Capture meaningful text blocks as well as controls, and keep alerts, dialogs, failures, and relevant surrounding context represented. The model-facing selector should operate after this capture stage.

### 2. A correct optimizer can still select the wrong information

A constructed case gives the selector a visible price and an unlabeled billing qualifier. It keeps the price and drops the qualifier even though both fit the available budget. Under the supplied relevance objective, the qualifier has no reward and incurs a token penalty.

An exact solver would not repair that scoring mistake. The bottleneck is the definition and recognition of necessary evidence, not just search quality. Label dependencies such as price/currency/period/conditions together, preserve failure evidence, and evaluate against independently labeled defects. An unknown defect may lack any label, which is why context expansion and discovery coverage remain necessary.

Even when the scoring function is accepted, greedy selection can lose. A simple budget-10 example offers one item costing 6 with value 12, and two items each costing 5 with value 9. Greedy chooses value 12; the exact solution chooses value 18. Best-single fallback does not fix this.

Use exhaustive optimization to audit small cases offline. If considering it at runtime, profile the actual tokenizer and bundle count first; the nine-item synthetic timing does not justify exponential enumeration for 80 elements. More sophisticated optimization still cannot guarantee correct downstream judgments with a poor objective.

### 3. Reversible encoding needs its own cost and quality checks

[compact_observation.py](compact_observation.py) stores shared element field names once and then ordered rows. It preserves all values, ARIA, errors, step IDs, and other payload fields. Unknown element schemas retain the original representation. A decoding check confirms equality after JSON normalization.

The ADK callback deep-copies request contents before changing them, preserving original session events. Tests and runner checks verify tool-call IDs and result pairing survive. A short schema explanation is added only when needed.

The guarded callback measures the original and candidate whole requests with the same local measurement function, keeping the original if the candidate is not smaller. This fixes the tiny-payload regression and includes the explanation's overhead. The guarantee is limited to that measured serialization, not future provider billing or model behavior. Measurement/conversion adds local compute and should be profiled on production-sized traces.

Reversibility proves data preservation, not equal model comprehension. A real model could misread a table or lose grounding accuracy. This requires a real-model comparison before enabling it by default.

## Concrete implementation sequence

| Order | Change and integration point | Acceptance requirement |
|---|---|---|
| 1 | Account for usage on each final model response in [journey_executor.py](C:/Users/sreen/OneDrive/Desktop/MarketTwin/services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/journey_executor.py:181), plus planner and verifier calls. Record model/version, attempts, input/cached/output/reasoning fields and known/unknown cost separately. | No duplicate counting of streaming usage or overlapping fields; missing usage stays unknown. Attribute retries rather than assuming only a final success consumed resources. |
| 2 | Persist full structured observations alongside existing artifacts in [step_recorder.py](C:/Users/sreen/OneDrive/Desktop/MarketTwin/services/execution-orchestrator/src/markettwin_execution_orchestrator/persistence/step_recorder.py:73). Revise [build_observation](C:/Users/sreen/OneDrive/Desktop/MarketTwin/services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/observations.py:42) to separate complete capture from bounded presentation. | Dense heading, qualifier, and alert fixtures become observable/retrievable. Retain source version, timestamp, order, and privacy scope. |
| 3 | Inject a request compiler through the persona runtime factory or [agent builder](C:/Users/sreen/OneDrive/Desktop/MarketTwin/services/execution-orchestrator/src/markettwin_execution_orchestrator/agents/persona_agents.py:12). Start with reversible encoding only, disabled by default. | Shadow compilation leaves sent requests unchanged. All values round-trip, existing events remain unmodified, and actual requests get smaller on applicable traces. |
| 4 | Run paired real-model evaluations with identical study coverage and an independent defect oracle. | No observed regressions on the agreed suite in recall, false passes, supported findings, criterion completeness, or persona fidelity. Report repeats and confidence intervals; never equate a small suite with universal proof. |
| 5 | Add recoverable bounded history and evidence selection separately, each behind its own flag. | Preserve transient errors and historical defects, validate fresh action targets, demonstrate recovery from omissions, and pass the same quality suite for each change. |
| 6 | Add host-side call/budget controls and mode-specific deterministic execution. | Exhaustion is explicit and never a false pass. More incomplete runs count as a regression. Persona studies must retain genuine navigation/discovery behavior. |

Keep the Python browser boundary and ADK. There is no evidence here that replacing the framework would be a better first move. The offline sample establishes that its before-model hook can transform request copies and preserve session history. The prototype uses the installed adapter's private conversion helper only as a test seam; production should wrap a stable application-owned measurement boundary and pin/test dependency upgrades.

Do not reduce personas, missions, visual verification, or output limits to make the first savings chart look better. Changing coverage is a distinct product decision. Lower output caps can truncate evidence-rich reports; shorter text is not automatically more precise. Use the existing deterministic report generation and validate criterion/evidence structure.

## What “no compromise” means for release

Set the release gate to no accepted quality regression, not to a desired percentage reduction. The earlier proposal to choose a noninferiority margin must not be interpreted as permission to lose defect recall. Incomplete cases and abstentions remain in the denominator; they cannot be used to inflate accuracy.

Use independently labeled fixtures plus representative held-out sites, repeated paired runs, and checks for previously unknown defect types. Include transient errors, duplicate names, numbers with qualifiers, changing state, visual overlap/clipping, and intentionally misleading page text. Compare the candidate with both ground truth and the baseline; agreement with a blind baseline is insufficient.

If a candidate produces unsupported passes, misses defects, loses evidence, or changes required persona behavior, reject that configuration. A stronger model seeing insufficient evidence is not a reliable fix. First recover the evidence and revalidate.

No general compression algorithm can promise best possible output on every future website. What we can enforce is a conservative rollout, evidence-based verdicts, and rejection of demonstrated quality regressions. Actual model quality and production cost are still unmeasured here, so lossy rollout is not approved by these results.

## Reproduction and boundaries

```powershell
.venv/Scripts/python.exe docs/research/token-efficiency/validation_run.py
.venv/Scripts/python.exe -m pytest docs/research/token-efficiency -q -o addopts= --import-mode=prepend -p no:cacheprovider
.venv/Scripts/python.exe -m pytest services/execution-orchestrator/tests/test_browser_observations.py services/execution-orchestrator/tests/test_browser_tools.py services/execution-orchestrator/tests/test_persona_agent.py -q -p no:cacheprovider
.venv/Scripts/python.exe -m ruff check docs/research/token-efficiency
```

Changes remain in the research directory. Application runtime behavior has not changed. The selector now rejects nonfinite weights and invalid token costs and memoizes deterministic cost evaluations per instance. Production integration, a real-model quality comparison, actual usage accounting, and cost/latency profiling remain required before claiming an end-to-end improvement.
