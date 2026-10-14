# SAM V2 architecture documents

**Updated:** October 12, 2026. **Status:** working design; implementation and integration validation pending.

This is the revised architecture package for SAM following the architecture audit and the user's confirmed constraints: **under $20/month recurring operating cost, existing hardware first, Mac mini later**. The hardware purchase is a separate one-time expense. SAM remains a separate project from MarketTwin.

| Document | Purpose |
|---|---|
| [Architecture V2](ARCHITECTURE_V2.md) | Product scope, components, deployment, intelligence, budget and migration |
| [Runtime contracts](RUNTIME_CONTRACTS.md) | Task state, permissions, tool actions, workers, evidence, memory and spending |
| [Build and validation plan](BUILD_AND_VALIDATION_PLAN.md) | Sequential milestones, concrete gates, experiments and change control |

Read the architecture first, then the contracts before implementation. The build plan identifies what must be demonstrated before each capability is enabled.

## Decision status

- **Confirmed:** personal primary SAM; requested helpers and eventual persistent employees; iterative correction and interest in GEPA; under-$20 operating ceiling; later Mac mini purchase.
- **Preserved requirements from the original plan:** web, phone and SMS; real computer; live view and takeover; memory; explicit approvals; no unsolicited outreach or ambient capture.
- **Recommended staging:** prove a local web-based core first. Phone/SMS stay in the full-V1 scope but require a measured affordable integration. This staging does not silently remove them.
- **Proposed engineering limits:** $19 planning envelope, one active root task, at most three authorized helpers, bounded repairs and optimization. They are starting settings, not measured optima.
- **Unresolved:** selected model and paid search source, exact workflow implementation, host capacity, speech pipeline, phone jurisdiction and full-V1 cost feasibility.

V2 is the current working design for subsequent SAM planning. It replaces the previous $100 budget recommendation. It does not turn proposed technologies into validated decisions or authorize purchases, deployment, account changes or implementation.

## Evidence and prior documents

- [Complete architecture audit](../sam-audit/SAM_ARCHITECTURE_AUDIT_2026-10-12.md): source research, risk register, 20 provisional ADRs and 12 integration experiments.
- [Earlier review](../SAM_PLAN_REVIEW_2026-10-11.md): 36 adversarial test cases and GEPA discussion.
- [Actual isolated experiment results](../sam-audit/experiment-results.json): crash/replay and concurrent budget mechanisms only; not SAM runtime evidence.
- [Original master plan](C:/Users/sreen/.codex/attachments/d002d68e-6eea-464a-971a-46a28ce8e1dc/SAM_MASTER_PLAN_V1.md): original requirements and product vision.

The current architecture has not passed end-to-end SAM benchmarks. No Perplexity parity or production-readiness claim is made.
