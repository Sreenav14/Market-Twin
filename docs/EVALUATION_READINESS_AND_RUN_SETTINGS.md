# Evaluation readiness and testing depth

Verified on 4 October 2026. This change keeps execution, evaluation, and model
reasoning as separate concerns.

## What the unavailable message meant

Execution completion does not mean report completion. The execution worker saves
journey results and marks a test completed. The independent evaluation worker
discovers completed tests without a completed version-1 report every five seconds,
performs deterministic and optional visual checks, and saves findings and a report.
The UI polls the results endpoint every five seconds until that report exists.

The latest real run, `55e313dc-b33f-46e8-890a-e837ebc47a7f`, completed execution at
20:05:52.436 UTC. Its report was saved at 20:06:23.577 UTC: **31.141 seconds later**.
The evaluation worker was running, and all five completed tests in the inspected
database had completed reports. No missing report or disconnected evaluation
pipeline was found in that inspection. These are observations of the local
environment, not a guarantee that every deployment has its worker running.

The previous “Evaluation is not available yet” message obscured this normal
asynchronous gap. It now says “Preparing evaluation” and explains that evaluation
follows execution, visual checks take time, and the page checks automatically.
Draft, queued, and executing tests receive distinct explanations. The UI does not
claim to know whether an individual evaluation has started: there is no worker
heartbeat or live evaluation status endpoint in this implementation.

## Reliability correction

Previously the evaluation worker treated any version-1 report row as a completion
marker, including a `failed` or `generating` row. Such a row could keep a completed
test out of discovery indefinitely. Only a **completed** version-1 report now
suppresses evaluation. Report persistence reuses an incomplete version-1 row when
evaluation succeeds and preserves an already completed report unchanged. The
existing per-run PostgreSQL advisory lock remains the ownership mechanism.
The execution orchestrator's diagnostic `run_latest_test_run.py` and
`run_evaluation.py` also use the worker's `process_run()` path, so they cannot
generate competing reports while the persistent worker owns the same run.

No new database tables, migrations, heartbeat service, or Kafka dependency were
introduced. Exceptions still roll back uncommitted findings and are retried by the
existing worker loop. Persistent failures require inspecting worker logs; retries
are not bounded by a newly introduced policy.

Keep the evaluation worker running independently of the API and execution worker:

```powershell
uv run --env-file .env python -m markettwin_evaluation_worker.worker
```

LangSmith tracing remains under the existing observability configuration. The
workflow root is `evaluation.run`; visual model calls appear beneath it. A purely
deterministic evaluation may legitimately have no model-call children.

## Testing depth

The user clarified that Low / Medium / High means **testing coverage**, not model
reasoning effort. The existing planner still generates three personas and combines
each persona with every mission. Depth therefore limits distinct missions:

| Depth | Maximum missions | Maximum journeys |
| --- | ---: | ---: |
| Low | 1 | 3 |
| Medium | 2 | 6 |
| High | 4 | 12 |

These are ceilings, not quotas: the planner must not invent irrelevant or duplicate
missions to fill them. Higher coverage can increase execution and evaluation time.
The existing per-journey time budget and browser safety rules are unchanged.

New tests default to Medium. The Control API validates the choice and freezes it
in `configuration_snapshot.testing_depth`. The new-test form describes the caps,
sends the selected value, and the test overview displays the saved setting.
The runtime passes the frozen choice into planning and rejects a generated or
replayed plan that exceeds its cap before persisting journeys or opening a browser.
Legacy runs without a saved depth retain the previous maximum of four missions;
their configuration is labelled as legacy coverage rather than inventing a user
selection.

Prompt reruns preserve the saved depth. An immutable coverage instruction follows
the editable Meta Agent input, and an identical suffix is not appended twice.
Editing prompts does not enlarge the run's coverage budget. This does not introduce
explicit journey assignment or horizontal-worker leases: those remain separate
architecture changes.

## Verification

Regression checks cover all three API snapshot values; propagation into planning;
legacy fallback; rejection of invalid persisted depth; rejection of an over-budget
plan before browser execution; incomplete-report recovery; completed-report
preservation; and the existing evaluation claim/retry lock behavior.

The existing browser workflow test selects Low and checks the actual create-test
POST body. Desktop and mobile checks also exercise evaluation waiting and a later
permission failure.

- Focused backend regressions: **19 passed** (52.95 seconds); a preceding set
  including knowledge-planning propagation also passed all 19 selected checks.
- Frontend TypeScript: passed with no errors.
- Both diagnostic evaluation scripts were verified against the shared claim
  path with mocked execution and database access: **2 passed** (30.70 seconds).
- Ruff for the changed Python modules and tests: passed.
- Desktop and mobile browser workflows: **6 passed** (35.4 seconds), including
  an accessibility and horizontal-overflow check on test creation.
- Both test-creation screenshots were inspected. The depth selector was then
  placed in its own existing form section so its label, input, help text, and
  spacing match the rest of the application. The creation checks were rerun
  after that correction: **2 passed** (31.8 seconds). An intermediate check
  caught duplicate accessible labeling on the wrapper; the extra region label
  was removed while retaining the select's native label and help association.

Temporary screenshot and browser-test output files are removed after inspection;
the durable regression tests and this documentation are retained.
