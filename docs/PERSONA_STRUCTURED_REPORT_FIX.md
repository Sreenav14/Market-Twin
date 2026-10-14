# Persona Agent report reliability

Verified on 4 October 2026.

## What failed

Two recorded journeys failed at the report boundary. One supplied `satisfied` as
the overall outcome, although that word is valid only for an individual success
criterion. Another supplied malformed JSON. These are MarketTwin runtime/report
failures; they do not establish that the application failed its product goals.
Existing findings correctly distinguish this execution reliability issue and keep
the recorded evidence available.

The previous Persona Agent relied on a prose JSON example without configuring
ADK's `output_schema`. The example also represented alternative values as one
pipe-separated string. Its model output cap was 512 tokens despite the report
containing actions, observations, blockers, criteria, evidence references and a
URL. That cap increases truncation risk. The supplied malformed JSON error alone
does not prove whether truncation or incorrect quoting caused that particular
response; the original full completion is needed to establish that.

## Changes and reasons

- Attach `PersonaAgentReport` as the Persona Agent's ADK output schema. The
  installed ADK 2.5 tool/schema path provides `set_model_response` for supported
  fallback models, serializes structured arguments as JSON, and validates them.
  Browser tools remain bound to the controlled session. See
  [ADK structured output guidance](https://github.com/google/adk-docs/blob/main/docs/agents/llm-agents.md).
- Give concrete valid examples and explicitly separate overall outcomes
  (`passed`, `failed`, `partial`, `inconclusive`) from criterion statuses
  (`satisfied`, `unsatisfied`, `unverified`). Insufficient evidence remains
  inconclusive. Unsupported outcomes are never silently converted to passes.
- Use a bounded 2,048-token Persona output budget and record the same effective
  budget in new runtime snapshots. The selected model and credentials still come
  from the existing environment configuration.
- Keep strict parsing and validation. A model can still ignore instructions or
  exceed its budget; these failures remain visible as runtime failures. This
  change does not replay browser actions, invent missing observations, or claim
  universal reliability across providers.

## Verification and operational behavior

Three regressions exercise the actual ADK runner with a deterministic fake model:
structured submission preserves quotes/newlines, a satisfied criterion stays
distinct from a passed overall outcome, and an invalid overall outcome is
rejected. Malformed free-text JSON is also rejected instead of becoming a pass.
No external model or application browser is called by these tests.

The original run's prompts, results, findings and evidence remain unchanged.
Restart an idle execution worker to load the change, then create a new run to
verify the selected real model. The new Agents page exposes saved prompts and
allows an edited prompt to create a separate rerun draft; starting it remains an
explicit user action.
