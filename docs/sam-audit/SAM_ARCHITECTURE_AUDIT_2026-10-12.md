# SAM architecture, feasibility, and change-stability audit

**Review date:** October 12, 2026. **Disposition:** Conditional Go for a bounded prototype; production readiness not established.

Prepared against SAM_MASTER_PLAN_V1.md and the user's comprehensive audit request. This is an independent assessment of the proposal, not a claim of an independent human review board. The skeptical second pass was performed by the same assistant and is recorded in section 14.

## 1. Executive Assessment

SAM is feasible as a persistent personal assistant using strong hosted models, real tools, isolated computers, evidence-based verification, and bounded delegation. The plan's general direction is defensible. It is not yet a validated production architecture, and no evidence establishes Perplexity parity, universal autonomy, or open-ended recursive intelligence improvement.

**Retain:** one owner-facing SAM, PostgreSQL, Python/FastAPI, a web interface, sourced memory, a real isolated workstation, hosted inference, explicit permissions, and staged delivery. **Resolve before dependent implementation:** task/action contracts, durable recovery semantics, execution isolation, evaluation criteria, shared budget admission, and the identity of the authoritative state store. **Experiment:** workflow engine, computer takeover, voice integration, retrieval configuration, delegation benefit, and GEPA. **Defer:** weight-level RL, automatic architecture evolution, multi-user infrastructure, and persistent employee fleets.

The principal architecture risk is not the choice between two web frameworks. It is allowing probabilistic decisions to control irreversible operations without deterministic boundaries, then mistaking a plausible response for a verified outcome.

Starting constraints updated after the user's October 12 clarification: recurring V1 spending must stay **under $20/month**, and a Mac mini is a later planned purchase. This supersedes the earlier $100 recommendation; hardware purchase is a separate one-time expense.

- One owner, one active interactive task, up to three authorized temporary helpers, and one writer per shared resource.
- Three initial workloads: sourced research reports; document/data analysis with checked artifacts; approved browser workflows with a draft or reversible output.
- Existing hardware first; the user plans to buy a **Mac mini later**. No RAM/storage configuration is selected before workload and compatibility measurements. Keep persistent data and tool interfaces portable; verify required executor images, virtualization, native apps and dependencies on the purchased machine before migration.
- Target a **$19 monthly operating envelope**, leaving a margin below the user's $20 ceiling. Provisional allocations: $12 model inference, $2 paid search/tools if needed, $4 incremental electricity/backup, and $1 billing/tax contingency. These are limits/allowances, not quotes or verified consumption. If non-model costs exceed their allocation, reduce inference spending. No automatic budget increase.
- Recommend one experienced full-stack/agent engineer as the accountable implementer, with periodic security/reliability review. A solo developer can prototype this, but must reduce simultaneous scope. Engineering effort estimates appear in section 6.

Two isolated experiments were actually executed. They reproduced duplicate effects after a lost receipt and overspending from non-atomic admission. These validate failure mechanisms, **not the proposed SAM implementation or PostgreSQL**. All live-agent, voice, isolation, and GEPA benchmarks remain pending.

## 2. Project Understanding

### 2.1 Materials actually reviewed and scope boundaries

| ID | Material | Review scope and evidentiary role |
|---|---|---|
| D1 | [SAM_MASTER_PLAN_V1.md](C:/Users/sreen/.codex/attachments/d002d68e-6eea-464a-971a-46a28ce8e1dc/SAM_MASTER_PLAN_V1.md) | Complete plan reviewed across this conversation; requirements and proposed stack, not implementation evidence |
| D2 | [Comprehensive audit request](<C:/Users/sreen/.codex/attachments/b3cdf77e-e449-4480-b770-3fbe5049d117/Pasted text.txt>) | Complete request; required review method and deliverable order |
| D3 | [Previous SAM assessment](C:/Users/sreen/OneDrive/Desktop/MarketTwin/docs/SAM_PLAN_REVIEW_2026-10-11.md) | Complete previous assessment, including GEPA clarification and 36 proposed tests; hypotheses re-examined here |
| D4 | [AGENTS.md](C:/Users/sreen/OneDrive/Desktop/MarketTwin/AGENTS.md) | Workspace instructions; preserve unrelated work, minimal changes, evidence and continuity |
| D5 | [CURRENT_STATE.md](C:/Users/sreen/OneDrive/Desktop/MarketTwin/docs/CURRENT_STATE.md) | Current top checkpoint and SAM entry; MarketTwin boundary only, not a complete fresh MarketTwin audit |
| D6 | [SESSION_HANDOFF.md](C:/Users/sreen/OneDrive/Desktop/MarketTwin/docs/SESSION_HANDOFF.md) | Current top checkpoint and SAM entry; earlier history reviewed previously, not revalidated |
| D7 | [MarketTwin README](C:/Users/sreen/OneDrive/Desktop/MarketTwin/README.md) | First 45 lines only, to confirm distinct product and implementation scope |
| E1 | [Experiment source](C:/Users/sreen/OneDrive/Desktop/MarketTwin/docs/sam-audit/experiments.py) | Isolated stdlib/SQLite mechanisms created for this audit; no product imports or network |
| E2 | [Experiment results](C:/Users/sreen/OneDrive/Desktop/MarketTwin/docs/sam-audit/experiment-results.json) | Actual successful run output, inspected after execution |

Discovery used repository filename searches, SAM/GEPA content searches in docs and README, and attachment filename searches. The only discovered SAM-specific source documents were D1 and D3, plus D2's new instructions. This does not claim a complete search of the user's computer or private cloud accounts. Unrelated MarketTwin documents were not treated as SAM specifications.

Document fingerprints, captured before this audit's continuity updates:

- D1 SHA256: `E9BEDD001CAA19D1E6A5836A48A86A7E3C15A6D49B002186AE5170D00432F237`
- D2 SHA256: `596615D7A30D8812D2EC3F80DD4CB97AD5D3C8FE1BBE06BE3737BCE20B6A8AB0`
- D3 SHA256: `B6AAD60C899F6B91BECEE512BF482E877EE261C158645A530E2652EDB27A148F`

**Not supplied/discovered:** SAM source tree, lockfile, deployment manifests, cloud account configuration, measured hardware profile, data inventory, provider entitlements, operational telemetry, production threat model, benchmark corpus, or real competitor results. D1 explicitly describes pre-implementation work. No application source was audited as if it implemented SAM.

Evidence labels throughout this report: **Fact** means observed document/tool output or a cited primary-source statement; **Experiment** means an executed isolated check; **Recommendation** is engineering judgment informed by that evidence; **Assumption** is an explicit planning input; **Unknown** requires measurement. Vendor documentation verifies documented behavior, not performance in this project. Issue reports identify test targets, not automatically confirmed defects in every release.

### 2.2 Requirements and traceability

No row currently has SAM end-to-end passing evidence. E1/E2 cover only two underlying mechanisms. T identifiers refer to the 36 cases in D3; P identifiers refer to section 9 here.

| Requirement | D1 location | Responsible component / contract | Validation evidence required |
|---|---|---|---|
| One capable general-purpose SAM | 1, 3.1 | Task runtime and tool adapters | P01, held-out completion and false-success measures |
| Main agent can work alone | 3.2 | Default single-agent execution | T01; single-agent baseline |
| Requested temporary helpers | 3.2, 12 | Root-controlled scoped worker pool | P05, T02/T08/T09 |
| Requested persistent employees | 3.2, 10 phase 5 | Employee lifecycle and resource ownership | Provision/revoke/retire test; deferred |
| Research with reliable citations | 2.4, 5, 11 | Evidence store, retrieval and verifier | P01/P06; claim-to-source checks |
| Real browser, terminal and artifacts | 4 | Isolated execution workspace | P03/P04/P11; actual output validation |
| Human takeover and safe resume | 4.1 | Controller generation, resource locks, fresh observations | P04; T14/T15 |
| Work survives restart | 3.1, 10 | Durable scheduler, intents and receipts | P02; E1 is only preliminary mechanism evidence |
| Permissions and exact approvals | 2.3, 9 | Authorization outside model; action binding | P03; T12/T13/T16–18 |
| Phone/SMS/web continuity | 2.1, 6 | Channel adapters resolving task and owner identity | P07; T21–23/T27 |
| No ambient capture or unsolicited outreach | 2.2–2.3 | Capture grants and outbound policy | P07; stop/capture and notification tests |
| Memory correction and provenance | 5 | Fact, episode, source and lesson records | P06/P08; T19/T20/T30 |
| Bounded costs | 3.3, 7.4 | Shared reservation ledger and provider metering | P05; E2 preliminary mechanism evidence |
| Improvement through GEPA | User clarification, D3 §6 | Separate optimizer and release gate | P08; T31–36 |
| Future providers and accounts | 8–9, 10 phase 6 | Versioned adapters, ownership fields and tenant enforcement | P09/P10; account isolation before expansion |
| Backups and restoration | 7, 9 | Consistent data/artifact backup and key recovery | P12; T29 |

### 2.3 Conflicts and hidden dependencies

The proposal combines conversation state, task state and computer ownership in one list, although they can differ concurrently. Separate these without changing the user's experience. The “no unsolicited outreach” rule means background work awaiting approval can remain paused indefinitely; do not silently add notifications. Owner-initiated status checks and active-session responses remain valid.

The proposed real Linux computer will not automatically run every Windows/macOS application. Native Office fidelity, OS-specific automation and local device capture are separate integrations. The database placement is unresolved: cloud task metadata and a local database must not become competing authorities. Define one authoritative store and fail safely when it is unreachable. A reachable phone gateway does not imply a functioning conversational agent during a home outage.

“No secrets in screenshots” is an objective, not an absolute property of authenticated browsing. Avoid sensitive views, redact where possible, restrict retention and access, and explicitly account for credentials/session tokens held by the browser. “Tenant IDs everywhere” helps migration but is not verified tenant isolation.

## 3. Architecture Audit

The following assessment covers necessity, failure behavior, growth, migration impact and falsification. Alternatives and accepted trade-offs are in section 5; ADRs in section 11 bind these to decisions. Read them together rather than treating a component name as an architectural guarantee.

| Component / purpose | Necessity and simplest sufficient form | Failure / bottleneck / scale concern | Evidence, migration seam and validation |
|---|---|---|---|
| API and web UI | Required intake/status; FastAPI and React remain reasonable | Process-bound work disappears on restart; blocking OCR can stall requests | Separate durable worker from request handling; task IDs survive UI changes; P02/P11; [FastAPI guidance](https://fastapi.tiangolo.com/tutorial/background-tasks/) |
| Primary reasoning runtime | Required; one bounded tool loop with explicit task contract | Context loss, invalid calls, false completion, correlated verifier errors | Artifact/evidence references outlive model context; P01/P09; no framework parity established |
| Workflow/scheduler | Required durable execution; DB-backed worker is candidate, not proven winner | Expired leases, poison jobs, duplicate delivery, unfair queues, retry storms | Persist intent, claim generation, retry policy and cancellation; P02/P05; [PostgreSQL locking](https://www.postgresql.org/docs/current/sql-select.html), [Temporal activities](https://docs.temporal.io/activity-definition) |
| Authorization and side effects | Required from first connected action | Stale approval, revoked grant, browser bypass, lost remote receipt | Bind actor/task/version/arguments/resource; authorize at execution boundary; P03/P04 |
| Model adapter and metering | Required thin adapter; broad routing optional | Provider quota, schema differences, feature loss, silent expensive fallback | Capability declaration, normalized usage/errors plus provider-specific extension; P09 |
| Helpers | Useful for independent work, unnecessary for every query | Duplicate research, synchronization, overdelegation, shared-file races | Root-controlled task contracts; immutable outputs plus serialized integration; P05 |
| Browser and terminal | Required for the vision; structured API first where supported | UI drift, downloaded malware, escaped process, leaked session credentials | Workspace lifecycle and tool contracts; P03/P04/P11; [Playwright Docker caveats](https://playwright.dev/docs/docker) |
| Live desktop | Required for takeover, not all helper work | Stale commands, concurrent API mutation, disconnected human lease | noVNC supplies a viewer/client, not SAM authorization or arbitration; enforce controller generation; P04; [noVNC embedding](https://novnc.com/noVNC/docs/EMBEDDING.html) |
| Database and artifacts | Required; metadata in PostgreSQL, bytes separately | DB outage, disk full, DB/object mismatch, unbounded history | Artifact IDs, hashes and staged publication; backups of both; P02/P12 |
| Knowledge and ingestion | Required provenance; semantic index/reranker conditional | Parser resource exhaustion, incorrect tables, stale embeddings, filtered recall | Originals are canonical; reindexable derived data; P06; [pgvector](https://github.com/pgvector/pgvector), [Docling](https://docling-project.github.io/docling/) |
| Personal memory | Required editable preferences and useful task history | Poisoned facts, cross-user leakage, contradictory versions | Separate asserted facts from inferred lessons; expiry/correction/deletion; P06/P08 |
| Phone/voice/SMS | Required full-V1 channels, can follow web prototype | Caller impersonation, codec mismatch, delayed barge-in, webhook duplicates | Stable channel envelope, bounded media session, stronger approval identity; P07 |
| Cloud/local connectivity | Needed when remote availability is enabled | Network partition, split-brain authority, stale worker reconnect | One authority, renewable worker grants; unavailable fallback; P02/P07 |
| GEPA improvement | Experimental, not required for initial execution | Reward gaming, benchmark leakage, regression, expensive evaluation | Versioned prompt bundles and frozen external grader; P08 |
| Telemetry and operations | Essential minimal audit and cost records | Logs leak data or fill disk; tracing outage stops tasks | Redacted event schema, quotas, retention, separate operational metrics; P11/P12 |

Use asynchronous job dispatch for long work; use synchronous reads for status and short validation. UI streaming can use SSE; voice and interactive computer transport have different latency and bidirectional needs. Do not force them through one generic event bus. Transactions must be short: never hold a database lock across model calls, browser activity, or human approval. A task waiting for permission should consume durable state, not an occupied worker.

The database-backed option must include durable admission, leasing, heartbeat expiry, retry classification, poisoned-job handling, cancellation and reconciliation. `SKIP LOCKED` helps competing consumers claim work; it is not a workflow engine or exactly-once delivery guarantee. PostgreSQL explicitly notes its inconsistent-view behavior is suited to queue-like access, not general-purpose reads. [PostgreSQL SELECT](https://www.postgresql.org/docs/current/sql-select.html)

## 4. Critical Risk Register

Likelihood is qualitative and conditional on implementing the identified weak design; no incident probabilities were measured. P0 blocks the affected capability, not read-only prototyping. P1 should be addressed before implementation of its subsystem; P2 is near-term; P3 is optional optimization.

| ID / priority | Issue → root cause | Likelihood / impact | Detection | Prevention / correction | Cost if fixed late |
|---|---|---|---|---|---|
| R01 P0 | Duplicate external write → crash after effect, before receipt | Plausible on retries / financial or data harm | P02, external ledger reconciliation | Stable operation ID, provider deduplication, unknown-outcome state; never blindly replay | High: connector semantics and historical repair |
| R02 P0 | Unauthorized effect → policy exists only in prompts or approvals are stale | High exposure with hostile content / critical | P03 mutation/revocation tests | Executor authorization; bind exact content and target; restrict tool and network capabilities | Very high: credentials and runtime redesign |
| R03 P0 | Workspace compromise → untrusted code shares host privileges/secrets | Exposure-dependent / critical | P03 isolation and egress checks | Dedicated VM/sandbox, no host mounts/socket, narrow credentials, sandboxed browser | High: credential rotation and data incident |
| R04 P0 | Concurrent human/agent action → lease without executor fencing | Plausible on delays / wrong actions | P04 delayed-command injection | Generation checked at execution, serialized resource writes and fresh state | High: distributed control retrofitting |
| R05 P1 | False success → verifier checks form or agreement, not evidence | High for open-ended work / trust failure | P01 seeded defects and unknown answers | Criterion-level satisfied/unsatisfied/unverified; calibrate independent grading | High: invalid stored outcomes contaminate learning |
| R06 P1 | Budget overrun → concurrent check-then-spend or unmetered reflection | Demonstrated mechanism / escalating spend | P05 reservation races and billing reconciliation | Atomic reservations, call ceilings, task-tree accounting, paid optimizer budget | Medium–high: broad instrumentation |
| R07 P1 | Lost or conflicting task state → local/cloud dual authority | Conditional on hybrid design / duplicated or lost work | P02 partition/reconnect | One canonical ledger; unavailable fallback rather than false admission | High: state migration and reconciliation |
| R08 P1 | Silent learned regression → optimization consumes its own benchmark | Likely without split discipline / systemic errors | P08 hidden family-separated holdout | Fixed evaluator, independent final test, versioned promotion/rollback | High: recover contaminated training/evaluation data |
| R09 P1 | Data leakage via provider, browser or logs → local storage mistaken for local processing | Plausible / confidentiality harm | P03 data-flow audit | Data classifications, approved endpoints, retention controls and redaction | High: cannot recall disclosed data |
| R10 P1 | Gateway dependency vulnerability → unpinned or exposed proxy | Version/config dependent / credential exposure | Advisory matching and SBOM review | Minimal trusted surface; pin patched version; reject caller-supplied routing | Medium before deployment, high after incident |
| R11 P1 | Call/SMS identity confusion → phone number treated as authentication | Plausible / unauthorized disclosure/action | P07 spoofed caller and replay cases | Caller number is context; owner authentication through trusted app for sensitive approval | High: identity contract rework |
| R12 P1 | Lost evidence/backups → DB and artifacts not restored consistently | Operationally plausible / unverifiable history | P12 restore and hash checks | Consistent manifests, durable publish sequence, key recovery, retention policy | High after loss |
| R13 P2 | Poor retrieval → post-index filters and wrong source versions | Corpus-dependent / omissions and wrong answers | P06 exact baseline and filtered recall | Version/ACL-aware queries; tune exact/iterative search before new DB | Medium; preserve originals to limit rework |
| R14 P2 | Unusable phone experience → codec conversion, buffered playback, slow reasoning | Plausible / abandonment | P07 measured turn and interruption latency | Lightweight voice handling; acknowledge long work; clear buffered audio correctly | Medium |
| R15 P2 | Cost/complexity outruns team → all channels, many frameworks and employees at once | High under solo scope / stalled delivery | Milestone cycle time and maintenance hours | Narrow first workloads; one runtime and scheduler; gated expansion | High sunk integration time |
| R16 P2 | OS/app mismatch → Linux assumed to reproduce all desktop workflows | Task-dependent / unsupported promises | P11 actual required apps and file fidelity | OS-specific executor only when required; disclose unsupported workflows | Medium–high if UI promises universal support |
| R17 P2 | Availability overpromised → gateway survives, worker does not | Likely during home outage / misleading UX | P07 host-offline drill | Distinguish contact availability from task capability; honest fallback | Low if specified early |
| R18 P3 | Premature model/infra optimization → choice driven by novelty | Avoidable / rework | ADR change review | Require measured deficiency and net benefit | Medium accumulated churn |

One concrete cascade: an ingestion spike fills disk, checkpoints fail, leases expire, another worker retries an external action, the first worker later resumes, and a duplicate effect occurs. Resource limits, storage watermarks, fail-closed dispatch, generation fencing and idempotency must work together. No single “retry” setting fixes the cascade.

## 5. Technology Decision Matrix

Ratings below are engineering comparisons for the proposed workload, not measured benchmarks. Every selection is contingent on its ADR and experiment. Ecosystem activity is useful support evidence, not a security or performance certificate.

| Decision | Minimal alternative | Balanced candidate | More sophisticated alternative | Assessment and verdict |
|---|---|---|---|---|
| Service architecture | One process for supervised demo | Modular API + durable worker + isolated executor | Domain microservices/event platform | Balanced separates failure/privilege boundaries without many deployments; retain monolith structure |
| Backend | Existing Python libraries | FastAPI typed API | TypeScript/NestJS or multiple services | Retain Python familiarity; language switch has no demonstrated benefit; CPU work outside request process |
| Frontend | Small React client | React Vite or already-started Next.js | SSR/BFF-heavy Next.js deployment | No evidence requires SSR for private dashboard; either is reversible; do not replace working Next.js solely for simplicity |
| Persistence | SQLite for throwaway single-process demo | PostgreSQL | Managed HA PostgreSQL | PostgreSQL suits concurrent state and ownership; HA cost deferred; backups essential immediately |
| Workflow | Explicit persisted bounded state machine | DB-backed worker or persistent LangGraph after P02 | Temporal | Compare two candidates, not five frameworks; durable graph state and durable activity effects remain different concerns |
| LLM access | Direct provider SDK | Thin internal adapter; optional LiteLLM library | Shared LiteLLM proxy/router | Start narrow; proxy adds a sensitive service; feature parity must be tested |
| Agent execution | Single tool loop | SAM with bounded helper pool | Multi-level autonomous hierarchy | Balanced only where P05 shows benefit; no default permanent agents |
| Browser | Direct Playwright tools | Playwright plus isolated desktop fallback | Browser Use / managed browser service | Keep direct deterministic tools; evaluate high-level agent layer only against actual tasks and permissions |
| General execution environment | Dedicated test account with constrained tasks | Dedicated Linux VM with containers where useful | Managed sandboxes/microVM fleet | VM boundary recommended for untrusted code; orchestration can remain Compose; no automatic kernel-security equivalence |
| Live desktop | Read-only screenshots | Authenticated noVNC plus SAM control manager | WebRTC/Guacamole/Kasm | noVNC POC remains reasonable; transport replacement only after measured latency/quality failures |
| Search | Metadata + PostgreSQL text search | Text + pgvector; optional reranking | Qdrant/OpenSearch/graph | Start exact where corpus allows; add ANN/reranking only with recall/latency measurements |
| Parsing | Format-specific parsers | Docling plus explicit format validation | Managed parser/OCR | Candidate, not universal fidelity guarantee; isolate resource-intensive parsing; vendor privacy/cost trade-off |
| Voice | Web text first; then STT/LLM/TTS | Twilio media bridge to chosen audio stack | LiveKit/Pipecat or direct realtime/SIP | Choose one media path; lower integration count preferred unless interruption tests fail |
| Secure access | Private local prototype | Private network + hardened public voice edge | Zero-trust gateway/enterprise identity | Network membership does not replace app authorization; persistent WebSocket support required |
| Secrets | OS secret store for trusted control process | Narrow credential broker and short-lived grants | Managed vault service | Do not expose full process environment to executor; Vault not required merely for one owner |
| Telemetry | Structured redacted events | OpenTelemetry plus minimal dashboard | Full observability stack | Keep a portable event schema; cost and evidence logs mandatory, extra services optional |
| Learning | Manual evidence-driven improvements | GEPA on selected prompt components | GA architecture search + routing RL + fine-tuning | GEPA is experimental; larger search space and weight training deferred |
| Deployment | Existing host | Dedicated host; optional cloud communication edge | Multi-region/cloud workers | Hybrid only for a demonstrated availability/capacity need; avoid duplicated state authority |

**Documented implementation constraints:**

- Playwright's standard Docker instructions warn that root disables Chromium sandboxing and distinguish trusted testing from untrusted browsing. The image is not a ready-made secure agent environment. [Playwright](https://playwright.dev/docs/docker)
- noVNC needs a VNC endpoint and appropriate WebSocket transport. It does not supply task ownership or action arbitration. That responsibility stays in SAM. [noVNC](https://novnc.com/noVNC/docs/EMBEDDING.html)
- LangGraph distinguishes graph checkpoints from cross-thread stores; in-memory savers do not survive restarts. Treat persistent checkpoint configuration as an integration requirement. [LangGraph](https://docs.langchain.com/oss/python/langgraph/persistence)
- OpenHands is oriented toward software development; Browser Use toward browser agents. Neither repository establishes all of SAM's personal-assistant requirements. Consider reusable execution components without adopting their entire product architecture. [OpenHands](https://github.com/OpenHands/OpenHands), [Browser Use](https://github.com/browser-use/browser-use)
- The inspected GEPA issue tracker discusses per-proposal reflection-cost visibility and cached evaluations consuming metric-call budgets. These are reasons to test the chosen version's accounting, not proof every current configuration is broken. [Issue 331](https://github.com/gepa-ai/gepa/issues/331), [Issue 316](https://github.com/gepa-ai/gepa/issues/316)

## 6. Feasibility Report

### 6.1 Capability feasibility

| Capability | Assessment | Restriction or dependency |
|---|---|---|
| Persistent tasks, sourced memory, files, web UI | Established technology | Correct implementation and recovery still required |
| Multi-source research and document/data work | Feasible but quality-sensitive | Reliable sources, artifact checking, held-out evaluation |
| Delegation and targeted retries | Established mechanism; benefit experimental | Shared resource/budget control and measurable value |
| Long-running browser work and takeover | Technically challenging | Sessions, stale state, remote effects, human interruptions |
| Phone/SMS identity and natural interruption | Feasible but integration-heavy | Country/number eligibility, audio pipeline, caller policy |
| Universal desktop operation | Only with meaningful restrictions | OS, app access, login, CAPTCHA, terms, task observability |
| GEPA improves future task quality | Experimental for SAM | Objective feedback and independent transfer evidence |
| Continuous autonomous weight learning | Not justified for V1 | Trainable model, rewards, data rights, compute, validation |
| Better than Perplexity across all tasks | Unsupported | Matched live comparisons; architecture resemblance is insufficient |
| Perfect safety/general intelligence | Not a defensible release claim | Finite tests cannot establish universal correctness |

### 6.2 Hardware and team recommendation

Reuse the current machine for a supervised prototype in an isolated environment. The user has selected a later Mac mini purchase as the hardware direction; no purchase or configuration is authorized by this audit. Measure memory headroom, disk I/O, restart behavior, actual power use and required application compatibility before sizing it. Plan migration through versioned database exports, artifact manifests, separately transferred credentials and executor compatibility tests. Do not assume a Linux desktop image, native macOS automation and Windows applications are interchangeable. No retail offer was selected, and no claim is made that the later Mac mini will eliminate hosted-model charges.

Planning estimate for one experienced full-time engineer: roughly **6–10 engineer-weeks** for a constrained web prototype with real tools, records and evaluation; **another 6–12 weeks** for a reliable personal pilot including takeover and voice; **4–8 additional weeks** for hardening, restoration and broader testing. These are low-confidence scope estimates, not commitments; overlap, familiarity and site-specific integrations can materially change them. Re-estimate after P01–P04. At 15 focused hours/week, elapsed time is much longer than the full-time figures. Budget recurring maintenance rather than treating launch as the end of work.

### 6.3 Cost model and recommended spending policy

**Current decision: under $20/month.** Use the $19 allocation in section 1 and existing hardware. Recommend a local web-first prototype with no paid hosting or rented desktop. Phone/SMS remain full-V1 requirements from D1; their deferral is a proposed staging choice, not permission to delete them from scope. Before enabling them, show that number rental, calls, audio inference, messaging/registration and hosting fit the same total ceiling; otherwise present the explicit scope/budget trade-off. No free-tier dependency is assumed to provide unlimited reliable service.

Preserve main-agent reasoning, sourced memory, verification and requested helpers. Reduce task volume and optional parallel work before removing correctness checks. GEPA is an occasional, explicitly budgeted experiment inside the same envelope, not a continuous background expense. Prototype availability follows the current host; any later 24/7 promise requires measured power and outage behavior. Existing internet and owner labor are assumed already available; hardware is a separate capital purchase. Incremental electricity, backup, taxes and fees must be counted when evaluating the operating ceiling.

The larger scenarios below are retained as **out-of-budget workload comparisons**, not V1 spending recommendations. They show why usage must be constrained; they do not override the user's ceiling.

Use USD planning scenarios, with US local inbound telephony only as an illustrative country assumption. All token volumes include coordinator, helpers, verification and retries. They are workload assumptions, not observed SAM consumption.

For transparent arithmetic, use the fetched GPT-5.4 text rates of $2.50 per million input tokens and $15 per million output tokens as a reference rate—not a final model recommendation. The page also lists cached-input discounts and long-context surcharges; this example assumes no cache discount and no surcharge-triggering request. Billable reasoning output must be included. [Official model pricing](https://developers.openai.com/api/docs/models/gpt-5.4)

`text cost = sum(input_tokens × input_rate + cached_tokens × cached_rate + billed_output_tokens × output_rate) / 1,000,000`

| Scenario | Tasks/month | Aggregate input/output per task | Input/output millions per month | Calculated text cost |
|---|---:|---:|---:|---:|
| Low | 60 | 25,000 / 4,000 | 1.5 / 0.24 | $7.35 |
| Medium | 300 | 80,000 / 12,000 | 24 / 3.6 | $114.00 |
| High | 900 | 250,000 / 35,000 | 225 / 31.5 | $1,035.00 |

These calculations were executed in E1/E2. They are not performance measurements or a claim that these token budgets are sufficient for every task.

The fetched Twilio US page lists local inbound calls at $0.0085/minute, a local number at $1.15/month, and Media Streams at $0.0044/minute. Thus this selected transport path costs `1.15 + minutes × 0.0129`, before speech/model charges, messaging, taxes and other features. It is $5.02 for 300 minutes and $20.50 for 1,500 minutes. Recheck account/region rates before purchase. [Twilio pricing](https://www.twilio.com/en-us/voice/pricing/us)

| Additional monthly item | Low | Medium | High | Basis |
|---|---:|---:|---:|---|
| Host/gateway/storage/backup allowance | $15 | $30 | $60 | Planning allowance, not vendor quote |
| Electricity allowance | $3 | $6 | $12 | Replace with measured kWh × local rate |
| Search/parsing allowance | $5 | $20 | $80 | Usage reserve; provider not selected |
| Audio inference allowance | $0 | $15 | $60 | Illustrative reserve; benchmark actual pipeline |
| US inbound number + streaming | $0 | $5.02 | $20.50 | No phone in low case; 300/1,500 minutes otherwise |
| GEPA experiment allowance | $0 | $25 | $150 | Separate capped optimization budget |
| Extra rented execution allowance | $0 | $0 | $100 | Conditional; not needed for initial local prototype |
| **Illustrative total including text** | **about $30** | **about $215** | **about $1,518** | Not a quote; excludes labor, hardware, SMS/registration and taxes |

Fixed costs: host, number, baseline storage and backup. Usage costs: inference, tools/search, audio, SMS segments, parsing and rental execution. Operational costs: upgrades, incident recovery, evaluation maintenance and owner review. Labor cost is `engineering_hours × agreed_rate`; no rate is assumed. Electricity is `average_watts / 1000 × hours × price_per_kWh`.

The under-$20 ceiling requires low-volume scope; it cannot support the medium scenario as written. A proposed initial per-task inference/tool reservation is $0.50, with deeper work using a larger explicitly allocated share of the same remaining monthly budget. This is a dispatch limit, not a promise that a complex task costs $0.50 or less. Admission must account for root, helper, verifier and optimizer work together. Stop paid dispatch before reservations exceed the available allocation; do not silently reduce verification or exceed the ceiling to finish a task. Provider metering delays mean cancellation cannot reverse consumed work. Reserve bounded in-flight calls and maintain a reconciliation margin. Failed experiments and unsuccessful tasks count toward cost. Validate actual monthly feasibility with measured utility and provider bills before claiming the cap is reliably met.

## 7. Scalability and Future-Change Analysis

Use an illustrative baseline of 10 tasks/day, averaging 10 minutes of active executor time. Little's-law arithmetic yields approximately 0.069 continuously averaged concurrent tasks; peak demand and internal helper fan-out dominate capacity. This is not a measured service-time distribution.

| Scenario | Illustrative task volume / average active task concurrency | Likely first limits | Required changes if observed | Migration difficulty / prevention now |
|---|---|---|---|---|
| Initial | 10/day / 0.069 | Browser RAM, model latency, owner approval | Queue work, cap helper concurrency, one executor | Low; stable task/resource contracts |
| 10× | 100/day / 0.69 | Bursts, provider quotas, parsing contention | Separate ingestion concurrency; add executor only after measurement | Low–medium; durable claims and quotas |
| 100× | 1,000/day / 6.94 | Worker capacity, DB connections, storage, noisy neighbors | Worker pool, connection pooling, object storage retention, tenant fairness | Medium; no need to assume PostgreSQL replacement |
| 1,000× | 10,000/day / 69.44 | Operational staffing, fleet security, billing, throughput quotas | Managed operations, autoscaled executors and tested HA; possibly stronger workflow service | High; commercial product scope, not a personal-PC promise |

Three simultaneous helpers can multiply executor demand; longer tasks change all estimates. Scaling task volume is different from scaling tenant count, dataset size, or availability. None implies Kubernetes automatically.

| Change | Components likely retained | Adjustment / change trigger |
|---|---|---|
| 10×–1,000× source corpus | Original storage and provenance contracts | Benchmark filtered recall and p95 retrieval; tune indexes, batch ingestion, then separate search only if needed |
| New model/provider | Task/evidence/approval records | Adapter contract tests, capability differences and data policy; no automatic fallback to an unapproved destination |
| OS-specific application | Control plane and task records | New executor adapter; test real app, auth and file fidelity |
| More tenants | Ownership model | Enforced authorization on DB/artifacts/cache/streams, per-tenant credentials and quotas before onboarding |
| Stronger privacy/compliance | Explicit data classifications | Region/retention controls, legal obligations and deletion propagation; provider choice may change |
| Partial outage | Durable tasks and single authority | Circuit breaker, queued resume, rejected stale workers; no active-active authority without a new ADR |
| Years of history | Stable IDs and artifact references | Archival and pruning, summaries with provenance, index rebuilds, restore windows |
| New developer/team | Modular code and contracts | One-command isolated dev setup, test fixtures, runbooks, diagrams and ADR ownership |
| Dependency deprecation | Product contracts | Pin/version inventory, scheduled advisory review, compatibility migration; replace component, not task semantics |
| Budget contraction | Single-agent and metering baseline | Reduce concurrency, optimize measured hot paths, pause expensive GEPA; preserve correctness gates |

**Initial release:** freeze interfaces and deliver bounded workflows. **6–12 months:** use real telemetry to decide on dedicated hardware, improved retrieval and validated GEPA; add voice/employee capabilities only through gates. **2–3 years:** multi-user operations, regional controls and execution fleets are scenarios, not requirements to build today. Model/software availability in that horizon cannot be predicted reliably.

## 8. Security and Reliability Assessment

### 8.1 Trust boundaries

Untrusted documents, sites, messages, caller audio, helper outputs and downloaded code never become authority. The policy controller owns grants and approves tool requests; executors receive the smallest necessary capability. Separate permission to read from permission to disclose: sending a query or typing into a website may transmit private data even if no “Submit” button is pressed. [OpenAI computer-use safety](https://developers.openai.com/api/docs/guides/tools-computer-use)

Keep provider credentials in the trusted control process/broker. Do not pass its environment, home directory, Docker socket or unrelated browser profile into an agent workspace. A VM is a useful containment boundary, but shared mounts and broad network routes can undo that boundary. Docker's documentation highlights daemon and configuration attack surfaces. [Docker security](https://docs.docker.com/engine/security/)

Authenticate live streams and downloads as well as API calls; include expiry, origin protection and revocation. Clipboard, uploads, redirects, localhost/private-address access and DNS changes need policy treatment. For MCP, verify server identity and token audience; do not treat a connector protocol as a permission system. [MCP security guidance](https://modelcontextprotocol.io/docs/draft/tutorials/security/security_best_practices)

PostgreSQL row security can add defense in depth, but owners and BYPASSRLS/superuser roles can bypass normal policies. Test through actual application roles, and enforce artifact/cache/search/stream boundaries independently. [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)

Local storage does not mean local inference privacy. OpenAI documents endpoint-specific retention and account-dependent controls; remote MCP providers have their own retention policies. Specify permitted data destinations and required account settings before sensitive data use. [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data)

### 8.2 Dependency evidence and limits

The inspected LiteLLM advisory GHSA-3cv6-jpf6-8222 documents authenticated proxy routing overrides that could expose provider credentials. This is a concrete reason to reject caller-controlled routing, keep proxies private, and select a verified patched release. The advisory lists multiple patched branches; a simplistic single-version comparison is insufficient. No SAM lockfile exists to determine exposure. [LiteLLM advisory](https://github.com/BerriAI/litellm/security/advisories/GHSA-3cv6-jpf6-8222)

A second published advisory concerns privilege escalation through salt-key reuse. It reinforces configuration/version review, not wholesale rejection of the library. No exploit was run and no claim is made that the user's existing environment is vulnerable. [LiteLLM advisory index](https://github.com/BerriAI/litellm/security/advisories)

This is not a complete dependency vulnerability scan: no SAM software bill of materials or selected image digests were supplied. Before release, generate a lockfile/SBOM, scan the exact artifacts, review relevant maintainer advisories and licenses, and document patch ownership. Repository activity alone cannot guarantee support longevity.

### 8.3 Voice, regulation and failure recovery

Twilio documents one bidirectional Media Stream per call, secure WebSocket connectivity and signature validation. Its media format uses 8 kHz mono mu-law, and clearing buffered audio is part of interruption handling. Confirm conversion and cancellation with the chosen speech stack. [Media Streams](https://www.twilio.com/docs/voice/media-streams), [WebSocket audio](https://www.twilio.com/docs/voice/media-streams/websocket-messages)

US application-to-person messaging registration can affect delivery and onboarding even for low volume. Country, number type, third-party calling and recording policies remain unresolved. Do not infer legal compliance from provider signup; determine jurisdictions and get appropriate review before public caller handling or outbound calling. The requested FCC page could not be fetched, so this audit makes no detailed FCC legal conclusion. [Twilio A2P guidance](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc)

Recommended personal-pilot objectives, subject to measurement: no loss of acknowledged tasks on worker restart; degraded status visible within 60 seconds of worker loss; restoration within four hours from a backup no more than 24 hours old. A daily backup cannot meet zero data loss after full host destruction. Distinguish process crash, disk loss and region loss. Full conversational availability during a home outage requires another functioning runtime; a fallback announcement is a narrower, honest service guarantee.

## 9. Proof-of-Concept and Testing Plan

### 9.1 Actually executed

E1 used Python 3.12.12 on Windows, standard-library SQLite, temporary audit-local databases, separate connections and a deliberately exited subprocess. No real accounts, cloud resources, paid model calls, application databases or existing services were used.

| Experiment | Procedure | Observed result | What it establishes / does not establish |
|---|---|---|---|
| X01 lost receipt, negative control | Commit simulated remote effect; terminate subprocess with exit 23 before receipt; replay | Effect count 1 → 2, with zero receipt before replay | Checkpointing alone permits duplicates; not a real provider or SAM test |
| X02 lost receipt, receiver deduplication | Same crash; receiving ledger enforces unique operation key | Effect count stays 1 after replay | Receiver deduplication works in this fixture; no guarantee for providers lacking it |
| X03 budget race, negative control | Eight connections observe 100 units, then each reserve 30; force overlap | All 10 trials reserve 240, leaving −140 | Reproduces check-then-act oversubscription; not estimated production likelihood |
| X04 atomic admission | Eight competing connections; conditional debit and reservation in transaction | All 10 trials admit 3, reserve 90, leave 10 | Demonstrates atomic admission in SQLite; not PostgreSQL load/scaling evidence |

The first attempt could not open a database in the sandbox's OS temporary directory and failed before any substantive experiment. The fixture was moved into a validated audit-local temporary directory and explicit connection cleanup added; the subsequent run exited successfully. No failed run is counted as passing. Temporary databases from the successful run were cleaned up. Source and raw JSON remain reproducible in this folder.

### 9.2 Pending architecture experiments

These experiments are **not executed**. Acceptance numbers are proposed engineering gates, not published standards. Each negative control should fail for the intended reason before the corrected implementation is trusted. T01–T36 in D3 remain the adversarial case catalog.

| ID / hypothesis | Minimal setup and procedure | Acceptance / failure criteria | Decision affected |
|---|---|---|---|
| P01 useful intelligence | 20 development tasks, then 60 family-separated held-out tasks; compare fixed single SAM, repair, delegation, learned version; three runs/task/configuration | Proposed ≥80% complete success; report category rates, false-success, abstention, cost and uncertainty. Critical fabricated success fails gate | Scope/model/prompt selection; reject broad intelligence claims without transfer |
| P02 durable execution | Isolated PostgreSQL and two workers; inject crashes before/after claim, effect, receipt and artifact publication; partition/reconnect; compare DB worker with one workflow candidate | No lost acknowledged job, no duplicate committed effect where dedup supported; unknown writes block replay; stale worker rejected. Any silent loss/duplicate fails | DB worker vs LangGraph/Temporal; action protocol independent of engine |
| P03 enforceable authorization | Synthetic files/accounts and isolated VM; malicious documents, redirect/private-address access, changed approval, revoked grant, unauthorized upload and tool requests | All seeded unauthorized operations blocked outside model; no secret in forbidden output; verify actual egress/process boundary | Executor, credential broker, approval model; blocks sensitive access |
| P04 safe takeover | Real browser + desktop stream; queue delayed command, take control, mutate state, disconnect/reconnect and hand back 100 times | Zero commands accepted from stale generation; no overlapping writers; fresh state before resume. Any stale effect fails | noVNC transport plus separate controller contract |
| P05 bounded delegation/cost | Same tasks with 0/1/3 helpers; 100 concurrent admission attempts; cancel root; force child failures and fake usage reconciliation | No new dispatch beyond reserved ceiling; no orphan workers; quality/time benefit at stated cost. No benefit means single-agent stays default | Helper policy, budget ledger, no deeper hierarchy without evidence |
| P06 retrieval and parsing | Representative 100-document fixture with versions, tables, scans and ACLs; ≥50 known-answer questions; exact vs approximate search | Proposed recall@10 ≥90% for labeled evidence; zero ACL leaks; preserve anchors and flag extraction gaps. Compare by document type | pgvector configuration/reranker/parser; no database replacement before tuning |
| P07 voice and channels | Test number and simulated webhooks; 30 scripted calls including interruption, spoofed identity, duplicate events, host outage and call termination | Proposed p95 ordinary-turn audible response ≤2.5 s; interruption clears playback ≤0.5 s; zero sensitive caller leakage; no unintended outbound notification | Media pipeline and country onboarding; failure may favor alternate transport |
| P08 GEPA improvement | Fixed model/tools/grader; separate mutation, selection and untouched test splits; ≤100 initial scored rollouts plus separately capped reflection spend; compare manual revision and simple search | Paired held-out gain with uncertainty, no material category regression, no policy/schema regressions; include optimization cost. Validation-only gain fails | Whether GEPA deserves promotion; extra GA/RL remains deferred |
| P09 provider substitution | Replay sanitized contract fixtures across two authorized providers; tool schemas, errors, cancellation, usage, images and long context | No silent unsupported feature or unapproved fallback; normalized usage reconciles against provider records | Thin adapter vs gateway; provider neutrality is tested, not assumed |
| P10 load/isolation | Synthetic ownership fixtures, growing queue/connections/artifacts; bursts reflecting 10× workload; later multi-tenant test | No cross-owner read/write/cache/stream access; bounded queue and memory; p95 admission <1 s excluding model work is proposed target | Scale-out trigger and account rollout |
| P11 hardware/artifact fidelity | Existing host; 1 then 3 browsers, representative parser and document generation; record RAM/CPU/disk and render outputs | No OOM, stable cancellation, proposed ≥25% RAM headroom, no missing content/formulas in supported formats | Dedicated machine sizing, concurrency cap and OS-specific executor |
| P12 restoration/retention | Backup metadata+artifacts+key procedure; restore to clean test host; expire grants; delete test source and query all derived indexes | Restore within agreed RTO/RPO; hashes match; revoked grants stay revoked; documented deletion behavior across active data/backups | Backup architecture and readiness for personal data |

P01's larger comparison is 720 attempts and should follow—not precede—the small development set. Repeat runs of one task are correlated; analyze differences by task family and report uncertainty rather than pretending all attempts are independent. Freeze test data before evaluating; changing prompts based on final-test answers consumes that holdout. Include human rubric checks for open-ended outputs and deterministic checks where available.

## 10. Recommended Architecture

This recommendation follows the preceding investigation; no application implementation or infrastructure redesign was performed.

**Owner/channel → authenticated intake → task contract and durable ledger → primary SAM → authorized tool/executor or scoped helper → evidence/artifact store → verification → targeted repair, approval wait, or delivery.** A separately budgeted GEPA job produces candidate prompt versions; it cannot alter live policy or its evaluator.

For the first prototype, keep API, scheduler code and evaluation logic in one modular application, with separately supervised worker processes and an isolated execution VM. PostgreSQL is the canonical task/approval/action store. Store artifact bytes outside rows and reference them through owned immutable IDs. A small React dashboard exposes actual task/evidence state. Use a fixed strong model baseline; defer learned routing.

When phone/remote access is enabled, add a narrowly scoped public communication edge. Initially it can authenticate requests and proxy to the single task authority, with a static honest fallback when unreachable. It must not acknowledge a queued task without durable admission. Do not create a second independently writable task database merely for availability. If offline admission later becomes required, add a durable inbox and reconciliation protocol under a new ADR, or move canonical control state to a reliable cloud host.

Keep current task work separate from improvement: execution uses released prompts; the optimizer sees authorized sanitized traces and sandbox test tools. GEPA's evolutionary selection is not automatically a cost/latency optimizer. A candidate must pass untouched evaluation, then receive a version and reversible release. A separate GA around GEPA and weight-level RL add complexity without measured benefit today. [GEPA paper](https://arxiv.org/abs/2507.19457), [DSPy GEPA](https://dspy.ai/3.1.1/api/optimizers/GEPA/overview/)

Stabilize these contracts early:

| Contract | Minimum information |
|---|---|
| Task | Owner/workspace, objective, acceptance criteria, deadline, budget, version, status, terminal reason |
| Action | Logical operation ID stable across retries, tool/arguments/content digest, grant version, resource version, intent/dispatch/receipt/unknown state |
| Tool result | Success/failure/unknown, external receipt, evidence IDs, retryability, usage and side-effect classification |
| Worker lease | Task, allowed capabilities, expiry, generation, cancellation state; stale generation denied by executor |
| Evidence/artifact | Owner, source/version/time, location/hash, content type, supported criterion and retention class |
| Model adapter | Supported modalities/tools, request/response mapping, usage, errors, cancellation and explicit provider extension fields |
| Prompt release | Component version, base model/tools/evaluator versions, dataset lineage, scores, approver and rollback target |
| Channel event | Provider event ID, caller identity strength, conversation/task IDs, authenticated envelope and deduplication key |

Do not create a generic plugin platform to implement eight contracts. Typed records and small interfaces are sufficient. Preserve original artifacts and canonical state so adapters and indexes can be replaced without rewriting user history.

## 11. Architecture Decision Records

All ADRs are **recommended/provisional**, not user-approved deployed changes. Class A is stable principle, B reversible implementation, C experiment, D deferred. Confidence refers to suitability under the stated constraints, not production validation.

| ADR / class | Decision and context | Alternatives / accepted trade-offs | Evidence and assumptions / confidence | Invalidation trigger and migration strategy |
|---|---|---|---|---|
| A01 A | One owner-facing SAM; capabilities behind it | Permanent swarm would increase coordination; single persona does not imply one model | D1 and requested UX; high | New multi-owner requirements change provisioning, not task identity; retain stable IDs |
| A02 A | Authorization and budgets outside model | Prompt-only policy simpler but unenforceable | R02/R06, X03–04; high | Policy engine can change behind grant/action contracts; authority must remain external |
| A03 A | One authoritative durable task/action ledger | Dual writable cloud/local state adds reconciliation | R01/R07, X01–02; high | Offline acceptance requirement triggers inbox/replication ADR; migrate with reconciled ledger |
| A04 A | Evidence-linked outcomes and explicit unknown state | Binary model-reported success hides uncertainty | D1/D3; high | New evidence types extend schema; preserve old provenance, never silently upgrade outcomes |
| A05 B | Python/FastAPI modular application with separate workers | TypeScript or services; accept Python runtime/typing discipline | Existing familiarity assumed; medium | Demonstrated team/runtime bottleneck; preserve HTTP/task contracts and migrate module by module |
| A06 B | PostgreSQL canonical metadata; separate artifact bytes | SQLite simpler, distributed DB unnecessary | Concurrency and ownership needs; medium-high | Measured persistence deficiency; export owned records and manifests, dual-read verification before cutover |
| A07 C | Compare DB-backed bounded worker with one persistent workflow candidate | LangGraph/Temporal reduce some custom state work but add semantics/operations | P02 not run; medium-low | Fail crash/cancel/upgrade tests or exceed maintenance budget; keep workflow adapter and drain old version |
| A08 B | Retain React; do not force Next.js↔Vite rewrite | SSR potentially useful later; private dashboard does not establish need | Product requirements; medium | Actual SEO/BFF/server-rendering requirement; keep API and route contracts |
| A09 B | Thin model boundary; fixed strong baseline before routing | Direct lock-in vs gateway complexity; preserve special capabilities | P09 pending, gateway advisory; medium | Several providers need shared auth/quota features; adopt patched gateway behind same contract |
| A10 A/C | Isolated execution is stable; VM/image choice experimental | Containers lower overhead, VMs stronger separation with overhead | Playwright/Docker docs and R03; high principle, medium implementation | P03/P11 failure; replace executor backend without changing task ledger |
| A11 B/C | Playwright structured tools plus desktop fallback | Browser Use/managed browser may speed setup but require own evaluation | Tool coverage and P04/P11; medium | Measured site/task failure; adapter replacement, preserve evidence format |
| A12 A/C | Exclusive resource control; noVNC transport POC | WebRTC/Guacamole add capabilities and operating work | R04; medium transport, high ownership principle | Measured poor interactivity; replace stream, retain control generations |
| A13 B/C | PostgreSQL text/provenance first; pgvector and parser choices measured | Dedicated search/managed parsing add cost but may improve workload | pgvector documented filter behavior; P06 pending; medium | Recall/latency/fidelity gate fails after tuning; rebuild derived index from originals |
| A14 A | Separate owner facts, episodes, source knowledge and candidate lessons | One memory bucket simpler but contaminates authority | D1/D3 and R08/R09; high | New memory types extend records; migrate with provenance and correction history |
| A15 C | Twilio plus one audio path as test candidate | Other carriers/direct SIP/LiveKit; country and latency trade-offs | Media/pricing docs; country assumed; medium-low | Registration, latency or cost failure; preserve channel/task envelope and migrate number carefully |
| A16 C | GEPA bounded offline optimization after baseline | Manual tuning/simple search may suffice; no promised superiority | GEPA research/issues; P08 pending; medium-low | No held-out net benefit or cost excess; retain manual release process and archive candidates |
| A17 D | Defer additional GA, routing RL and weight training | Could improve mature repeated workloads; high evaluation/compute burden | No SAM training/reward data; high confidence to defer | Repeated measured deficiency plus training feasibility; add one optimizer at a time behind frozen eval |
| A18 B | Structured logs and portable telemetry; explicit backup manifests | Large observability stack adds operations | Evidence/cost/recovery requirements; high | Volume/compliance need; export event schema, retain security/data minimization |
| A19 B/C | Local prototype; hybrid edge only for remote channels | Cloud-only may simplify availability but raises cost/data exposure | Host/region measurements absent; medium | Availability/capacity misses; move authoritative host with backup/restore and worker re-registration |
| A20 A/D | Ownership IDs now; multi-tenant rollout later | Building full SaaS now increases scope | One-owner requirement; high | Explicit new-user demand; P10 security/billing gate before onboarding |

Change control: record the concrete deficiency, reproduce it, compare an incremental repair with replacement, measure benefit using the same workload, estimate migration/operating cost, document rollback, and update the ADR. A new release, benchmark headline, or popular framework is not sufficient. Freeze a release's model/prompt/tool/scheduler versions; drain or explicitly migrate in-flight work. Review decisions at milestone boundaries, not on every library announcement.

## 12. Implementation Roadmap

This is a proposed sequence, not authorization to implement in this audit. It retains the full vision while making failure-sensitive dependencies explicit.

| Stage | Deliverable / dependencies | Acceptance gate |
|---|---|---|
| 0: decision baseline | Pick three workloads; approve budgets/data destinations; freeze task/action/evidence contracts | Datasets and failure cases prepared; A07/A10 experiment plans agreed |
| 1: supervised core | One SAM, web intake, isolated tools, durable records, actual artifacts | P01 development cases useful; P02/P03 core boundaries pass before real account actions |
| 2: delegation and repair | Scoped temporary workers, cost reservation, criterion verifier and targeted retries | P05 demonstrates benefit; no orphan tasks/budget reset; false-success cases caught |
| 3: operational personal pilot | Takeover, restart/restore, retention, provider errors and host sizing | P02–04/P09/P11–12 pass; owner can stop, inspect and recover work |
| 4: phone/SMS continuity | One voice path, authenticated channels and unavailable fallback | P07 plus jurisdiction/account eligibility; no unsolicited outreach |
| 5: controlled GEPA | Candidate prompt evolution against fixed grading; versioned release | P08 held-out net benefit and rollback; no runtime self-modification |
| 6: broader capability | Additional apps, persistent employees if requested | Per-integration outcome and access tests; resource retirement and cleanup |
| 7: productization | Multi-account identity, quotas, support and billing | P10 isolation/load plus operational/compliance review |

Stages 4 and 5 may be reordered according to user value once stages 1–3 are reliable. Neither justifies postponing basic provenance, grants, cancellation or cost control. Evaluate before buying dedicated hardware. Avoid treating a polished UI or functioning phone call as evidence that the reasoning system is ready.

## 13. Remaining Unknowns

| Unknown | Recommended resolution | Does it block? |
|---|---|---|
| Actual first three owner tasks and acceptable output | Use the proposed three categories, then collect concrete examples | Blocks final acceptance definition, not isolated prototype |
| Existing hardware capacity/OS-specific needs | P11 on current machine before shopping | Blocks hardware purchase, not audit |
| Workload affordable within confirmed under-$20 ceiling | Use $19 envelope; measure per-task and non-model costs; reduce volume as needed | Blocks unrestricted paid operation; budget preference is now resolved |
| Exact model/provider account and quotas | Verify entitlements, pricing and P09 | Blocks paid live benchmark/provider commitment |
| Workflow engine selection | P02 comparison with upgrade/cancellation cases | Blocks durable-runtime commitment |
| Credential/egress/isolation implementation | P03 real boundary test | Blocks sensitive tools/untrusted execution |
| Voice country, caller/recording policy | Select number jurisdiction; provider and legal review | Blocks live third-party communications rollout |
| Artifact format fidelity | Representative Word/Excel/PDF workflows, P11 | Blocks universal format support claims |
| Retrieval corpus and access patterns | Collect representative lawful test sources; P06 | Blocks search scale promises |
| GEPA benefit and reward reliability | P08 with clean holdout and fixed judge | Blocks automatic promotion, not SAM core |
| Maintenance capacity | Assign patch/backup/evaluation owner and runbook | Blocks production-readiness claim |
| Perplexity comparative quality | Same tasks, access, budgets, date and intervention rules | Blocks superiority/parity claim |
| Exact dependency exposure | Lockfile/image digests and targeted advisories | Blocks security signoff |

No exhaustive retail, regional cloud-price, or legal survey was performed because deployment country, provider accounts and hardware model remain unspecified. The cost model deliberately separates fetched rates from allowances. Some requested reference pages, including Perplexity SPACE and the FCC page, failed direct retrieval; no detailed conclusions rely on their unavailable contents.

## 14. Final Go / Conditional Go / No-Go Assessment

### Skeptical second pass and revisions

I challenged this report from the perspective of an engineer responsible for maintaining it. This was a second pass by the same assistant, not an independent reviewer or separate agent.

| Challenge | Resulting correction |
|---|---|
| “You call a DB worker simple, but are rebuilding a workflow engine.” | A07 remains experimental; compare crash/cancel/upgrade behavior before committing. Do not mandate a homemade scheduler. |
| “The SQLite experiments are not PostgreSQL or real-provider tests.” | Explicitly scoped X01–04 to mechanisms. P02/P05 remain unexecuted gates. |
| “The earlier assessment labeled too many design gaps P0.” | P0 narrowed to critical affected-capability blockers; quality/learning/budget maturity mostly P1. |
| “The cost table could imply a fixed monthly promise.” | Token assumptions, allowances, excluded costs and cap-versus-usage distinction are explicit. |
| “The proposed VM still exposes authenticated account data.” | Browser sessions/egress/clipboard and credential scope remain separate controls; VM is not complete protection. |
| “Hybrid creates a second source of truth.” | Initial edge has no independent task authority; offline admission is a separate future decision. |
| “GEPA can overfit your grader and validation set.” | Separate final holdout and frozen evaluator required; runtime remains version-pinned. |
| “Your original broad benchmark could be expensive before basic functionality works.” | Start with 20 development cases; expand to 720-attempt comparison only after basic gates. |
| “Early UI/framework replacement contradicts minimal churn.” | React framework choice is reversible; retain an already-started choice unless evidence warrants migration. |

**Answer to the central question:** Given what is known, the most defensible choice today is the existing plan's small primary-agent architecture, strengthened with explicit contracts and isolated execution—not a new all-in-one agent framework or unrestricted self-evolving hierarchy. It is defensible as a candidate to validate, not a uniquely proven optimum.

Evidence that could prove this recommendation wrong includes: a workflow framework materially reducing failure/recovery complexity; cloud-only execution costing less overall than hybrid; the chosen Linux environment failing essential apps; helpers consistently worsening cost-adjusted success; semantic search adding no useful recall; GEPA gains disappearing on untouched tasks; or hosted inference failing the owner's data policy. Each has a named experiment and migration seam rather than an unconditional commitment.

**Go:** requirements/contracts, evaluation fixtures, isolated read-only prototype and the proposed experiments. **Conditional Go:** useful connected personal pilot only after its permission, recovery, artifact and budget gates pass. **No-Go today:** production autonomy across arbitrary accounts, guaranteed Perplexity superiority, unbounded recursive learning, unsupervised live prompt/policy mutation, or claims of complete future-proofing.

The purpose of this audit is to make subsequent change evidence-driven. The audit is complete at the document/research/mechanism level; the explicitly listed integration and field tests are required work before production decisions, not hidden assumptions of success.
