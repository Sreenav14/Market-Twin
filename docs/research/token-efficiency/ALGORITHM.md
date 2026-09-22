# A budgeted evidence controller for MarketTwin

Research and reference implementation, September 20, 2026. This extends [the repository audit and literature review](RESEARCH.md). Application code is unchanged. No paid model requests were made.

**Validation update:** [adversarial samples and the implementation decision](VALIDATION.md) found collector blind spots and nonoptimal greedy selections. Start with guarded reversible encoding; keep lossy selection experimental until real-model quality gates pass. The single illustrative selector result below is not a general optimality result.

**Conclusion: build a controller combining structured evidence selection, observation masking, and adaptive execution. Existing research supplies the components; none of the studies reviewed establishes an end-to-end solution with unchanged defect recall and persona fidelity for MarketTwin.** This is a proposed engineering synthesis, not a claim of a new scientific invention or a globally optimal agent.

The practical target is the lowest measured cost that satisfies a defined quality contract. Fewer tokens alone is an inadequate objective: a cheap false pass is a worse result, and reducing the number of personas changes study coverage.

## 1. What the closest research contributes

This is a targeted review of relevant methods, including their limitations, not a claim to have read every efficiency paper. Numerical results below belong to the authors' benchmarks, not MarketTwin.

| Primary source | Finding or mechanism | What to borrow and what not to assume |
|---|---|---|
| [The Complexity Trap, 2025](https://arxiv.org/html/2508.21433v3) | Observation masking roughly halved cost against raw histories in the studied coding agents and competed with summarization. Summaries sometimes lengthened trajectories. | Start with cheap masking and explicit retained facts. A coding solve rate does not establish browser defect recall. Masking alone still leaves action/history growth. |
| [AgentDiet, 2025](https://arxiv.org/html/2509.23586v1) | Removes useless, redundant, and expired trajectory information. Reported input savings were 39.9–59.7%; total cost savings were 21.1–35.9%. | Give observations a validity lifetime and retain recent failures. Its LLM reflector costs money; do not invoke one on every small browser result. |
| [Prune4Web, 2025/AAAI 2026](https://arxiv.org/html/2511.21398v1) | Generates scoring programs to reduce browser grounding candidates. | Borrow programmatic candidate filtering and expansion. Candidate-count reduction is not a corresponding reduction in dollars or a guarantee of successful planning. |
| [AdaComp, 2024](https://arxiv.org/html/2409.01579v1) | Predicts an adaptive retrieval size using training labels derived from successful answering. | Context size should depend on the task. Its predictor requires data and can be wrong; a fixed top-20 cut is not an equivalent algorithm. |
| [Fundamental Limits of Prompt Compression, 2024](https://arxiv.org/abs/2407.15504) | Frames compression using rate–distortion and studies query-aware selection. | Define acceptable task distortion and measure it. It does not provide a universal lossless compressor for arbitrary tasks and budgets. |
| [Optimal Skill Selection for LLM Agents, August 2026 preprint](https://arxiv.org/html/2608.19993v1) | Optimizes saturating relevance against context cost under a budget, with guarantees for its specified objective and assumptions. | Borrow diminishing returns and a token penalty. Its theorem does not transfer to our dependency bundles, nonadditive serialization costs, or unknown downstream correctness. |
| [Inference-Time Budget Control for LLM Search Agents, May 2026 preprint](https://arxiv.org/html/2605.05701v1) | Uses estimated marginal value to choose search, decomposition, or answering under tool-call and output-token budgets. | Borrow the decision about whether another action is worthwhile. MarketTwin must additionally account for input, images, retries, and verification. Value estimates are not an oracle. |
| [Sufficient Context, 2024/2025](https://arxiv.org/html/2411.06037v3) | Distinguishes insufficient evidence from failures despite sufficient evidence; studies selective answering in RAG. | Treat evidence expansion and stronger reasoning as different remedies. Track abstention and completeness so withholding answers cannot masquerade as higher quality. |
| [ACON, 2025](https://arxiv.org/html/2510.00615v2) | Learns context compression guidance from failure cases, reporting reductions in peak context. | Use compression-induced failures to improve rules offline. Peak-context savings do not directly establish net dollar savings. |
| [LLMLingua-2, 2024](https://arxiv.org/html/2403.12968v2) | Trained token selection compresses natural-language context. | A later candidate for long prose. Keep exact identifiers, amounts, negations, criteria, and tool schemas outside generic token pruning. |

The choice is therefore not to place a generic summarizer in front of every request. First use explicit browser structure and inexpensive host-side decisions. Add a learned compressor only where a controlled comparison shows net benefit.

## 2. The objective and its limits

The ideal problem is:

```text
minimize expected end-to-end cost per assigned study
subject to:
  required persona/mission coverage unchanged
  defect recall and report correctness meet the accepted baseline
  false-pass rate does not exceed the accepted threshold
  sufficient completion and evidence coverage
  persona behavior remains faithful to the study
```

Cost includes all model requests, retries, images, compression/routing calls, and infrastructure. Track logical input tokens, cached input, output/reasoning, dollars, and latency separately. Do not sum overlapping usage fields. A rate-limit rejection is not a measurement of total billed usage.

The environment and future actions are unknown, so an online controller cannot prove it has found the cheapest correct trajectory for every website. The defensible claim is empirical: lower cost on matched tasks, with predeclared quality gates and confidence intervals. A finite benchmark also cannot prove zero future regressions.

## 3. Maintain evidence separately from model context

Persist canonical observations and artifact references before selection. Each evidence item needs a stable ID, page/scene version, capture time, provenance, modality, visibility scope, and relevant dependencies. A stored screenshot is not a substitute for a structured observation, nor is a screenshot reference the same as supplying pixels to a vision model.

The audited app stores useful screenshots and accessibility evidence, but full canonical structured observations need an explicit persistence path before aggressive recoverable pruning. Treat this as a prerequisite.

The next model request contains five bounded components:

1. Stable instructions and tool definitions.
2. The persona, mission, and literal success criteria.
3. A compact progress ledger: established facts, unresolved criteria, attempted actions, failures, and artifact references.
4. The current selected scene, including relevant text beyond interactive elements.
5. Recent tool exchanges retained in a valid provider message structure.

Old verbose observations are replaced by compact records pointing to stored evidence. Preserve tool-call/result pairing and unresolved errors. Historical evidence can remain valid *as history* without being valid evidence of the current screen. Do not discard an earlier defect merely because navigation changed the page.

For deltas, include the base scene version and changed/deleted IDs. Send a fresh compact snapshot after navigation, loss of synchronization, or a substantial scene change. Never give a model an uninterpretable delta whose base was removed.

## 4. Select evidence under a real token budget

Split candidate context into semantic atoms or bundles. Examples include an element plus its accessible label, a price plus currency and billing period, a failure plus the action that caused it, or a visual artifact plus its page and viewport identity.

Let `S` be selected atoms and `P` mandatory atoms. A useful initial proxy is:

```text
F(S) = sum_j weight[j] * min(1, sum_{i in S} covers[i,j])
       - lambda * tokens(serialize(S))

subject to:
  P is contained in S
  every selected atom's dependencies are also selected
  selected evidence is valid for its intended use and allowed for this agent
  tokens(serialize(S)) <= evidence_budget
```

The saturation term means repeating the same fact receives no extra reward. It is an evidence-diversity proxy, not a probability of correctness or a declaration that criteria passed. Use separate aspects for supporting evidence, counterevidence, and independently required corroboration. Bundle complementary information: a number without its units must not receive the value assigned to a complete price.

The evidence budget is the smaller of the chosen per-request input target and model capacity after fixed instructions, tools, message overhead, output reservation, and headroom. Account for images separately using the actual provider/model rules. Validate the final provider-bound request; tokenizer counts on an intermediate Python dictionary are insufficient.

Pin literal criteria, active action targets, current scene identity, unresolved failures, known relevant contradictions, and the evidence dependencies required to interpret them. These pins are determined by explicit rules and reviewed labels initially. The system cannot guarantee retention of an unknown defect it never captured: include generic alert/dialog/error detection and a reserve for surrounding visible context, rather than selecting only text matching the goal.

A first implementation uses dependency-aware marginal gain per incremental token:

```text
selected = dependency_closure(mandatory)
if selected cannot fit: expand within the authorized cap or return insufficient_budget
repeat:
    score each eligible bundle by added objective / added serialized tokens
    reject bundles violating budget, dependencies, freshness, or visibility
    add the best positive-gain bundle
until no positive-gain bundle fits
compare against the best feasible single-bundle alternative
```

Do not fill unused space merely because it exists. Preserve spatial/reading order after selection; ranking should not falsely imply that an obscure control was prominent. For persona studies, evaluator-only facts and privileged target paths are forbidden inputs to the persona.

The reference implementation supplies this heuristic plus exhaustive enumeration for small offline cases. Exact enumeration proves an optimum only for the supplied finite proxy. Neither method proves optimal model behavior. The familiar submodular greedy guarantees require conditions that this full formulation does not establish.

Start with transparent weights based on unresolved criteria, current action relevance, novelty, provenance, and error signals. Later fit weights on labeled training traces and measure their effect on held-out tasks. Do not add an expensive LLM request merely to score every atom.

## 5. Decide whether to spend another call

Selection reduces request size. A separate host-side controller reduces avoidable requests:

| Observed condition | Next operation |
|---|---|
| A permitted deterministic operation has satisfied preconditions | Execute it, capture fresh state, verify its postcondition. |
| A target is missing from a truncated observation | Expand the relevant scene or retrieve the omitted region before asking the same model again. |
| Target identity is ambiguous | Retrieve labels/nearby context or more candidates; do not guess an index. |
| Evidence needed for a visual criterion is missing | Capture and verify the required current pixels. DOM existence alone cannot prove readability. |
| An action repeats with unchanged state or repeats the same failure | Trigger bounded recovery or terminate unresolved. |
| Adequate evidence exists but a model cannot make a valid decision | Consider a stronger model under the remaining budget. |
| All required criteria have sufficient verified evidence | Finalize using structured results and the existing deterministic report generator. |
| No permitted useful operation fits the remaining budget | Finish incomplete with explicit unresolved criteria. Never convert timeout into pass. |

Initially these are rules, not a second autonomous agent. Later estimate action value from empirical success/recovery rates conditional on task class, evidence gap, and failure type. Select actions using estimated quality improvement relative to expected incremental dollars and latency. Do not trust the model's self-reported confidence as a calibrated stopping rule.

Reserve budget for required verification before discretionary exploration. Enforce maximum model calls, actions, retries, tokens, and dollars in the host, including calls made by verifiers and compressors. Reconcile estimates against returned usage; preserve an explicit unknown-cost state when usage is unavailable. Avoid immediate repeated retries after a rate-limit response.

A regression procedure may reuse a previously verified route while recollecting current evidence. A usability persona generally must discover its own route: supplying shortcuts can erase precisely the confusion the study should measure. Mode-specific permission to automate is part of the algorithm, not a later optimization toggle.

## 6. Integrated runtime sketch

```python
while not study_terminal:
    observation = capture_or_reuse_valid_current_observation()
    store_canonical_observation(observation)
    update_evidence_and_progress_ledger(observation)

    if required_results_have_verified_evidence():
        return finalize_structured_results()

    operation = choose_rule_based_operation(state, gaps, failures, study_mode)
    if not budget.can_reserve(operation, required_verification_reserve):
        return incomplete_with_unresolved_criteria()

    if operation.needs_model:
        atoms = extract_allowed_atoms(state, ledger, operation)
        selected = select_with_pins_and_dependencies(atoms, input_budget)
        # An infeasible selection enters bounded expansion or incomplete handling.
        request = assemble_valid_request(selected, recent_tool_pairs)
        budget.validate_and_reserve_final_request(request)
        decision, usage = invoke_model(request)
        budget.reconcile(usage)
        validate_decision_schema_and_policy(decision)
        revalidate_scene_version_and_target(decision)
        execute_permitted_decision(decision)
    else:
        execute_and_verify(operation)

    account_for_nonmodel_work_and_update_loop_detector()
```

This is the design for integration, not functionality already wired into ADK. A request callback must actually replace or mask old contents in the final assembled request. In the installed ADK version, `include_contents='none'` still retains the current invocation's tool interactions. Since a whole journey is one invocation, setting that flag alone does not bound its history. Likewise, a separate `max_steps` dataclass does not enforce the running agent's budget.

## 7. Example: the Wikipedia heading check

The goal is to establish that the Software testing page can be reached and its heading is readable without clipping or overlap.

Keep the goal, actual route taken, current URL/scene, heading text and geometry, relevant overlapping elements or banners, any failed actions, and fresh visual artifact identity. Keep nearby context when needed to judge layout. A detected heading and an in-viewport rectangle establish only partial facts: they do not prove that pixels are readable or unobscured.

Mask repeated earlier navigation menus after preserving route and failures. Use a current viewport plus a suitable crop when needed for verification; account for their actual cost. The result can remain `visual_verification_pending` while semantic criteria pass. Stop only when required evidence is complete or a budget/recovery limit produces an explicit incomplete result.

If the user requests a factual regression check, a single approved procedure may be enough. If the study requires three distinct personas, keep them. Report savings from changing scope separately from savings produced by this controller on identical coverage.

## 8. Fit and test the algorithm without fooling ourselves

Create labeled fixtures covering clipping, sticky overlays, misleading text, duplicated labels, delayed content, authentication, pricing qualifiers, navigation failures, and long pages. Include cases where the relevant content is a paragraph, not a button or heading. The current observation extractor's positional element cap cannot be assumed to capture those facts.

Use baseline and candidate runs with the same tasks, personas, missions, initial state, model configuration, and required evidence. Repeat stochastic runs. A successful baseline action is useful comparison data but is not ground truth; independently label defects and verify reports.

Compare ablations in this order:

1. Current system with usage instrumentation.
2. Reversible compact serialization only.
3. Observation masking plus a structured progress ledger.
4. Budgeted evidence selection and bounded expansion.
5. Host-side call control and mode-permitted deterministic operations.
6. Optional learned compression or model routing.

Measure defect recall, false-pass rate, unsupported findings, completion, evidence correctness, and persona fidelity, alongside median and tail tokens/dollars/latency. Count incomplete results in coverage denominators. A candidate that answers only easy cases must not win by selective reporting.

Tune on training/validation fixtures; reserve unseen sites and defects for evaluation. When compression causes a baseline-correct case to fail, identify the missing evidence or damaged dependency, add a regression fixture, and revise the selection rules. Counterexample-driven improvement is more useful than endlessly adjusting a generic prompt.

For an initial pilot, require no observed regression in defect recall, false passes, supported findings, criterion completeness, or required persona fidelity on the agreed suite. Report confidence intervals and sample counts. Passing a small pilot is a rollout gate, not proof of universal equivalence. More incomplete results count as reduced quality, even when they avoid unsupported passes.

Train a predictor or compressor only if its expected future savings exceed its inference, training, hosting, and cache-disruption costs. Measure this across subsequent calls, not merely the size of its first output. Use the rule-based controller as the cost baseline it must beat.

## 9. What is implemented and verified

[budgeted_selector.py](budgeted_selector.py) implements mandatory retention, dependency closure, validity/visibility exclusion, exact serialized cost through an injected function, diminishing-return feature coverage, a token penalty, greedy selection, and a small exhaustive audit solver.

[test_budgeted_selector.py](test_budgeted_selector.py) now has sixteen passing test cases, including 60 seeded small problems checked against the exhaustive proxy oracle. Tests cover budget overflow, mandatory forbidden dependencies, counterevidence retention, redundant evidence, unused budget, malformed IDs, dependency cycles, invalid numerical inputs, cost caching, and a demonstrated greedy counterexample. Ruff passes. These tests validate selector mechanics, not MarketTwin quality. The separate codec suite adds six passing cases; see the validation follow-up above.

The synthetic tokenizer demo selected 138 tokens from 461 eligible tokens under a 240-token budget. It retained the goal, state, alert, heading, viewport reference, and prior failure; excluded stale and forbidden material; and matched the exhaustive proxy optimum for that fixture. Weights were hand supplied. This is **not** a measured reduction in production cost or proof of preserved defect recall. See [selector-demo-results.json](selector-demo-results.json).

Run locally from the repository root:

```powershell
.venv/Scripts/python.exe docs/research/token-efficiency/budgeted_selector.py
.venv/Scripts/python.exe -m pytest docs/research/token-efficiency/test_budgeted_selector.py -q -o addopts= --import-mode=prepend -p no:cacheprovider
```

The next integration sequence is usage accounting and canonical evidence persistence, compact request assembly, bounded history, then the selector and execution rules behind a feature flag. Establish the matched quality benchmark before enabling lossy selection by default. The substantial opportunity is eliminating repeated state and unnecessary decisions while preserving the evidence needed to find defects; its actual savings remain to be measured.
