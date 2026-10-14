# Controlled deep-feature fixture benchmark

Implemented 2026-10-14 for T01 of [MKT.md](../../MKT.md).

## What exists

The [registration fixture](../../services/execution-orchestrator/tests/fixtures/deep_testing_app/index.html)
has good and deliberately bad variants of the same feature. All state stays in
the current page; navigating again resets the case. The independent
[manifest](../../tests/benchmarks/markettwin_deep/manifest.json) defines eight
cases and three diagnostic probes. It is versioned `deep-fixture-v1`.

The eight cases are valid input, empty input, invalid email, maximum-length
violation, dependent role selection, recovery, delayed address validation and
navigation. The bad variant contradicts six case expectations; valid input and
recovery remain successful controls. These are six **case contradictions**, not
six independently counted root defects: three validation cases share a defect.

Independent Chromium tests also check the accepted 12-character boundary, rejected
13-character boundary, duplicate Save buttons, page reset, 320px/1280px layout,
and the existing BrowserController's origin/network restrictions. A local fixture
exception does not permit `public_only` access to loopback.

The [direct benchmark runner](../../services/execution-orchestrator/scripts/run_deep_fixture_benchmark.py)
starts an ephemeral loopback server, isolates each case in a fresh browser
context, executes runner-owned actions and reads actual UI state. It writes
`results.json`, `results.md`, and a screenshot for each completed case. Reports
include fixture/manifest hashes, actual observed values, execution status,
missing results, and numerator/denominator counts. Failed tool executions remain
unverified; missing cases remain in the planned denominator.

## Reproduce

Run from the repository root using installed dependencies:

```powershell
.venv\Scripts\python.exe services/execution-orchestrator/scripts/run_deep_fixture_benchmark.py --local-development --variant good --output-dir .local/deep-fixture-good
.venv\Scripts\python.exe services/execution-orchestrator/scripts/run_deep_fixture_benchmark.py --local-development --variant bad --output-dir .local/deep-fixture-bad
```

These commands use no model, database, shared port 5191, or external target.
The explicit flag is required. Runtime network requests are restricted to the
exact ephemeral fixture origin; service workers are blocked. CSS selectors in
the manifest belong to this deterministic fixture runner and are not exposed as
new agent tools.

The older live pipeline runner remains separate. Its CLI now requires the flag:

```powershell
.venv\Scripts\python.exe services/execution-orchestrator/scripts/run_v1_benchmark.py working --local-development
```

That historical V1 runner uses configured model providers and the local
database/storage. It was **not executed in this session**. Commands in historical
benchmark documents predate the required flag. The current database refused a
read-only baseline connection; live setup is not presently verified.

## Actual acceptance results

Fresh execution on 2026-10-14:

| Check | Result |
| --- | --- |
| Independent real Chromium fixture tests | 9 passed |
| Direct good-variant browser cases | 8/8 completed, 8/8 oracle-ground-truth agreement |
| Direct bad-variant browser cases | 8/8 completed, 8/8 oracle-ground-truth agreement |
| Bad-variant oracle verdicts | 6 not_satisfied, 2 satisfied controls |
| New scoring/CLI regressions | 6 passed |
| Final combined fixture/scoring suite | 15 passed in 21.51 seconds |
| Ruff and strict Pyright for new fixture/runner tests | Passed |

Detailed local run evidence: `.local/deep-fixture-good/results.json` and
`.local/deep-fixture-bad/results.json`, with adjacent Markdown and screenshots.
These generated files are local diagnostic artifacts rather than committed
customer evidence. Runs distinguish `mode=direct_fixture` from an autonomous
MarketTwin execution. The good/bad variant is recorded explicitly.

## Remaining gates

Policy, upload and ambiguous-delivery probes are in the manifest. The fixture
tests verify network-policy behavior and probe states; the direct runner reports
these probes as **not executed**. It does not fabricate a persisted blocked case,
upload attempt or confirmed delivery verdict.

No autonomous precision, recall, evidence correctness, model cost or case
repeatability metric is established by this runner. These fields remain unknown.
Existing legacy persona narratives cannot soundly be mapped to the new case IDs.
Scoring persisted autonomous runs requires the T02 plan/case binding, T05 recorded
assertions and T06 execution/coverage path. T01 establishes deterministic fixture
truth and a reproducible direct command; the product feature milestone remains
open until the actual agent pipeline executes and verifies its own bounded cases.
