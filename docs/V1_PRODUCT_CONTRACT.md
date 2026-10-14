# Current V1 product and evidence contract

The active plan is `MKT.md`. `CURRENT_STATE.md` records validated progress;
`SESSION_HANDOFF.md` and `NEXT_SESSION.md` preserve the implementation history.
This document describes current behavior, not a production-readiness claim.

## Agent settings and linked knowledge

Agent Settings groups applications (projects), then tests. Each test shows all
recorded agent roles in creation order. Sequential runtimes show their entire
child tree, including the final structured reporter. Planner/persona edits fork
new drafts; historical snapshots remain immutable. Unknown fields, invalid or
duplicate names, unsupported types, excessive/nested children, non-finite or
out-of-range temperatures, and unregistered tools are rejected. LLM temperature
defaults to 0.05 (range 0–0.2). Models that do not support the requested sampling
setting show requested and effective settings separately. Additional agents reuse
the same controlled browser session and evidence rules; their agreement is not
independent product evidence. Up to three extra LLM children run before the reporter.

Knowledge ingestion accepts files or public HTTP(S) links. Link research reads
the submitted HTML/text page and up to four relevant same-site pages. It stores
source URLs and readable content as the original research source, then reuses the
existing evidence-grounded knowledge/skill generator and draft approval process.
This is a bounded source review, not an exhaustive site audit. Private/reserved
addresses, embedded credentials and nonstandard ports are rejected; connections
pin validated public IPs and preserve TLS identity. Redirects are validated and
response size/time/page counts are bounded. JavaScript-only and authenticated
content may require an exported document. Proposed skills are never auto-approved.

## Browser execution

Google ADK personas use controlled tools backed by the existing Python Playwright
BrowserController. Target/network policy is enforced on actions and navigation.
The existing execution store holds journeys, attempts, ordered steps and artifacts.
Read-only recovery after failed actions preserves the original failure.
No new browser service, history store or production infrastructure is required.
Interactive user takeover for OTP, MFA or CAPTCHA is deferred.

## Evidence and results

- Confirmed product issues require relevant browser evidence belonging to the
  cited run, journey, execution and step. An artifact link alone is not proof.
- Needs Verification retains synthetic observations, repeated claims and
  inconclusive judgments. Repetition is not independent proof, never raises
  severity and never contributes to confirmed totals.
- Execution issues describe failed actions, timeouts and policy limitations.
- Execution completion and evaluation completion are separate states.
- No findings does not establish complete coverage or a defect-free application.
- Exact selected-step evidence is shown; missing evidence is explicit.
- Signed artifact access reuses existing authorization; raw storage locations and
  credentials are not returned by journey read endpoints.
- Journey reads authorize the run and enforce journey ownership. Ordered step
  pages and artifact metadata are bounded; safe summaries exclude entered values
  and raw browser exception text.

## Planning context

The creator chooses an authorized target, goal, depth and optional approved
knowledge. Approved sets are copied into the run configuration. `build_run_request`
forwards that snapshot into planning. Configuration displays selected set names.
This preserves provenance; knowledge describes intent rather than proving behavior.
Creation produces a draft; Start test is explicit.

## User interface

Public `/` explains the product with an interactive illustration labelled as an
example. `/how-it-works` describes setup, execution, categories and limitations.
`/login` opens the existing local workspace identity flow. Workspace read access
continues to use authenticated and authorized APIs. Test navigation focuses on
Summary, Journeys, Findings and Report. Advanced records remain accessible.
Animations are finite, use transform/opacity, and honor reduced-motion settings.

## Release checks

After implementation: backend suites and focused authorization/evidence regression
tests; frontend typecheck, tests and build; desktop/mobile browser interactions,
keyboard navigation and accessibility checks; reproducible local benchmark with
actual database and object-store artifact checks. Preserve fixture checksums and
historical failed runs. Detection recall and false confirmations remain unresolved
until measured release criteria pass. See `V1_BENCHMARK_RESULTS.md`.
