# MarketTwin Engineering Playbook for Future LLM Chats

This file defines how an assistant should reason about and modify MarketTwin.

---

## 1. Product principle

MarketTwin is valuable because autonomous Persona Agents behave like different users, not because it can execute a scripted browser checklist.

Preserve Persona autonomy unless the Study Contract explicitly defines a deterministic functional/regression procedure.

---

## 2. Agenticity rule

Use the right abstraction for each task.

### Use a true agent when

- the task is multi-step;
- the environment changes after actions;
- the model must adapt from intermediate observations;
- autonomous behavior is part of the product value.

This applies primarily to Persona Journeys.

### Use a direct model call when

- one bounded input should produce one bounded judgment;
- no external multi-step interaction is needed.

This applies to the current visual verifier.

### Use deterministic code when

- correctness/security must not depend on model discretion;
- the rule is known and testable.

This applies to policy, budgets, leases, evidence provenance, and base reporting.

---

## 3. ADK rule

Do not replace the Persona's ADK multi-turn tool loop with a deterministic controller that chooses each browser action.

Correct:

```text
MarketTwin supervises
      ↓
ADK Persona autonomously observes/reasons/calls tools
```

Incorrect:

```text
MarketTwin decides next action
      ↓
LLM is only called to fill in a step
```

MarketTwin may stop/suspend an agent for budget, policy, HITL, provider, or lifecycle reasons, but normal product-navigation decisions belong to the Persona.

---

## 4. Browser rule

There is one browser authority only.

Do not introduce:

- a second Playwright controller;
- a Node browser service as a competing authority;
- direct model-to-browser access;
- bypasses around `BrowserController` policy.

All browser actions remain bounded MarketTwin tools executed by BrowserController.

---

## 5. Evidence rule

Canonical evidence and model context are different things.

Persist the strongest practical evidence first. Then reduce what is sent to the model.

Never infer pixel properties from semantic state alone.

Visual criteria require screenshot pixels.

The Persona may request visual evidence but does not inspect screenshot pixels directly in V1.

---

## 6. Context compiler rule

The Context Compiler answers:

> What does the Persona need to know to make its own next decision?

It does not answer:

> What should the Persona do next?

Never encode ordinary `next_action` instructions into the progress ledger for persona/usability mode.

---

## 7. Agent memory rule

Agent memory/progress ledger may preserve:

- known facts;
- unresolved criteria;
- failures;
- contradictions;
- blockers;
- important evidence references.

It must not overwrite:

- persona identity;
- mission objective;
- literal criteria;
- target/policy constraints.

It must not become a hidden deterministic plan for the Persona.

---

## 8. LLM authority rule

LLMs cannot:

- authorize a target;
- increase their own budget;
- grant human control;
- bypass browser policy;
- decide that missing evidence is complete merely by assertion;
- authorize secret capture;
- invent evidence IDs;
- override database ownership.

Models propose/interpret. Application code enforces.

---

## 9. Token-efficiency rule

Measure before optimizing.

Capture:

- input tokens;
- cached input tokens;
- output tokens;
- reasoning tokens where available;
- calls;
- browser actions;
- retries;
- latency;
- cost when known;
- peak TPM pressure where available.

Preferred optimization order:

1. remove redundant Journey assignments;
2. eliminate repeated model payloads;
3. compact current-scene representation;
4. add progress ledger;
5. bound/compact old ADK history;
6. criterion-aware context selection;
7. provider/model routing;
8. learned compression only if measured necessary.

Do not “optimize” by removing genuine Persona autonomy.

---

## 10. Prompt/YAML rule

Keep reusable agent templates versioned.

Persist the effective runtime prompt/config for every executed agent.

UI displays historical runtime truth as both readable fields and YAML.

The model does not need to generate YAML syntax itself.

---

## 11. Human assistance rule

Human login/MFA/CAPTCHA uses the exact same Journey browser.

Before private takeover:

- stop new agent actions;
- stop ordinary capture/traces;
- persist handoff state;
- grant one scoped lease.

After Done:

- revoke human input;
- verify safe expected state;
- resume capture;
- resume the ADK Persona Journey;
- let the Persona decide what to do next.

Never capture secret input.

---

## 12. Development discipline

One small step at a time.

For every step:

### Explain

- what changes;
- why it matters;
- how it fits the current topic.

### Modify

- smallest practical set of files.

### Verify

Use focused tests/lint/typecheck.

### Stop

Wait for the user's `done` before continuing.

---

## 13. Repository inspection rule

Before exact edits:

- inspect the authoritative branch;
- inspect relevant current files;
- remember local working tree may be ahead;
- ask for `git status --short` / `git diff --stat` or a push when exact local state matters.

Do not guess file contents.

---

## 14. V1 scope

V1 includes:

- authorized targets;
- Study Contract;
- personas/missions/explicit assignments;
- autonomous ADK Persona Journeys;
- canonical evidence;
- efficient agent context/memory;
- targeted visual verification;
- human-assisted authentication;
- criterion truth/provenance;
- findings/report;
- Agents transparency/YAML/usage UI;
- Journey/Evidence/Activity UI;
- production execution path;
- minimal AWS deployment.

V1 excludes unless newly proven necessary:

- unrestricted crawling;
- CAPTCHA bypass;
- credential storage;
- payment execution;
- unrestricted destructive actions;
- a second browser stack;
- advanced visual perception stacks;
- learned prompt compression;
- extra autonomous agents with no measured need.

---

## 15. New-agent decision test

Before adding any model agent, ask:

1. Does it need an adaptive multi-step loop?
2. Does it interact with an evolving environment?
3. Is autonomy valuable to the product result?
4. Would deterministic code or one direct model call be safer/cheaper?
5. Can its actions be bounded and audited?

If deterministic code or one model call is enough, do not create another agent.
