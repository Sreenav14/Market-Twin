# SAM — Architecture V2

**Date:** October 12, 2026. **Design status:** conditional prototype architecture.

## 1. Purpose and constraints

SAM is one persistent personal assistant that researches, reasons, operates tools and a real computer, creates usable outputs, remembers appropriately, verifies its work and corrects failures. When the owner instructs it, SAM can delegate bounded work to temporary specialists. Persistent employees are a separate later lifecycle feature.

The main assistant should remain useful without helpers. Its intelligence comes from the selected models, evidence gathering, computation, tool quality and effective feedback. Creating more agents does not by itself establish greater intelligence.

Hard planning constraints:

- Recurring V1 operating costs must remain **under $20/month**. Use a $19 envelope while measurement is pending.
- Reuse current hardware. A Mac mini is planned later; configuration is not selected yet.
- No automatic purchases or budget increases. Buying hardware is separate from the recurring ceiling.
- One owner initially. Include ownership in records, but defer commercial multi-user infrastructure.
- Keep consequential actions subject to exact authorization and verification.
- No unsolicited calls/texts/alerts; no ambient microphone/camera capture without explicit scoped activation.
- Preserve the original phone/SMS/web vision. Do not label a web-only prototype “full V1 complete.”

Assumptions: existing internet access and owner development time are available without new subscription/labor charges. Incremental electricity, backup, paid APIs, hosting, telecom and taxes belong in operating costs. If these cannot fit, reduce volume or explicitly revisit scope; never quietly raise the ceiling.

## 2. Scope by milestone

| Capability | Local core milestone | Full V1 / later |
|---|---|---|
| Main SAM, web chat and task history | Required | Extend through same runtime |
| Research, files, data and document outputs | Required on representative tasks | Broader formats/apps after validation |
| Memory and source library | Basic provenance and editable preferences | Hybrid retrieval when measured useful |
| Requested temporary helpers | After budget/permission gate | More concurrency only if justified |
| Evidence-based retries | Required | Improve using observed failures |
| Real browser/terminal/workspace | Required isolated environment | Add OS-specific executors as needed |
| Live desktop and human takeover | Gate before interactive account workflows | Required for complete V1 experience |
| Phone/SMS and active voice | Pending cost, identity and integration gate | Retained full-V1 requirements |
| GEPA optimization | Separately capped experiment after baseline | Promote only measured improvements |
| Persistent employees | Deferred lifecycle implementation | Created only on explicit instruction |
| Mac mini | No purchase needed for core milestone | Migrate after compatibility and restore tests |
| Weight-level RL, autonomous architecture evolution | Not selected | Separate evidence-driven decision |

Start with three useful workloads: a cited research report, a reproducible data/document task, and an approved browser workflow ending in a draft or reversible artifact. Hold back arbitrary external writes until their action contracts are tested.

## 3. End-to-end operation

**Owner request → authenticated intake → durable task → plan → authorized tool/helper work → evidence → verification → targeted repair or result.**

1. Resolve the owner, requested outcome, available data and current grants.
2. Record success criteria, output formats, resource limits and a task version.
3. Retrieve relevant facts and evidence; do not load the whole library into the prompt.
4. SAM chooses the next useful action. The controller checks authority, budget and resource ownership before dispatch.
5. Tools execute in a scoped environment and return observations, artifacts, receipts and usage.
6. SAM checks the original criteria against actual evidence. Unknown outcomes remain unverified.
7. If correction is warranted, retry the failed part with a changed strategy within the same task budget.
8. Deliver the result with sources, limitations and status. Record candidate lessons separately from trusted facts.

An approval wait preserves state and releases worker capacity. An ended voice conversation does not cancel authorized background work. Canceling a task stops future dispatch but cannot undo an external effect already committed.

## 4. Components and ownership

| Component | Responsibility | Must not own |
|---|---|---|
| Web/channel adapter | Authenticate requests, display status, accept approvals | Independent task truth or expanded permissions |
| Control API | Task admission, identity, grants, approvals and cancellation | Long work tied to a live HTTP request |
| Durable worker/scheduler | Claims, checkpoints, retry scheduling and recovery | Guessing whether an unknown remote write succeeded |
| Main SAM | Planning, evidence interpretation, tool choice, synthesis | Direct modification of policy, budgets or release gates |
| Helper pool | Scoped tasks with restricted data/tools and deadlines | Unlimited spawning or independent spend allowances |
| Tool/executor boundary | Validate action/grant, isolate execution, emit receipts and artifacts | Broad host/admin credentials |
| Computer control manager | One controller per resource, fencing and safe handback | Treating a screen viewer as an authorization system |
| PostgreSQL ledger | Canonical tasks, actions, grants, costs and metadata | Large screenshot/video bytes in task rows |
| Artifact/library storage | Originals, outputs, source versions and evidence | Unsourced claims automatically promoted to facts |
| Verifier | Criterion checks, artifact validation, unresolved gaps | Rewriting the user's criteria to make an answer pass |
| Improvement job | Candidate lessons and GEPA experiments | Live mutation of active tasks or its own grading rules |

These are logical responsibilities. Implement them as modules and a small number of processes, not a microservice for each row.

## 5. Technology baseline and open choices

| Layer | Current candidate | Decision boundary |
|---|---|---|
| API/backend | Python + FastAPI | Retain unless a concrete constraint disproves fit |
| Web app | React; Vite is a simple new-app option, Next.js also acceptable | Do not migrate an existing frontend without benefit |
| Persistence | PostgreSQL | Canonical task and action metadata |
| Workflow | Bounded DB-backed worker evaluated against one persistent workflow alternative | Must pass crash, lease, cancellation and upgrade tests before selection |
| LLM integration | Thin provider adapter, one strong fixed baseline model initially | Select model using quality/cost tests; no final model/version pinned here |
| Browser | Direct Playwright tools | High-level browser-agent library only after measured benefit |
| Terminal/desktop | Dedicated isolated VM/execution environment | No personal home-directory or control-process secret mounts |
| Desktop viewing | noVNC candidate plus SAM control manager | Stream transport can change without changing ownership contracts |
| Search | Metadata + lexical search; pgvector when justified | Test citation quality and filtered recall before ANN/reranking complexity |
| Parsing | Format-specific parsers; Docling candidate | Real extraction and rendering fixtures determine supported formats |
| Voice/SMS | Provider and audio bridge selected through proof of concept | Country, caller authentication, latency and total cost unresolved |
| Telemetry | Structured redacted events and cost records | Portable tracing; no need for a large monitoring stack initially |
| Learning | Versioned lessons; bounded GEPA experiment | Fixed independent evaluator and held-out transfer gate |

No Kubernetes, separate message platform, graph database, paid GPU or dedicated model-routing service is required by this starting design. This is not proof that none will ever be useful.

Source-supported caveats and comparisons are retained in the [architecture audit](../sam-audit/SAM_ARCHITECTURE_AUDIT_2026-10-12.md). In particular, browser sandbox configuration, external-write idempotency and provider feature differences require explicit integration checks.

## 6. Deployment now and later

**Initial local deployment:** owner browser connects to an authenticated local app. API and worker modules share the authoritative PostgreSQL ledger. The worker dispatches to an isolated execution environment. Artifact bytes live in a dedicated local directory with checksums and a backup procedure. Hosted inference is accessed only through the trusted adapter. No paid hosting or cloud desktop is assumed.

This deployment is available while its host and dependencies are available. It does not meet an unmeasured 24/7 uptime promise. Never put an active database directory inside a consumer file-sync workflow as a substitute for a consistent database backup; export/backup database state through its supported process.

**Remote/phone stage:** introduce a narrowly scoped communication edge only after pricing and account eligibility are verified. Keep one task authority. The edge can return an honest unavailable response if the host is offline; it must not claim task acceptance without durable admission. Remote access must authenticate both web traffic and streams. A tunnel/private network is transport, not a replacement for application authorization.

Offline task acceptance, cloud failover and a fully conversational outage fallback are additional requirements requiring durable inbox/reconciliation or a relocated authority. They are not implicit in purchasing a phone number.

**Later Mac mini:** preserve task, artifact and tool contracts. Export and verify the database, copy hashed artifacts, re-provision credentials, validate executor/VM and dependency compatibility, then run restore and representative task tests. Keep only one active authority during cutover. The Mac purchase does not remove hosted-model costs or guarantee that all existing containers/native apps work unchanged.

## 7. Delegation and repair

Default to main-SAM execution. A user can authorize helpers for a task within its existing budget; persistent employee creation is distinct. Initial proposed limits are one active root task and at most three temporary helpers, subject to hardware and available reservations. Start with fewer when practical. Only the root schedules helpers; no helper-created descendants initially.

Each helper receives an objective, source references, permitted tools, exclusions, acceptance criteria, deadline, output contract and a reservation from the parent budget. It returns evidence-linked artifacts, unresolved gaps and usage. It cannot create a new independent monthly allowance.

Repair is a decision, not repetition:

- Read failure: bounded backoff if transient.
- Missing evidence: different source/query or explicit unresolved result.
- Wrong calculation: executable recalculation or independent check.
- Poor decomposition: revise affected dependencies.
- Invalid file: repair and re-open/render it.
- Authorization failure: wait for permission; do not route around it.
- Unknown external write: reconcile first; no blind retry.

Proposed defaults: two correction attempts per subtask and one major replan per task. A new helper name does not reset them. All attempts share the deadline and root budget. A retry must identify new evidence or a changed approach. Successful outputs are retained unless changed inputs invalidate them.

## 8. Memory, evidence and learning

Store four distinct kinds of information: owner-confirmed preferences/facts; sourced external knowledge; task episodes and results; candidate procedural lessons. They have different authority. A model's reflection is a candidate lesson, not a verified fact or permission.

Evidence records identify source, version, retrieval time, location and supported claim. Documents preserve original bytes and extraction versions. Derived indexes can be rebuilt. Corrections and deletion apply to active indexes/caches as well as canonical records, with backup retention explicitly disclosed.

Verification reports each mandatory criterion as satisfied, unsatisfied or unverified. Schemas, citations that merely open, screenshots of unrelated content and repeated agent agreement are not sufficient proof. Use code/calculation checks where possible and evidence-focused judgment where necessary. Subjective outputs require a rubric and may require owner feedback.

GEPA operates in a separate improvement job: sanitized execution evidence → candidate prompt changes → development tests → selection validation → untouched final evaluation → versioned promotion or rejection. Freeze the model/tools/grader during the first experiment. Do not optimize permissions, billing, evaluator instructions or final test answers. All model calls, including reflection, are metered.

GEPA is optional under this budget. Do not run continuous optimization just because SAM is idle. A larger GA search or RL training project requires a separate demonstrated need; no promise of limitless recursive improvement is made.

## 9. Under-$20 operating budget

| Envelope item | Monthly allowance | Interpretation |
|---|---:|---|
| Model inference | $12 | Main SAM, helper, verifier, repair and any optimizer calls combined |
| Paid search/tools | $2 | Only if needed and available within the cap |
| Incremental electricity/backup | $4 | Unmeasured allowance; actual consumption can reduce inference allowance |
| Taxes/billing contingency | $1 | Reserve, not a guaranteed upper bound |
| **Planning total** | **$19** | Leaves nominal room below $20; feasibility must be measured |

Hosting and rented desktops have no allocation in the initial local milestone. Phone/SMS must be funded by reallocating within this same envelope if enabled; do not treat their charges as free additions. Optional paid GEPA also comes from the existing allocation.

The controller checks committed spend plus outstanding reservations and fixed/estimated charges before starting paid work. Reserve for bounded in-flight calls; reconcile actual provider bills. Unknown usage remains reserved. Do not count provider account alerts as guaranteed spend enforcement. If a task cannot fit, pause with its partial result and budget reason.

A proposed $0.50 per-task initial envelope limits execution; it is not a price promise or evidence that complex research fits. Larger tasks may consume a larger explicitly allocated share of the monthly balance. Correctness and access controls remain mandatory even when spend is low. Reduce volume rather than silently declaring unverified work complete.

The project must first measure cost per useful completed task and incremental host costs. Until then, **under $20 is a design constraint, not a validated unlimited-use service price**.

## 10. Stable decisions and change rules

Stabilize ownership, task/action IDs, versioned approvals, evidence references, worker generations, usage records and artifact manifests. Keep model, executor, stream and search implementations behind small explicit interfaces.

Replace a component only when an observed deficiency, comparison against a simpler fix, measurable benefit, migration cost and rollback plan justify it. Preserve current working components when they meet the gates. A new framework release alone is not a reason to redesign.

The [runtime contracts](RUNTIME_CONTRACTS.md) define these boundaries; the [build plan](BUILD_AND_VALIDATION_PLAN.md) defines how to validate them.
