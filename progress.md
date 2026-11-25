## 2026-11-24 | Marley (Muse) — SKR complete; captcha fixed; MT-000226 monitored, validated, and one correction

**Source knowledge recovery (Sol's reviewed order) — ALL FIVE STEPS BUILT + VERIFIED.** Streams A–C in parallel with exclusive file ownership; research decisions applied (BM25 + char-gram fallback + ask-door escalation for selection; sections packed atomically, never truncated; generate-both-then-publish with preview compatibility RETAINED — the older preview-removal pass is deferred, nothing deleted). Step 5: fixture half fully proven (orc 132/0, ctl 143/0, KW 96/6); live half proven through plan loading (ingest → dual publish → approve → pin → load) on real run MT-000225. The final link — a requirement followed into an executed check with browser evidence — is NOT live-proven. Open items, exactly as found: **D-D1** a file pinned directly AND via its own collection loads twice (fix designed, HELD by the owner's 2026-11-24 no-changes order; production file verified byte-untouched; one unproven regression test sits appended in the test file); **D-D2** Klaviyo has no compiled graph, so zero requirement-derived checks were authored (design boundary); **D-D3** the expired login park closed all remaining items not_checked, so no browser evidence for the two test requirements exists. Per-stream checkpoints: .local\\marley-skr\\CHECKPOINTS-{A,B,C,D}.md on the PC.

**reCAPTCHA egress — FIXED + LIVE-PROVEN (owner rule, 2026-11-24).** Diagnosis: the widget's script/iframe loads were allowed; its two verification POSTs (reload, userverify) were blocked by the old method gate "CAPTCHA assets require GET or HEAD", so no token could ever be produced (the owner's "Missing reCAPTCHA response" screenshot). Fix: cross-origin sends allowed by default; one classifier blocks a send — with a named reason recorded — only when its body carries sensitive data (sensitive field classes, or a Luhn-valid card number); G1 (internal/private) absolute; every block and every newly-seen third-party domain recorded. hCaptcha and Turnstile covered. Evidence: 21/21 flow probe; browser sweep 175/176 (the 1 proven pre-existing); live on the real Klaviyo login — widget renders, no loading error, allow events recorded. **Activation deferred:** the worker was not restarted (7 owner runs in flight); the fix activates at the next worker restart. Checkpoint: .local\\marley-skr\\CHECKPOINTS-CAPTCHA.md.

**MT-000226 (slop, Klaviyo) — monitored, then independently validated.** Monitor's report: run-report.md (repo root) — verdict GOING RIGHT with 5 numbered issues (lane 1 died silently in minute one and was never replaced; desktop-only configuration vs the two-viewport rule; the captcha failure leaves no trace in the run record; park 600s config vs the 15-minute design record; stop_reason one-liner incomplete). Validator's report: result-validation.md (repo root) — **RIGHT WITH EXCEPTIONS (2)**: all 19,476 element verdicts reproduce exactly under the measurer's own rules; defects recount identically from three sources; the withheld percentage recomputes exactly from the payload's areas (0.2432); served payload deep-equal to stored. Exceptions: (E1) families.states_visited says 49, the same payload carries 55 states; (E2) the published provenance_errors falsely accuse 44 of 45 minor verdicts of gate failure — tier_context is stripped before the publication aggregate re-checks the gate (with true context: 0 errors; prominence 1.7175, not the published 1.5151). Neither exception changes a verdict or a count.

**CORRECTION to the "16 broken images" framing (Marley, 2026-11-24 ~01:16 CST):** the 16 severe findings on /bfcm are NOT broken images. Direct fetch of all 16 URLs: every one returns HTTP 200 with real image bytes (2.6 KB–926 KB). The run's browser recorded complete=true with natural_width=0 — the load finished with zero pixels because the fetch failed on OUR side (the same run shows client-blocked third-party requests elsewhere; the run predates the egress fix). Substance: our fetch failure published as a product defect — the broken-media verdict must require server-side failure evidence, not merely zero pixels in our browser. Settling step: re-measure /bfcm on current code after the worker restart. The validation report carries this as a signed addendum.

**Designer audit of the live MT-000226 Summary — grade 5/10** ("professional skeleton, unfinished finish"; 11 of 20 spec-v2 requirements met, 6 partial, 3 violated). Artifact: summary-audit-mt-000226. Structural fixes S1–S7 (fix-first grouping merge; defects headline excluding test-condition classes — 486 of 575 are environment errors, true console errors 89; pending grouped by path prefix; gate line in plain words; re-run diff reason line; unverified-state chip; takeaway stop caption) await the owner's go; implementation route is Sol per the implementation plan.

---

# MarketTwin audit progress

## November 24 — Marley design follow-through

Applied the five-destination shell, moved Check the look into New test, and kept legacy Slop, Testers and Settings bookmarks meaningful. Apps → Personas now links to instructions from that application's tests. New test starts with the run kind. Settings exposes Profile and Workspace. Home's empty state uses the real workspace empty state. Knowledge has Map, Freshness, Skills and Expectations anchors, source-library links in both directions, and clearly named list/entry components. Removed the unreferenced LearnTaskForm. Watch toolbar files were outside this work.

New Look reports exclude recorded browser-blocked and empty-response resource messages from headline JavaScript signal totals. Original observations remain available in Test conditions. Historical totals still use the saved aggregate and the caption names their basis.

Web typecheck and build passed. The initial nine-suite check returned 68 passes with one freshness assertion failing because the new link duplicates its text. The corrected navigation, map and instructions rerun returned 26 passes. Aggregate and evaluator tests returned 10 passes. Remaining Marley work includes the full CSS token and concept stylesheet migration, the physical Knowledge panel split, remaining summary vocabulary and legacy run-route consolidation, and the live artifact and comprehension acceptance checks.

## November 24 — protected browser navigation

Added a compact Back, Forward and Reload toolbar in Watch. Commands are enabled after the first protected frame and use the authenticated viewer's sequence and ownership checks. They act on the current test page and its existing history. Verified 22 viewer UI tests, three browser-owner tests including real Chromium navigation and detached-lease rejection, and web typecheck. The serving worker still needs to load the new code. Four runs were marked running at the restart check, so no worker was restarted.

## November 24 — CAPTCHA failure in Watch

Follow-up used an isolated room and worker lane with JS capture, visited Klaviyo, entered the browser's human control mode and reloaded the login page there. Both observations had a reCAPTCHA response field and no load-error banner. Observed Google provider responses were HTTP 200, while unrelated third-party requests were denied. MT-000227 was completed when rechecked, with no retained authentication or resume events found. The live provider failure did not reproduce and its exact cause remains unknown. The diagnostic script is in .local/marley-skr/check_captcha_handoff.py.

MT-000227 was awaiting human assistance and Watch showed an active operator lease. The user screenshot showed Klaviyo's reCAPTCHA load error within the connected viewer. The run recorded allowed reCAPTCHA and gstatic host events and no matching Google provider egress-denial events. A fresh controller probe on Klaviyo rendered the widget with zero CAPTCHA request failures. This narrows the investigation to the live handoff path or session conditions. The exact failing request in the active lease was not observed. No network policy or live lease was changed.

## November 24 — serving worker follow-up

- Verified local API health and HTTP 200 from the web UI. PostgreSQL showed the worker was actively handling MT-000227 (`24ab899f-599a-53c3-b7fe-a2eeef882d6b`). No worker restart was needed for the BFCM check.
- MT-000227 measured BFCM. The saved checkpoint records 18 image observations and zero severe broken-media flags. All 18 are undecided. Sixteen completed with unknown HTTP status and two remained incomplete. This verifies conservative classification on the serving worker. It leaves the underlying image-loading cause unresolved.
- Human-assistance, knowledge grounding and lane pool suites returned 25 passes. The knowledge fixture exercises file citation and case authoring. Human-operated Watch completion and a live source-to-browser requirement remain open. No human request was active when checked in MT-000227. Lane replacement and protected/public expiry isolation remain open.

## November 24 — MT-000226 recovery implementation

- Look publication now retains tier context and publishes inspected pages separately from recorded states. Replayed cached MT-000226 (`eeae9164-d51c-500b-8a70-7c15820f4293`) with its checkpoint context. The served and stored exports matched. Replay returned 55 states, zero provenance errors, prominence 1.7175 and a withheld percentage. Historical stored data was left intact.
- Look Summary surfaces score and its scope before backlog and comparisons. Unattributed historical image failures group by page and are marked for review. Desktop scan retries an in-view incomplete image probe once after a 250 ms wait. New broken-media flags require observable HTTP failure and zero pixels. Resource Timing does not always expose status; unavailable status and invalid media with HTTP 200 remain undecided. The owned Chromium fixture confirmed a real 404 still fires. It does not prove BFCM behavior.
- Lane retirement now records claim, phase, cause and remaining non-retired lanes. Desktop report timing distinguishes active, handoff and elapsed seconds. Replacement remains conditional on recovery evidence. Existing reason fields distinguish desktop cutoff from the run stop reason.
- Collection loading skips an identity already loaded through a direct pin or preceding collection. The existing deduplication regression and mid-run loading fixture are green. No live knowledge-derived browser run was attempted.
- Focused frontend tests 9 passed, typecheck and production build passed. Evaluator and catalogue tests 29 passed. A wider test run had 86 passes and one fixture assertion affected by an extra browser console message from the new explicit 404. The corrected fixture now selects the intended application message and passed on rerun. Existing repository-wide lint and whitespace findings remain.
- No serving worker revision or human takeover was verified. Local checks found no listener on the usual web, API and database ports. Open release work includes user-operated Watch completion, protected/public expiry isolation, fresh BFCM evidence, image failure subtypes beyond HTTP status, matched lane recovery measurements, first-paint and comprehension checks, and a cited knowledge-to-browser acceptance run.

## November 24 — MT-000226 planning review

Cross-checked the monitor and validator with saved payloads, Designer screenshots and DOM captures, current evaluator code, CAPTCHA checkpoint and SKR streams A–D. Added the ordered release plan to planner.md. No application changes, worker restart or new run in this review. Human challenge completion, running-worker revision, fresh media attribution and a live knowledge-derived browser check remain open.

## 2026-11-23 (late) | Marley — Source knowledge recovery: implementation running (3 parallel streams)

Sreenav's instruction: implement Sol's "Source knowledge recovery — reviewed implementation order" (planner.md, top) optimally, with multiple agents, research in parallel. State of play:

**Research (done, applied):** a parallel research pass settled the open design questions; full text is in Marley's workspace (skr-research-20261123.md). Decisions the builders are implementing: (R1) selection = BM25 over NFKC + casefolded tokens, character 3–5-gram cosine as fallback, both-empty escalates to the existing select_knowledge_files ask-door with the returned order recorded in the plan (resumed runs replay it identically), door down = named `selection_unavailable` omission. Ingestion-time embeddings were researched and REJECTED (vector-store + re-embed obligations; multilingual benchmarks can score below good BM25). (R2) packing: sections atomic (skip, never truncate), pins whole first, per-file cap = 1/3 of the 24k budget, ~2k held back as the mid-run reserve, omissions carry slug + reason + token count. (R3) publish: both outputs to their versioned hash keys, hashes verified, then ONE pointer flip in the existing _save transaction — no distributed transaction. (R4) boundaries: oversize media refused with a named reason; capped text records its omission; sections processed vs total recorded per entry.

**Structure (owner asked for parallel agents; exclusive file ownership per stream):**
- Stream A — Sol step 1: the Lead knowledge wiring in harness_run.py (the fenced insertion from the doc-33 build) + its harness tests. A first builder was stopped mid-step when the owner parallelised; its edits to harness_run.py / test_harness_run.py are in place and Stream A begins with a diff audit against the pre-edit snapshots before completing them.
- Stream B — Sol step 2: knowledge_loading.py selection + packing per R1/R2, tests first (multilingual brief, paraphrased brief, oversized document, door escalation, door-down omission, resume replay).
- Stream C — Sol steps 3+4: control-api ingestion + knowledge-worker (atomic dual-output publish per R3, extraction shared, preview compatibility RETAINED per Sol's order — the older preview-removal register is deferred, not executed; boundary measurements + named-refusal tests per R4).
- Stream D — Sol step 5 (after A–C land): fixture end-to-end + the LIVE verification. Docker is UP again on the PC (postgres/kafka/minio healthy), so the live half is unblocked: real upload → approve → run pinning a file → requirement followed to browser evidence + one mid-run open, real run IDs recorded separately from fixture results.

Per-stream checkpoints live on the PC in .local\\marley-skr\\ (CHECKPOINTS-A/B/C.md); snapshots in .local\\marley-backups\\skr-*. Completion claims will carry test IDs and failed-ID sets against the recorded baselines, per the owner's standing rule. — Marley

## November 23 — knowledge ingestion audit

Traced source extraction, Markdown and preview builds, persistence, run pinning, file selection and checkpoint requests. Recorded findings in research.md. Worker and focused consumer tests returned 135 passed and six skipped. Live model grounding, source-to-browser-check attribution and real workload timing remain open. Audit only.

## November 23 — Results v2 shared Summary implementation

- Summary now uses the same frame for Look, Explore, Persona, Contract and historical reports. The original overview, results and report routes remain usable. Watch and Activity have separate surfaces, and the Watch assistance link carries the human-action anchor.
- A built-app Chromium fixture verified Summary at 1440, 1024, 768 and 390 px with no horizontal overflow or axe violations within the report frame. Keyboard review opened the finding details and kept the exact evidence link. The historical feature-case fragment opened its case list.
- Look Chromium fixture checks reconstructed the MT-000223 `ui-element-58-e161` link at desktop and 390 px and replayed the MT-000222 export with 3,780 pending URLs across 569 paths, 20 initial state rows and no initial artifact requests. The live database was unavailable.
- The 29 Board and harness projection tests passed. Ruff passed for the harness writer. The vocabulary gate covers all 42 producible UI rule words and the tested verdict, check, persona and Contract reason maps. Live evidence access, actual saved payload replays and owner sign-off remain open.

## 2026-11-23 (late) | Marley (Muse) — Results spec v2 RELEASED, auditor-gated

Astra — the Results redesign package is complete on my side and has passed every gate. What landed in the repo root tonight:

- **results-ui-spec-marley.md — now v2** (replaces v1 in place). The implementation contract for the Results surface: one frame for all four run kinds (Look / Explore / Persona / Contract), every display decision traced to the audited display map (Appendix B), the 18 lost-data restores as a numbered backend list in §8 (evaluator projections RB-1…RB-6 first, then the 9 web-only restores; zero API changes), the vocabulary-completeness test in §9, acceptance in §10.
- **UI_IMPLEMENTATION_PLAN.md** — the whole-app plan from the Principal Designer agent: 7 steps, Results first, every audit finding mapped to its step.
- **DESIGN_DECISIONS.md** (D1–D10), **DESIGN_SYSTEM.md**, **UI_UX_AUDIT.md** (27 findings), **INFORMATION_ARCHITECTURE.md** — the design authority behind the spec.
- **display-map.md** + **data-inventory.md** — the evidence base: all 304 displayable report elements traced produced → persisted → served → rendered; 117 never reach the screen today; 230 display decisions, each cited to the research.

**Verification, not assertion:** an independent auditor agent gated each deliverable against 77 research-derived criteria. The inventory passed its re-gate (304 / 187 rendered / 117 never rendered — independently recomputed, incl. the rule-catalogue census: 79 rules, 39 producible, 37 with no producer). The display map passed after two fix rounds. Spec v2 + the interactive prototype passed the final gate after two one-paragraph/one-line fixes. The prototype (in my sandbox, on Sreenav's screen) is the visual reference for the spec.

**For your plan, Astra:** fold spec v2 in as the Results contract and UI_IMPLEMENTATION_PLAN.md's step order as the sequence. Sol implements; I verify against the saved runs (MT-000222 / MT-000199 / MT-000165 + the MT-000223 deep link) and report back here. Three carried items, none blocking: (1) CONF-02 — headline sizes are built at the Designer's ruling (verdict/takeaway 24px); Sreenav confirms at sign-off. (2) Ten manual checks (keyboard pass, greyscale, 390px deep-link reload, first-screen order…) are owed at sign-off — listed in the gate report, most need the live app. (3) One question is with Sreenav: whether the vocabulary-completeness test + the missing KIND_WORDS word (focus_indicator_invisible → "Focus not visible") may be implemented directly as a narrow exception; if not, it is step 1's first task in the normal route.

Write anything you need from me under a `## For Marley` heading here and I will pick it up. — Marley

## 2026-11-23 | Marley — Results UI research + spec delivered

Delivered to this folder: `results-ui-research-marley.md` and `results-ui-spec-marley.md` (pointer in planner.md). The interactive prototype (Muse artifact "MarketTwin Results — Redesigned") is built from the real MT-000199 / MT-000222 / MT-000165 figures and passed a live control-by-control audit; two label-clipping defects were found and fixed in that loop. Next on my side: verify Astra/Sol's implementation against the spec's §9 acceptance list on the saved reports, and report back here. — Marley

## 2026-11-23 | Marley (Muse) — connected, here to help

From Marley, Sreenav's personal agent, connected to this workspace over Tailscale at Sreenav's request. I have read research.md, planner.md and this file, and the shared "Research code complexity" conversation — including Sreenav's last message there, which set the shape: Astra makes the plan, Muse helps, and these three files stay the shared record.

What I am bringing to the Results UI work:
1. A deep research pass on results/report UI design (named products + published UX evidence), delivered as `results-ui-research-marley.md` in this folder.
2. A design contribution for the Results pages inside the locked product constraints (Soft Proof theme tokens, the frozen status language, verdict-first hierarchy, the three slop family numbers never blended), for Astra to fold into the plan.
3. Verification help on this machine: API payloads, saved runs, built pages — measured facts, reported back here.

Astra — the plan is yours. If you need anything from me (research on a specific question, the exact fields a saved report carries, a check against a real run such as MT-000222 or MT-000199, a second read of a design decision), write it under a `## For Marley` heading in this file and I will pick it up. I will not overwrite your sections; anything I add is signed Marley.

## November 23 — Results design review for deployment

Reviewed the supplied MT-000223 screenshot and the existing shared-link case for run `b186893e-162b-50e6-b8f4-ca70a4ccc985`. Traced the visible hierarchy and grouping to SlopReport.tsx, verified score eligibility against slop_aggregate.py, and incorporated Astra's assessment and ONS/W3C guidance. Added the design evidence to research.md and the ordered implementation and release checks to planner.md. These were design checks. No UI changes, deployment or new audit run were performed.

Open items are the Muse critique (Tailscale peer visible, service entry point requested), implementation, browser replays, comprehension testing and deployment verification. The saved MT-000223 and MT-000222 cases are acceptance inputs, not successful runs of the redesign.

## MT-000222 pending inventory

The four existing owned Chromium fixture tests also passed under the new schedule, including the measured defects and worker cutoff cases.

Implemented desktop path rotation within the existing section rotation, preserving exact URL claims and reconstructing queue order from saved pending URLs. On the same 3,780-URL saved backlog, the first 117 claims covered 96 distinct paths with rotation and 88 without it. Both replays accounted for every URL. This compares queue order only. Results displays the URL count across paths, supports filtering within each path, and reads both the structured pending inventory and older pending-page signals. New desktop results carry their pending inventory in coverage and omit one redundant signal per pending URL. Verification passed 51 workflow and pool tests, 14 report tests and web typecheck. Live runtime and rare-variant defect recall require matched browser benchmarks.

The stage 3 follow-up in planner.md now specifies compatible report labels, family scheduling, exception sampling and matched acceptance tests. An additional replay of the final ledger found eight query-bearing addresses among 152 visited keys. The 3,216 pending query variants describe backlog composition; their count alone cannot explain runtime. Planning only.

Run `d28537b5-f87a-56b6-97b8-a03141ab973d` finished with partial coverage at the desktop time budget. Collection recorded 117 measured pages, 118 measured states, six unverified pages and 3,780 pending URL addresses. The pending list has 569 distinct host/path combinations. Five research benchmark paths contributed 3,216 query variants (85% of pending), discovered from their respective benchmark pages. This count measures queued URL addresses. The audit did not establish visual or behavioral equivalence within each query family. Report route and variant counts together and benchmark sampling within high-cardinality families before changing scheduling.

## Retired replay Start message

MT-000081 was the only local draft with a frozen contract source. MT-000222 had no marker and was already running when checked. The run layout now shows the historical draft read-only, links to fresh Explore test creation for its application and target, and scopes Start errors to the current run. The API continues rejecting retired replays. Verified with nine layout tests, five focused API tests, and web typecheck.

## Desktop detector baseline and shared Start verification

Desktop worker time budget now persists across retries. It stops measurement at 555 seconds from execution start and reserves 45 seconds for finalization. Results coverage records pending pages, unfinished visual reviews, the cutoff reason and human wait. In an accelerated real Chromium fixture, a stalled review hit the 10-second work cutoff: one measured page survived, six remained pending, one visual review remained unfinished and zero lanes retired. The four browser fixture tests passed, along with 58 workflow/pool/evaluation tests and web typecheck. This verifies worker cutoff semantics. Queue-to-Results latency on the shared deployment is still unverified.

Live Persona handback passed on `4f43adea-1e23-5534-a543-e734c3c49b34`. On the same browser the owner entered a synthetic code and the resumed Persona task verified the original protected route and its unique page title. The member opened Results. This used the isolated local web/API/gateway, direct executor and evaluator, and a deterministic browser task in place of model-selected actions.

Detector catalogue v3 now locates the clipped primary control. The shared-font and repeated-label rules emit informational observations. On the same seven labeled cases: two correctly flagged defects, three clear controls, one sibling comparison awaiting review and one unopened-menu case untested. Zero false flags and zero misses among the five determinate scoped cases. Two holdout pages await independent review. Sol reported 124 focused backend tests passed and a final nine-test fixture/catalogue rerun passed. Model review and remote artifact storage were stubbed in this benchmark.

Results now includes supported page and cross-page findings in its priority list, retains affected locations for grouped observations and separates informational typography signals. The frontend passed typecheck and 13 report tests. MT-000199 rendered in real Chromium at 1280 and 390 pixels, including charts and pending-page search. The severe cross-page case was checked with a test payload.

Shared execution deployment is still blocked: the worker's older loaded auth module failed before browser creation in run `a715c583-4609-41ef-911d-8387c0c0fb2b`. The operator stop request for that disposable run was accepted. Windows denied the narrowly scoped approved worker termination, so the supervisor did not reload it. In an isolated local app, synthetic CAPTCHA handoff succeeded in run `a16ab6bb-6716-5ab8-8c35-84c9f6fe8bb0`, including authorized private viewer control and resumption on the protected route.

Sol added a seven-page owned Chromium fixture and a replay of the original MT-000199 and MT-000206 observations. Before detector changes: one correctly flagged broken image, one correctly clear asymmetric layout, two false flags on intentional typography, one missed clipped primary button, one sibling-control observation awaiting review, and one untested closed-menu state. The historical replay reproduced MT-000199's 0.2% over 16,699 judged observations. These labels cover seven specific cases, not general product accuracy.

Shared run `a715c583-4609-41ef-911d-8387c0c0fb2b` passed Create and Start and reached the worker. It exposed a stale Python module in the shared process at import of `is_account_entry_route`. Successful direct-executor tests did not cover this deployment failure.

## Recovery patch verification and human handoff

Sol verified 133 auth, Harness, Persona, browser-privacy and Room tests, plus five focused inventory, lane-wait and cooperative-resume checks. Persona excludes operator wait from its goal deadline. Explore inventory binds handoff to the watched Room. Desktop handback checks the intended authorized route before measurement. Arbitrary app-specific gates still require voluntary takeover. Separate live Persona and Explore handoffs and shared-worker deployment remain unverified.

Reverified after protected-route verification changed: `64b3b661-cf34-5b30-8045-d6aafea80893` retained only `/` and `/protected`. The operator connected in Watch, the protected URL received an authenticated request after handback, and the member opened Results. The fixture recorded 8.34 seconds of operator wait and 7.66 seconds of active work. This evidence applies to a desktop run with a synthetic one-time code.

Premature handback run `1f14211f-5131-5c14-b658-c2ff8bd97b61` passed. The operator opened the protected viewer and handed back before entering the code. Results retained the public page and left the required step unverified. The fixture saw no authenticated visit. The run recorded 5.27 seconds of operator wait and 5.33 seconds of active time in the local fixture.

Desktop human handoff succeeded in local app run `f6fdb568-e40f-596c-8f98-ea7ad39464e9`, browser `b038148a-af0c-460c-802c-bd6eb7619b5f`. The public page contained a signup link. Its protected destination prompted for a synthetic one-time code. The owner took control in Watch over the private viewer and handed the same session back. The fixture observed the protected request with its session cookie. Only the public and protected pages appeared as measured states; the stored run events contained no code. The initiating member could view Results, and their unauthorized claim was denied. This used a disposable target, isolated real web/API/gateway, and direct execution/evaluation.

Four-lane local acceptance run `068693f6-14fe-4340-8d8a-c25f9f48e023` published report `724732eb-d4d2-42fe-b1fe-638bbde6a71c`. After all four fixture workers retired, the initiating member opened Results, saw two measured, four unverified and four pending pages, and opened the retained 1280 × 900 evidence. Calling evaluation twice returned the same report identity. The fixture used the live frontend, API and storage with a directly queued disposable draft, direct worker calls, stubbed model reviews and an injected interruption. This verifies partial reporting. Broker dispatch, customer-run recovery and automatic browser takeover were outside that check. A separate handoff acceptance check is in progress.

## Consolidated implementation handoff

Updated planner.md after reconciling the terminal MT-000206 events with the earlier product-quality plan. The first patch now reproduces interruption and verifies partial reporting end to end. The seven quality and delivery stages follow in dependency order, with the older handoffs retained as reference. Checked the order against the active pool and desktop review code and the recorded MT-000199/206 evidence. Planning only. The first new acceptance run ID is pending implementation.

## MT-000206 terminal diagnosis

Run `f25fad6e-1870-411a-b402-f74a222dabcb` failed after 15m36s. The terminal monitor recorded 421 distinct requested URLs started, 394 measurements covering 392 distinct final URL strings, and 424 pending. At 20:47:31 UTC two lead checkpoints recorded page-load `action_failed`, an unavailable lead review and an applied fallback stop with partial coverage. At 20:48:34 UTC the run event and worker log both recorded `PoolExhaustedError`. The pool checks whether every lane retired with work remaining before returning its stopped result. The underlying lane exceptions and cause of lead unavailability remain unverified. Regression case for the recovery plan: exercise simultaneous lane retirement and an applied stop, publish verified checkpoint results with the interruption reason, and preserve per-lane causes. Diagnosis only.

## Product-value checkpoint

Revised the existing [seven-stage plan](planner.md) around the builder's release decision, from first URL through verified repair. Added evidence requirements for consistency, perceived genericness and usability, a matched cost/quality benchmark, sampling for missed defects, and customer tasks to verify report usefulness. Checked the proposal against the existing lane pool, desktop review path and the MT-000206 and MT-000199 audit records. This is a planning change. The cross-release comparison, benchmarks and customer observations are proposed acceptance work.

## 2026-11-21 | MT-000206 product-quality review

At 11m47s MT-000206 still showed running, 323 distinct final URL strings measured and 449 pending. It had missed the ten-minute completion target. Re-ran the local Chromium report check for MT-000199 (`0b9aae6a-70d1-4d7d-afea-6757dbe072aa`). It passed at widths 1280 and 390, rendered 18 pages recorded, 8,912 pending and 52 states, and exercised the pending search and chart assertions. The test used the local report API through an in-process transport. It establishes rendering behavior, not user comprehension.

Reviewed the live desktop audit for Sup_3303 (`f25fad6e-1870-411a-b402-f74a222dabcb`), traced capture → evaluator → Results, retrieved the actual entry screenshot and compared it with all three entry findings. The sampled browser traversed many destinations. Its entry assessment overinterpreted typography and supplied no identifiable pair for its alignment claim. Earlier Klaviyo report evidence corroborates the separate issue with the report denominator. [Observations and limits](research.md) · [Seven-stage implementation and acceptance plan](planner.md)

This checkpoint changed audit and planning documents only. The session continuity files under docs were already deleted in the worktree. Their HEAD versions are historical and the existing deletions were preserved. Current decisions are recorded here and in planner.md. Open verification includes independent labeling, a fresh cross-mode app run with operator handback, a measured comprehension test and matched full-stack latency/cost benchmarks.

**Checkpoint 2026-11-19 · HEAD `50799ab` · line-by-line audit in progress**

- The research and source references live in [research.md](research.md).
- The active worktree is the audit target. The baseline included 203 modified, 86 deleted, and 164 untracked Git status entries. The deleted continuity files were read from HEAD as historical context.
- Inventoried 880 first-party code and configuration files totaling 193,973 physical lines. Parsed 620 Python files and 220 TypeScript/TSX files. The research ledger records the manual source ranges and marks remaining files.
- Members can create drafts, but the UI hides Start from them. Draft creation has a 30-second browser deadline and a 600-second API freshness wait. Dispatch and report can misstate progress, the harness can commit terminal evidence ahead of its resume snapshot, and knowledge upload extracts the source twice.
- Live Kafka and both worker heartbeats were healthy when checked. Read-only local database queries found 22 older executions with quarantined evaluation and no completed report, one queued run without a matching outbox command, and three failed manual freshness checks. Two preflights hit a redirect constructor mismatch already corrected in the current code.
- Full verification recorded 1,967 Python tests passed, eight failed, and 31 skipped. Web typecheck passed and the web suite recorded 338 passed and five failed. Ruff reported 445 diagnostics. Alembic has one migration head. The research log records each failure and its evidence.

## Remaining code audit

1. Continue semantic review in `freshness/freshness_repository.py`, then the helpers preceding the main functions in `workflow/harness_run.py` and `workflow/case_execution.py`. The main functions and freshness sweep and reconcile stages have been read. Keep the precise source ranges in the research ledger.
2. Continue through the remaining UI, persistence, migrations, deployment, and test fixtures. The full Python and web suites have finished. Several failures come from stale fixtures. The desired contract for page coverage notices in the UI audit fixture still needs verification.
3. Use the member Create → Start gap and delayed preflight as the first cross-service acceptance paths on a disposable fixture. That live workflow remains unverified.

## Product validation checkpoint · November 19

- Reviewed the existing audit against multi-page functionality, persona tasks, UI consistency, dynamic planning, multimodal Markdown attachments and live human assistance. Added findings 18–21 and read-only database evidence to [research.md](research.md).
- Eight of ten stored Explore frontiers had one visited URL. The three completed runs in this subset retained 131, 131 and 2,059 pending candidates. Identified an early empty-inventory guard and page-first scheduling in current source. The subsequent verification below identifies the recorded stop reasons. Current React viewer latency remains unmeasured.
- Five focused Python modules passed, 41 tests total. No product code changed. [planner.md](planner.md) records the repair order, component references, fixture requirements and proposed performance targets.
- **Next implementation checkpoint:** promote the reproduced empty-first-page case into a regression and test busy-first-page fairness, then run member Create → Start → page-two assertion → persisted report on a disposable app. Record build, run ID, visited/indexed counts, pending work and stop reason. Next verify automatic and voluntary takeover on the same browser and measure distinct painted frames during motion. The wider line-by-line audit above remains open.

## Plan recheck

- Reproduced the empty-first-page guard with the production harness function and existing doubles. Four neighboring Python tests and web typecheck passed. Historical full-suite results remain in the research ledger.
- Rechecked the database per run. Two partial completions stored a lead access blocker and one stored a handoff stop. Added a separate handoff recovery gate to the plan, preserved creation-time knowledge pinning and identified existing fixtures for reuse.
- The next implementation pass starts with a permanent regression and the page-two member path. Overall product recovery, handback across all modes, and real viewer paint latency still require acceptance runs.
- Local Watch transport benchmark passed at 59.60 fps over 30 seconds with zero heartbeat repeats. All three one-page completions also had completed reports. Current-run viewer paint and report presentation remain open acceptance checks.

## Recovery implementation

- **Empty first page · finding 18.** Added a harness regression with an empty entry and a seeded second route containing a Search control. Before the change, it raised `BrowserDiscoveryEmptyError` while the existing exhausted-frontier test passed. The scheduling loop now reports empty discovery only when it has no work left within the frontier budget. The full harness file passed 92 tests. This verifies the driver behavior with doubles. The real member journey and busy-entry scheduling are pending.
- **Member Start · finding 0.** Matched the UI Start gate to the API's workspace write permission. The owner/admin lifecycle gate still controls deletion. The RunLayout suite passed seven tests, including member and viewer draft controls. Web typecheck passed. Kafka, outbox relay and both worker heartbeats were ready on loopback. Live verification remains pending.
- **Busy entry · finding 18.** Reproduced the harness running all seven entry-page items before indexing the next route. It now gives discovery a turn after at most four Board selections while a route is pending. In-flight work is absorbed before the browser is rebound. Updated the lead-stop regression to leave a third page pending and verify the same coverage event. Full harness suite passed 93 tests. The live fixture first used the IP loopback origin and received a mutation-origin 403. Re-running from the configured localhost origin.
- **Evaluation error · finding 11.** Overview now defers to the same results error panel used by Results on a failed evaluation request. The stale progress banner is hidden and the retry action remains available. RunLayout and Overview suites passed 10 tests together, and web typecheck passed. Live failure injection is pending.
- **Live member Create and Start.** Run `107af7f7-903c-4bcf-9240-57878628856b` was created and started through the local web UI, with HTTP 201 and 202. The worker parked at action preflight because the loopback fixture setting also selected the built-in registration work list. It did not exercise discovery. The next fixture run explicitly seeds an empty work list for this disposable draft to select the inventory driver.
- **Map eligibility · finding 17.** Draft creation rechecks the selected successor against the original application, target and ready/released criteria. An ineligible successor falls back to the original map and records the failed pin. The preflight creation suite passed 13 tests. Asynchronous draft preparation and the earlier freshness receipt issue remain open.
- **Live member discovery.** Run `f51c8a28-42d2-466c-bbf8-4c784609dcf3` accepted Start but the consumer did not pick it up within the first fixture lifetime. It later failed with empty discovery after the fixture shut down. With the fixture kept alive longer, run `ac2b546e-0840-44a2-a9f0-fadf5b44b703` completed execution through the real UI, API, Kafka and worker. Its frontier visited the entry and `/details` with no candidates remaining. Evaluation raised `ValueError: Broken Board result lacks repeated failure proof`. Direct evaluation reproduced the same error on this disposable run.
- **Partial exploration in reports.** The completed Board report shows the size of the saved pending frontier and the recorded stop reason when available. The focused RunReport, RunLayout and RunOverview suites passed 19 tests. This covers an unfinished frontier without changing the Board verdict. Live report validation is pending.
- **Repeated browser failure and resume checkpoint.** The runner persists both completed execution outcomes as failures when the fresh browser context reproduces the same observed failure. Strict report proof validation still applies. The ordinary terminal Board event and its resume checkpoint now commit together before expectation feedback. The harness regression checks the proof IDs and the persisted checkpoint at the first result commit. Harness and report suites passed 108 tests together. A fresh live run with the updated worker is pending.
- **Dispatch failure · finding 8.** The run detail and batched list diagnosis now look up a queued run's quarantined dispatch and surface the stopped state immediately. The readiness, API and preflight creation suites passed 85 tests. Broker fault injection remains open.
- **Live report verification.** After the supervised worker reloaded, the real member flow for run `65ea6576-4e64-4fc4-8e04-ece03b965dde` reached both pages, had zero pending URLs, and rendered the persisted report with a reproduced Broken result and recorded-steps links. The broken action in this attempt was on the entry page. The fixture was then changed to put the broken read-only action on page two.
- **Freshness receipts · finding 12.** A recent timestamp now permits reuse only when a successful terminal receipt names the original or resulting map. A failed recent receipt triggers a new sweep. The readiness, run API and preflight suites passed 86 tests.
- **Page-two assertion timing.** Live run `e7743bd1-e32c-45e0-a874-64dc97545b0b` reached both pages and rendered its report. Its intentional page-two defect was incorrectly unverified. The saved assertion showed `target_enabled` ran on the entry page before the generated navigation step. Updated generated cases to check enabled immediately before the action, after any route change. A fresh live run is needed after worker reload.
- **Page-two defect verified with current code.** The harness, item and evaluator suites passed 110 tests. Member draft `2b1e0614-307b-4622-9f61-232e620225ed` was created in the real UI. Running the current executor and evaluator directly on this draft visited both routes, left zero pending URLs and rendered the real report with the page-two `Search details` control marked Broken and linked recorded steps. The direct invocation emitted connection cleanup warnings on exit. The attempt to reload the shared execution worker returned Windows Access Denied. A same-run replay through the normal Start and Kafka path remains open.
- **Optional task trace · finding 16.** Terminal capture uses its own three-second deadline after the action and assertion deadline exits. A failed trace database operation rolls back before mandatory case completion is recorded. The task-skill and task-spec suites passed 33 tests, including a simulated optional write failure.
- **Confirmed defect explanation.** The Board now records whether both attempts showed no visible effect or repeated the same browser error. Three focused reproduction tests passed. The preceding live report was generated before this wording change.

### Remaining release gates

1. Replay the page-two member fixture through Start and Kafka on the updated worker. Finish asynchronous draft preparation and idempotent retry. Exercise relay and evaluator failures on disposable runs.
2. Finish same-URL and button-led exploration, then verify partial coverage across the report and run list. Reproduce watchdog recovery and checkpoint interruption against the real services.
3. Continue with takeover and handback, viewer paint measurements, attached Markdown grounding, per-run assignments and the shared UI states in planner order.

### November 20 recovery verification

- The updated supervised worker completed the first member product milestone. Disposable fixture run `c54fb32a-4b21-465d-ac8e-67836a385410` used the real Create and Start buttons (201 and 202), Kafka, executor, evaluator and rendered Results. The saved frontier contained both the entry and /details with zero pending. The report checked 2/2 eligible controls, showed Open details as Worked and Search details as Broken with no visible effect on either attempt, and linked recorded steps. The fixture retained loopback approval and selected discovery via the draft work-list adjustment documented above. First-action latency was not instrumented in this run. This replay supersedes the open page-two replay item above.
- Draft preparation now returns a durable receipt immediately when a map sweep is building. Start resolves the receipt, rechecks successor eligibility and retains the prior timeout fallback. Preflight creation and run API suites passed 66 tests after removing polling. Coverage for Start resolution and live mapped drafts remains open.

- Added the coding-agent work order and product runtime benchmark to planner.md. Read persisted TestRun and Report timestamps for fixture c54fb32a-4b21-465d-ac8e-67836a385410. Recorded 27.3 s draft to execution start, 44.4 s execution and 2.7 s execution end to report creation. Repeated timings and Start-to-first-action instrumentation remain open. The 20% improvement target is provisional.
- Current mapped-draft and idempotent Create changes passed 92 focused API tests and web typecheck. The escalated frontend test result and real concurrent retry with a mapped draft remain unverified.

- Verified concurrent mapped-draft Create against current FastAPI routes and local PostgreSQL using an authenticated disposable member with in-process HTTP transport. Both concurrent requests returned 201 and the same run ID, c5044b03-f70f-5751-8a0b-63f821822c5e. Database counts confirmed exactly one draft for the request and one preparation receipt for its new map. The response exposed preparing. Requests through database count verification took 2.44 seconds. Browser readiness-to-Start remains open. The shortest-path table in planner.md groups stage checks around reusable fixtures.
- Corrected the RunLayout member test fixture to include the required readiness checks array and removed its type assertion. The initial rerun exposed the incomplete mock. The three focused web suites then passed 25/25 in 20.56 seconds.

- Mapped-draft readiness now keeps the preparation reason visible while polling and displays the completion message. The role regression covers disabled Start while preparing and enabled Start after readiness succeeds. The three focused web suites passed 25/25. Chromium on the real web UI, using current FastAPI routes through in-process transport and local PostgreSQL, showed Map preparation completed and enabled Start for run c5044b03-f70f-5751-8a0b-63f821822c5e. The live knowledge worker completed the saved receipt. This browser verification opened the ready draft after completion and did not start the earlier disposable target. The live failure injection gate remains open.

- Verified failure visibility with two scoped fault injections on disposable local runs and the real web UI backed by current FastAPI routes and PostgreSQL. The real relay persisted quarantine after an injected final-attempt TimeoutError for dac7ec05-ba49-4c6a-8d83-2c9ff35502df and Overview showed dispatch stopped. The real evaluation worker persisted quarantine after an injected final-attempt RuntimeError for df55a5ee-f3fd-40e3-adf6-e6db4ca18dce. Results returned HTTP 503 and Chromium showed the report-generation error. These injections targeted one saved row per service and did not interrupt the shared broker or workers. Operator reset and successful replay remain open.
- Added partial-exploration labels to the application and workspace test lists. The lists and harness report now count pending URL candidates through the same formatter. Web typecheck passed. Chromium showed the label on the application list for disposable run df55a5ee-f3fd-40e3-adf6-e6db4ca18dce after seeding two pending candidates. Same-URL state and button-led navigation discovery remain open.

- The Explore result now queues an authorized URL observed after a successful navigation action, including a button with no anchor. The destination is persisted with the item result and resume checkpoint. Anchor collection also canonicalizes the existing queue once per collection pass. The full harness suite passed 93 tests for queue deduplication and both new action-navigation variants passed after using an eligible Search control in the second-page test. Disposable member run 1bc07177-c6ed-45ac-8080-1ce1b96a0db7 was created and rendered in the real web UI. Its browser followed a button to the only path to /details, visited both URLs, left zero pending, and reported Open details Worked and Search details Broken with recorded steps. Execution and evaluation were called directly for the current-code variant. The standalone process emitted connection cleanup warnings after persisting the report. A broker-backed replay of this new variant and replayable same-URL states remain open.

- Full harness check after button navigation passed 94 tests. As groundwork for same-URL coverage, each observation poll now fingerprints only the controls in that rendered pass, so temporary controls from earlier polls do not count toward the settled state. The 10 focused outcome and navigation tests passed after that change. Opening and replaying a new same-URL state remains open.
- Core checkpoint: a member must be able to create and start a test, watch it explore, take and return control when needed, and receive a report with reproducible evidence and explicit coverage limits. Continue with a tab or dialog fixture that requires replaying its opener before checking the revealed controls. Keep the working two-page case as the baseline.

- User prioritized UI Slop after seeing raw XML in the live viewer. The audit loads sitemaps in the watched room and then scores pages in sibling contexts. Both desktop and mobile entry captures are currently sent to artifact storage before visual review. Added implementation and fixture acceptance plan in planner.md. The screenshot also shows a stale frame during active run events. The disconnect cause and the Slop code changes remain open.
- Explore same-URL checkpoint before the priority change: disposable run 84d9ee1f-1bb0-457b-8379-075a97c45075 used the real browser and directly invoked current execution/evaluation. Its report showed both checks on one URL and reproduced the hidden Search details defect. Shutdown emitted connection cleanup warnings. Full harness suite had 94 passes and one failing call-order assertion in the new same-URL mock. Fixture stabilization and normal Start/Kafka replay remain open.

### UI Slop screenshot fix

- Sitemap fetches now use an isolated browser context under the existing navigation policy. Added a 20-document and 30-second discovery budget, and sitemap fallback counts. Lane zero uses the watched room for audit work and Activity distinguishes it from background lanes. Regressions covered context cleanup on success and timeout and checked that discovery XML is never sent through the watched navigation path.
- Audit discovery filters obvious non-page links. The actual document MIME type is checked before measuring, including after a redirect or interaction. Results lists excluded URLs and types. Disposable run 2b403db8-fa82-4319-b600-86d82a0721f7 visited its HTML entry and a page reachable only through a nested sitemap. It excluded feed.xml and an extensionless redirect that landed on application/json. Chromium rendered Excluded documents (2) on Results.
- Audit captures are temporary until inspection establishes a finding. Storage receives screenshots only for measured flags or views cited by visual findings, with up to two views per comparison. The audit removes its temporary capture files on teardown. The same disposable run retained zero screenshots on its clean HTML page and two viewport screenshots on the seeded overflow page, with both pages measured. The browser created the run through the UI. The current executor and evaluator were invoked directly, with review-model output stubbed and network scope restricted to the local fixture. Run a fresh broker-backed audit after the worker reload to verify Watch and measure forced reconnect behavior. The previously reported disconnect remains unclassified.
- Verification: 80 focused backend tests passed, including browser, document, lane, and proof-selection coverage. The UI Slop report test and web typecheck passed. The backend test process emitted a Windows temporary-directory cleanup warning after its successful result.

### MT-000184 production UI audit diagnosis

Run `d59b25a1-dbd4-4100-8d33-6c75670bd1b7` stopped with 45 page inspection events and 45 page checkpoints. The last page-start event showed 564 URLs pending, including blog pages outside the submitted product path. Last audit progress was 20:21:29 UTC on November 20. The first execution's cancellation stack shows a lane waiting on the progress flush lock. The log does not identify the lock holder or establish why progress originally ceased. The supervisor restarted the worker at 21:22:37 UTC. It began retrying the command at 21:22:58 UTC and logged StallWatchdogError at 21:23:21 UTC during setup. The watchdog uses the latest event for the entire run, allowing old silence to cancel a new attempt before its own 900-second window. The database recorded Failed at 21:23:24 UTC. Verified by read-only run/event/execution queries, the run-specific worker trace, supervisor log and watchdog source. Open work includes fencing the stall clock to the current attempt, capturing lock-holder diagnostics and exposing recoverable partial coverage. No production rerun or code change for this diagnosis.

### MT-000184 retry and checkpoint repair

- The stall watchdog now uses the later of the current attempt's start and the last recorded activity. The worker regression covers the production timing with a 24-second-old retry and a one-hour-old event. Separate cases cover true inactivity and human takeover.
- Audit pages leave the in-flight queue before the checkpoint snapshot and page findings are committed together. Resuming also restores excluded document URLs and sitemap discovery counts. The Chromium fixture run 374ac6f1-73f4-45fb-b5c0-3c15d720370f was created as a member and interrupted after two pages completed. A fresh database session resumed the current executor. Results showed three HTML pages, the overflow evidence, both document exclusions and zero duplicate absorptions. The completed overflow page started once and the interrupted page started twice. The fixture invoked execution and evaluation directly, used one lane to make the interrupt deterministic and stubbed the model reviews. Broker redelivery and a real supervisor restart remain open.
- Screenshot uploads no longer hold the shared progress lock. The artifact metadata write still uses it. A warning identifies the run and operation if the lock is held for 30 seconds, with the lane for lane-scoped writes. The storage test verifies lock ownership during upload and metadata writes. The cause of the original production silence remains open.
- Current and historical watchdog failures return a specific reason. Results shows checkpoint coverage and marks the final score unavailable when a stopped UI audit has no report. The report component tests passed. A true watchdog cancellation is covered in the worker tests and still needs a combined worker-to-browser fault test.
- Chromium loaded the stored MT-000184 run d59b25a1-dbd4-4100-8d33-6c75670bd1b7 against the current local API code and verified the watchdog reason on Overview and Results, plus the unavailable score on Results. This used the existing failure record. No audit was rerun. Final verification passed 95 focused Python tests, 10 Results tests and web typecheck.

### Explore same-URL coverage and interrupted input

- A refresh could re-index a state already opened by an action and add inherited controls back to the Board. Inventory now preserves the replay steps and control exclusions for that state. The failing-first harness check now passes. Real Chromium run f0f1ada2-148a-4687-9071-1d571bc3e5ee showed exactly 2 of 2 controls, Open details Worked and Search details Broken with both attempts and recorded steps, with one visited URL and no pending URLs. The fixture was created through the member UI. The current executor and evaluator ran directly. Standalone shutdown emitted database connection cleanup warnings after Results rendered.
- Explore recovery now queries the persisted browser step ledger for interrupted items. If an input may have reached the browser, the item closes as Could not check with a reason to verify the effect before retrying. Unstarted work still resumes and already terminal checks keep their outcomes. The targeted tests cover both sides of the persisted-input boundary and the same-URL discovery path.
- The member browser fixture dccdd982-d22f-44bd-b861-3b0c6131ca43 injected an interruption immediately before the Search details Board result was published. PostgreSQL retained four click steps across its original attempts. The resumed executor issued zero additional clicks and the database contained two distinct terminal Board results. Chromium showed Open details Worked and Search details Could not check with the verification instruction and recorded steps. Execution, interruption, resume and evaluation were invoked in the fixture process. The worker redelivery path still needs a current-build test against the real broker.
- The recovered run exposed a bare Ready heading at 1 of 2 eligible checks. Results now qualifies Ready as Ready for checked scope and shows the count of eligible checks without a confirmed outcome.
- Reopened the same saved run dccdd982-d22f-44bd-b861-3b0c6131ca43 in Chromium after changing Results. It rendered Ready for checked scope, one eligible check with no confirmed outcome and the instruction to verify the interrupted input. Final verification passed 131 harness and worker tests, 11 Results tests and web typecheck. Remaining gates include current-build broker redelivery, lost-browser recovery and operator replay after quarantine. The supervised shared worker predates these changes. The next dependent milestone is protected browser takeover and verified handback with viewer paint measurements.

### MT-000190 live audit diagnosis

At 17:08 Chicago time on November 20, production-target run b9c0b6ee-bfc9-4bfd-9915-5576b9247c3f had run for about 65 minutes. The submitted product page finished at 16:08. Of 58 completed inspections, 57 were blog pages. Four lanes were inspecting more blog pages, with 564 URLs queued, 187 completed model calls and 59 lead reviews. At 16:29 there were 23 completed pages and 565 queued. Fourteen pages finished in the last ten minutes. The audit was making progress but sitemap and link discovery kept replenishing the queue. Its latest lead review chose to continue because uninspected pages remained. This was a read-only run inspection. Scope selection, page-template sampling and an explicit whole-audit budget remain open.

### Whole-UI Calculator first assessment

- The UI audit now persists the submitted page's initial desktop and mobile assessment after measuring both views and linking available finding evidence. Overview and Results render it while the run is active. It gives the assessed element count, up to five prioritized observations, viewport and proof when available. The panel identifies its scope as the initial page views. Interaction and site-wide conclusions follow the full run.
- The section queue rotates across discovered sections, remembers canonical pending keys and drains all eligible URLs. Added a regression for uneven sections and equivalent URL deduplication. The pooled lead-review path avoids piling up routine page-end reviews while the lead is busy. The 38 focused pool and workflow tests passed. Windows pytest emitted a temporary directory cleanup warning after the passing result.
- Chromium exercised run 2afcf6b8-02c2-48da-b41e-ab7b37133522. The submitted-page panel rendered in 3.16 seconds from the fixture's executor invocation while the run was still Running. The fixture then interrupted and resumed with a fresh session, inspected all three HTML pages, preserved the overflow evidence and both excluded documents, and rendered the final audit. Chromium used the real local UI and database, one worker lane, model review stubs and direct executor/evaluator calls. This is a functional check and a fixture timing. The normal Start-to-assessment time, multiple-lane behavior with the live model, and paired completion benchmark remain open.
- Both Overview and Results suites passed 16 tests. Web typechecking passed. Parallel sitemap discovery, progressive site-wide findings, calibrated design ratings, comprehensive coverage fixtures and the remaining release gates in planner.md are still open.

### MT-000198 live product and storage check

Glean_77 (`bb0f2708-eda6-4106-a22a-d571f2b354b6`) produced a submitted-page assessment with 1,579 judged elements and 10 observations. The displayed five included a centered hero and equal-width cards. All five referenced the same desktop image and four also referenced the same mobile image. The checkpoint has no publication timestamp. The first homepage interaction event was 105.9 seconds from execution start, after the assessment publication point in the current workflow. Browser paint time was not measured.

At 00:29 UTC on November 21 the worker still had over 2,100 pages queued. The saved-image tally grew from 26 (4.69 MiB) to 43 (9.19 MiB). The local worker directory contained 47 PNGs (9.66 MiB) in the latter sample. The English control appeared in 13 state progress events across nine URLs. Nine page checkpoints serialized to 9,039,262 bytes of JSON text in total, excluding database compression. These observations support prioritizing actionable findings, reusing evidence for the same shared component, and separating cheap page measurements from expensive interaction and model review. Persist minute samples in `.local/mt-000198-storage.csv`. This is an in-progress observation. Final coverage, user-visible timing, incremental unique findings, peak disk use and successful cleanup remain unverified.

### Desktop audit planning checkpoint

The desktop plan now specifies a single browser visit for URL validation and UI measurement, including redirect aliases, meaningful query and hash routes, soft 404s, and localized exceptions. Added an acceptance fixture that checks the user-visible outcomes and repeat visits after interruption. This update defines future verification.

Follow-up verification of MT-000199 found a completed run with partial coverage. Its collection recorded 18 pages and 8,912 pending URLs. Checked the saved queue against host, path, locale and query counts, and traced sitemap seeding in the executor. Added discovery-source reporting and cross-mode release checks to planner.md. Application changes were outside this planning pass.

Finalized the ten-minute desktop audit plan at the top of planner.md. Reviewed MT-000199 (0b9aae6a-70d1-4d7d-afea-6757dbe072aa), the MT-000198 storage log and the current Slop workflow. The Klaviyo sample at 25 minutes recorded 18 page completion events, 8,912 pending URLs and 52 saved screenshots totaling 4,222,966 bytes. The final Glean monitor row recorded failed status with 62 saved screenshots totaling 12,420,668 bytes and zero local PNGs in the monitored directory. These are observations of the earlier workload. The proposed fast path, target site size, concurrency, cost and deadlines still require verification. The pre-pause desktop test log records 48 passes and one setup error caused by denied access to the pytest temporary directory. This planning pass changed documentation only.

### Desktop scan implementation

The normal Check the look executor now uses one 1280 px desktop visit to classify the document and measure the initial rendered page. Sitemap discovery runs alongside page claims. The run records first discovery source and a compact inspection event. URL identity preserves the ordered query string, regional paths and conventional hash routes. Page results and coverage checkpoints are committed together. Existing browser lanes handle page work. The first page and up to 24 distinct section and layout combinations can receive visual review. Severe measured page issues remain eligible for proof. Temporary fast-path screenshots are released after review and evidence selection.

Local Chromium run 4c4e701b-327d-4fb0-b464-a0ca78dd865c rendered the first assessment 2.88 seconds after the fixture invoked the executor. It resumed after an injected interruption, covered all three desktop pages, excluded two documents, retained overflow evidence and loaded Results. This used a member browser session, one browser lane, stubbed model review and direct executor and evaluator calls. Web typechecking passed.

Open work includes the large-site benchmark through the normal Start and dispatch chain, measured concurrency scaling, finer URL classifications and alias reuse, incremental storage for the queue snapshot, cross-page evidence grouping, and progressive findings beyond the submitted page. The fixture time establishes a local result, with the ten-minute production target still unverified.

The final focused run passed 49 tests covering workflow, pool, evidence and visual-review validation. The desktop regression verifies that navigation starts during sitemap discovery and that two pages receive exactly two navigations. It also verifies the saved sitemap source. Pytest required an unsandboxed rerun to access its temporary directory. Scoped diff checks passed.
Reviewed the saved MT-000199 report and verified its headline against the stored element verdicts. Recorded the diagnostic repetition and coverage-list rendering issue in research.md and added a Results redesign milestone to planner.md. Visual reproduction and member usability validation remain open.

### Results presentation

The design review now opens with recorded pages, pending pages and recorded states, followed by up to three representative flagged elements with links to evidence. Score details and diagnostic logs use disclosures. The pending URL browser supports search and incremental display. Functional outcomes prioritize broken and unresolved checks. Persona reports summarize participants, impressions and friction with the same metric typography. Contract and legacy results share the report styling. Verified saved Klaviyo run 0b9aae6a-70d1-4d7d-afea-6757dbe072aa in Chromium at 1280 and 390 px. Both showed 18 recorded pages, 8,912 pending URLs and 52 states without document-level horizontal overflow. The pending-URL search handled a missing query. The historical payload still downloads in full. User comprehension testing remains open.
MT-000203 planning review verified distinct requested URLs, measured final destinations and exclusions separately. Added the ordered Sol handoff and acceptance fixture at the top of planner.md. This pass changed documentation only.

### MT-000203 handoff stage 1

Added monotonic phase totals, counts and maximums to desktop run collection events. Timed navigation, settle, DOM probe, measurement, visual review, screenshot capture, evidence retention, database lock wait and inspection commit. Recorded the first checkpoint size and every 64th write. These are attempt-local timings. Concurrent worker times overlap. Actual provider token usage is available in existing model.call.completed events where reported. Focused workflow and pool suites passed 39 tests.

Four-lane loopback run be2954f8-12be-4cc5-85b0-927361efe55a recorded 43 page states and two document exclusions. The submitted-page assessment appeared 5.44 seconds after direct executor invocation, execution finished after 46.17 seconds and Results appeared after 48.30 seconds. Peak sampled checkpoint size was 5,259 bytes. Evidence retention led the cumulative timings at 114.39 seconds across lanes. The fixture unintentionally contained 41 sparse catalog or linked pages that also fired the dead-end rule. The overflow fixture fired both that rule and viewport integrity. This run shows the cost of repeated evidence uploads on a finding-heavy fixture. The local run used stubbed visual review and direct execution and evaluation. Full Start and dispatcher timing remains open, as do redirect provenance, alias ownership, Watch metadata and a measured production speedup.

Revised the fixture to give ordinary pages meaningful text and navigation. Run e9a58963-2d4b-4e54-8933-c29773464693 with four lanes recorded 43 desktop pages, two document exclusions and one retained screenshot for the seeded overflow. First assessment appeared 3.03 seconds after executor invocation, execution ended after 16.70 seconds and Results appeared after 18.67 seconds. Across the four lanes, settle consumed 13.97 seconds, navigation 3.06, probe 1.28, measurement 0.09, inspection commits 2.03, and evidence retention 3.05. Lock wait accumulated 16.86 seconds across 248 acquisitions, with a 2.11-second maximum. Sampled checkpoint peak was 5,447 bytes across 88 writes. The fixtures differ in content and evidence load, so these are two baseline workload profiles. Model review was stubbed in both. Continue with redirect provenance and alias ownership, then validate Watch and the paired benchmark.
## November 24 — MT-000230 human handover routing

Run 181e4096-f17d-5fb7-ba7e-0142cbebee9e was awaiting human help. Its events recorded all three Google widget hosts and ten unrelated submission blocks. An isolated real Klaviyo login reproduced blocked static-app.klaviyo.com script and font requests on takeover/reload. Fixed GET script, style and font routing for authorized target pages during human control. The same CDN script and three fonts returned 200 on the patched route. The widget loaded after takeover and reload. A separate Google POST to /g/collect was mislabeled as a CAPTCHA denial. The diagnostic now checks the provider path. Browser policy, diagnostics and gateway suites passed 77 tests and the Chromium leased navigation test passed. Watch reload routes through the gateway and owner to the leased page. The user's exact banner and successful human verification remain unconfirmed. The serving worker predates this patch. Preserve the active lease and roll out after drain.

## November 24 — Marley run routes, Knowledge sections and styles

Run overview, report and results bookmarks now open Summary. Findings, evaluation and tester perspectives open Summary views. Board, journeys, missions and tester bookmarks open Activity views. Assistance opens Watch at the handover panel. Redirects preserve existing filters and evidence fragments, including across sign-in. Existing journey, finding and evidence detail URLs still resolve. Home links now use the canonical routes. Removed the infrastructure badge from the test header and checked the report vocabulary against the 42-rule catalogue.

Separated the Knowledge map, freshness, skills and expectations UI along the existing query boundaries. Consolidated the Soft Proof palette in tokens.css and replaced the mixed theme entry with shell, product surface and marketing styles. The production build separates the example dataset and 21.14 kB of marketing CSS from the product entry. Added guards for the shared palette, run stylesheet colors and legacy stylesheet growth. Existing shared component and legacy rules still need a full token-by-token audit.

The local browser rendered the public example report. The saved MT-000223 evidence bookmark (b186893e-162b-50e6-b8f4-ca70a4ccc985) reached workspace sign-in. Authenticated evidence screenshot access and the owner comprehension check remain open.

Web typecheck and production build passed, with existing font-resolution and chunk-size notices. The full web suite returned 344 passes and three Tests directory failures before the test updates. Updated the old handover link assertions and mocked the paginated application tests request. The latest reruns passed all 13 Tests directory and RunLayout checks and all 52 navigation, Home, assistance and stylesheet checks.

## November 24 — MT-000231 reCAPTCHA rollout check

Matched the screenshot to MT-000231 (783d5472-f0bb-57de-ab1b-c2427eba513c). Watch port 8020 belonged to PID 24528, started at 7:41 AM local time. The routing and diagnostics patch was saved at 9:30 AM. The live run reached the older worker. The run recorded all three Google widget hosts and unrelated egress blocks. That event stream does not establish successful verification. The safe reload check deferred restart because the run was still awaiting help and the protected lease was still being renewed. Other running rows had been idle for more than two days. Browser policy and diagnostics tests passed all 55 cases. Reload after the active case drains, confirm new listener ownership and verify login through a fresh human handover.

## November 24 — execution worker restart

The user authorized restarting the local worker. The standard restart script stopped at the Watch port check. Port 8020 was still owned by PID 24528. Confirmed the worker and supervisor chain before attempting a targeted restart. Windows denied termination of the worker. A terminal with rights to stop the existing process is required to complete rollout.

## November 24 — execution worker restarted

The administrator launch of scripts/start-worker.ps1 replaced PID 24528. Watch port 8020 was verified on the new worker PID 37080, started at 10:41 AM local time after the CAPTCHA routing patch. The local control API returned HTTP 200. Human-operated Klaviyo login remains the live acceptance check.

## November 24 — Look Summary audit corrections

The reported link is MT-000232 (8983059e-e120-561d-8fb6-b028af23aa24). The attachment audits MT-000226 (eeae9164-d51c-500b-8a70-7c15820f4293). Updated the shared Look Summary so both saved runs use site-section pending bars with working filters, score thresholds in percentages, visible partial-run and comparison explanations, unverified state chips, accessible Coverage bookmarks and named diagnostics. Historical JavaScript totals exclude recorded browser test conditions when the old aggregate contains them. Image observations group by page path, role and region and remain unverified without recorded HTTP failure evidence. Saved report data was preserved.

Authenticated Chromium verification on both real reports at widths 1280 and 390 confirmed Coverage focus, visible bars, bounded URL results and filtering. MT-000226 showed 39 serious and 89 minor JavaScript signals. MT-000232 showed 70 serious and 330 minor. Both first-priority evidence links opened their panels on mobile. Those two findings showed measurement evidence without screenshot previews. The web typecheck, production build and 23 focused tests passed.

## November 24 — Results wiring verification

Related follow-up on Look output quality is recorded in the November 24 independent product-output check in results-evaluation.md. Recounted both archived reports and ran 56 focused tests with 54 passing. The open items are the two conflicting media tests, independent designer calibration, and a fresh end-to-end producer check.

Connected Explore outcome bookmarks to the saved checks filter and preserved other query parameters. Look evidence now follows router hash changes and page measurements can open an attached screenshot when available. Verified 46 focused tests and web typecheck. Authenticated live checks verified MT-000232's stored screenshot end to end and confirmed MT-000226's results, legacy route and screenshot download. The later cross-kind replay could not authenticate. The local sign-in returned HTTP 500 and the Docker Desktop engine was unavailable, although the control API health endpoint returned 200. Saved Persona and Contract replays remain open.

## November 24 — Look finding calibration

Excluded semantic time elements and date-led editorial metadata from the eyebrow heuristic. Verified all 14 MT-000232 newsroom labels match the exemption and the contrast signal remains available. Aligned image tests with the requirement for a captured origin error. The browser workflow verified HTTP 404 and the editorial negative control. The report now names the element count and links unconfirmed page observations to their recorded state. Verified 55 focused Python tests, five Look UI tests, web typecheck and authenticated MT-000232 (8983059e-e120-561d-8fb6-b028af23aa24) overflow evidence at 1280 and 390 px. Independent designer labels and fresh producer publication remain open.

Six report browser tests also passed against the local web server using installed Chrome in the desktop and mobile projects. The additional sandboxed API instance could not bind the occupied control port or resolve the configured Kafka host. The existing serving API passed its health probe and authenticated saved-report replay.

## November 24 deep Look result validation

Recounted MT-000226 and MT-000232 for repeated page findings, measured route overlap, contrast, image uncertainty and browser diagnostics. Ran three controlled score calculations and reran the desktop benchmark and aggregate tests with nine passing. The benchmark exposed three sparse-page warnings outside its selected grading rules. Added the evidence and implementation order to results-evaluation.md. Independent designer labels and fresh publication remain open.

## November 24 MT-000235 lane recovery implementation

Desktop Look now records a safe policy subtype on an unverified page and keeps the browser lane available for another claim. A durable journey-wide policy stop still stops admission. A recoverable session loss can schedule one replacement per lane and leaves the failed page unverified. Desktop authentication handoff keeps other browser sessions available. The crawl selects known section roots ahead of deeper routes within that section. The report shows the number of retired lanes when coverage is partial.

Verified 58 Python tests including the four-lane refusal regression, bounded replacement and real Chromium fixtures. Five Look UI tests and the web typecheck passed. The authenticated Summary for MT-000235 (6025f261-9e63-5e15-a0bb-666957583ca6) showed the three-of-four-lane message. A fresh worker-backed Klaviyo run and real concurrent login or CAPTCHA handoff remain open.

## November 24 execution and evaluation wiring audit

The control path dispatches execution through Kafka. Evaluation polls Postgres for completed runs without a completed version-1 report. Desktop Look first saves a recoverable collection checkpoint, then publishes final state rows and completion in one transaction. Evaluation holds a per-run advisory lock and publishes an idempotent report. The API distinguishes pending evaluation from quarantine, and the run workspace polls for pending results.

Compared MT-000226 and MT-000232 directly in Postgres. Execution and report states matched 55/55 and 52/52, element counts matched 19,476/19,476 and 18,608/18,608, and both coverage documents were JSON-equal. The authenticated API served MT-000232 version 1 with 52 states and 46 inspected pages. This database no longer contained MT-000235, and its API returned 404. MT-000236 was still executing on the last check. Both workers had fresh heartbeats. In the trailing seven days, 29 successful Look reports were generated a median 0.21 seconds and a p95 5.42 seconds after execution completion. Thirteen Explore reports measured 1.10 seconds and 5.14 seconds. These are generation timestamps, with API visibility and UI refresh outside the measurements. Forty-two focused evaluator tests passed with one mock warning.

Found 24 historical completed runs without a report in quarantine and zero eligible unrecovered runs at the query snapshot. Twenty-two legacy harness rows have saved boards and no board-result events, with RuntimeError recorded. Two Explore rows have ValueError recorded. The error type alone does not establish the failing invariant. The current poller waits for a batch of up to 20 evaluations and its scheduled graph audit before discovering more work. Desktop evaluation's timeout applies after selection, with queue and polling delay outside it. Look also lacks an explicit validated producer-to-evaluator manifest, and absence of final state rows can flow into an empty aggregate if a malformed completed run reaches it. The report projection drops typed lane and policy metadata, although the visible failure detail survives in its signal. Owner-stopped Look runs can preserve state rows but are cancelled and excluded from report evaluation.

Keep the existing durable handoff. Prioritize a small versioned completion contract and stable failure codes, then make the poller refill free capacity independently of graph audit. Measure queue delay, report commit and API readiness independently. Reproduce each historical quarantine cohort before any backfill. This audit changed documentation only.


## MT-000237 lane fix — build progress (Marley, 2026-11-24)

**Team launched (parallel build, one integration checker):** research writer (research.md section), planner (detailed step plan), four implementers (Fix A — slop_run.py diagnosability; Fix B — controller.py pre-flight self-heal; Fix C — auth_verifier.py challenge timeout; Fix D — error-page-rest fixture test), a baselines runner (pre-change failed-ID sets for the five suites), and an integration checker (cross-fix consistency, guardrail audit of every draft, live prototype integration test, application readiness). Marley implements directly; the local Cursor session is not used for this build. Drafts are built against read-only copies of the PC sources in Marley's sandbox and applied to the PC repo only after hash verification, per the plan's step order.

**Plan:** Steps 0–7 (snapshots + baselines → Fix D written and run pre-fix for failure evidence → Fix A → Fix B → Fix C → Fix D passes → full five-suite verification, zero new failed IDs → completion record). Held, untouched: policy.py, offsite semantics, the egress classifier, _configure_page adoption, pool replacement policy, the evaluation score gate, frontier/budget.

**Draft status and integration-check verdicts** (full report: `~/workspace/lane-fix-build/INTEGRATION-REPORT.md`):

- Fix A (slop_run.py diagnostic fields): draft complete — **PASS-WITH-NOTES.** All seven field names match the spec exactly; the exception is threaded into `absorb_attempted_failed` via an optional `diagnostics=` kwarg (the pool's lane-death caller is unaffected); the current-URL read is defensive and uses the real `_get_session` signature. Notes: the tests landed in `tests/test_slop_pool.py`, where the old stripped-detail assertion actually lived, and correctly update that contract (the detail now appears only in `policy_error_detail`); one hunk beyond the spec's letter extends the `_publish_states` key whitelist so the new fields actually reach published state events — in-scope and necessary.
- Fix B (controller.py self-heal): draft complete — **PASS.** Exactly two hunks; the heal fires only on `TargetUrlValidationError` from the resting-page check, resets via a raw page goto (5-second bound, errors swallowed, no recursion), re-checks once, and re-raises the original error if the reset fails. All four spec unit tests present. Blast radius, stated plainly: `_agent_control_action` wraps 23 controller methods and offsite is configured for all three run kinds, so the heal also reaches Explore and Persona sessions — safe, because the trigger class (a resting page that is not a public URL at all) is never a legitimate working page, and `policy_refused` behaviour is unchanged (proven live below).
- Fix C (auth_verifier.py timeout): draft complete — **PASS-WITH-NOTES.** The timeout now returns False via the new `inspect_sensitive_challenge` (which also reports `timed_out` distinctly), and `verify_authenticated_role` is explicitly re-guarded to fail closed on a timed-out check, with a test. Two notes: (1) the spec's info-level signal (`UI_STATE_UNASSESSED`, "Challenge check timed out; treated as no challenge.") is recorded by **no** landed code — the channel for it is fully specified in `fix-c/DEPENDENCY-controller-session-slop_run.md` (a session flag + controller accessor + slop_run drain, mirroring an existing pattern) but was implemented by nobody; a parent decision (land it as a companion, or descope the signal) gates application. (2) If that drain lands as specified, it collides with the codebase's unassessed accounting (`_is_unassessed`, slop_run.py:187) and with Fix D: a timed-out page's measured entry state would be reported "unverified", failing Fix D's assertions — the drain's placement must be re-decided, not landed as written. Also recorded: `verify_recovery_target` (controller.py:2704) keeps the new semantics unguarded (bounded, but an explicit accept is owed), and a second, distinct 10-second checkpoint-signals timeout (controller.py:702–706) is untouched and out of scope.
- Fix D (fixture test): draft complete — **PASS-WITH-NOTES.** Purely additive to `tests/test_slop_fixture.py`; real controller, policy and lane factory; the error-page rest is produced by an auto-submitted cross-origin POST form refused at the route handler (no journey stop, the production shape), and the slow page stalls the challenge inspection inside a captcha-titled iframe with `runtime_human_assistance=True`. Notes: the spec's "timeout path at most once per resting page" is operationalized as "the slow page is measured + at most one ≥9-second failed state per lane", which B+C deliver; and the fixture needs a one-time machine setup — a global IP (93.184.216.34) aliased onto loopback (a hosts alias to 127.0.0.1 cannot work under `public_only`) — or the test **skips**, and a skip must be treated as not done at Steps 1 and 5.

**Integration scenario results (prototype, real production code, real Chromium; drafts applied to a scratch copy — exactly three files differ from the pristine tree, no version drift):**

- Baseline (4 lanes, plain site): identical before/after — lanes inspect 4/2/2/2, zero failures.
- Off-origin drift: unchanged — every claim still `policy_refused`, no reset attempted.
- Error-page rest (the MT-000237 state: page on `chrome-error://chromewebdata/`, journey not stopped): before — claims fail `target_url` in ~0 s, page frozen, the production signature reproduced exactly; after — the lane heals and inspects the next pages (0.7 s, 0.6 s).
- Challenge stall: before — every claim fails as a load failure at ~10 s, permanently; after — all claims inspected (the stalled page itself in 31.7 s; later claims in under a second). The failure is cured; a genuinely wedged page still costs bounded inspection time while it remains the resting page.

**Open items:**

- PC application of every draft is pending the PC waking, plus the hash gate: the live PC files (three sources + the touched test files) must hash-equal the copies the drafts were built against (reference hashes are in the integration report); any mismatch means the file moved and the draft must be re-diffed, not overwritten.
- Suite baselines are pending (PC asleep at build start; the baselines runner retries on wake).
- Decisions owed before application: Fix C's signal — land the companion channel (with its drain placement fixed) or descope it; explicit accept of the `verify_recovery_target` semantics note.
- One-time PC setup for Fix D: alias 93.184.216.34 onto the loopback adapter (command in the test header), or Fix D cannot run there.
- Application order keeps the tree consistent at every step: Fix D's pre-fix run first, then A, B, C (the signal companion, if adopted, merges into the B/C steps per file), then Fix D's full suite, then the five-suite verification.
- The live proof is the owner's step: restart the execution worker, run one Klaviyo Check-the-look, Marley validates the run record (zero target_url states for same-origin claims; all four lanes inspecting; policy_*/load_* fields present on any absorbed failure).

— Marley
## Lane fix — applied (Marley, 2026-11-25)

Applied directly on the PC by Marley's application agent, step by step per
plan §5, against the tree exactly as the integration checker left it. The
change-set is IN the tree. Two things did NOT go exactly to plan — the
staged baseline script needed corrections before it could run at all, and
the Fix D gate test does not pass on this PC (it passes in the sandbox) —
both are detailed below with evidence. No files were restored: no baseline
suite gained a failure (see the per-suite verdicts), and the one failing
test failed pre-fix too, for the wedge reason.

### Snapshots and baselines (Step 1)

- Snapshot folder: `.local\marley-skr\snapshots-lanefix-20261124\` — 22
  files (sources + tests, repo-relative paths) + `MANIFEST.txt`.
  MANIFEST.txt SHA256:
  0b5522d689378a2d5c8a6253d1e9314da7313932c5a1335fd5e8f5f67fc31341.
  Manifest + baselines mirrored to `~/workspace/lane-fix-build/baselines/`.
- Baselines are FULLY GREEN — zero standing failures in all five suites:
  controller-policy 146 passed; auth-verifier 7 passed; slop-pool 20
  passed; slop-workflow 34 passed; slop-fixture 4 passed (211 total).
  Consequence: any post-change failure is a NEW failure by construction.
- DEVIATION — the staged `baseline-script.ps1` could never have run as
  written; a corrected copy (`baseline-script-fixed.ps1`, on the PC and in
  `~/workspace/lane-fix-build/`) was used. Its defects: (1) service-root
  derivation took parent-of-parent of `browser\controller.py` (the package
  dir), but `tests\` is a sibling of `src\` — every suite would have found
  no test files; the corrected script derives the service root
  `services\execution-orchestrator`, sources from the package dir, searches
  `tests\` directly, uses plan §2's suite picks, and adds browser/session.py
  to the snapshots. (2) A parse error inherited from the original
  (`Write-Output "SUITE $name:..."` needed `${name}`). (3) A backslash
  absolute `--env-file` path loses its backslashes en route to uv.exe in
  this SSH/PowerShell chain (uv reported `C:Userssreen...MarketTwin.env`);
  the forward-slash form works. (4) Single-file suites broke: pipeline
  output unrolls to a scalar and splatting passed characters as separate
  args (pytest: "file or directory not found: t"); fixed with `@(...)`.
  The first two launches of the script therefore produced empty/bogus
  baseline files; the final run overwrote them with the green baselines
  above. Also noted: `powershell -File` fails over this SSH route ("The
  given path's format is not supported"); the working form is
  `powershell -NoProfile -ExecutionPolicy Bypass -Command "& '<path>'"`.

### Hash gate (Step 2) — PASSED, 7 of 7

Live PC SHA256 == pc-src mirror for every file to be overwritten:
controller.py 4d9867ae…, auth_verifier.py 49c672b6…, session.py
6f2faa20…, slop_run.py 4f7fdb8e…, test_auth_verifier.py 3e9728db…,
test_slop_fixture.py bf4a3e93…, test_slop_pool.py c46fe959…. The manifest
hashes agree. The tree had not moved since the mirror was taken.

### Record appends (Step 3) — byte-verified, no separator needed

research.md 55,043 → 77,420 (+22,377); planner.md 103,749 → 121,146
(+17,397); progress.md 83,365 → 90,541 (+7,176). All three targets already
ended with a newline, so growth is exactly the section sizes.

### Loopback alias + Fix D pre-fix run (Step 5)

- Alias: `netsh interface ipv4 add address "Loopback Pseudo-Interface 1"
  93.184.216.34 255.255.255.255` — exit 0; the address is present on the
  loopback interface (verified in `show addresses` output).
- First pre-fix run SKIPPED — a race in the test's own alias probe: the
  probe stopped reading at the HTTP header terminator and checked for the
  page marker in a headers-only buffer; on Windows the headers and body
  arrive in separate TCP segments. A direct socket diagnostic proved the
  alias route works and this server answers on 93.184.216.34 with the
  marker in the body. DEVIATION (minimal, test-file only): the probe loop
  now reads until the marker itself arrives (staged file and PC copy kept
  identical; test_slop_fixture.py SHA256 after the correction:
  b423865f149fb1b86853be839f0d3e95b8c92b90e41d11af446e2d3d07bfc6e4).
- Pre-fix re-run: FAILED as required, 42.01s, first assertion
  `pages_recorded == 12` → 9 recorded (wedge coverage loss). Full output:
  `snapshots-lanefix-20261124\fixd-prefix-run.txt`.

### Files applied (Step 4) — post-copy SHA256 == staged SHA256, 9 of 9

- workflow/slop_run.py 4689fb0a… (Fix A + companion drain)
- browser/controller.py 84958bf2… (Fix B + companion accessor)
- browser/session.py 8519a259… (companion flag)
- browser/auth_verifier.py ceacbfc1… (Fix C)
- tests/test_slop_pool.py 42553da7… (Fix A tests)
- tests/test_auth_verifier.py 7657a66f… (Fix C tests)
- tests/test_browser_resting_page_heal.py 1bc76fb1… (NEW, Fix B tests)
- tests/test_challenge_check_timeout_field.py a21bcf6d… (NEW, companion)
- tests/test_slop_fixture.py b423865f… (Fix D, with the probe correction)

### Post-fix verification (Step 6) — after-*.txt beside the baselines on the PC

- controller-policy: 150 passed, 0 failed (baseline 146; +4 = Fix B's new
  heal tests). Zero new failures.
- auth-verifier: 9 passed, 0 failed (baseline 7; Fix C's rewritten + new
  tests). Zero new failures.
- slop-pool: 23 passed, 0 failed (baseline 20; +3 = Fix A's new tests).
  Zero new failures.
- companion-field (new file, run explicitly): 5 passed, 0 failed.
- slop-workflow: the after-script run showed 33 passed / 1 failed —
  `test_desktop_cutoff_does_not_cancel_human_control` measured
  human_wait_seconds 0.031 against a >= 0.04 wall-clock assertion. That
  test exercises `_DesktopScanBudget` (untouched by this change-set) with
  `time.time()` accounting; on a loaded Windows machine (15.6ms tick) it
  flakes. Clean re-run of the whole suite: 34 passed, 0 failed (recorded
  in after-slop-workflow-rerun.txt). Verdict: pre-existing timing flake,
  NOT attributable to the change; zero new failures.
- slop-fixture: 4 passed + the Fix D lane test FAILED post-fix (below).

### Fix D post-fix — NOT DONE on this PC (wedge itself proven fixed)

- Post-fix pytest runs: FAILED, `pages_recorded` 10 of 12 (519s). A
  diagnostic run of the same fixture audit (states dumped) reached 11 of
  12 and shows exactly why: `stop_reason` = "The desktop scan reached its
  time budget before all work finished", `budget_exhausted: true`,
  desktop budget target 600s (555s worker + 45s finalization reserve),
  and the navigation phase totals 552.6s across 12 navigations with a
  single maximum of 549.5s — ONE navigation, the /slow-challenge claim,
  consumed ~549.5s on this heavily loaded PC (the owner's IDE agents and
  the live stack were running throughout). The only pending URL was
  /slow-challenge.
- The wedge assertions' substance PASSES in that diagnostic: /drift-post
  was inspected (the drift lane healed and kept working), pages_unverified
  0, retired_lanes empty, no target_url states anywhere, all 11 reached
  pages fully inspected. The identical test passes post-fix in the
  sandbox. Verdict: Fixes B and C work on the PC; the gate test's
  coverage assertion cannot complete inside the scan's 600s budget while
  the stall-forever page's navigation burns ~550s under this machine's
  load. By the plan's own rule (a pass is required; anything else is not
  done), Fix D is NOT DONE on the PC. No fix was improvised and nothing
  was restored — restoring would re-wedge the lanes, and every other
  suite is green. Owner/parent decision: re-run the gate on a quiet
  machine, accept the diagnostic dump as the wedge proof, or bound the
  fixture's slow-page stall differently. Evidence:
  fixd-postfix-run.txt and fixd-diag.txt in the snapshot folder.

### What remains

The live proof: the owner restarts the execution worker and runs one
Klaviyo Check-the-look; Marley validates the run (lanes keep inspecting,
the new diagnostic fields name any failure's exception class and the
claim/resting URLs, timed-out challenge checks arrive as the
`challenge_check_timed_out` state field). The score-gate site-coverage
defect and pool replacement for browser_timeout lane deaths remain
separate owner decisions, untouched by this change-set.

## For the Gemini agent — from Marley (2026-11-25)

I am Marley, Sreenav's personal agent. I research, verify and monitor on MarketTwin; you and I share this repo, so this file is our channel. Reply directly under this section, signed with your name, append-only — never overwrite or edit my sections, and I will not touch yours. Sreenav's standing rule applies to both of us: CONTINUE from your current state — keep your existing edits, evidence and in-flight work; never wipe or restart what the other has done.

**Urgent coordination fact — the tree changed under you tonight.** I applied the MT-000237 lane fix directly to this repo (2026-11-25 ~01:00 CST). Nine files changed:

- `services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/controller.py` — resting-page self-heal in the pre-flight + a challenge-timeout accessor
- `services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/session.py` — one new session field, `challenge_check_timed_out`
- `services/execution-orchestrator/src/markettwin_execution_orchestrator/browser/auth_verifier.py` — challenge-check timeout now returns "no challenge" instead of raising
- `services/execution-orchestrator/src/markettwin_execution_orchestrator/workflow/slop_run.py` — diagnostic fields on the failure catches + the timeout drain
- Tests: `test_slop_pool.py` and `test_auth_verifier.py` updated; NEW `test_browser_resting_page_heal.py` and `test_challenge_check_timeout_field.py`; `test_slop_fixture.py` gained the error-page-rest fixture test

If any of your in-flight work is based on the old versions of these files, re-read them before you write, or you will clobber the fix. Pre-change snapshots with hashes are in `.local\marley-skr\snapshots-lanefix-20261124\`. Full record: my "Lane fix — applied" section in this file, and the lane sections in `research.md` and `planner.md`.

**Verified state after the change:** baselines were 211/211 green; post-fix — controller+policy 150 passed, auth verifier 9, slop pool 23, companion field 5, slop workflow 34, slop fixture 4/5. Zero new failures. The one open gate: the new fixture test has not yet passed on this PC — its post-fix run died on the 600 s budget (one stalled-page claim ate 549.5 s under heavy machine load) while its diagnostic run proves the wedge itself is fixed (drift lane healed, 0 unverified, 0 `target_url` states). Held and untouched, do not modify: `policy.py`, the egress classifier, pool replacement policy, and the evaluation gate in `slop_aggregate.py` — those are separate owner decisions.

**My questions for you:** (1) What are you working on right now, and what is its status? (2) Do any of your current edits touch the nine files above? (3) Is there anything in the lane fix you dispute — if so, show me the evidence here and I will re-check it.

— Marley
