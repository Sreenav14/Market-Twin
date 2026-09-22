# MarketTwin Agentic Boundaries

**Purpose:** Make it explicit which components are true agents, which are bounded model calls, and which must remain deterministic application code.

---

## 1. Definition used here

A component is **agentic** when the model can repeatedly observe intermediate state, choose from allowed actions/tools, act, inspect the result, and adapt its next decision until it decides the task is complete or blocked.

A component is a **direct model call** when it receives a bounded input and returns one structured answer without autonomously interacting with an external environment.

A component is **deterministic code** when the application owns the logic and no model decision is needed.

Agentic is not automatically better. Use agenticity only where autonomy over a multi-step environment is part of the product value.

---

## 2. Current code audit

| Component | Current implementation | Classification | Target decision |
|---|---|---|---|
| Persona Agent | ADK `LlmAgent` + browser tools + `InMemoryRunner` multi-turn loop | **Truly agentic** | KEEP agentic |
| Browser smoke agent | ADK `LlmAgent` + browser tools | Agentic smoke/test utility | Keep only for smoke/gates, not product architecture |
| Meta Agent | ADK `LlmAgent`, structured planning output, no tools | Bounded planning model wrapped as agent | Keep bounded; no need to force a tool loop |
| Visual verifier | direct LiteLLM multimodal completion | **Direct model call** | KEEP direct and targeted |
| Deterministic evaluator | Python code | Deterministic | KEEP deterministic |
| Report generator | Python code | Deterministic | KEEP deterministic |
| BrowserController | Python/Playwright | Deterministic execution authority | KEEP deterministic |
| Action policy | Python | Deterministic security/policy | KEEP deterministic |
| Evidence recorder/storage | Python + DB/S3 | Deterministic | KEEP deterministic |
| Context compiler (planned) | Python | Deterministic context shaping | Must NOT decide Persona action |
| Agent memory/progress ledger (planned) | Structured app state | Deterministic memory support | Feeds Persona; does not script Persona |
| Run/Journey supervisor (planned) | Python | Deterministic supervision | Enforce bounds; do not choose ordinary Persona actions |
| HITL manager (planned) | Python + UI | Deterministic lifecycle/security | KEEP deterministic |
| Model gateway (planned) | Python | Deterministic accounting/routing | KEEP deterministic |
| Optional future narrative report model | Not implemented | Direct model call if added | Only if measured value |

---

## 3. Persona Agent: the core autonomous actor

Current code is already aligned with the desired product behavior:

```text
ADK Persona Agent
   ↓
browser_get_state
   ↓
Persona reasons
   ↓
chooses browser tool
   ↓
receives result
   ↓
reasons again
   ↓
... until done/blocked
```

This is the MarketTwin differentiator and must not be replaced by a deterministic controller choosing each next action.

The future context/memory work should make the loop cheaper and clearer, not remove it.

---

## 4. Meta Agent: why it does not need the same autonomy

The Meta Agent's environment is not an evolving browser. Its job is to transform:

```text
Study Contract + target context
        ↓
Personas + missions + explicit assignments
```

A single structured planning invocation is acceptable. It can remain an ADK `LlmAgent` for shared framework/telemetry/configuration, but “making it more agentic” would add cost without obvious value unless future planning tools are genuinely needed.

---

## 5. Visual verifier: why it should stay a direct call

The visual verifier answers one narrow question against exact screenshot evidence:

```text
criterion + viewport + optional crop
        ↓
multimodal model
        ↓
satisfied / unsatisfied / unverified
```

Giving it autonomous tools or a multi-turn loop would increase cost and complexity and could weaken evidence provenance. Keep it direct until a concrete failure mode proves otherwise.

---

## 6. What must never become an LLM authority

Do not delegate these to agents:

- target authorization;
- sensitive credential policy;
- browser ownership;
- lease validity;
- evidence ownership/provenance;
- budget enforcement;
- rate-limit admission;
- database invariants;
- stale command rejection;
- whether a secret may be captured;
- artifact access control;
- final factual criterion truth when deterministic evidence can establish it.

Models may suggest; code enforces.

---

## 7. Correct relationship between supervision and agenticity

```text
MarketTwin sets the field and the rules.
Persona chooses how to play within them.
```

The supervisor may say:

```text
Allowed target: example.com
Remaining wall time: 90s
Sensitive fields: human-only
Browser tools: these 10
```

It must not say:

```text
Now click Pricing.
Now scroll 600 px.
Now choose plan A.
```

Those ordinary product decisions remain the Persona's responsibility.

---

## 8. HITL and agenticity

Human assistance is an infrastructure/security interruption, not a replacement Persona.

```text
Persona encounters login
→ policy requires human
→ suspend ADK journey
→ human acts in same browser
→ verify safe resume
→ resume ADK journey
→ Persona observes new page and chooses what to do next
```

The Persona remains autonomous before and after the handoff.

---

## 9. Context compiler and agent memory rule

The compiler may choose **what information to show the Persona**, but not **what decision the Persona should make**.

Good:

```yaml
known_facts:
  - Pricing page opened
unresolved:
  - Whether annual billing terms are understandable
recent_failure:
  - CTA locator changed after navigation
```

Bad:

```yaml
next_action:
  click: annual-plan
```

unless the Study Contract is explicitly a deterministic regression mode with a pre-approved procedure rather than a persona/usability journey.

---

## 10. Future agent creation policy

Before adding any new LLM agent, ask:

1. Does the task require multiple adaptive steps against an evolving environment?
2. Does autonomy materially improve the product outcome?
3. Can deterministic code or one bounded model call do it more safely/cheaply?
4. Can its actions be constrained and audited?
5. Does it preserve evidence truth and persona boundaries?

If the answer to the first two is no, do not create another agent.
