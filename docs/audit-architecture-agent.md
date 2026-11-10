# Architecture audit — agent work record

Scope: current working tree, owner's Boss / Lead / Worker / Room / Board contract.
This is source review and targeted mechanics validation, not real-provider or
end-to-end acceptance. Sequential MKT/T00–T13 gates remain unchanged.

## Findings

| ID | Priority | Classification | Evidence and impact |
|---|---|---|---|
| AR1 | High | Reproduced and repaired; mocked driver verification passed | `workflow/harness_run.py:1152` retains `needs_human_login` after opaque confirmation, continues other work, then the old Close path at 1246–1268 unconditionally completed the run. `HarnessState.next_pending` ignores that status. Existing `test_one_opaque_confirmation_parks_one_item_only` actually asserted `done` with a waiting item. Updated the test to the latest owner's Close requirement; added a guard parking the run after other work completes. Prior driver failed the new regression; complete harness file now passes 29 tests. |
| AR2 | High | Confirmed implementation gap; browser reproduction needed | `workflow/harness_items.py:197` and `:202` generate enabled-before/visible-after assertions for ordinary buttons/links. Only checkbox/radio receives an outcome check at `:211`. `harness_run.py:264` maps satisfied to worked; later inventory at `:1190` first navigates back to the start URL and never checks the previous action's intended result. A no-op Search/Open menu button can therefore count worked. Reproduce against a real local no-op button before selecting the correct unknown/outcome policy. |
| AR3 | High | Reproduced and repaired; mocked driver verification passed | `harness_run.py:987` starts proof for a broken generated item; old `:1090` only tested whether confirmation's overall status was broken. It did not require the same assertion to fail on both attempts. A new fail(A)/fail(B) regression reproduced an incorrect broken status. Proof acceptance now requires an intersection of failed `(assertion_id, oracle)` identities across the two executions as well as completed broken confirmation. A matching fail(A)/fail(A) remains broken; pass/timeout still downgrade. |
| AR4 | High | Architecture gap, not proof of unsafe production replay | `harness_run.py:685` resets persisted running items to pending without effect reconciliation. However production `worker.py:136` treats interrupted duplicate delivery as failed and avoids replay. The promised crash/restart resume is therefore not established by the driver branch. Trace explicit resume API/delivery acceptance before changing this; do not remove fail-closed worker recovery. |
| AR5 | High | Confirmed architecture gap | `run_executor.py:124–154` dispatches persona and slop to separate loops. `persona_run.py:170` visits saved URLs and emits impressions; `slop_run.py:96` uses an in-memory crawl/state list, publishing all states at `:159`. Neither owns the shared durable per-item Board lifecycle. Both independently mark completed (`persona_run.py:295`, `slop_run.py:192`). One dispatcher does not implement the owner's one-engine/one-Board contract. Broad consolidation requires a proposal. |
| AR6 | Medium | Confirmed missing wiring | Production search found `rank_items` and `rank_slop_suspects` only at their definitions in `models/ask.py:169/:226`; callers are tests. `harness_run.py:835` picks plain Board order. Inventory is code-only link crawl (`:783–830`); no Lead route/recovery call exists in that driver. Supervisor design remains incomplete. |
| AR7 | Medium | Confirmed configuration/requirement mismatch | `models/ask.py:46` defaults narration to model and everything else to deterministic, contrary to owner's “Model API answers today” for fixed supervisory questions. Decisions calibration is a configuration flag, not measured evidence. Do not enable paid endpoints during this audit. |
| AR8 | High | Confirmed explicit-park Room lifetime gap; real workflow acceptance still needed | `BrowserController.__aexit__` (`browser/controller.py:185`) calls `close`; `close` (`:167–179`) closes every session and clears its own broker. `close_session` finally unregisters the owner handle (`:2094`), closes context/browser (`:2104–2113`) and removes session records (`:2118`). Harness explicit parked returns leave the context manager, so a DB Room row can stay open while its browser is destroyed. A new dispatch constructs a new controller (`harness_run.py:715`) with a fresh broker (`controller.py:151`); snapshot take at `harness_run.py:731` cannot read the destroyed controller's broker. No handoff to a separate storage keeper appears in this path. In-item waiting does retain context while the call is pending; this finding specifically concerns explicit parked returns. The fake controller's no-op exit cannot establish same-live-Room resume. Ownership redesign requires a proposal; no code change here. |

## Narrow AR1 repair

Owned application edit: `workflow/harness_run.py` only. Before Close, locate a
remaining `needs_human_login` item, preserve all item outcomes, persist run
`awaiting_human` / stage `needs_login` and bounded existing park metadata, and return
without `mark_completed`. This preserves the old behavior of finishing independent
items before parking. The regression additionally checks that completion was not
called. It does not establish a live retained browser across a parked return (AR8).

## File-by-file review coverage

Paths below are under `services/execution-orchestrator/src/markettwin_execution_orchestrator/`
unless prefixed otherwise. Full means the whole file was read in this agent pass;
it is not a claim of behavior testing.

| File | Coverage | Focus |
|---|---|---|
| `workflow/run_executor.py` | Full | Actual three-kind dispatch, validation, durable budget binding |
| `workflow/harness_state.py` | Full | Board identity, statuses, dedupe, counters, snapshot/event persistence |
| `workflow/harness_items.py` | Full | Safety classification, generated assertions, inventory identity |
| `workflow/harness_run.py` | Partial: 247–500 and 531–1269 | Inventory/work/proof/park/Close; fixture construction 1–246 not reviewed |
| `workflow/persona_run.py` | Full | Independent URL walks, conditions, quotes, teardown, completion |
| `workflow/slop_run.py` | Full | In-memory crawl, JS attribution/recheck, delayed event persistence |
| `models/ask.py` | Partial: definitions/defaults, ranking 169–244 | Missing call-sites, deterministic/model fallback; complete typed-output audit remains |
| `workflow/case_execution.py` | Partial: action/assertion finalization and exception handling 1110–1269; symbol searches | No complete safety/approval contract review claimed |
| `worker.py` | Partial: 100–260 | Interrupted duplicate policy and execution exception cleanup |
| `browser/controller.py` | Partial: close/context manager and Room/proof APIs 167–190, 337–445 | Session identity/lifetime; actual proof body and control fencing incomplete |
| `services/execution-orchestrator/tests/test_harness_run.py` | Partial: mechanics helpers 620–815; opaque/login/proof tests 875–1030 | Test-double blind spots and AR1 regression |

## Commands and evidence

Read-only `Get-Content` batches and `rg -n` searches traced actual dispatch,
ranking call-sites, assertions, park metadata and lifecycle owners. No provider
calls, database changes or heavy suites were run by this agent at this checkpoint.
Regression runner slot was coordinated with root: the harness file uses doubles,
so it did not consume the real browser/database integration slot.

### AR1 fresh validation

- `.venv\Scripts\python.exe .local/audit-20261108/architecture-close-before.py`
  failed as expected: **1 failed**, 2.82s, expected `needs_login`, observed `done`.
  This isolated process omits the new guard in memory only; no source rollback or
  working-tree overwrite occurred. Log: `architecture-close-before.log`.
- `.venv\Scripts\python.exe -m pytest services/execution-orchestrator/tests/test_harness_run.py -q -p no:cacheprovider`
  passed: **29 passed**, 5 pre-existing collection/deprecation warnings, 9.54s.
  Log: `architecture-harness-after.log`.
- Focused Ruff reports only the two pre-existing diagnostics:
  `harness_run.py:237` E501 and `test_harness_run.py:605` E402. The new test's
  initially long assertion was wrapped; no new lint finding remains.
- Tested source SHA256: `harness_run.py`
  `FDB9A4CF266E063C0F7E9D2FFDD924EE2F543398405EA011CC4858F49BF93060`;
  `test_harness_run.py`
  `B9F502D5A83CA6E0C231C5D5D871945F5B3522F4582E75A790D8A62F96C0677D`.

No real-browser retention, provider calibration, crash recovery or architecture
parity acceptance is inferred from these mocked mechanics tests.

### AR3 fresh validation (supersedes AR1-only file hashes above)

- `.venv\Scripts\python.exe -m pytest services/execution-orchestrator/tests/test_harness_run.py -k proof_requires_the_same_failed_assertion -q -p no:cacheprovider`
  reproduced **1 failed / 1 passed**, 13.06s: `target_visible` confirmation of an
  initial `target_enabled` failure incorrectly returned broken. Log:
  `architecture-proof-before.log`.
- Full harness command above after repair: **31 passed**, 5 pre-existing warnings,
  13.12s; `architecture-proof-after.log`. Prior observed-once pass/repeated failure
  checks remain in the file. No test was weakened to obtain this result.
- Focused Ruff still reports only old E501 at production line 237 and old E402 at
  test line 605. Final SHA256: production
  `E688024676B27525649C66C3DA4AAE87AA9AA23E27480BC4A0719344347038B9`;
  test `5F3E893FCA8217DD554E84C401F50AF72C61ACE3BFAC905A9C9F1C39973B0067`.
