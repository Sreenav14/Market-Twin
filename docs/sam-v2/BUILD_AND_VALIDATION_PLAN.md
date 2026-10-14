# SAM V2 — Build and validation plan

**Date:** October 12, 2026. **Status:** proposed implementation sequence; no SAM build started by this documentation task.

## 1. Delivery rules

- Keep recurring operating costs under $20; use the provisional $19 envelope in the architecture document.
- Build on current hardware; purchase/migrate to a Mac mini later after measurements.
- Deliver and verify one milestone at a time. Do not build all channels and optimization systems simultaneously.
- Preserve the full vision. A web-only milestone is not full-V1 completion.
- Check permissions, cost and evidence before expanding autonomy. Never trade verification for a nicer demo.
- Keep SAM separate from MarketTwin application code, databases and running services.

## 2. Sequential milestones

| Milestone | Deliverable | Required validation before progression |
|---|---|---|
| M0 — lock the experiment | Three representative task families; acceptance rubrics; allowed data/providers; budget ledger specification; host inventory | Clear outcomes, estimated costs and isolated test environment; select workflow candidate through recovery spike |
| M1 — useful main SAM | Local authenticated web intake, one main agent, browser/file tools, durable task records and usable artifact | Completes representative tasks with source/step evidence; restart preserves acknowledged work; no unauthorized tool path |
| M2 — verify and repair | Criterion outcomes, artifact checks, targeted retries and root-level cancellation | Seeded wrong answers/files are caught; bounded retries change strategy; unknown writes never blindly replay |
| M3 — requested helpers | Scoped temporary helper pool and shared reservations | Compare against single-SAM baseline; no independent budget resets, duplicate assignments or orphan work |
| M4 — personal computer control | Real desktop view, exclusive takeover, fresh handback, backup/restore | Delayed old commands rejected; actual resource mutations reconciled; restoration and credential isolation verified |
| M5 — full-V1 channels | Selected phone/SMS/audio integration into same task runtime | Identity/codec/interrupt/outage tests pass; measured recurring total remains under $20 at declared usage |
| M6 — controlled improvement | Versioned lessons and a small GEPA experiment when budget permits | Untouched transfer evaluation beats baseline without critical regressions; optimizer cost included; rollback works |
| M7 — later expansion | Requested persistent employees and migration to Mac mini | Workspace lifecycle, revoke/retire, compatibility, restore and single-authority cutover tests |

M5 is cost-gated. If phone/SMS cannot fit, present the measured shortfall and staging options to the owner; do not drop channels or increase spending without an explicit decision. M6 is optional for completing ordinary tasks and must not consume funds reserved for M1–M5 operation. Mac migration can occur when hardware arrives, independent of employee feature timing.

## 3. Validation gates

The detailed audit defines P01–P12. Reuse those experiments rather than creating a second incompatible suite. The earlier review contains T01–T36 adversarial cases. All live-SAM gates below remain pending.

| Gate | Procedure and acceptance |
|---|---|
| Outcome quality | Start with 20 development tasks. Later run held-out research, artifact, data and browser cases; report full/partial/blocked/false-success outcomes separately. Proposed pilot target ≥80% complete success on the declared bounded workload, with category counts and uncertainty |
| Durable recovery | Kill isolated workers before/after claims, external-like effects and receipts. No acknowledged task lost; no duplicate effect where idempotency supported; unknown outcomes remain blocked |
| Authorization | Change approved destination/content, revoke grants, inject instructions into documents, try cross-workspace and forbidden egress. All seeded unauthorized actions rejected at the executor |
| Budget | Competing workers reserve near the limit; force billing timeouts. Never admit work beyond outstanding exposure; include failed and optimizer calls; verify actual provider and utility costs |
| Delegation | Same tasks and budget with no helpers versus bounded helpers. Keep helpers optional unless quality/time gains justify total cost; cancel root and confirm child cleanup |
| Takeover | Delay agent commands, transfer to owner, mutate page/file, disconnect and hand back. Zero stale-generation commands accepted; fresh observations before resume |
| Retrieval | Known-answer corpus with source versions and ACLs. Test exact baseline before approximate search; preserve citation anchors and identify missing extraction |
| Artifacts | Open the actual produced files, verify content/formulas and inspect rendered layout on supported formats |
| Voice/SMS | Duplicate events, unknown callers, interruption, audio/session termination and host outage. No sensitive disclosure, unintended outreach or phantom task admission; latency measured, not guessed |
| GEPA | Fixed model/tools/grader and separate development/selection/final sets. Compare original prompt and simple/manual revisions; no promotion based solely on validation score |
| Restore/migration | Restore database and hashed artifacts to clean environment; revoked grants stay revoked; old host fenced before new dispatch; check target machine compatibility |

The 80% quality target is a proposed bounded-pilot threshold, not evidence of general reliability or permission to allow critical safety failures. Any critical authorization or data-loss failure blocks the affected release. A finite test suite cannot prove universal correctness.

## 4. Cost experiment before paid expansion

For each representative task, record root/helper/verifier input and billed output tokens, tool/search charges, wall time, retries, outcome and active executor time. Compute cost across **all attempts divided by useful completed tasks**, retaining blocked/failed counts. Record model/provider/rate versions.

Measure incremental electricity rather than assuming the $4 allowance fits an always-on host. Add backup and applicable tax/telecom fees. Reserve these first, then allocate the variable model budget. If fixed/incremental costs alone approach $20, the planned service level is infeasible without an explicit change.

Run small paid trials only when their allocation is authorized. Do not begin with the audit's 720-attempt comparison or 100-rollout GEPA ceiling if the remaining budget cannot fund it. Those are maximum experimental designs, not mandatory minimum spend. Free tools/tiers may be evaluated but are not assumed unlimited or guaranteed available.

No number of daily tasks is promised until representative usage is measured. A hard budget may mean a task pauses, fewer tasks run, or GEPA does not run that month.

## 5. Evidence already available

The [isolated experiments](../sam-audit/experiments.py) ran on Python/SQLite with synthetic local ledgers. Their [saved results](../sam-audit/experiment-results.json) showed:

- Lost-receipt replay creates two effects without receiver deduplication and one with it in the fixture.
- In ten forced races, eight unguarded workers reserve 240 units against 100; atomic admission reserves 90 and leaves 10 in all ten control trials.

These justify testing the corresponding design boundaries. They do not validate PostgreSQL, external providers, browser permissions, real costs, SAM intelligence, GEPA benefit or Mac compatibility. Do not mark M1–M7 passed using these results.

## 6. Decision register and change control

Use the audit's A01–A20 ADRs as the detailed history. V2 updates the budget and hardware assumptions while preserving their evidence conditions.

| Classification | Decisions |
|---|---|
| Stable foundations | Single owner-facing identity; authority outside model; one task ledger; evidence-linked outcomes; explicit unknown effects; ownership and provenance |
| Reversible choices | Python API organization, React packaging, model adapter, artifact backend, browser/stream transport, search implementation |
| Experimental choices | Workflow scheduler, executor isolation configuration, phone/audio stack, model selection, helper economics, GEPA |
| Deferred choices | Commercial multi-tenancy, fleet scaling, weight-level RL, nested autonomous agent hierarchy, automatic code/architecture evolution |

Before a significant change, document the reproduced deficiency, baseline results, simplest repair, alternative measurement, migration cost and rollback. Update the ADR and affected contracts. New tools must pass the same authorization/evidence/budget tests. Never let framework novelty replace a demonstrated need.

## 7. Full-V1 acceptance and unresolved decisions

Full V1 requires the original web/phone/SMS contact paths; useful main-SAM tasks; actual computer visibility and takeover; durable progress and memory; bounded permissions/cost; and demonstrated cross-domain outputs. Under-$20 feasibility must be evaluated at an explicit usage level. The local core can ship as a supervised prototype before that full gate, clearly labeled.

Before implementation, select the first concrete tasks, model/provider access, workflow experiment and isolated executor. Before phone rollout, resolve country/number, authentication, capture/recording rules, speech pipeline and recurring charges. Before buying the Mac mini, measure required RAM/storage and application compatibility. Before GEPA promotion, establish a credible fixed grader and independent test set.

**Current disposition:** documents ready for implementation planning; bounded prototype is a conditional go. Production autonomy, full-V1 affordability and improved intelligence remain outcomes to demonstrate.
