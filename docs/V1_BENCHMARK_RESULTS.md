# V1 controlled fixture benchmark results

This is the append-only raw results record required by
`MARKETTWIN_FIX_SPEC_FOR_CODEX.md` §8.3. Preserve earlier outcomes when adding
new runs. Fixture: `tests/fixtures/v1_benchmark/index.html`; expected feature
journeys are help navigation, display-name save, Continue, contact validation,
billing destination, and preview confirmation. The intentionally unresolved
external-confirmation state and restricted-origin probe are excluded from the
product-feature denominator. The fixture file hash was checked against the saved
pre-fix maps and matched the current file.

## 2026-11-02 pre-fix diagnostic (incomplete; not acceptance)

The following batch used pre-fix loaded source and was intentionally stopped after
the fifth report because recall and completion already failed. The sixth good run
had no completed report. Do not use it to pass any gate. Full step/assertion/replay
evidence is retained in
`.local/contract-benchmark-acceptance-20261101.json`.

| Variant | Repeat | Run ID | Seeded findings | Navigation | Terminal journeys | Inconclusive / executed | Feature map |
| --- | ---: | --- | ---: | --- | ---: | ---: | ---: |
| broken | 1 | `28b3d621-d914-43d4-b0b2-8c478c9446ee` | 2/4 | detected | 18/27 (66.7%) | 3/21 (14.3%) | 6/6 |
| broken | 2 | `5ee09823-10c4-4f28-a44a-27747fecc704` | 0/4 | not detected | 6/12 (50.0%) | 3/9 (33.3%) | 3/6 |
| broken | 3 | `1486bad3-9bdb-4bdb-acfd-4572d1de20b1` | 2/4 | detected | 18/27 (66.7%) | 0/18 (0%) | 6/6 |
| good | 1 | `99ef6fc0-2444-4a4a-b082-ec2b434ca315` | 0 false confirmations | — | 18/24 (75.0%) | 0/18 (0%) | 6/6 |
| good | 2 | `e4a0b362-e741-4a4a-b082-a7f8-5313f0a2d7ad` | 0 false confirmations | — | 18/24 (75.0%) | 0/18 (0%) | 6/6 |
| good | 3 | `33dd1ad6-fbce-4876-8389-13d9c91a8f96` | no report | unknown | unknown | unknown | no map |

All five reports recorded zero manual queue/worker interventions and passed
provenance/report-integrity checks. Across their maps, the six known functional
journeys appeared in 27/30 opportunities; broken repeat 2 had only 3/6. Map
coverage measures observed feature actions; it does not replace terminal-verdict
completion. The incomplete sixth slot was finalized as interrupted through the
worker's existing duplicate-delivery recovery path without replaying browser
actions.

**Gate result: failed.** Each broken repeat must confirm at least 3/4 seeded
defects; all three measured broken repeats failed. Every run must reach at least
80% terminal journeys; all five reported runs were below that threshold. One
broken repeat exceeded the 20% inconclusive limit. This diagnostic batch is not
the repaired acceptance run.

## 2026-11-02 repaired acceptance attempt 1 (failed; not acceptance)

The first repaired loopback-only batch was stopped after repeat 3 because a case
remained active beyond its 240-second budget with no persisted step/event, pending
approval, pause request, or human action. Its stale run was finalized through the
worker's existing interrupted-delivery recovery path, with no action replay. The
checkpoint JSON is `.local/contract-benchmark-acceptance-20261102-repaired.json`.
The run is recorded as failed with one manual recovery and cannot count toward
acceptance. Do not modify the fixture or acceptance thresholds.

| Variant | Repeat | Run ID | Report status | Per-run gates | Raw outcome table |
| --- | ---: | --- | --- | --- | --- |
| broken | 1 | `71a49707-4d52-4b78-8868-1f13bbfaf622` | reported | 4/4 defects; navigation detected; 24/24 terminal; 0 inconclusive; 0 manual; integrity pass | append after all six reports |
| broken | 2 | `d6831426-db71-44fa-acb7-8f808c49771a` | reported | 4/4 defects; navigation detected; 23/24 terminal; 1/24 inconclusive; 0 manual; integrity pass | append after all six reports |
| broken | 3 | `03d6ef49-4e68-4a6a-9fed-170d98ce59f2` | failed (no report) | stalled execution; 1 manual recovery; excluded | no report |
| good | 1 | pending | pending | pending | pending |
| good | 2 | pending | pending | pending | pending |
| good | 3 | pending | pending | pending | pending |

## Previous next-step plan (superseded by the fresh acceptance below)

Pending a deterministic timeout-path fix and regression. Run a fresh set of three
broken and three good repeats under a new artifact path; do not mix these with
either diagnostic batch above.


## 2026-11-02 baseline frozen-contract broken replay 1

This is the valid baseline broken-fixture replay 1: discovery ran against the good fixture, then one contract was approved and frozen before replay against the broken fixture across three personas. The immutable source contract is `.local/contract-benchmark-source-contract-20261102.json`, contract ID `04e84d9b-1a27-4f1e-b8ae-fca678a1d3cd`, version 1, hash `3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373`; report and execution-plan hashes match. Run 2 independently rediscovered and is retained as discovery-reliability data but excluded from replay counts. Run 3 began another discovery, was stopped before a report, and finalized failed through supported interrupted-delivery recovery. Fixture and thresholds are unchanged. Source run ID: `ed1eba45-267d-44af-956d-463209266c77`; report integrity: `true`; manual interventions: 0.

The per-run scorer verified 4/4 seeded defects, including incorrect navigation. Terminal journey-persona results: 21/24 (87.5%); inconclusive: 3/24 (12.5%). This baseline counts as broken replay 1 and meets its per-run gates.

### Baseline replay and protocol-deviation checkpoint

| Slot | Run ID | State | Created to report | Confirmed findings | Verified seeded recall | False confirmations | Navigation | Terminal / inconclusive | Manual interventions | Replay use |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | ---: | --- |
| Broken replay 1 | `ed1eba45-267d-44af-956d-463209266c77` | reported | 15m19.7s | 4 | 4/4 | 0 | detected | 21/24 (87.5%) / 3/24 (12.5%) | 0 | baseline; counts |
| Discovery diagnostic | `44674ee0-9e8f-4af3-bbf9-cdffeb35120e` | reported | 16m37.2s | 4 | 4/4 | 0 | detected | 20/24 (83.3%) / 4/24 (16.7%) | 0 | excluded: independent rediscovery |
| Interrupted diagnostic | `5e39c03e-8a6d-4d9a-aa9b-012f7e82e74e` | failed: protocol deviation | no report | ? | ? | ? | ? | ? | 1 operational cancellation/recovery | excluded |

Run 1 is the counted broken replay baseline. Run 2 records discovery reliability only and is not counted as a replay because it used a new discovery/contract. Run 3 has no report. The remaining work is two broken-fixture and three good-fixture executions/replays against the exact archived contract hash above; do not rediscover or change the contract.

### Run 1 timing baseline

| Stage | Start | End | Duration |
| --- | --- | --- | ---: |
| Full run creation to report | 17:28:43.881Z | 17:44:03.575Z | 15m19.7s |
| Discovery (worker start to discovery completed) | 17:29:05.615Z | 17:31:37.981Z | 2m32.4s |
| Contract execution/replay (execution plan to run completed) | 17:31:43.091Z | 17:43:44.939Z | 12m01.8s |
| Report generation | 17:43:45.508Z | 17:44:03.575Z | 18.1s |

The 273 completed browser/assertion steps account for about 599.4 of the 721.8 seconds in the execution window: assertions 357.1s, navigation 126.7s, clicks 80.6s, fills 28.8s, and page-index reads 6.2s. The run contains 12 linked replay executions. Reusing the frozen contract removes the measured 2m32s discovery portion from a repeated run; it cannot remove the roughly 12m of required execution and replay work. Screenshot/object transfer latency is not separately timed in persisted evidence, so the artifacts do not support attributing that remainder to uploads.

### Discovery coverage against the six declared functional features

Coverage denominator: the six product features listed at the top of this document; the restricted-origin probe and external-confirmation state are excluded. The saved good-fixture discovery map contains all six feature keys (6/6). The primary `main_page_navigation` journey completed with a valid-name fill, `Save display name` click, and the `Display name saved successfully.` marker.

| Declared feature | Discovery feature key | Journey key | Completed | Concrete observed action |
| --- | --- | --- | --- | --- |
| Display-name save / primary journey | `main_page_navigation` | `journey_d9702e77c58cda85122d` | yes | Fill `Display name` (`valid_name`); click `Save display name`; observed `Display name saved successfully.` (steps 4842?4843) |
| Continue | `continue_step` | `journey_f836989631abc11f728f` | yes | Click `Continue to next step`; observed `Next step` (step 4846) |
| Contact validation | `contact_validation` | `journey_e5807dca570876979c3a` | yes | Fill `Contact address` empty; click `Check contact address`; observed `Contact address is required` (steps 4849?4850) |
| Billing destination | `billing_settings` | `journey_a50f0666c2c384f31cdc` | yes | Click `Open billing settings`; observed `Billing settings` (step 4864) |
| Preview confirmation | `preview_generation` | `journey_788008295d4841dfb8a9` | yes | Click `Generate preview`; observed `Preview ready` (step 4857) |
| Help navigation | `help_guide` | `journey_805cf5e4d88a72a3f28e` | yes | Click `Open help guide`; observed `Help guide` (step 4860) |

### Per-journey/persona outcomes (24 rows)

| Journey key | Persona | Execution ID | Execution status | Verdict | Reason | Planned steps | Completed steps |
| --- | --- | --- | --- | --- | --- | --- | --- |
| journey_d9702e77c58cda85122d | 0 | ca182f24-b219-4c1e-a08b-544ad103fc31 | completed | satisfied | ? | 3 | 3 |
| journey_f836989631abc11f728f | 0 | 18c09160-396e-4749-b681-dda686a0323b | failed | unverified | execution_incomplete | 2 | 1 |
| journey_e5807dca570876979c3a | 0 | 3b283c1b-aac8-4f33-825b-6f26ae4c559f | failed | unverified | execution_incomplete | 3 | 3 |
| journey_6f2359086e98d99e7fa8 | 0 | c1153500-167a-4bad-b54b-50395188b07e | failed | unverified | execution_incomplete | 3 | 3 |
| journey_788008295d4841dfb8a9 | 0 | b3c3d157-f93f-4f44-85c9-39714ee31f83 | completed | not_satisfied | ? | 2 | 2 |
| journey_805cf5e4d88a72a3f28e | 0 | 1640996a-d6d1-44c3-848e-2af0ba5ba153 | completed | satisfied | ? | 2 | 2 |
| journey_a50f0666c2c384f31cdc | 0 | 033a7157-86eb-4e8c-a09b-9489cbba95a3 | completed | not_satisfied | ? | 2 | 2 |
| journey_4c224ee2682e030b2f1d | 0 | 4d64130e-7b6b-40bf-84d2-cd0616055534 | completed | satisfied | ? | 3 | 3 |
| journey_d9702e77c58cda85122d | 1 | 000fe959-e487-40b3-b5cc-245598e7be11 | completed | satisfied | ? | 3 | 3 |
| journey_f836989631abc11f728f | 1 | 0a8bf742-0fe6-4897-9cf6-7eb354499d77 | completed | not_satisfied | ? | 2 | 1 |
| journey_e5807dca570876979c3a | 1 | c08ad01f-eef5-408b-88dd-570c8bb255e1 | completed | not_satisfied | ? | 3 | 3 |
| journey_6f2359086e98d99e7fa8 | 1 | d6931a81-b736-4528-9c7f-bc7ea2acda11 | completed | satisfied | ? | 3 | 3 |
| journey_788008295d4841dfb8a9 | 1 | b790a764-b7fb-4790-87a5-9f82968727bb | completed | not_satisfied | ? | 2 | 2 |
| journey_805cf5e4d88a72a3f28e | 1 | 32ba7c01-3cc5-46d4-ae4b-a11c36d91c56 | completed | satisfied | ? | 2 | 2 |
| journey_a50f0666c2c384f31cdc | 1 | 374547fd-7b69-4f52-b8dc-5b2b3398f796 | completed | not_satisfied | ? | 2 | 2 |
| journey_4c224ee2682e030b2f1d | 1 | 93441298-946f-47e3-8584-dd60f84e1d4f | completed | satisfied | ? | 3 | 3 |
| journey_d9702e77c58cda85122d | 2 | 3101e9bb-7422-4912-a5da-faeb4fe6852f | completed | satisfied | ? | 3 | 3 |
| journey_f836989631abc11f728f | 2 | ebe7221c-ef70-4e0b-8add-d2963ca7c76f | completed | not_satisfied | ? | 2 | 1 |
| journey_e5807dca570876979c3a | 2 | 8375166e-5f40-4630-bde0-9e65f5d12e98 | completed | not_satisfied | ? | 3 | 3 |
| journey_6f2359086e98d99e7fa8 | 2 | 4fc4261e-4e04-4267-a5e9-4da7355e29ab | completed | satisfied | ? | 3 | 3 |
| journey_788008295d4841dfb8a9 | 2 | 0bf9f685-c6aa-48fb-8fb0-6596a54a524b | completed | not_satisfied | ? | 2 | 2 |
| journey_805cf5e4d88a72a3f28e | 2 | df890f79-b214-477b-a416-8c842762e97c | completed | satisfied | ? | 2 | 2 |
| journey_a50f0666c2c384f31cdc | 2 | feb33e17-ba09-42b1-a6f1-fdd2e32ca598 | completed | not_satisfied | ? | 2 | 2 |
| journey_4c224ee2682e030b2f1d | 2 | 884da799-5aa0-47a6-af40-03c4e63c8de8 | completed | satisfied | ? | 3 | 3 |

### Raw execution attempts (36 rows; includes original attempts and replays)

| Journey ID | Case ID | Persona | Attempt | Execution ID | Execution status | Verdict | Blocker | Elapsed ms | Planned steps | Completed steps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2bf292f4-1be1-4ed8-99b5-728e7ecae755 | journey_f836989631abc11f728f | 0 | 1 | 18c09160-396e-4749-b681-dda686a0323b | failed | unverified | runtime_failed | 23765 | 2 | 1 |
| 522acd87-3e84-4664-a7da-e23d4a7bcd25 | journey_d9702e77c58cda85122d | 0 | 1 | ca182f24-b219-4c1e-a08b-544ad103fc31 | completed | satisfied | ? | 35983 | 3 | 3 |
| 2bf292f4-1be1-4ed8-99b5-728e7ecae755 | journey_f836989631abc11f728f | 0 | 2 | 5f348f86-0a93-4b21-890c-ab9774331f4b | failed | unverified | runtime_failed | 23625 | 2 | 1 |
| 971f32db-2ca9-4264-b9bb-1b9f9db1bebf | journey_e5807dca570876979c3a | 0 | 1 | 3b283c1b-aac8-4f33-825b-6f26ae4c559f | failed | unverified | runtime_failed | 60702 | 3 | 3 |
| 971f32db-2ca9-4264-b9bb-1b9f9db1bebf | journey_e5807dca570876979c3a | 0 | 2 | 5c29ca1e-6d9b-4dc8-803e-7b2b50939109 | completed | not_satisfied | ? | 40390 | 3 | 3 |
| edc22e6a-dfb2-4530-8ac4-efbd95e73ffd | journey_788008295d4841dfb8a9 | 0 | 1 | b3c3d157-f93f-4f44-85c9-39714ee31f83 | completed | not_satisfied | ? | 20640 | 2 | 2 |
| 2144f7f5-f740-45cb-87a3-4d46e4aa98e8 | journey_6f2359086e98d99e7fa8 | 0 | 1 | c1153500-167a-4bad-b54b-50395188b07e | failed | unverified | runtime_failed | 29297 | 3 | 3 |
| edc22e6a-dfb2-4530-8ac4-efbd95e73ffd | journey_788008295d4841dfb8a9 | 0 | 2 | 06c68d93-51a3-426c-a980-dd2bb1a64acd | completed | not_satisfied | ? | 23188 | 2 | 2 |
| c47047a5-9316-4bfe-acdb-b4f33d28fdfe | journey_805cf5e4d88a72a3f28e | 0 | 1 | 1640996a-d6d1-44c3-848e-2af0ba5ba153 | completed | satisfied | ? | 14515 | 2 | 2 |
| 2ba272b7-7fb7-4e39-9697-0ff1c83156f3 | journey_a50f0666c2c384f31cdc | 0 | 1 | 033a7157-86eb-4e8c-a09b-9489cbba95a3 | completed | not_satisfied | ? | 22266 | 2 | 2 |
| 806c0dc9-9141-416e-8f84-213e68ad2268 | journey_4c224ee2682e030b2f1d | 0 | 1 | 4d64130e-7b6b-40bf-84d2-cd0616055534 | completed | satisfied | ? | 20483 | 3 | 3 |
| 2ba272b7-7fb7-4e39-9697-0ff1c83156f3 | journey_a50f0666c2c384f31cdc | 0 | 2 | 174b02bf-990e-49eb-9064-fa36046d7e4c | completed | not_satisfied | ? | 18984 | 2 | 2 |
| f9c59597-a8cd-4bfc-b28c-e0a59bcb6fb6 | journey_d9702e77c58cda85122d | 1 | 1 | 000fe959-e487-40b3-b5cc-245598e7be11 | completed | satisfied | ? | 20375 | 3 | 3 |
| 2ad1edaf-40c7-4466-8e25-566132372970 | journey_f836989631abc11f728f | 1 | 1 | 0a8bf742-0fe6-4897-9cf6-7eb354499d77 | completed | not_satisfied | assertion_precondition_failed | 12812 | 2 | 1 |
| 34f164a7-963d-4146-b2c9-5f22af5de5f2 | journey_e5807dca570876979c3a | 1 | 1 | c08ad01f-eef5-408b-88dd-570c8bb255e1 | completed | not_satisfied | ? | 21671 | 3 | 3 |
| 2ad1edaf-40c7-4466-8e25-566132372970 | journey_f836989631abc11f728f | 1 | 2 | 4f8d42cb-908b-4ee2-8add-6d872d9aba09 | completed | not_satisfied | assertion_precondition_failed | 10452 | 2 | 1 |
| 34f164a7-963d-4146-b2c9-5f22af5de5f2 | journey_e5807dca570876979c3a | 1 | 2 | b1e7a69b-778d-4575-83e9-29995d070fdb | completed | not_satisfied | ? | 22062 | 3 | 3 |
| f21d4aa1-ba5c-4731-aa43-84256ec7c139 | journey_6f2359086e98d99e7fa8 | 1 | 1 | d6931a81-b736-4528-9c7f-bc7ea2acda11 | completed | satisfied | ? | 14985 | 3 | 3 |
| aeeeda2c-10c0-4901-aa0f-95deb59fd8eb | journey_788008295d4841dfb8a9 | 1 | 2 | 17718f6e-e039-478a-9ad1-f2b77ece36e0 | completed | not_satisfied | ? | 18155 | 2 | 2 |
| aeeeda2c-10c0-4901-aa0f-95deb59fd8eb | journey_788008295d4841dfb8a9 | 1 | 1 | b790a764-b7fb-4790-87a5-9f82968727bb | completed | not_satisfied | ? | 18656 | 2 | 2 |
| 04842f54-b59d-4f8a-a9ed-67f1f7034d72 | journey_805cf5e4d88a72a3f28e | 1 | 1 | 32ba7c01-3cc5-46d4-ae4b-a11c36d91c56 | completed | satisfied | ? | 10750 | 2 | 2 |
| 8bef3a50-85b5-4a64-9465-1371d6205d6b | journey_a50f0666c2c384f31cdc | 1 | 1 | 374547fd-7b69-4f52-b8dc-5b2b3398f796 | completed | not_satisfied | ? | 17952 | 2 | 2 |
| 8bef3a50-85b5-4a64-9465-1371d6205d6b | journey_a50f0666c2c384f31cdc | 1 | 2 | 4114bdda-3b4d-444b-b362-37d959a72f99 | completed | not_satisfied | ? | 16859 | 2 | 2 |
| 0373299a-c2fc-401e-9739-1e5f966299c3 | journey_4c224ee2682e030b2f1d | 1 | 1 | 93441298-946f-47e3-8584-dd60f84e1d4f | completed | satisfied | ? | 13344 | 3 | 3 |
| b293a859-31ed-47b5-ab64-79a065821f93 | journey_d9702e77c58cda85122d | 2 | 1 | 3101e9bb-7422-4912-a5da-faeb4fe6852f | completed | satisfied | ? | 11609 | 3 | 3 |
| 8adac070-f5b2-4d89-bc44-8245cca8cd30 | journey_f836989631abc11f728f | 2 | 1 | ebe7221c-ef70-4e0b-8add-d2963ca7c76f | completed | not_satisfied | assertion_precondition_failed | 11577 | 2 | 1 |
| 8adac070-f5b2-4d89-bc44-8245cca8cd30 | journey_f836989631abc11f728f | 2 | 2 | 26d0ca7f-93df-41a0-a22c-76dceb62c280 | completed | not_satisfied | assertion_precondition_failed | 10187 | 2 | 1 |
| 72a22573-45b7-43ff-a7e7-a391a891ca79 | journey_e5807dca570876979c3a | 2 | 1 | 8375166e-5f40-4630-bde0-9e65f5d12e98 | completed | not_satisfied | ? | 18984 | 3 | 3 |
| 72a22573-45b7-43ff-a7e7-a391a891ca79 | journey_e5807dca570876979c3a | 2 | 2 | 8f7422f2-921d-4f12-9182-cf424b29c779 | completed | not_satisfied | ? | 19922 | 3 | 3 |
| a163b88f-479e-4799-976d-ab93a1cf5527 | journey_6f2359086e98d99e7fa8 | 2 | 1 | 4fc4261e-4e04-4267-a5e9-4da7355e29ab | completed | satisfied | ? | 12844 | 3 | 3 |
| 4d5c95ee-a972-4232-99b4-5bf60f0dc65c | journey_788008295d4841dfb8a9 | 2 | 1 | 0bf9f685-c6aa-48fb-8fb0-6596a54a524b | completed | not_satisfied | ? | 18983 | 2 | 2 |
| 4d5c95ee-a972-4232-99b4-5bf60f0dc65c | journey_788008295d4841dfb8a9 | 2 | 2 | 3d5a073c-8fca-4e23-8729-4a33b2f0a3b0 | completed | not_satisfied | ? | 16938 | 2 | 2 |
| 10aa497f-5e32-4808-9d24-f9bd399a7083 | journey_805cf5e4d88a72a3f28e | 2 | 1 | df890f79-b214-477b-a416-8c842762e97c | completed | satisfied | ? | 10875 | 2 | 2 |
| 6d2c9b6b-6d46-41a3-ae6c-7b198c271079 | journey_a50f0666c2c384f31cdc | 2 | 1 | feb33e17-ba09-42b1-a6f1-fdd2e32ca598 | completed | not_satisfied | ? | 16968 | 2 | 2 |
| 6d2c9b6b-6d46-41a3-ae6c-7b198c271079 | journey_a50f0666c2c384f31cdc | 2 | 2 | 00a886c9-1d7f-4d08-adc7-e534a6932c29 | completed | not_satisfied | ? | 15702 | 2 | 2 |
| 28b9b731-498c-4f70-bb42-5a2293956e27 | journey_4c224ee2682e030b2f1d | 2 | 1 | 884da799-5aa0-47a6-af40-03c4e63c8de8 | completed | satisfied | ? | 18250 | 3 | 3 |

### Per-assertion outcomes (105 rows)

| Journey key | Persona | Assertion ID | Oracle | Origin | Status | Expected | Observed | Step ID | Elapsed ms | Artifact IDs | Execution ID |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| journey_d9702e77c58cda85122d | 0 | chk_journey_d9702e77c58cda85122d_s2_1 | visible | user_approved | satisfied | True | True | 4878 | 827 | ["e7e4abc5-c59a-4130-92aa-40a89d4bed3f","cee01e55-2eda-4c9d-8026-81fb4565ed2a"] | ca182f24-b219-4c1e-a08b-544ad103fc31 |
| journey_d9702e77c58cda85122d | 0 | chk_journey_d9702e77c58cda85122d_s2_2 | enabled | user_approved | satisfied | True | True | 4879 | 922 | ["b7fec978-8631-4617-8974-bbf15d1069e1","013db6a7-d295-4cd1-92c6-ce6f4204a8de"] | ca182f24-b219-4c1e-a08b-544ad103fc31 |
| journey_d9702e77c58cda85122d | 0 | chk_journey_d9702e77c58cda85122d_s2_3 | visible_text | user_approved | satisfied | Display name saved successfully. | Display name saved successfully. | 4881 | 1468 | ["2d2277bc-5db8-4289-b7ad-49e88142e00a","e9b1aa49-d05b-4f36-97a7-075df0cd17a6"] | ca182f24-b219-4c1e-a08b-544ad103fc31 |
| journey_d9702e77c58cda85122d | 0 | chk_journey_d9702e77c58cda85122d_url_4 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 4882 | 609 | ["3aab359e-2765-4568-a5d4-013195b20365","1ec95d01-c29d-4284-8c9f-d253d6941bf4"] | ca182f24-b219-4c1e-a08b-544ad103fc31 |
| journey_d9702e77c58cda85122d | 0 | chk_journey_d9702e77c58cda85122d_title_5 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 4883 | 610 | ["69569810-14fc-4369-8496-1cb376d31d1b","40069763-41ef-45e1-87c5-0954a360ce34"] | ca182f24-b219-4c1e-a08b-544ad103fc31 |
| journey_f836989631abc11f728f | 0 | chk_journey_f836989631abc11f728f_s1_1 | visible | user_approved | satisfied | True | True | 4885 | 733 | ["4f5fda7f-069d-4734-8605-782936f8ce45","6d542ccc-3f45-424c-94c3-93530cec91ee"] | 18c09160-396e-4749-b681-dda686a0323b |
| journey_f836989631abc11f728f | 0 | chk_journey_f836989631abc11f728f_s1_2 | enabled | user_approved | not_satisfied | True | False | 4886 | 4140 | ["28c271aa-e049-4f0f-8617-e331cb5f4902","31709fae-7277-4287-9dfb-20edfb9ed561"] | 18c09160-396e-4749-b681-dda686a0323b |
| journey_e5807dca570876979c3a | 0 | chk_journey_e5807dca570876979c3a_s2_1 | visible | user_approved | satisfied | True | True | 4892 | 890 | ["612acfd3-6b30-46a1-b71b-0abc406c6ad9","fb5ed2d6-0413-41f9-9855-bfcf589bce59"] | 3b283c1b-aac8-4f33-825b-6f26ae4c559f |
| journey_e5807dca570876979c3a | 0 | chk_journey_e5807dca570876979c3a_s2_2 | enabled | user_approved | satisfied | True | True | 4893 | 2734 | ["a9f5e890-1e2b-4dfc-9449-7b5529082c55","1f4f99b7-c908-4255-b160-8f2d45786f4d"] | 3b283c1b-aac8-4f33-825b-6f26ae4c559f |
| journey_e5807dca570876979c3a | 0 | chk_journey_e5807dca570876979c3a_s2_3 | visible_text | user_approved | not_satisfied | Contact address is required | absent | 4895 | 7530 | ["ca58c58e-c983-4d9f-83a3-1a6131605111","d00f289c-4562-4269-9432-87230eaf2967"] | 3b283c1b-aac8-4f33-825b-6f26ae4c559f |
| journey_e5807dca570876979c3a | 0 | chk_journey_e5807dca570876979c3a_url_4 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 4896 | 655 | ["a0ebf2fe-37ea-4a44-bd8a-40ca3e3ad9ae","641ca62f-a670-4ba4-b124-e2edf1df2915"] | 3b283c1b-aac8-4f33-825b-6f26ae4c559f |
| journey_e5807dca570876979c3a | 0 | chk_journey_e5807dca570876979c3a_title_5 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 4897 | 780 | ["02512d42-3713-4712-b086-319a7fbd7278","2cfc2eb4-b92c-49ae-b885-ddf154f161ae"] | 3b283c1b-aac8-4f33-825b-6f26ae4c559f |
| journey_6f2359086e98d99e7fa8 | 0 | chk_journey_6f2359086e98d99e7fa8_s2_1 | visible | user_approved | satisfied | True | True | 4908 | 812 | ["5b11a082-fe4b-4a3e-96d1-6b69890311ee","38844160-c948-422f-9776-f5d49a273344"] | c1153500-167a-4bad-b54b-50395188b07e |
| journey_6f2359086e98d99e7fa8 | 0 | chk_journey_6f2359086e98d99e7fa8_s2_2 | enabled | user_approved | satisfied | True | True | 4909 | 813 | ["28cb36cb-18e7-4ade-8275-78db9e3b5e7b","9e619534-fe62-4dca-84ce-69e9930796e3"] | c1153500-167a-4bad-b54b-50395188b07e |
| journey_6f2359086e98d99e7fa8 | 0 | chk_journey_6f2359086e98d99e7fa8_url_3 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 4911 | 625 | ["ef829f95-f27d-465f-a958-317c1abd4394","f925f8b9-a078-4cc4-a58e-7bd31319c9c6"] | c1153500-167a-4bad-b54b-50395188b07e |
| journey_6f2359086e98d99e7fa8 | 0 | chk_journey_6f2359086e98d99e7fa8_title_4 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 4912 | 625 | ["aaffe4b5-0c10-42db-abba-6d54f478a989","3164a26a-01c3-4edb-be52-35036349196e"] | c1153500-167a-4bad-b54b-50395188b07e |
| journey_788008295d4841dfb8a9 | 0 | chk_journey_788008295d4841dfb8a9_s1_1 | visible | user_approved | satisfied | True | True | 4914 | 672 | ["0ff982f6-1d05-48b6-9f88-fca4ec0a6fb8","a6b076f3-91aa-412d-8617-883eafa67d15"] | b3c3d157-f93f-4f44-85c9-39714ee31f83 |
| journey_788008295d4841dfb8a9 | 0 | chk_journey_788008295d4841dfb8a9_s1_2 | enabled | user_approved | satisfied | True | True | 4915 | 672 | ["9a27f514-0246-4252-9592-a59a4fcccad9","5d976aaa-b2da-49d5-bcde-6bf0398f3ff7"] | b3c3d157-f93f-4f44-85c9-39714ee31f83 |
| journey_788008295d4841dfb8a9 | 0 | chk_journey_788008295d4841dfb8a9_s1_3 | visible_text | user_approved | not_satisfied | Preview ready | absent | 4917 | 6718 | ["1b0e5a94-ef62-4987-a289-ec589b43d587","7b7ce19e-a0a2-4b4f-ac35-08b04d981803"] | b3c3d157-f93f-4f44-85c9-39714ee31f83 |
| journey_788008295d4841dfb8a9 | 0 | chk_journey_788008295d4841dfb8a9_url_4 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 4918 | 625 | ["3a04227d-e2b0-4267-9abe-2e57dd2edf15","38d203bb-eb22-4a86-a5fc-9ba5303d088a"] | b3c3d157-f93f-4f44-85c9-39714ee31f83 |
| journey_788008295d4841dfb8a9 | 0 | chk_journey_788008295d4841dfb8a9_title_5 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 4919 | 594 | ["3effac39-a920-4455-a294-1f91453c4cd8","d96d6ced-cda0-4b9c-965c-d5a5d173c9ce"] | b3c3d157-f93f-4f44-85c9-39714ee31f83 |
| journey_805cf5e4d88a72a3f28e | 0 | chk_journey_805cf5e4d88a72a3f28e_s1_1 | visible | user_approved | satisfied | True | True | 4928 | 828 | ["0189461a-4b0d-4734-a461-fbdae46a31da","c27463fc-36f8-4e7f-877f-7fe2a4b25956"] | 1640996a-d6d1-44c3-848e-2af0ba5ba153 |
| journey_805cf5e4d88a72a3f28e | 0 | chk_journey_805cf5e4d88a72a3f28e_s1_2 | enabled | user_approved | satisfied | True | True | 4929 | 718 | ["9fbd8b1e-58b2-42e8-a921-d82555466750","c2905d80-53d0-4033-8ab6-fcfcab978ed1"] | 1640996a-d6d1-44c3-848e-2af0ba5ba153 |
| journey_805cf5e4d88a72a3f28e | 0 | chk_journey_805cf5e4d88a72a3f28e_s1_3 | visible_text | user_approved | satisfied | Help guide | Help guide | 4931 | 780 | ["42897dc4-e06c-405d-97e7-dc881e9f0455","95c65234-2709-4a6c-8182-9f253781218c"] | 1640996a-d6d1-44c3-848e-2af0ba5ba153 |
| journey_805cf5e4d88a72a3f28e | 0 | chk_journey_805cf5e4d88a72a3f28e_url_4 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 4932 | 594 | ["7e98370f-81e8-443f-8581-d9dc7b70e002","9519a381-7c63-45a2-8eef-28a28be5a96a"] | 1640996a-d6d1-44c3-848e-2af0ba5ba153 |
| journey_805cf5e4d88a72a3f28e | 0 | chk_journey_805cf5e4d88a72a3f28e_title_5 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 4933 | 640 | ["ce189f71-b886-4ed3-8566-14372d3fa593","6e7ff4d9-329e-4ddb-a9bc-5ae141e7bcf6"] | 1640996a-d6d1-44c3-848e-2af0ba5ba153 |
| journey_a50f0666c2c384f31cdc | 0 | chk_journey_a50f0666c2c384f31cdc_s1_1 | visible | user_approved | satisfied | True | True | 4935 | 671 | ["b97bedf3-10a0-41be-8262-77e72fa5bca5","837e3d58-8711-43ca-944f-bef294b4200e"] | 033a7157-86eb-4e8c-a09b-9489cbba95a3 |
| journey_a50f0666c2c384f31cdc | 0 | chk_journey_a50f0666c2c384f31cdc_s1_2 | enabled | user_approved | satisfied | True | True | 4936 | 687 | ["9061104c-4410-4675-81b8-f327705f19dd","8c897ed0-2051-4a01-9abd-989de5b24360"] | 033a7157-86eb-4e8c-a09b-9489cbba95a3 |
| journey_a50f0666c2c384f31cdc | 0 | chk_journey_a50f0666c2c384f31cdc_s1_3 | visible_text | user_approved | not_satisfied | Billing settings | absent | 4938 | 6702 | ["e144d4b4-ec36-425b-a817-175670a47b99","35e18f15-05ab-4c38-9b30-55a5cc17e4a8"] | 033a7157-86eb-4e8c-a09b-9489cbba95a3 |
| journey_a50f0666c2c384f31cdc | 0 | chk_journey_a50f0666c2c384f31cdc_url_4 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 4939 | 781 | ["486c54e1-478a-4b64-ae1b-7bfccc292628","fc1ed4bc-fc0b-44fc-b081-0d67fcb27b1c"] | 033a7157-86eb-4e8c-a09b-9489cbba95a3 |
| journey_a50f0666c2c384f31cdc | 0 | chk_journey_a50f0666c2c384f31cdc_title_5 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 4940 | 655 | ["e9a38067-a2a9-4fa8-b537-dd378b909fde","87eaa8a9-906f-4b20-bfab-19ca951bc085"] | 033a7157-86eb-4e8c-a09b-9489cbba95a3 |
| journey_4c224ee2682e030b2f1d | 0 | chk_journey_4c224ee2682e030b2f1d_s2_1 | visible | user_approved | satisfied | True | True | 4950 | 719 | ["911b6079-9c68-4f15-9de0-3a32bd9223a6","d7089132-b010-4483-8607-21d7415a4626"] | 4d64130e-7b6b-40bf-84d2-cd0616055534 |
| journey_4c224ee2682e030b2f1d | 0 | chk_journey_4c224ee2682e030b2f1d_s2_2 | enabled | user_approved | satisfied | True | True | 4951 | 703 | ["c660a2d5-5811-45c4-a94a-c445f5a3f992","2e6a3c94-ae5e-433e-bdba-6bc607c93587"] | 4d64130e-7b6b-40bf-84d2-cd0616055534 |
| journey_4c224ee2682e030b2f1d | 0 | chk_journey_4c224ee2682e030b2f1d_url_3 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 4953 | 594 | ["2a6b82e3-45f7-4b6a-b290-1abc6043921f","a4d0ab65-a895-4dd2-b925-5560a6bd94f9"] | 4d64130e-7b6b-40bf-84d2-cd0616055534 |
| journey_4c224ee2682e030b2f1d | 0 | chk_journey_4c224ee2682e030b2f1d_title_4 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 4954 | 671 | ["6fc6866e-a252-4713-978f-7aee81f78a0c","71748eda-3635-48d8-a502-5b2e273434b9"] | 4d64130e-7b6b-40bf-84d2-cd0616055534 |
| journey_d9702e77c58cda85122d | 1 | chk_journey_d9702e77c58cda85122d_s2_1 | visible | user_approved | satisfied | True | True | 4957 | 765 | ["95f7f1f8-d491-4ba3-b98d-a1d44c2b9930","e95fc38f-3c6a-4326-a08f-d608e64df417"] | 000fe959-e487-40b3-b5cc-245598e7be11 |
| journey_d9702e77c58cda85122d | 1 | chk_journey_d9702e77c58cda85122d_s2_2 | enabled | user_approved | satisfied | True | True | 4958 | 672 | ["e788c28e-c7ab-409e-8526-9577d954cfd5","3086e74e-92a8-4629-a4b0-45b8dc545d67"] | 000fe959-e487-40b3-b5cc-245598e7be11 |
| journey_d9702e77c58cda85122d | 1 | chk_journey_d9702e77c58cda85122d_s2_3 | visible_text | user_approved | satisfied | Display name saved successfully. | Display name saved successfully. | 4960 | 1030 | ["39719784-6bb4-4c0e-9ab5-de4d52998cdd","12eaac08-8c37-447a-91c9-be2d828117c4"] | 000fe959-e487-40b3-b5cc-245598e7be11 |
| journey_d9702e77c58cda85122d | 1 | chk_journey_d9702e77c58cda85122d_url_4 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 4961 | 639 | ["e64ace75-f944-4950-9657-9654f739c422","f8ecc66a-10cb-46ad-86d8-26d3b629d481"] | 000fe959-e487-40b3-b5cc-245598e7be11 |
| journey_d9702e77c58cda85122d | 1 | chk_journey_d9702e77c58cda85122d_title_5 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 4962 | 641 | ["ce826ef1-0bd5-457a-9fff-ea284f557b62","221a0da6-872f-47a3-8267-d120e40d6b17"] | 000fe959-e487-40b3-b5cc-245598e7be11 |
| journey_f836989631abc11f728f | 1 | chk_journey_f836989631abc11f728f_s1_1 | visible | user_approved | satisfied | True | True | 4964 | 1078 | ["39dc074b-e830-4c3c-8190-99bc10ced5b6","aaa7639c-c291-4941-8578-1abfc8ee0814"] | 0a8bf742-0fe6-4897-9cf6-7eb354499d77 |
| journey_f836989631abc11f728f | 1 | chk_journey_f836989631abc11f728f_s1_2 | enabled | user_approved | not_satisfied | True | False | 4965 | 3765 | ["bf70491c-7ad8-44bc-be65-131aecaa7213","76da0fd6-c4bf-4d63-8697-c6e7615950c7"] | 0a8bf742-0fe6-4897-9cf6-7eb354499d77 |
| journey_e5807dca570876979c3a | 1 | chk_journey_e5807dca570876979c3a_s2_1 | visible | user_approved | satisfied | True | True | 4971 | 797 | ["174db705-1fba-4ae2-bfb3-a1acc9c3dec8","3b5f75a0-e3e7-425e-bd37-6737371085f3"] | c08ad01f-eef5-408b-88dd-570c8bb255e1 |
| journey_e5807dca570876979c3a | 1 | chk_journey_e5807dca570876979c3a_s2_2 | enabled | user_approved | satisfied | True | True | 4972 | 672 | ["5d977a06-71f2-4e6e-99de-a1cabd4f79b0","12bdd082-726c-420b-a223-78b12189ae36"] | c08ad01f-eef5-408b-88dd-570c8bb255e1 |
| journey_e5807dca570876979c3a | 1 | chk_journey_e5807dca570876979c3a_s2_3 | visible_text | user_approved | not_satisfied | Contact address is required | absent | 4974 | 6687 | ["1c9827a6-a89f-4f3b-b20a-7ecbf2ff0bdb","bec4c55c-1ae8-45ec-8377-efd260dfce96"] | c08ad01f-eef5-408b-88dd-570c8bb255e1 |
| journey_e5807dca570876979c3a | 1 | chk_journey_e5807dca570876979c3a_url_4 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 4975 | 562 | ["f2966ffb-6662-40dd-a999-a4e5a38cbe60","15a78a87-d6ab-4e2c-a95a-f859c9f3f7a8"] | c08ad01f-eef5-408b-88dd-570c8bb255e1 |
| journey_e5807dca570876979c3a | 1 | chk_journey_e5807dca570876979c3a_title_5 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 4976 | 718 | ["3b1e64e6-e93b-4899-849c-a71613251fd1","01922d1b-4c41-4281-86df-0177a1d5adc2"] | c08ad01f-eef5-408b-88dd-570c8bb255e1 |
| journey_6f2359086e98d99e7fa8 | 1 | chk_journey_6f2359086e98d99e7fa8_s2_1 | visible | user_approved | satisfied | True | True | 4987 | 750 | ["1341d999-af3e-4380-9d0e-095ef4a1bc3d","6b099671-faad-4781-bfcb-4a29884205b2"] | d6931a81-b736-4528-9c7f-bc7ea2acda11 |
| journey_6f2359086e98d99e7fa8 | 1 | chk_journey_6f2359086e98d99e7fa8_s2_2 | enabled | user_approved | satisfied | True | True | 4988 | 702 | ["6755d93e-3450-4d44-b624-6f77a470c049","9e33779a-b0ff-40b7-8270-960892d91ebd"] | d6931a81-b736-4528-9c7f-bc7ea2acda11 |
| journey_6f2359086e98d99e7fa8 | 1 | chk_journey_6f2359086e98d99e7fa8_url_3 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 4990 | 625 | ["c68cef64-a129-4202-b76d-87a9ca34245c","c3fa81bf-3e04-43ba-94c8-6e5b23b1fbd7"] | d6931a81-b736-4528-9c7f-bc7ea2acda11 |
| journey_6f2359086e98d99e7fa8 | 1 | chk_journey_6f2359086e98d99e7fa8_title_4 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 4991 | 608 | ["a09227eb-fc3f-40f0-807e-9ee1b8f17f44","8ab3e956-bafc-482b-93c4-6e7696ee0eab"] | d6931a81-b736-4528-9c7f-bc7ea2acda11 |
| journey_788008295d4841dfb8a9 | 1 | chk_journey_788008295d4841dfb8a9_s1_1 | visible | user_approved | satisfied | True | True | 4993 | 687 | ["ee7e48e7-51a2-464b-9df3-fc150bf54449","2a65ca6a-45f4-462d-97dd-34d2294edfe8"] | b790a764-b7fb-4790-87a5-9f82968727bb |
| journey_788008295d4841dfb8a9 | 1 | chk_journey_788008295d4841dfb8a9_s1_2 | enabled | user_approved | satisfied | True | True | 4994 | 625 | ["c08c9a5d-00b7-446b-9bfe-92f1bda83b42","34fb8eef-de37-4652-9ee0-b2c9f9a5fcea"] | b790a764-b7fb-4790-87a5-9f82968727bb |
| journey_788008295d4841dfb8a9 | 1 | chk_journey_788008295d4841dfb8a9_s1_3 | visible_text | user_approved | not_satisfied | Preview ready | absent | 4996 | 6750 | ["f7bcacca-2c55-4d66-b688-8de7a23b6f5e","da5845a3-e5ee-4397-83f8-425190a39a54"] | b790a764-b7fb-4790-87a5-9f82968727bb |
| journey_788008295d4841dfb8a9 | 1 | chk_journey_788008295d4841dfb8a9_url_4 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 4997 | 577 | ["ad41ef44-662e-4826-ad55-a05d38e84550","a5b9cdce-3709-433b-b614-1814a49c3373"] | b790a764-b7fb-4790-87a5-9f82968727bb |
| journey_788008295d4841dfb8a9 | 1 | chk_journey_788008295d4841dfb8a9_title_5 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 4998 | 593 | ["dbab5fc7-cc51-49f9-9058-365d58995a94","ea0628d8-1140-4629-81fb-9ad4632fe498"] | b790a764-b7fb-4790-87a5-9f82968727bb |
| journey_805cf5e4d88a72a3f28e | 1 | chk_journey_805cf5e4d88a72a3f28e_s1_1 | visible | user_approved | satisfied | True | True | 5007 | 625 | ["41900b46-ae03-475f-8a30-b4dfa8e123cd","66282fd7-a8a4-4140-9bc9-d6aed8f4a833"] | 32ba7c01-3cc5-46d4-ae4b-a11c36d91c56 |
| journey_805cf5e4d88a72a3f28e | 1 | chk_journey_805cf5e4d88a72a3f28e_s1_2 | enabled | user_approved | satisfied | True | True | 5008 | 641 | ["9d7d77a6-ea85-4f33-8cd1-43a6d21c6674","927b2135-6611-45ce-8077-d94d0206a628"] | 32ba7c01-3cc5-46d4-ae4b-a11c36d91c56 |
| journey_805cf5e4d88a72a3f28e | 1 | chk_journey_805cf5e4d88a72a3f28e_s1_3 | visible_text | user_approved | satisfied | Help guide | Help guide | 5010 | 765 | ["8169b75c-e6be-44e6-86b9-0f84b4ae56ef","f01fe291-558c-4853-a5b8-dc215b356f80"] | 32ba7c01-3cc5-46d4-ae4b-a11c36d91c56 |
| journey_805cf5e4d88a72a3f28e | 1 | chk_journey_805cf5e4d88a72a3f28e_url_4 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 5011 | 594 | ["66381db8-26e6-4744-81ab-f4e3904984a5","0055d672-4d68-43a8-b66a-d1266819a6f4"] | 32ba7c01-3cc5-46d4-ae4b-a11c36d91c56 |
| journey_805cf5e4d88a72a3f28e | 1 | chk_journey_805cf5e4d88a72a3f28e_title_5 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 5012 | 577 | ["885cc5a1-4170-481b-a027-9e5fa6927bcc","4b05e98f-bc0d-4bd4-bf99-ab6089649d68"] | 32ba7c01-3cc5-46d4-ae4b-a11c36d91c56 |
| journey_a50f0666c2c384f31cdc | 1 | chk_journey_a50f0666c2c384f31cdc_s1_1 | visible | user_approved | satisfied | True | True | 5014 | 625 | ["f44cefce-db31-4715-b206-50e13810e2a0","367a38c3-53a6-4316-b98b-9a39da1ffc2a"] | 374547fd-7b69-4f52-b8dc-5b2b3398f796 |
| journey_a50f0666c2c384f31cdc | 1 | chk_journey_a50f0666c2c384f31cdc_s1_2 | enabled | user_approved | satisfied | True | True | 5015 | 641 | ["cf088afe-59e7-4411-8010-2f7cd5b37f7e","ecfdd76c-d3f2-4b9f-894c-a80b8935adec"] | 374547fd-7b69-4f52-b8dc-5b2b3398f796 |
| journey_a50f0666c2c384f31cdc | 1 | chk_journey_a50f0666c2c384f31cdc_s1_3 | visible_text | user_approved | not_satisfied | Billing settings | absent | 5017 | 6641 | ["fbc62e24-a983-4622-955f-5e65e730acf1","56d29f91-ce91-4aa8-a9a4-ec4216254384"] | 374547fd-7b69-4f52-b8dc-5b2b3398f796 |
| journey_a50f0666c2c384f31cdc | 1 | chk_journey_a50f0666c2c384f31cdc_url_4 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 5018 | 609 | ["309f5dae-6e6b-46e6-9d59-25fa2466ad3b","f603034f-0713-4e5b-ab6b-5dec80d2e5d0"] | 374547fd-7b69-4f52-b8dc-5b2b3398f796 |
| journey_a50f0666c2c384f31cdc | 1 | chk_journey_a50f0666c2c384f31cdc_title_5 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 5019 | 609 | ["7d7d31b8-0248-4276-91b3-fd7bee1550ef","c28e9193-1149-4e50-855a-d2327df1db41"] | 374547fd-7b69-4f52-b8dc-5b2b3398f796 |
| journey_4c224ee2682e030b2f1d | 1 | chk_journey_4c224ee2682e030b2f1d_s2_1 | visible | user_approved | satisfied | True | True | 5029 | 688 | ["a55bd559-f7c7-4f4a-b9b7-ff773a41ad48","5a46522a-69f3-4909-8447-2290c87a41e2"] | 93441298-946f-47e3-8584-dd60f84e1d4f |
| journey_4c224ee2682e030b2f1d | 1 | chk_journey_4c224ee2682e030b2f1d_s2_2 | enabled | user_approved | satisfied | True | True | 5030 | 655 | ["4de08c1e-bb77-45c5-9497-28e7c6839e86","aaea474e-f7ed-4039-9fbb-c79182472eac"] | 93441298-946f-47e3-8584-dd60f84e1d4f |
| journey_4c224ee2682e030b2f1d | 1 | chk_journey_4c224ee2682e030b2f1d_url_3 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 5032 | 625 | ["0978085c-ca43-4428-a35c-3a5061c6e967","c72ce2b6-eb41-45da-9b45-77128cb6689b"] | 93441298-946f-47e3-8584-dd60f84e1d4f |
| journey_4c224ee2682e030b2f1d | 1 | chk_journey_4c224ee2682e030b2f1d_title_4 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 5033 | 577 | ["a65c7c5d-75e3-48eb-b2a3-7a5b173746a9","df19154a-3752-4e1f-a815-51914e1d65ce"] | 93441298-946f-47e3-8584-dd60f84e1d4f |
| journey_d9702e77c58cda85122d | 2 | chk_journey_d9702e77c58cda85122d_s2_1 | visible | user_approved | satisfied | True | True | 5036 | 625 | ["0a8792e8-4c0b-450b-9795-bbc122dd1ef3","57b5a913-735c-41fa-a363-4697b9097839"] | 3101e9bb-7422-4912-a5da-faeb4fe6852f |
| journey_d9702e77c58cda85122d | 2 | chk_journey_d9702e77c58cda85122d_s2_2 | enabled | user_approved | satisfied | True | True | 5037 | 687 | ["a97d2685-66e7-466a-be71-f907852143ec","2443d27f-298f-4f47-89af-b73c2a5ffd41"] | 3101e9bb-7422-4912-a5da-faeb4fe6852f |
| journey_d9702e77c58cda85122d | 2 | chk_journey_d9702e77c58cda85122d_s2_3 | visible_text | user_approved | satisfied | Display name saved successfully. | Display name saved successfully. | 5039 | 750 | ["4e187640-c803-4de0-8179-c63f72c64f3b","82fbea35-fbc6-459e-bb1a-2f5d97ef7767"] | 3101e9bb-7422-4912-a5da-faeb4fe6852f |
| journey_d9702e77c58cda85122d | 2 | chk_journey_d9702e77c58cda85122d_url_4 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 5040 | 561 | ["e22d6f58-edc5-4a7d-9b1c-17fedebb5dfd","3b21ac48-c391-44f5-aa41-2103a13347bf"] | 3101e9bb-7422-4912-a5da-faeb4fe6852f |
| journey_d9702e77c58cda85122d | 2 | chk_journey_d9702e77c58cda85122d_title_5 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 5041 | 577 | ["0c6cdb2e-be94-4247-9752-d02d9da051d0","1746aca2-49b3-4444-ac5b-096d840dd86a"] | 3101e9bb-7422-4912-a5da-faeb4fe6852f |
| journey_f836989631abc11f728f | 2 | chk_journey_f836989631abc11f728f_s1_1 | visible | user_approved | satisfied | True | True | 5043 | 702 | ["50a22b63-fcf6-4c6c-b528-f86a7b5484ae","43037708-b0d6-402f-9b0e-da03f80703af"] | ebe7221c-ef70-4e0b-8add-d2963ca7c76f |
| journey_f836989631abc11f728f | 2 | chk_journey_f836989631abc11f728f_s1_2 | enabled | user_approved | not_satisfied | True | False | 5044 | 3671 | ["315df344-17c3-4f7a-965c-f8c64daf16d9","75133b64-b733-44ea-8a98-34200f06462a"] | ebe7221c-ef70-4e0b-8add-d2963ca7c76f |
| journey_e5807dca570876979c3a | 2 | chk_journey_e5807dca570876979c3a_s2_1 | visible | user_approved | satisfied | True | True | 5050 | 655 | ["350071eb-1b43-4937-ac35-0ebe7f65e701","3e8e9e24-39da-49bb-814f-1afe67c9b6ee"] | 8375166e-5f40-4630-bde0-9e65f5d12e98 |
| journey_e5807dca570876979c3a | 2 | chk_journey_e5807dca570876979c3a_s2_2 | enabled | user_approved | satisfied | True | True | 5051 | 639 | ["2a180853-99c6-4a50-aa1a-5c094c76fd68","d6258750-4178-4855-9b1e-7a4128eddc37"] | 8375166e-5f40-4630-bde0-9e65f5d12e98 |
| journey_e5807dca570876979c3a | 2 | chk_journey_e5807dca570876979c3a_s2_3 | visible_text | user_approved | not_satisfied | Contact address is required | absent | 5053 | 6655 | ["081685e2-7569-4863-8204-34889f554875","82a0d718-fbb7-428b-8b7d-d26df683d497"] | 8375166e-5f40-4630-bde0-9e65f5d12e98 |
| journey_e5807dca570876979c3a | 2 | chk_journey_e5807dca570876979c3a_url_4 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 5054 | 625 | ["fcd36d1e-db2c-481f-bd9a-dc70e224f213","0c5e20d6-6fe8-47ed-90fa-c5e6bdd7798c"] | 8375166e-5f40-4630-bde0-9e65f5d12e98 |
| journey_e5807dca570876979c3a | 2 | chk_journey_e5807dca570876979c3a_title_5 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 5055 | 609 | ["a1811720-aa2e-4842-9eee-1448f55d8824","b2379191-7aab-4028-812f-aa3afe7f9e7b"] | 8375166e-5f40-4630-bde0-9e65f5d12e98 |
| journey_6f2359086e98d99e7fa8 | 2 | chk_journey_6f2359086e98d99e7fa8_s2_1 | visible | user_approved | satisfied | True | True | 5066 | 686 | ["4821096e-32cf-47a9-a3ea-e72951bb2a24","409f8114-4fb9-4f41-907c-7b23c4fe6d28"] | 4fc4261e-4e04-4267-a5e9-4da7355e29ab |
| journey_6f2359086e98d99e7fa8 | 2 | chk_journey_6f2359086e98d99e7fa8_s2_2 | enabled | user_approved | satisfied | True | True | 5067 | 687 | ["2961eb6e-a4de-4a6d-907a-4a361ec66382","9e7efe75-d2e9-4f64-b356-ee7de6a974cd"] | 4fc4261e-4e04-4267-a5e9-4da7355e29ab |
| journey_6f2359086e98d99e7fa8 | 2 | chk_journey_6f2359086e98d99e7fa8_url_3 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 5069 | 563 | ["0e2393b0-f8e6-48dc-9c32-2ffc8bf8754f","c0895c17-30ac-4f1a-9c30-024c2d627959"] | 4fc4261e-4e04-4267-a5e9-4da7355e29ab |
| journey_6f2359086e98d99e7fa8 | 2 | chk_journey_6f2359086e98d99e7fa8_title_4 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 5070 | 578 | ["09a3f109-14fd-48cc-b7ec-e1fcad1031e9","d83f8f8d-5bb2-44be-b1d1-7f91b2f5b534"] | 4fc4261e-4e04-4267-a5e9-4da7355e29ab |
| journey_788008295d4841dfb8a9 | 2 | chk_journey_788008295d4841dfb8a9_s1_1 | visible | user_approved | satisfied | True | True | 5072 | 687 | ["61e86035-1dd8-4215-80b9-2351b44ed67d","c70bfd12-1d5d-4246-992d-4d057e721cd7"] | 0bf9f685-c6aa-48fb-8fb0-6596a54a524b |
| journey_788008295d4841dfb8a9 | 2 | chk_journey_788008295d4841dfb8a9_s1_2 | enabled | user_approved | satisfied | True | True | 5073 | 766 | ["edb532a5-766e-4d6d-be10-0cca89983ac7","8d90c9d4-0123-41e0-bf62-9ea59e06e17e"] | 0bf9f685-c6aa-48fb-8fb0-6596a54a524b |
| journey_788008295d4841dfb8a9 | 2 | chk_journey_788008295d4841dfb8a9_s1_3 | visible_text | user_approved | not_satisfied | Preview ready | absent | 5075 | 6734 | ["ee2de2ad-df64-4876-bd05-15fc20c8a14b","ac072bd1-c2c8-471c-81e0-8328b41ac6e3"] | 0bf9f685-c6aa-48fb-8fb0-6596a54a524b |
| journey_788008295d4841dfb8a9 | 2 | chk_journey_788008295d4841dfb8a9_url_4 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 5076 | 577 | ["5dc0ee53-d0ea-45f1-b321-4c5cb3dd6e55","ac137404-7c3f-4bce-8f9f-bcfa570ebdc4"] | 0bf9f685-c6aa-48fb-8fb0-6596a54a524b |
| journey_788008295d4841dfb8a9 | 2 | chk_journey_788008295d4841dfb8a9_title_5 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 5077 | 562 | ["e819c77f-cb62-40f3-8fb5-82356613a10f","5200bcea-8732-4cad-8b3c-ef669baae2ff"] | 0bf9f685-c6aa-48fb-8fb0-6596a54a524b |
| journey_805cf5e4d88a72a3f28e | 2 | chk_journey_805cf5e4d88a72a3f28e_s1_1 | visible | user_approved | satisfied | True | True | 5086 | 672 | ["3de57f49-e660-44e4-bd81-c3ab4d700baa","98c65336-779d-4dd2-a3e4-942a64da40fe"] | df890f79-b214-477b-a416-8c842762e97c |
| journey_805cf5e4d88a72a3f28e | 2 | chk_journey_805cf5e4d88a72a3f28e_s1_2 | enabled | user_approved | satisfied | True | True | 5087 | 686 | ["f1e99e91-b129-4db2-9d67-a42a90a73977","b6773b76-44a8-4e41-b056-a4bbeb462e80"] | df890f79-b214-477b-a416-8c842762e97c |
| journey_805cf5e4d88a72a3f28e | 2 | chk_journey_805cf5e4d88a72a3f28e_s1_3 | visible_text | user_approved | satisfied | Help guide | Help guide | 5089 | 781 | ["4b1a93cb-219f-48d5-96f9-781e16badde9","9c8a9828-485f-496e-b485-42b6d570773c"] | df890f79-b214-477b-a416-8c842762e97c |
| journey_805cf5e4d88a72a3f28e | 2 | chk_journey_805cf5e4d88a72a3f28e_url_4 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 5090 | 563 | ["437c5b0f-7124-41a2-9104-22f5fab79e08","284bd0b6-003e-4f3b-9007-3191d3ee18a3"] | df890f79-b214-477b-a416-8c842762e97c |
| journey_805cf5e4d88a72a3f28e | 2 | chk_journey_805cf5e4d88a72a3f28e_title_5 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 5091 | 625 | ["00b4ca34-5fb6-4a17-9e82-49a0c1eb45b5","78a7fba9-a623-47d0-b846-cac95b56295d"] | df890f79-b214-477b-a416-8c842762e97c |
| journey_a50f0666c2c384f31cdc | 2 | chk_journey_a50f0666c2c384f31cdc_s1_1 | visible | user_approved | satisfied | True | True | 5093 | 750 | ["e3fffba4-cbc6-4ca1-b626-f934bcc22737","a95a2a3d-9664-41e2-99d2-d22ed434e27b"] | feb33e17-ba09-42b1-a6f1-fdd2e32ca598 |
| journey_a50f0666c2c384f31cdc | 2 | chk_journey_a50f0666c2c384f31cdc_s1_2 | enabled | user_approved | satisfied | True | True | 5094 | 718 | ["dd08e548-7b62-449b-9c8c-9c4fe5041028","79ca443d-20c0-46c6-bcaf-074605c8030c"] | feb33e17-ba09-42b1-a6f1-fdd2e32ca598 |
| journey_a50f0666c2c384f31cdc | 2 | chk_journey_a50f0666c2c384f31cdc_s1_3 | visible_text | user_approved | not_satisfied | Billing settings | absent | 5096 | 6672 | ["8cb2b634-4b48-4d5a-bcf8-731748a2f992","bb0a2351-aafc-4280-973a-33e3e4966444"] | feb33e17-ba09-42b1-a6f1-fdd2e32ca598 |
| journey_a50f0666c2c384f31cdc | 2 | chk_journey_a50f0666c2c384f31cdc_url_4 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 5097 | 561 | ["2c303148-d3d9-40c2-9d23-807ab9a6a829","e2e5d7c2-f524-45ff-acb6-5a29140190f6"] | feb33e17-ba09-42b1-a6f1-fdd2e32ca598 |
| journey_a50f0666c2c384f31cdc | 2 | chk_journey_a50f0666c2c384f31cdc_title_5 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 5098 | 608 | ["d82e972b-f95e-47bc-94b2-7ca4a7f8185a","f71cdc6f-37a2-4228-a2b2-a8ebd49ee59f"] | feb33e17-ba09-42b1-a6f1-fdd2e32ca598 |
| journey_4c224ee2682e030b2f1d | 2 | chk_journey_4c224ee2682e030b2f1d_s2_1 | visible | user_approved | satisfied | True | True | 5108 | 735 | ["26dd2191-abf3-4f2f-950f-d6573b6eefb5","bf813ef3-bc4e-4b18-9822-29c965215be4"] | 884da799-5aa0-47a6-af40-03c4e63c8de8 |
| journey_4c224ee2682e030b2f1d | 2 | chk_journey_4c224ee2682e030b2f1d_s2_2 | enabled | user_approved | satisfied | True | True | 5109 | 766 | ["c89da430-33fa-4c7d-9344-c4784e4e02a9","eed62564-2d8e-45ef-b48d-f49d5d2f2bdf"] | 884da799-5aa0-47a6-af40-03c4e63c8de8 |
| journey_4c224ee2682e030b2f1d | 2 | chk_journey_4c224ee2682e030b2f1d_url_3 | url_path_v1 | user_approved | satisfied | http://127.0.0.1:56136/index.html | http://127.0.0.1:56136/index.html | 5111 | 609 | ["ddbdab4b-2f1c-4f2a-8682-a0c4a7e7fb88","c47259f5-28e0-4105-acb7-be0e7b6f4942"] | 884da799-5aa0-47a6-af40-03c4e63c8de8 |
| journey_4c224ee2682e030b2f1d | 2 | chk_journey_4c224ee2682e030b2f1d_title_4 | title | user_approved | satisfied | MarketTwin controlled benchmark | MarketTwin controlled benchmark | 5112 | 625 | ["0826d7d5-e358-4c7d-90ad-8bb629f70552","f6ae27ec-f5d7-438e-be25-844593500157"] | 884da799-5aa0-47a6-af40-03c4e63c8de8 |

### Replay links (12 rows)

| Journey ID | Contract version | Contract hash | Original execution | Original attempt | Original verdict | Replay execution | Replay attempt | Replay verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2bf292f4-1be1-4ed8-99b5-728e7ecae755 | 1 | 3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373 | 18c09160-396e-4749-b681-dda686a0323b | 1 | unverified | 5f348f86-0a93-4b21-890c-ab9774331f4b | 2 | unverified |
| 971f32db-2ca9-4264-b9bb-1b9f9db1bebf | 1 | 3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373 | 3b283c1b-aac8-4f33-825b-6f26ae4c559f | 1 | unverified | 5c29ca1e-6d9b-4dc8-803e-7b2b50939109 | 2 | not_satisfied |
| edc22e6a-dfb2-4530-8ac4-efbd95e73ffd | 1 | 3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373 | b3c3d157-f93f-4f44-85c9-39714ee31f83 | 1 | not_satisfied | 06c68d93-51a3-426c-a980-dd2bb1a64acd | 2 | not_satisfied |
| 2ba272b7-7fb7-4e39-9697-0ff1c83156f3 | 1 | 3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373 | 033a7157-86eb-4e8c-a09b-9489cbba95a3 | 1 | not_satisfied | 174b02bf-990e-49eb-9064-fa36046d7e4c | 2 | not_satisfied |
| 2ad1edaf-40c7-4466-8e25-566132372970 | 1 | 3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373 | 0a8bf742-0fe6-4897-9cf6-7eb354499d77 | 1 | not_satisfied | 4f8d42cb-908b-4ee2-8add-6d872d9aba09 | 2 | not_satisfied |
| 34f164a7-963d-4146-b2c9-5f22af5de5f2 | 1 | 3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373 | c08ad01f-eef5-408b-88dd-570c8bb255e1 | 1 | not_satisfied | b1e7a69b-778d-4575-83e9-29995d070fdb | 2 | not_satisfied |
| aeeeda2c-10c0-4901-aa0f-95deb59fd8eb | 1 | 3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373 | b790a764-b7fb-4790-87a5-9f82968727bb | 1 | not_satisfied | 17718f6e-e039-478a-9ad1-f2b77ece36e0 | 2 | not_satisfied |
| 8bef3a50-85b5-4a64-9465-1371d6205d6b | 1 | 3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373 | 374547fd-7b69-4f52-b8dc-5b2b3398f796 | 1 | not_satisfied | 4114bdda-3b4d-444b-b362-37d959a72f99 | 2 | not_satisfied |
| 8adac070-f5b2-4d89-bc44-8245cca8cd30 | 1 | 3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373 | ebe7221c-ef70-4e0b-8add-d2963ca7c76f | 1 | not_satisfied | 26d0ca7f-93df-41a0-a22c-76dceb62c280 | 2 | not_satisfied |
| 72a22573-45b7-43ff-a7e7-a391a891ca79 | 1 | 3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373 | 8375166e-5f40-4630-bde0-9e65f5d12e98 | 1 | not_satisfied | 8f7422f2-921d-4f12-9182-cf424b29c779 | 2 | not_satisfied |
| 4d5c95ee-a972-4232-99b4-5bf60f0dc65c | 1 | 3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373 | 0bf9f685-c6aa-48fb-8fb0-6596a54a524b | 1 | not_satisfied | 3d5a073c-8fca-4e23-8729-4a33b2f0a3b0 | 2 | not_satisfied |
| 6d2c9b6b-6d46-41a3-ae6c-7b198c271079 | 1 | 3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373 | feb33e17-ba09-42b1-a6f1-fdd2e32ca598 | 1 | not_satisfied | 00a886c9-1d7f-4d08-adc7-e534a6932c29 | 2 | not_satisfied |

### Confirmed seeded findings and exact replay evidence (4 rows)

| Journey key | Assertion ID | Check | Finding reason | Original execution | Original step | Replay execution | Replay step | Verification | Original artifacts | Replay artifacts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| journey_788008295d4841dfb8a9 | chk_journey_788008295d4841dfb8a9_s1_3 | After clicking button 'Generate preview', text 'Preview ready' appears. | reproduced | b3c3d157-f93f-4f44-85c9-39714ee31f83 | 4917 | 06c68d93-51a3-426c-a980-dd2bb1a64acd | 4924 | verified_deterministic | ["1b0e5a94-ef62-4987-a289-ec589b43d587","7b7ce19e-a0a2-4b4f-ac35-08b04d981803"] | ["d3e52fce-2446-4e86-ad4a-b399c5de3f40","dd44f678-26de-4338-bba6-9b4879506c87"] |
| journey_a50f0666c2c384f31cdc | chk_journey_a50f0666c2c384f31cdc_s1_3 | After clicking link 'Open billing settings', text 'Billing settings' appears. | reproduced | 033a7157-86eb-4e8c-a09b-9489cbba95a3 | 4938 | 174b02bf-990e-49eb-9064-fa36046d7e4c | 4945 | verified_deterministic | ["e144d4b4-ec36-425b-a817-175670a47b99","35e18f15-05ab-4c38-9b30-55a5cc17e4a8"] | ["277f0de2-e5bc-4a90-bc6a-23e7e1258780","13423dc4-60a8-4c32-9076-ce465bdc765a"] |
| journey_f836989631abc11f728f | chk_journey_f836989631abc11f728f_s1_2 | At step 1, button 'Continue to next step' is enabled. | reproduced | 0a8bf742-0fe6-4897-9cf6-7eb354499d77 | 4965 | 4f8d42cb-908b-4ee2-8add-6d872d9aba09 | 4968 | verified_deterministic | ["bf70491c-7ad8-44bc-be65-131aecaa7213","76da0fd6-c4bf-4d63-8697-c6e7615950c7"] | ["4e5f017c-9b5e-459f-a1e3-8d0497e2967d","6590e14d-6128-4a7f-9f39-5edc2368b27e"] |
| journey_e5807dca570876979c3a | chk_journey_e5807dca570876979c3a_s2_3 | After clicking button 'Check contact address', text 'Contact address is required' appears. | reproduced | c08ad01f-eef5-408b-88dd-570c8bb255e1 | 4974 | b1e7a69b-778d-4575-83e9-29995d070fdb | 4982 | verified_deterministic | ["1c9827a6-a89f-4f3b-b20a-7ecbf2ff0bdb","bec4c55c-1ae8-45ec-8377-efd260dfce96"] | ["fa9d917c-dddc-4ffd-b5c8-ff3209ba3026","e1af9c4a-9460-412f-bc03-7d6779eb49f3"] |

## Comparison to legacy and deep engines (not measured)

The retained controlled-fixture acceptance artifacts are all `discovery_contract_v1`,
including the pre-fix and repaired 4/4 reports. The only counted frozen-contract replay
so far is broken replay 1: 4/4 seeded defects, navigation detected, and 21/24 terminal
journey-persona outcomes. The same-fixture three-broken/three-good campaign is still
incomplete. These results show per-run behavior for the new mode, not an improvement
over an older engine.

No matched `legacy_persona` or `deep_feature_v1` run against this same four-defect
fixture, approved checks, target, personas, and budget was found in the retained records.
`.local/audit/recent-evaluations.json` contains nine `deep_feature_v1` runs, but they
cover different applications/tasks with 2–5 planned cases and are not seeded-fixture
comparisons. The historical failure matrix records selected old failures but states its
database reread was unavailable and current precision/recall/coverage/repeatability are
unknown. Therefore, we cannot claim that the new mode beats either older engine. A
matched old-engine benchmark with the same fixture/oracles/budget and scored evidence is
required to support that claim.

## Frozen replay preflight attempt (2026-11-02)

The initial source-run replay launch was rejected during read-only preflight before
creating a run or executing any browser action. The preserved log is
`.local/contract-benchmark-single-contract-20261102.log`. The validator compared
serialized fixture rules without accounting for optional `scope_name: null` and
`scope_role: null` fields present in the source snapshot. Inspection confirmed the
source run retains both original approval flags and the exact three declared fixture
rules; this was a representation mismatch, not a policy or authorization change.
No replay acceptance gates were measured. The source contract remains unchanged.

The first normalized-rule retry passed source validation and created destination
run `43054f88-411e-4e79-9472-e087f7cdf761` as campaign replay 2 / operational run 4,
with the source run/hash copied. Its `/contract/start` request returned HTTP 503
before freezing or queueing. A read-only DB check confirms the destination remains
`draft` with an `approved` contract, no frozen contract, and no discovery stage;
the benchmark checkpoint records `contract_reused` and no execution/report. The
preserved files are `.local/contract-benchmark-single-contract-20261102-retry1.json`
and `.log`. This is a launch/readiness failure, not an acceptance result, and no
replay action or gate was measured. The response body was not captured, so the
specific readiness check causing HTTP 503 is not yet confirmed.

## Frozen contract replay 2 (operational run 4)

Fresh replay run `721d6ec8-1b7d-40d6-a2d4-c3959ef9915b` reused source run
`ed1eba45-267d-44af-956d-463209266c77`, contract
`04e84d9b-1a27-4f1e-b8ae-fca678a1d3cd`, version 1, and hash
`3fe82169502657202ceb372c6744163f035bac03267e31fc96f980b5e9bcf373` without
discovery. Readiness preflight returned ready with dispatch, Kafka, execution,
evaluation, and model checks all true. The scored broken-fixture report confirmed
4/4 seeded defects (including navigation) and 4 findings; 24/24 original
journey/persona outcomes were terminal (100%), with 0/24 inconclusive (0%).
All 4 confirmed findings mapped to seeded defects (0 unexpected confirmed findings).
There were zero manual interventions, complete provenance, and valid report
integrity; the good-fixture false-confirmation gate is not measured by this broken
run. Replay create-to-report took 590.19 seconds (9m50s), 329.5 seconds (5m30s)
faster than the source full run's 15m19.7s. Persisted execution took 541.03 seconds
(9m01s), report generation took 26.08 seconds, and discovery event count was zero.

Correction (2026-11-02): an earlier status message mistakenly assigned source
Run1 completion counts to Run4. The saved Run4 report and scorer output both show
24/24 terminal, 0/24 inconclusive; Run1 remains 21/24 and 3/24.

Run artifact: `.local/contract-benchmark-single-contract-20261102-retry2.json`;
log: `.local/contract-benchmark-single-contract-20261102-retry2.log`. These are
per-run results only; the six-run campaign remains incomplete.

## Frozen contract good-fixture replay 1 (operational run 6)

Run `acde605d-19ba-4947-92d9-5d2ef9ae91de` reused source run
`ed1eba45-267d-44af-956d-463209266c77` and the same contract ID/version/hash; the
scorer found complete provenance and the saved report hash matched the frozen
source. On the good fixture, there were 0 unexpected confirmed findings and no
seeded defects. Completion was 23/24 (95.8%), with 1/24 inconclusive (4.2%); there
were zero manual interventions and report integrity passed. The inconclusive case
was `journey_788008295d4841dfb8a9` (persona index 2): all five assertions and both
actions completed successfully, but browser cleanup timed out, leaving the case
`runtime_failed` / unverified. Replay create-to-report took 328.50 seconds (5m28.5s),
591.20 seconds (9m51.2s) faster than the source full run. Persisted execution took
304.19 seconds, report generation 17.43 seconds, and discovery event count was zero.
The campaign is still in progress; no aggregate gate conclusion is drawn here.

## Frozen contract good-fixture replay 2 (operational run 7)

Run `2ca8d0d2-4eae-4949-846e-7627ee6c783e` reused the same frozen contract,
discovery map, and source target. It produced 0 false/unexpected confirmed findings
and 0 seeded-defect findings on the good fixture. Completion was 24/24 (100%),
with 0/24 inconclusive outcomes and zero manual interventions. Provenance was
complete and report integrity passed. Replay create-to-report took 344.48 seconds
(5m44.5s), 575.22 seconds (9m35.2s) faster than the source full run; persisted
execution took 320.14 seconds and report generation 17.58 seconds. Discovery event
count was zero. Good-fixture replay 3 remains in progress.

## Frozen contract replay 3 (operational run 5)

Run `6c0a7ac9-8ae8-47d7-902b-d147ac681e8e` reused the same source contract ID,
version, hash, discovery map, target, and approved fixture policy. Its broken-fixture
report confirmed 4/4 seeded defects, including navigation; all four confirmed
findings mapped to seeded defects (0 unexpected confirmed findings). Original
journey/persona completion was 24/24 (100%), inconclusive outcomes 0/24 (0%), and
manual interventions 0. Provenance was complete and report integrity passed.
Replay create-to-report took 683.20 seconds (11m23s), 236.50 seconds (3m57s)
faster than the source full run's 15m19.7s. Persisted execution took 657.33 seconds
(10m57s), report generation took 18.69 seconds, and discovery event count was zero.
This completes the required three broken-fixture runs (baseline run 1 plus
operational runs 4 and 5); three good-fixture replays remain.
