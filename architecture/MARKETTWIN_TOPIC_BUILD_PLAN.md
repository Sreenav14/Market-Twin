# MarketTwin Topic-by-Topic Build Plan

**Rule:** Build one topic at a time in small verified steps. The user runs each step and replies `done` before the next step.

**Critical architecture correction:** ADK remains the owner of each Persona Agent's multi-turn reasoning/tool loop. MarketTwin supervises, constrains, measures, persists, and pauses/resumes that loop; it does not choose normal Persona browser actions.

---

## Topic 1 — Model usage telemetry + effective agent runtime snapshots

### Goal

Know exactly which agent/model invocation consumed tokens and persist the exact runtime configuration shown later in the Agents UI.

### Create/change

- model invocation/usage persistence;
- usage repository;
- capture ADK event `usage_metadata` where available;
- visual verifier usage capture;
- model name/role/attempt/latency/status;
- effective prompt/config snapshot per Meta/Persona/verifier role;
- deterministic YAML rendering of runtime snapshot.

### Done when

A run can answer:

```text
Meta Agent: input/output/cached tokens
Persona p1-m1: input/output/cached tokens
Persona p2-m1: ...
Visual verifier criterion X: ...
```

and each executed agent has a historical prompt/config snapshot.

---

## Topic 2 — Study Contract + explicit assignments

### Goal

Remove unconditional Persona × Mission expansion while preserving required persona coverage.

### Create/change

- `StudyContract` schema;
- study mode;
- budgets/policies placeholders;
- explicit assignment schema;
- Meta Agent prompt/output update;
- plan validation;
- `PlanRepository` persistence of only assigned journeys;
- `journey_planner.py` no longer creates the full Cartesian product.

### Done when

A narrow one-mission study with three required personas creates three Journeys, not nine.

---

## Topic 3 — Canonical observation boundary

### Goal

Separate evidence truth from what is sent to the Persona model.

### Create/change

- canonical observation schema;
- scene/version identity;
- completeness/omission metadata;
- richer semantic collection where needed;
- targeted frame/region retrieval path;
- canonical observation persistence;
- model observation derived separately.

### Important

Do not first add aggressive relevance pruning while the collector still has known positional-cap blind spots.

### Done when

MarketTwin can retain a richer observation as evidence while sending a smaller model view without losing the original observation.

---

## Topic 4 — Agent memory / progress ledger

### Goal

Give the autonomous Persona compact working memory so ADK does not need to carry the raw Journey transcript forever.

### Store/derive

- known facts;
- unresolved criteria;
- directly observed failures;
- blockers;
- important contradictions;
- relevant evidence step IDs;
- recent failed locators/actions;
- current page/scene reference.

### Rule

The ledger supports reasoning. It never prescribes the next ordinary action.

### Done when

A Persona can continue making its own decisions with compact memory after old raw tool messages are masked/compacted.

---

## Topic 5 — Context Compiler + bounded ADK history

### Goal

Reduce per-turn input tokens while preserving agentic behavior.

### Create

```text
context/compiler.py
context/encoding.py
context/history_policy.py
```

### Rollout order

1. reversible compact encoding with size guard;
2. avoid redundant ARIA + semantic representations in the model payload;
3. mask/compact expired historical observations after ledger facts are retained;
4. preserve necessary recent tool-call/result pairs;
5. criterion-aware selection with retrieval/expansion fallback;
6. learned compression only if measured later.

### Done when

Matched Persona runs use materially fewer input tokens without worsening defined quality/evidence gates.

---

## Topic 6 — Journey supervision + budgets while ADK keeps the loop

### Goal

Supervise autonomous ADK Journeys without converting them into scripted model calls.

### Create/change

- Journey/run budget objects;
- wall-time/call/action/token/retry limits;
- provider pacing;
- verification reserve;
- loop/repetition detection;
- graceful budget stop/suspend;
- checkpoint metadata around pauses.

### Supervisor responsibilities

Allowed:

- start/stop/suspend Journey;
- enforce limits;
- reject policy violations;
- manage provider admission;
- request human handoff;
- persist checkpoints.

Not allowed:

- choose ordinary next browser action;
- tell the Persona which product path to take;
- replace Persona reasoning.

### Done when

A Persona is still fully autonomous inside ADK but cannot accidentally consume the entire run budget or retry forever.

---

## Topic 7 — Shared Model Gateway / accounting boundary

### Goal

Make Meta, Persona, and visual model usage attributable and consistently rate-limited/accounted.

### Important

This does not mean replacing ADK with raw model calls. ADK can keep using its model adapter; MarketTwin adds a shared accounting/configuration/admission boundary around provider use where the installed ADK version permits.

### Done when

Provider TPM pressure can be paced and every model role has attributable usage/retry/cost metadata.

---

## Topic 8 — HITL / human assistance

### Existing scaffolding

- `HumanActionRequest`;
- `HumanControlLease`;
- browser `begin_human_control()` / `end_human_control()`;
- capture-disable behavior.

### Build

- durable waiting/suspended state;
- same-browser retention;
- single-owner lease;
- expiry;
- control epoch/browser generation;
- private viewer/gateway;
- API claim/complete/cancel;
- stale input rejection;
- verified resume;
- UI.

### Agentic rule

After resume, ADK Persona sees the new state and decides what to do next.

### Done when

A human can complete login/MFA in the exact Journey browser without secret capture and the autonomous Persona continues afterward.

---

## Topic 9 — Criterion truth / evaluation integration

### Create

Per criterion:

```text
verdict: pending/pass/fail/unresolved
provenance: autonomous/assisted/human_precondition
evidence_completeness: sufficient/partial/missing
linked evidence IDs
```

### Done when

Persona opinion is no longer the final authority and assisted success is distinguishable from autonomous success.

---

## Topic 10 — Agent Transparency UI

### Build

A real `Agents` section.

Show:

- Meta Agent;
- every generated Persona Agent;
- visual verifier role/invocations as appropriate;
- exact effective prompt;
- YAML view;
- template version;
- model;
- enabled tools;
- persona/mission;
- status;
- token usage/cost;
- browser actions/tool calls;
- result;
- evidence.

### Done when

A user can answer “which agents existed, what prompt did each receive, what did each do, and how much did it cost?” from the UI.

---

## Topic 11 — Journey / Evidence / Activity UI

Replace current placeholder pages with real APIs/views for:

- journey list/detail;
- step timeline;
- evidence list/detail;
- activity/run events;
- criterion evidence;
- usage summaries.

---

## Topic 12 — Production execution wiring

Move from manual scripts to the intended production path:

```text
API
→ transactional outbox / Kafka
→ orchestrator worker
→ ADK Persona Journeys
→ evaluation worker
→ report/results
```

Do not add another workflow engine simply to achieve this.

---

## Topic 13 — AWS / CI / recovery / V1 acceptance

Complete:

- minimal-cost AWS deployment;
- worker/browser isolation;
- IAM/storage hardening;
- CI;
- process recovery;
- stale lease/browser handling;
- backup/retention;
- load/rate-limit tests;
- final E2E acceptance.

---

## Topic 14 — Adaptive optimization (post-core V1)

Only after measured baselines:

- model routing;
- more aggressive criterion-aware selection;
- learned compression;
- sophisticated visual trajectory analysis;
- advanced browser perception.

Do not let Topic 14 block V1.
