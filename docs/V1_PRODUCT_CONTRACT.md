# V1 product contract

**Status (2026-11-02): six-run benchmark gates passed; Phases 0–7 implemented
and final regression validation passed locally.** New runs default to
`discovery_contract_v1`. Legacy and deep modes remain explicitly selectable, and
historical runs without a saved mode retain their legacy interpretation.
See [current status](CURRENT_STATE.md) and [session handoff](SESSION_HANDOFF.md)
for the active acceptance results.

## User-facing behavior

1. The owner selects an authorized application and describes its purpose. The
   discovery run explores within that application's allowed origin and records
   observed features, journey steps, blockers, and links to persisted execution
   evidence. An interaction is required for a journey to count as completed.
   Blocked or incomplete exploration remains visible as such.
2. MarketTwin proposes a draft of plain-language checks from observed journeys.
   The owner can edit checks or exclude checks and journeys. Draft checks have no
   authority to establish a defect.
3. On approval, the API marks each included check `user_approved`, records the
   approving user and time, and advances the contract. Starting execution freezes
   the contract and stores its identity and content hash with the run. The frozen
   checks and actions define the run's test plan.
4. The deterministic runner executes the approved journeys for three configured
   persona variants, records steps and artifacts, and retries a failed check once
   in a fresh browser execution. It links that replay to the original execution.
5. A product defect is confirmed only when the evidence belongs to the run and
   approved plan, the approved check fails in the original execution, and that
   same check fails again in the linked replay under the same frozen contract.
   Confirmed findings include evidence from both attempts. A passing replay is an
   unverified `did_not_reproduce` observation. Missing or invalid replay evidence
   remains unverified, including `replay_unavailable`; blocked and timed-out work
   is reported as incomplete rather than a product defect.
6. Experience scores are a separate assessment based on recorded journey facts
   and, when available, screenshots. Missing model configuration or invalid
   fact citations can make a score unavailable. Experience scores cannot create,
   confirm, change, or remove findings.
7. The market-readiness verdict is deterministic and reports its inputs. Coverage
   below 60% or fewer than two completed personas yields `insufficient_evidence`;
   a confirmed high or critical defect yields `not_ready`; otherwise confirmed
   defects or a persona mean below 3 yield `ready_with_issues`; the remaining
   case is `ready`. Experience data does not replace functional evidence.

An owner may explicitly reuse a completed run's approved frozen contract through
the create-run API's `frozen_contract_source_run_id`. Reuse requires the same owner,
workspace, application, target, and unchanged target snapshot. It preserves the
contract ID, version, approval, checks, and content hash, while binding a new run ID
for execution ownership. Discovery is not repeated; every new action, assertion,
confirmation replay, and screenshot belongs to the new run. The source contract
and its discovery evidence remain unchanged. Runtime action-policy permissions
remain separate from approval of the test contract.

## Limits and guarantees

- The system reports only behavior it observed and checks the owner approved. It
  does not establish that undiscovered routes, unapproved behavior, unexecuted
  journeys, or untested environments work.
- A failed check by itself is not a confirmed finding. Approval, contract/hash
  consistency, run ownership, saved step/artifact evidence, and linked replay
  evidence are verified before a report can expose a confirmed finding.
- Timeouts, policy blocks, authentication barriers, provider failures, and
  incomplete journeys describe test limitations. They do not prove a product bug.
- Persona experience scores are model assessments grounded in supplied facts;
  they are not deterministic usability measurements or defect oracles.
- This contract does not promise a readiness outcome, comprehensive coverage,
  security certification, or generalization beyond the tested target and run.

## Current mode and acceptance status

`legacy_persona`, `deep_feature_v1`, and `discovery_contract_v1` remain separate
execution modes. New server requests and the new-run UI now default to
`discovery_contract_v1`, following the passing six-run benchmark required by
section 8.2 of the [fix specification](../MARKETTWIN_FIX_SPEC_FOR_CODEX.md).
Explicit legacy/deep requests remain supported. Phase 7 focused checks passed
65 Python and 23 frontend tests. A preceding full Python run had one viewer-control
failure under concurrent benchmark load; that test passed in isolation without
relaxing its safety assertions. Final full regression passed: 1,245 Python tests,
23 skips, zero failures; 199 frontend tests passed. Typecheck, build, Ruff, and
focused production Pyright checks passed. No deployment or commit is implied.
Detailed run metrics and the scorer gate table are in
[`V1_BENCHMARK_RESULTS.md`](V1_BENCHMARK_RESULTS.md).

### Measured benchmark scope and limits

The passing campaign reused one owner-approved frozen contract
(`04e84d9b-1a27-4f1e-b8ae-fca678a1d3cd`, version 1,
`3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373`) and its
discovery map across three broken-fixture and three good-fixture replays. All four
seeded defects, including navigation, were confirmed in each broken run. The good
runs produced no confirmed findings. Across all runs, 138 of 144 original
journey/persona outcomes were terminal; six were inconclusive. Three good-fixture
personas across Runs 6 and 8 were inconclusive because cleanup timed out after
their actions and assertions completed. Cleanup timeouts remain a measured runtime
limit; they are not treated as product defects. The benchmark covers only this
fixture, approved contract, target, personas, and execution budget. No matched
legacy or deep-engine comparison exists, so these results do not establish
superiority over those modes.

## Implementation references

- Contract schema and hash: `packages/shared-python/src/markettwin_shared/discovery_contract.py`
- Approval and freeze API: `services/control-api/src/markettwin_control_api/api/test_contracts.py`
- Evidence and replay evaluation: `services/evaluation-worker/src/markettwin_evaluation_worker/contract_evaluator.py`
- Report proof validation: `services/control-api/src/markettwin_control_api/api/contract_report_validation.py`
- Experience assessment: `services/evaluation-worker/src/markettwin_evaluation_worker/experience_evaluator.py`
- Readiness rule: `services/evaluation-worker/src/markettwin_evaluation_worker/market_verdict.py`
