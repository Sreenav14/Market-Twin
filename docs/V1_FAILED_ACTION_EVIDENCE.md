# Failed-action evidence — TASK 03

Recoverable browser action failures are committed with their original error first.
The tool then attempts a read-only observation of the same bound session within
five seconds and records its screenshot/accessibility artifacts against that
failed step. It never retries the action or changes its status to completed.

The existing controller still enforces session ownership, target/network policy,
and agent control. Human-controlled or unavailable sessions cannot be captured.
Failed capture returns `evidence_status: unavailable` without substituting a
different step's evidence or replacing the original error. Successful capture
returns the sanitized observation and `evidence_status: captured`.

Evidence upload or database failure rolls back only the evidence transaction;
the earlier committed failed action remains intact. Timeout cancellation also
rolls back so the session can continue safely. Session and policy failures retain
their existing propagation behavior.

Regression coverage checks exact step/session binding, preservation of failure
status and error, unavailable capture, and rollback on upload failure/cancellation.
