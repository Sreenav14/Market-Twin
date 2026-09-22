# MarketTwin LLM Handoff Context

Use this file when starting a new ChatGPT/LLM conversation about MarketTwin.

---

## Project identity

Project: **MarketTwin**  
Repository: `Sreenav14/Market-Twin`  
Authoritative committed branch: `refactor/python-browser-controller`

The user's local tree may be ahead of GitHub. Inspect exact current code before proposing edits.

MarketTwin creates synthetic personas, executes authorized browser Journeys, persists evidence, evaluates criteria, and produces evidence-linked findings/reports.

The user is a solo developer and is learning while building.

---

## Required working style

- Work in very small implementation steps.
- Explain what/why/how simply.
- Give one focused coding task at a time.
- User runs/tests and replies `done` before the next step.
- Prefer forward progress over long detours.
- Do not perform broad refactors unless a measured/observed need requires them.
- Inspect the current repo before exact edits.
- Never ask the user to print secrets.

---

## Core stack

- React + TypeScript
- FastAPI / Python 3.12
- Google ADK
- LiteLLM
- Playwright Python
- PostgreSQL + pgvector
- MinIO local / S3 prod
- Kafka KRaft / outbox direction
- npm + uv

Do not revive a separate Node browser runtime or Playwright MCP inside MarketTwin.

---

## Most important architectural correction

**ADK continues to own each Persona Agent's conversation/tool loop.**

MarketTwin owns the run around it.

```text
MarketTwin Run/Journey Supervisor
    ├─ contract/assignments
    ├─ authorization/policy
    ├─ budgets/rate limits
    ├─ evidence
    ├─ telemetry
    ├─ HITL suspend/resume
    └─ evaluation lifecycle
           │
           ▼
      ADK Persona Agent
      observe → reason → tool → observe → reason → ... → finish
           │
           ▼
      BrowserController
```

Do **not** migrate ordinary next-action decisions out of the Persona Agent into a deterministic execution controller.

The Persona remains genuinely agentic.

---

## Agentic boundaries

### Truly agentic

**Persona Agent**

- ADK `LlmAgent`;
- has bounded browser tools;
- receives intermediate observations;
- autonomously chooses subsequent actions;
- adapts/retries/explores;
- decides when the mission is complete/blocked.

Keep this architecture.

### Bounded planning model

**Meta Agent**

- currently ADK `LlmAgent` with structured output;
- no browser tools;
- produces personas/missions (future: explicit assignments) from the study contract.

It does not need a long-running tool loop merely to be called “agentic.”

### Direct model call

**Visual Verifier**

- direct LiteLLM multimodal call;
- one criterion + exact viewport/crop;
- returns satisfied/unsatisfied/unverified.

Keep it targeted rather than making another autonomous agent.

### Deterministic code

- BrowserController;
- security/action policy;
- evidence storage/provenance;
- budgets;
- rate limiting;
- HITL leases;
- deterministic evaluator;
- base report generator;
- context compiler;
- progress ledger maintenance.

---

## Browser invariant

```text
ADK Persona Agent
        ↓
Journey-bound MarketTwin browser tools
        ↓
BrowserController
        ↓
Playwright Python
        ↓
Chromium
        ↓
Authorized target
```

`BrowserController` is the sole browser authority.

---

## Evidence architecture already built substantially

Important completed/local-ahead work includes:

- fixed 1280×900 viewport;
- viewport screenshots, not default full-page screenshots;
- screenshots after major browser actions;
- visible semantic elements + bounding boxes;
- focused crop derived from the same viewport screenshot;
- ~48px crop padding;
- Persona cannot inspect screenshot pixels;
- evaluation-worker visual verifier reads real pixels;
- visual verification only for explicit visual steps;
- exact criterion evidence step IDs;
- exact viewport/crop lookup by execution + step;
- evidence-linked visual findings;
- secure presigned artifact access.

Do not revert to giant full-page screenshots as normal evidence.

---

## Current token problem

A recent run created 9 Journeys and reached roughly a 200K TPM limit.

Main causes:

- Persona × Mission Cartesian expansion;
- repeated/growing ADK tool/history context;
- large repeated browser observations;
- no model usage telemetry/budgeting.

Fix without removing agenticity:

- explicit assignments;
- richer canonical evidence but smaller model observation;
- progress ledger / agent memory;
- bounded ADK history/compaction;
- context compiler;
- budgets/loop guards;
- provider pacing.

---

## Agent transparency requirement

V1 requires an **Agents** UI.

Repository definitions eventually live in versioned YAML such as:

```text
config/agents/meta_agent.yaml
config/agents/persona_agent.yaml
config/agents/visual_verifier.yaml
```

For every run, persist the **effective runtime snapshot actually used**.

UI must expose:

- exact effective prompt;
- deterministic YAML representation;
- template version;
- model;
- available tools;
- persona/mission;
- actions/tool calls;
- usage;
- result;
- evidence.

Historical runtime truth must not change when repo YAML changes later.

---

## Planned topic order

1. model usage telemetry + runtime agent snapshots;
2. Study Contract + explicit assignments;
3. canonical observation boundary;
4. agent memory/progress ledger;
5. context compiler + bounded ADK history;
6. Journey supervision + budgets while ADK keeps the loop;
7. shared model accounting/rate-limit boundary;
8. HITL durable same-browser suspend/resume;
9. criterion truth/provenance/completeness;
10. Agent Transparency UI;
11. Journey/Evidence/Activity UI;
12. production worker/outbox wiring;
13. AWS/CI/recovery/final acceptance;
14. adaptive optimization later.

There is **no** topic that replaces the ADK Persona loop with a sequence of isolated LLM calls.

---

## HITL direction

Same browser context:

```text
Persona Journey running
→ authentication boundary
→ suspend/checkpoint
→ waiting_for_human
→ private human control
→ verify safe resume
→ resume ADK Persona Journey
```

After resume, the Persona sees the current page and autonomously decides what to do next.

Never capture passwords/OTP/MFA/CAPTCHA responses.

---

## Key existing gaps

- token/model telemetry;
- effective agent runtime snapshots/YAML persistence;
- Study Contract;
- explicit assignments;
- canonical observation persistence;
- progress ledger;
- context compiler/bounded history;
- run/Journey budgets;
- rate-limit supervision;
- durable retained browser host for HITL;
- complete lease/viewer/API/UI lifecycle;
- first-class criterion truth/provenance/completeness;
- Agents UI;
- real Journey/Evidence/Activity pages;
- production worker wiring;
- AWS/CI/recovery.

---

## Rules not to violate

- Keep ADK Persona Agent agentic.
- Keep one Python browser authority.
- Context Compiler chooses information, not Persona actions.
- Progress ledger stores memory, not a scripted next step.
- Deterministic code owns security and budgets.
- Do not blindly rerun expensive runs.
- Never rerun an already-evaluated report without explicit idempotent support.
- Do not add new agent roles merely because an enum exists.
- Use direct model calls where a single bounded judgment is sufficient.
