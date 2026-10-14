# SAM V2 — Runtime and data contracts

**Status:** proposed contracts, not implemented schemas. **Date:** October 12, 2026.

These records define observable behavior. They need not each become a separate service or database table. Durable records must survive process restarts; derived UI state is reconstructed from them.

## 1. Core records

| Record | Required fields or semantics |
|---|---|
| Owner/workspace | Stable IDs; access boundaries on every owned record, artifact and stream |
| Task | ID, owner/workspace, request, objective, acceptance criteria, output formats, task version, deadline, budget, status and terminal reason |
| Subtask | Parent/root IDs, dependencies, assigned worker, input versions, acceptance criteria, attempts and output/evidence IDs |
| Grant | Actor, tools/resources, permitted operation classes, purpose, expiry, version and revocation status |
| Approval | Owner identity strength, task/version, exact normalized action arguments and content digest, target/resource, expiry and consumption state |
| Action | Stable logical operation ID, attempt ID, tool/schema version, inputs, grant/approval references, expected resource version, dispatch state, receipt or unknown result |
| Worker claim | Task, worker ID, generation, expiry, heartbeat, scoped capabilities and cancellation state |
| Tool result | Success/failure/unknown, outputs, evidence, external receipt, error class, retryability and usage |
| Artifact | ID, owner, bytes location, content type, checksum, producing action, publication state and retention class |
| Evidence | Source/artifact, version/date/location, observation time, criterion/claim supported and limitations |
| Usage/reservation | Root task, worker, provider/model/tool, bounded estimated cost, actual usage, currency/rate version and reconciliation status |
| Memory/lesson | Type, source, authority, applicability, owner, confidence/evaluation evidence, version and correction/retention state |
| Release | Prompt/model/tool/workflow versions, dataset lineage, evaluation results and rollback target |
| Channel event | Provider event ID, verified sender metadata, identity strength, channel/conversation/task IDs and deduplication key |

Keep provider-specific response fields where needed; normalizing everything into a lowest-common-denominator chat message can lose tool, image, cancellation or billing semantics. Raw provider payload retention must follow the data policy.

## 2. Independent state machines

| State domain | States | Rules |
|---|---|---|
| Conversation | inactive, connecting, active, ended | Ending it does not cancel approved work |
| Task | queued, running, awaiting_approval, paused, recovering, completed, partial, blocked, failed, canceled | completed requires evidence for mandatory criteria; waiting releases worker capacity |
| Computer control | available, agent_controlled, transferring, human_controlled, disconnected | No overlapping write authority; generation checked at executor |
| Action | prepared, awaiting_approval, ready, dispatching, succeeded, failed, unknown, canceled_before_dispatch | Unknown remote effect is not a safe retry indication |
| Lesson | candidate, evaluating, rejected, released, retired | Only released version selected for new tasks; policy cannot be learned into broader permission |

Task status is not derived solely from conversational wording. A worker's “done” message cannot directly mark the root complete. Reopening work requires an explicit task transition/version; canceled or completed task claims cannot silently dispatch new actions.

## 3. Durable execution protocol

1. Validate request identity and persist task admission before returning an accepted task ID.
2. Claim a runnable unit in a short transaction; assign a generation and expiry.
3. Persist the action intent and root-budget reservation before dispatch.
4. Revalidate current grant, task version, cancellation and resource ownership at the execution boundary.
5. Execute outside database transactions. Do not hold locks during model/browser calls or approval waits.
6. Persist the result/receipt, publish artifacts and reconcile usage.
7. On restart, inspect persisted state. Reconcile dispatching/unknown writes before deciding whether replay is safe.

The same logical operation ID is reused across retries; attempt IDs differ. Receiving services must enforce idempotency when available. A local unique key alone cannot deduplicate an arbitrary remote effect. When the remote service lacks safe deduplication or authoritative status, an ambiguous write blocks automatic replay.

Leases detect abandoned work; **fencing rejects stale workers**. Expiry does not prove the previous worker stopped. Use a generation checked by the controlled executor. External systems that cannot honor fencing require serialized dispatch and explicit reconciliation; do not claim universal exactly-once effects.

Artifact publication uses a staged state: write bytes → verify checksum/readability → mark metadata ready. Recovery identifies pending records and orphan bytes. Completion requires accessible artifacts, not just committed metadata. Backups include a consistent database/artifact manifest.

## 4. Permissions and approval

Treat documents, sites, messages, tool outputs and helper responses as data. They cannot grant permission. Validate ownership and grant version on every invocation, including artifacts, streams, retrieval and background tasks.

Approval is specific to who acts, for which task/version, on which target, with what exact content/arguments, and until when. Changing the recipient, amount, destination, file attachment or relevant resource version invalidates the prior approval. Duplicate approval callbacks must not create duplicate effects.

Reading private material does not authorize uploading it or sending it to any model/provider. Data destination restrictions apply before model calls, searches, browser input and connector calls. Authenticated browser sessions are sensitive capabilities even when raw passwords never reach the prompt.

Revocation prevents new dispatch and terminates active work where possible. The UI must show effects already completed or still uncertain. Owner cancellation cannot guarantee rollback of an in-flight remote write.

## 5. Human takeover

Takeover changes the controller generation, rejects pending stale commands and waits for known in-flight resource writes to finish or enter an explicit uncertain state. Human control is enabled only after the transfer boundary is resolved. Browser, terminal or API writes affecting the same resource must respect its ownership, not just mouse events.

On handback, inspect fresh page/session/file state and reconcile changed inputs before replanning. A disconnected viewer does not automatically make stale agent commands valid. Expiry/recovery behavior must be explicit. Viewing permission and control permission are separate.

## 6. Shared budget admission

At the start of the billing period, reserve known fixed charges and estimated non-model costs. Variable allocations cannot exceed what remains within the under-$20 total constraint. The initial planning envelope is $19, not an amount to spend automatically.

Before a paid call, atomically reserve its bounded estimated maximum. Calculate available funds using actual committed usage plus outstanding reservations. Helpers, verifiers, retries and GEPA all charge the root/monthly ledger; new worker IDs do not reset allowances.

On success/error/cancellation, reconcile actual billable usage. Do not release uncertain charges prematurely. Provider billing delays, currency/taxes and non-token tool charges require headroom. If a reliable upper bound is unavailable, restrict or disable the call until its exposure can be bounded. Static per-call counters alone do not implement a dollar ceiling.

Stopping work means no new paid dispatch, saving partial artifacts and a visible budget reason. No unsolicited alert is implied. The owner sees status in the active session or when checking the dashboard.

## 7. Verification and evidence

For each criterion record: outcome, evidence IDs, check method, evaluator version and limitations. Methods may include deterministic calculation, test execution, file/render inspection, source comparison and human judgment.

Missing evidence gives unverified. Contradictory evidence requires investigation or a clearly reported unresolved conflict. Multiple helpers citing one underlying source do not establish independent corroboration. Final synthesis is checked against original requirements even when each helper passed its own task.

Known invalid outputs are not promoted into trusted memory. Preserve original and corrected versions so a later review can explain why a result changed. An owner preference correction has authority over that preference, not over unrelated factual claims.

## 8. GEPA and release contract

Run mutation feedback on development data, candidate selection on validation data, and promotion on untouched final data. Split related source/task families together. A final test that informs subsequent tuning is no longer untouched.

Freeze the evaluator and policy. Optimize one textual component initially; pin models/tools so results are interpretable. Record optimizer, reflection, evaluation and failed-attempt costs. Paid experiments need an allocation inside the existing monthly envelope.

A candidate release must show reproducible held-out benefit without critical policy or schema regression; inspect per-category performance. If no benefit is demonstrated, retain the previous release. Active tasks keep their pinned release. Promotion, monitoring and rollback are explicit operations, not SAM silently rewriting itself.

## 9. Channel and migration contract

Resolve phone, SMS and web events to a common owner/task model, but preserve identity strength. A phone number alone is not enough for sensitive approvals. Deduplicate inbound provider events. Audio session state is separate from durable task state.

Migration to the later Mac mini transfers data through verified exports/manifests. Re-provision credentials, check dependency and executor compatibility, and test restore before enabling dispatch. Fence the old host, preserve in-flight unknown effects and enable only one authoritative worker/control arrangement after cutover. If validation fails, restore the previous arrangement rather than running two competing copies.
