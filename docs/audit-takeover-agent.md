# Takeover audit evidence — 2026-11-10

Scope: the remaining real-PostgreSQL failure in
`test_claim_is_exclusive_and_generation_fences_stale_input`. Existing workspace
edits were preserved. No production data or configuration was changed.

## Findings and repairs

### T1 — Stale synthetic identity fixture (test defect)

The fixture mocks `DatabaseViewerAuthority.actor()` for its synthetic cookie.
The gateway's combined authorization path, `viewer_gateway.py:227`, now calls
`permitted_session()`, which checks the actual auth session in PostgreSQL and
bypasses that mock. The fixture never created that identity/session. Its initial
1008 rejection was correct production behavior.

Updated `services/control-api/tests/test_human_action_repository.py:927` to supply
synthetic identity at both entry points. The combined fixture still delegates
entitlement to the actual database `permitted()` implementation. User/workspace,
target, execution, browser, generation and lease checks remain real. This check
does not establish real login-session authentication, which remains mocked.

### T2 — Valid reconnect rejected after lease renewal (confirmed behavioral bug)

Fixing T1 exposed the real defect at the existing reconnect scenario: transport
disconnect discarded the gateway's `_attached` entry, although the browser owner
retained its disconnected connection and lease for reconnect. Refreshing a ticket
renewed the gateway lease expiry but skipped the owner renewal. Reattachment then
failed the owner's full lease equality check because the expiry differed.

At `viewer_gateway.py:461`, retain the owner-attachment bookkeeping after transport
detach. Existing renewal now updates the disconnected owner's lease as well.
No actor, lease, generation, origin, entitlement or owner equality check was relaxed.

Reviewed every `_attached` use: registration, renewal, expiry and revocation.
Actual concurrent sockets are guarded separately by `_connected`. Expiry removes
lease/attachment entries before awaiting owner cleanup; revocation removes both.
The retained entry therefore matches the retained owner connection's lifetime.

## Verification

Inspected `docker ps`: disposable container `markettwin-audit-20261109`, loopback
port 55439. Every database run used explicit synthetic settings:
POSTGRES_HOST=127.0.0.1, POSTGRES_PORT=55439, POSTGRES_DB=mt_scope_audit,
POSTGRES_USER=mt_audit, synthetic audit password, MARKETTWIN_TEST_DATABASE=1.

Command for each focused run:

```powershell
.venv\Scripts\python.exe -m pytest services/control-api/tests/test_human_action_repository.py -q
```

| Evidence under `.local/audit-20261108/` | Outcome |
|---|---|
| `takeover-before.log` | Reproduced initial handshake policy rejection: 1 failed, 22.20s |
| `takeover-after.log` | Identity fixture repaired; exposed reconnect rejection: 1 failed, 21.51s |
| `takeover-fixed.log` | Both repairs applied: 1 passed, 25.15s |

Passing regression exercises actual PostgreSQL lease/approval operations and a
real local Chromium browser through local HTTP/WebSocket services. Viewer scenarios:
disconnect, active release, reconnect with input, expired/reclaimed lease, failed
notification and delivery retry. Assertions include strict generation fencing,
same context, verified continuation and late-duplicate notification behavior.

The failed reconnect run left a pending fixture-created wait_for_revoke task when
the assertion aborted. The successful run contains no pending-task warning.

`takeover-fixed.log` SHA256:
`7566DE36701229CE6900BC18944B248F688FB48A3BF283E2808A94A4A0AA76F9`.

`ruff check services/control-api/tests/test_human_action_repository.py` passes.
Ruff over both edited files reports five existing gateway diagnostics: import
order at line 7 and long lines 180/406/412/418. These precede this repair and were
not cosmetically changed. `git diff --check` for both edited files passes.

## Review coverage and limits

- Test helper `_exercise_viewer_release_lifecycle`: reviewed in full. Surrounding
  large repository integration test: partially reviewed, executed in full.
- Gateway authorization, ticket issue/renew/revoke, transport connection and final
  cleanup, all attachment references: reviewed; observer internals partially read.
- Owner attach/detach/renew/require and permission authority implementation:
  targeted review. These files are not claimed fully reviewed.
- Internal bridge is ASGI transport; browser transport is real loopback WebSocket.
  Production identities, deployed TLS/proxy, paid providers and wider device
  acceptance were not tested by this focused check.
- Existing gateway expiry/combined-authority unit tests were inspected but have
  not been rerun in this agent slot. Include relevant viewer tests in final gates.

Heavy runner slot released to browser agent after the focused passing run. The
disposable container remains for other audit integration checks; this agent did
not stop shared audit infrastructure or modify shared checkpoint documents.

## T3 — Revoked login could continue receiving observer pixels (confirmed)

Full source review of viewer authority, service, and gateway found that read-only
observation rechecked user/workspace/target entitlement before and after capture,
but checked the authenticated session cookie only at WebSocket handshake. Revoking
the session alone could leave the stream authorized until its 15-minute grant
expired, unlike control transport's live-session checks.

Added `test_observer_session_revocation.py`: synthetic capture revokes the login
while entitlement remains valid, then returns a private frame. Before the repair,
that frame was transmitted: **1 failed, 5.97s** (`observer-revocation-before.log`).
The test uses provider-free fake capture/transport and is not a deployed or real
identity-system integration.

Repair in `_connect_observer`: re-resolve the cookie at admission and before and
after capture, alongside the unchanged entitlement/generation/expiry checks. A
session revocation observed after capture prevents that frame from leaving. Cleanup
still stops screencast and releases observer bookkeeping. No auth cache introduced.

Command:
`.venv\Scripts\python.exe -m pytest services/execution-orchestrator/tests/test_observer_session_revocation.py services/execution-orchestrator/tests/test_viewer_gateway.py -k 'observer_drops_frame or expiry_prunes or combined_authority' -q -p no:cacheprovider`

Result: **3 passed, 15 deselected in 2.33s**, `observer-revocation-after.log`.
The additional checks add live session lookups; post-fix observer FPS is unmeasured.
Include the observer browser/throughput checks in the relevant final integration
gate. The earlier real takeover pass predates this observer-only repair.

Coverage update: `viewer_authority.py`, `owner_service.py`, and `viewer_gateway.py`
have now been read in full in this agent session (including previously read source
segments). This is semantic source review plus the focused tests listed, not full
behavioral acceptance of every branch. Owner implementation and large repository
integration test remain partially reviewed as described above.

Gateway SHA256 after both production repairs:
`651E962F07BA347151533037E5880D55B92C47C8E27D04998B1BF834041D1673`.
