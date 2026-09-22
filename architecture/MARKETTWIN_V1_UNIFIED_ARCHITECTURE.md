# MarketTwin V1 Unified Architecture

**Date:** 20 September 2026  
**Status:** Working implementation contract for V1  
**Primary correction:** ADK continues to own each Persona Agent's multi-step reasoning/tool loop. MarketTwin supervises the run around that loop; it does not choose the Persona's next browser action.

---

## 1. Product objective

MarketTwin is an evidence-driven synthetic-user testing system. It accepts an authorized target and study brief, creates realistic user perspectives and bounded missions, executes autonomous Persona Journeys in isolated browsers, preserves evidence, evaluates criteria, and returns evidence-linked findings and reports.

V1 optimizes for:

1. genuine persona autonomy;
2. trustworthy evidence and provenance;
3. bounded token/cost usage;
4. safe browser control;
5. human-assisted authentication when needed;
6. transparent agent configuration and behavior;
7. recoverable execution;
8. a clear UI showing what happened, why, and at what cost.

The goal is not the fewest tokens at any cost. It is the lowest measured total cost that still satisfies the study contract, persona fidelity, evidence requirements, and defect-detection quality.

---

## 2. Core architectural rule

MarketTwin owns the **run**. ADK owns each Persona Agent's **Journey reasoning loop**.

```text
MarketTwin Run Supervisor
    ├─ Study Contract
    ├─ assignments
    ├─ authorization/policy
    ├─ budgets/rate limits
    ├─ evidence persistence
    ├─ HITL suspend/resume
    ├─ usage accounting
    └─ evaluation lifecycle
            │
            ▼
       ADK Persona Agent
       ┌──────────────────────────────┐
       │ observe current model view   │
       │ reason as the persona        │
       │ choose an allowed tool       │
       │ inspect the tool result      │
       │ reason again                 │
       │ ...                          │
       │ decide when the mission ends │
       └──────────────────────────────┘
            │
            ▼
      BrowserController
            │
            ▼
          Chromium
```

MarketTwin must **not** become a per-step scripted controller that decides what the Persona should click next.

---

## 3. Technology decisions

Keep:

- React + TypeScript frontend;
- FastAPI / Python backend;
- Google ADK for agent runtime;
- LiteLLM/model adapters;
- Python Playwright browser controller;
- PostgreSQL as durable truth;
- MinIO locally / S3 in production;
- evaluation worker for deterministic and targeted model verification;
- existing outbox/job direction rather than a new workflow platform.

Do not introduce:

- a second browser authority;
- a Node browser controller;
- direct model-to-browser access outside MarketTwin tools;
- a separate LLM “execution controller agent”;
- generic compression models before simpler deterministic reductions are measured.

---

## 4. Three logical planes

### Control / Supervision Plane

Owns:

- Study Contract;
- planning validation and explicit assignments;
- Journey admission/start/stop;
- run/journey budgets;
- provider pacing and retries;
- browser policy;
- HITL requests and leases;
- durable checkpoints around suspend/resume;
- lifecycle state.

It **does not** choose ordinary Persona browser actions.

### Evidence Plane

Owns:

- canonical observations;
- viewport screenshots;
- focused crops;
- accessibility snapshots;
- execution steps;
- logs;
- provenance;
- completeness/omission metadata;
- artifact storage.

Evidence is authoritative and cannot be silently dropped merely to save model tokens.

### Reasoning Plane

Owns:

- Meta Agent planning;
- ADK Persona Agents;
- compact model-facing observations;
- agent memory/progress ledger supplied to the Persona;
- visual verifier;
- optional future model routing.

Reasoning context may be compacted. Evidence may not silently disappear.

---

## 5. Study Contract

Every TestRun starts from an immutable, versioned Study Contract.

The contract records at least:

- study mode;
- study brief;
- required personas;
- missions;
- explicit persona-to-mission assignments;
- literal success criteria;
- target and dependency scope;
- prompt/template versions;
- model policy;
- browser action policy;
- execution budgets;
- verification requirements;
- human-assistance policy;
- contract version/hash.

Supported V1 modes:

| Mode | Purpose | Efficiency boundary |
|---|---|---|
| Functional/regression | Check bounded known behavior | Deterministic helpers/procedures may be reused when contract allows, but current evidence is recollected |
| Persona/usability | Observe realistic behavior | Preserve persona autonomy, discoverability, reading/spatial order, and relevant uncertainty |

The old unconditional Persona × Mission Cartesian expansion is removed. The planner provides explicit assignments validated against the contract.

Example:

```text
3 required personas
1 mission
3 assignments
= 3 autonomous Persona Journeys
```

---

## 6. Agentic boundaries

Not every model call should be an agent.

### Persona Agent — agentic by design

The Persona Agent must remain an ADK `LlmAgent` with browser tools and a multi-turn tool loop.

It owns:

- interpreting the mission from its persona perspective;
- deciding which allowed browser action to take next;
- adapting to intermediate observations;
- natural exploration/recovery;
- deciding when the mission is complete, blocked, or inconclusive;
- producing criterion evidence references and a final structured result.

### Meta Agent — bounded planning reasoning

The Meta Agent may remain an ADK `LlmAgent`, but it is not required to have a browser/tool loop. Its job is a bounded planning transformation from Study Contract + target context to validated personas/missions/assignments.

This is more like structured planning than a long-running autonomous agent, and that is appropriate.

### Visual Verifier — direct model verification

The visual verifier is intentionally a targeted multimodal model call for one criterion and exact image evidence. It should **not** become an autonomous agent unless a measured need appears.

### Deterministic evaluator/reporting — code

Authorization, evidence ownership, criterion bookkeeping, deterministic findings, budgets, rate limits, and the base report should remain code, not agents.

---

## 7. Agent templates, effective prompts, and UI YAML

MarketTwin separates repository templates from historical runtime truth.

### Repository templates

Versioned YAML, e.g.:

```text
config/agents/
    meta_agent.yaml
    persona_agent.yaml
    visual_verifier.yaml
```

Templates contain:

- role/type;
- version;
- model policy/default;
- stable instructions;
- declared tools;
- output schema reference;
- reusable behavior rules.

### Effective runtime snapshot

Before an agent executes, MarketTwin snapshots the exact effective configuration actually used:

```yaml
agent_id: persona-p1-m1
agent_type: persona_browser
template_version: 3
model:
  name: openai/gpt-4o-mini
persona:
  name: Cautious first-time user
mission:
  objective: Understand pricing
  success_criteria:
    - Pricing is discoverable
available_tools:
  - browser_get_state
  - browser_navigate
  - browser_click
  - browser_capture_element
effective_prompt: |
  ...exact runtime prompt...
```

The LLM does not need to generate YAML syntax. MarketTwin renders deterministic YAML from validated structured runtime data.

### Agents UI

For each run, the UI exposes:

```text
Agents
├─ Meta Agent
├─ Persona Agent 1
├─ Persona Agent 2
├─ Persona Agent 3
└─ Visual Verifier invocations / verifier role
```

Per agent show:

- role/type;
- template version;
- exact effective prompt;
- YAML view;
- model;
- tools;
- persona/mission;
- status;
- actions/tool calls;
- usage;
- result;
- linked evidence.

Old runs always show the exact snapshot they used even after templates change.

---

## 8. Browser authority

`BrowserController` remains the sole browser authority.

```text
ADK Persona Agent
      ↓
MarketTwin bounded Python browser tools
      ↓
BrowserController
      ↓
Playwright Python
      ↓
Chromium
```

The Persona may propose/call a browser tool, but BrowserController/policy code decides whether the command is permitted.

Security, authorization, sensitive-field handling, target scope, and browser ownership remain code-enforced.

---

## 9. Canonical observation vs model observation

The current `BrowserObservation` is doing two jobs that should eventually be separated.

### Canonical Observation

The evidence-side representation records what MarketTwin actually observed, with provenance and known gaps. It can include:

- URL/title;
- viewport and scroll metrics;
- semantic controls/elements;
- text blocks/regions where practical;
- geometry/visibility;
- frame identity;
- relevant open-shadow-root content;
- dialogs/alerts;
- errors;
- screenshot/artifact references;
- scene/version identity;
- completeness and omission metadata;
- capture timestamp.

Do not claim it is universally complete when lazy, inaccessible, cross-origin, or unsupported regions exist.

### Model Observation

The Persona receives a compact representation derived from the canonical observation.

The compact view must preserve enough information for the Persona to choose its own next action. It must not reveal evaluator-only answers or hidden navigation shortcuts in persona/usability studies.

---

## 10. Context efficiency without removing agenticity

The cost problem is solved around the ADK loop, not by replacing it.

### Preserve

- Persona autonomy;
- ADK multi-turn tool loop;
- intermediate observations;
- natural decision-making;
- tool-based recovery.

### Reduce

- redundant persona/mission assignments;
- repeated full browser state;
- stale historical observations;
- duplicate ARIA + semantic payloads;
- unnecessary tool-schema verbosity;
- repeated facts already captured in working memory.

### Context Compiler

The compiler answers:

> What does this Persona need to know now to make its own next decision?

It does **not** answer:

> What action should the Persona take next?

Model context should contain approximately:

```text
Pinned persona + mission + literal criteria + policy
Compact progress ledger / agent memory
Current relevant scene
Recent meaningful tool interactions
Known failures/blockers
Budget information if appropriate
```

Full evidence remains outside the active context.

---

## 11. Agent memory / progress ledger

Agent memory is compact working memory for the Persona, not a deterministic script.

Example:

```yaml
progress:
  known_facts:
    - Reached the Software testing page
    - Main heading is semantically present
  unresolved:
    - Visual readability
    - Clipping/overlap
  failed_actions: []
  blockers: []
```

The Persona receives this memory and still decides what to do.

Pinned information that must not be summarized away:

- persona identity;
- mission objective;
- literal success criteria;
- target authorization/policy;
- human-assistance restrictions.

---

## 12. Usage telemetry and model accounting

Before optimizing further, measure actual requests.

Record per model invocation:

- test run;
- agent/role;
- journey/execution when applicable;
- model/provider;
- attempt/retry;
- input tokens;
- cached input tokens;
- output tokens;
- reasoning tokens where available;
- total tokens;
- request size estimate;
- latency;
- provider request/attempt IDs when available;
- status/error;
- known cost or cost-unknown state.

This telemetry feeds both engineering benchmarks and the Agents UI.

---

## 13. Run/Journey supervision and budgets

MarketTwin supervises the autonomous ADK Journey without micromanaging it.

The supervisor may enforce:

- wall-time limit;
- model-call limit;
- input/output token budget;
- browser-action limit;
- retry limit;
- provider pacing;
- loop/repetition guard;
- verification reserve;
- run-wide admission control.

A budget constrains the agent; it does not dictate its actions.

When a hard supervision condition is reached, MarketTwin may stop/suspend the Journey and mark unresolved criteria explicitly.

---

## 14. HITL / human assistance

HITL must preserve the same Journey browser.

```text
ADK Persona Journey
    ↓
reaches authentication boundary
    ↓
MarketTwin policy indicates human assistance required
    ↓
Journey is suspended/checkpointed
browser remains alive
    ↓
waiting_for_human
    ↓
private human control on same browser
    ↓
Done
    ↓
MarketTwin verifies safe resume state
    ↓
ADK Persona Journey resumes
    ↓
Persona observes the new state and decides what to do next
```

MarketTwin does not tell the Persona which downstream action to take after login.

Private takeover rules:

- stop ordinary evidence capture before secrets are entered;
- stop/segment traces;
- grant one authenticated scoped lease;
- reject stale/expired input;
- never store passwords/OTP/MFA/CAPTCHA responses;
- verify safe resume state;
- resume capture only after private control ends.

---

## 15. Visual verification

Keep the current hybrid design:

```text
Semantic/browser evidence first
        ↓
Can criterion be established without pixels?
   yes → no VLM
   no  → explicit visual evidence step
        ↓
viewport + optional same-image crop
        ↓
visual verifier
```

The Persona does not inspect screenshot pixels directly in V1. It explicitly requests visual evidence when a criterion depends on visual properties.

The visual verifier reads actual pixels and returns satisfied/unsatisfied/unverified with exact artifact provenance.

---

## 16. Criterion truth

Persona reports are observations, not the final truth authority.

Every criterion should eventually have independent structured truth:

```text
verdict:
  pending | pass | fail | unresolved

provenance:
  autonomous | assisted | human_precondition

evidence_completeness:
  sufficient | partial | missing

linked evidence IDs
```

Evaluation reads canonical evidence, not merely compressed Persona context.

---

## 17. Reporting

Keep deterministic reporting as the V1 base.

Do not send the entire run transcript to another LLM just to generate a report.

An optional narrative model call may be added later if it creates measured value, but it is not required for report correctness.

---

## 18. Topic-oriented implementation sequence

Build by topic, each in small tested steps:

1. usage telemetry + effective agent runtime snapshots;
2. Study Contract + explicit assignments;
3. canonical observation boundary;
4. agent memory / progress ledger;
5. context compiler and bounded ADK history;
6. Journey supervision + budgets/rate-limit pacing while ADK retains the loop;
7. durable HITL / retained browser + resume;
8. criterion truth/evaluation integration;
9. Agent Transparency UI;
10. Journey/Evidence/Activity UI;
11. production worker/outbox/recovery wiring;
12. AWS/CI/security/final V1 acceptance;
13. adaptive model routing/learned compression only later.

There is no step that migrates Persona next-action control out of ADK.

---

## 19. Acceptance principle

For every optimization, compare matched runs using the same:

- Study Contract;
- assignments;
- target/task;
- model configuration where applicable;
- defect fixtures / labeled expectations.

Measure:

- total tokens;
- peak TPM;
- cost;
- model calls;
- browser actions;
- completion;
- defect recall;
- false passes;
- unsupported findings;
- evidence completeness;
- persona fidelity;
- human assistance/minutes;
- latency.

Optimize one major factor at a time and keep rollback flags until quality is demonstrated.
