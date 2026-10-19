# Durable publication and evaluation recovery

Apply migration `a7d8e9201b34` before deploying this worker and the Control API.
It adds retry metadata without deleting, publishing, or completing existing work.

Outbox failures back off from 5 seconds with exponential growth, capped at one
hour; the eighth failure quarantines the retained event. Evaluation failures
back off from 30 seconds, capped at one hour; the fifth failure quarantines the
completed run's evaluation. Only a completed version-1 report marks evaluation
complete. Successful provenance snapshot persistence alone does not.

A publish timeout can mean Kafka accepted the message but its acknowledgement
was lost. Retrying can deliver a duplicate. Consumer deduplication remains
required. Do not mark an event published manually to clear a backlog.

Inspect backlog and quarantine in a trusted database administration session:

```sql
SELECT count(*) AS unpublished, min(created_at) AS oldest_unpublished,
       count(*) FILTER (WHERE quarantined_at IS NOT NULL) AS quarantined
FROM integration.outbox_events WHERE published_at IS NULL;
SELECT id, attempts, next_attempt_at, quarantined_at, last_error
FROM integration.outbox_events WHERE published_at IS NULL ORDER BY id;
SELECT id, evaluation_attempts, evaluation_next_attempt_at,
       evaluation_quarantined_at, evaluation_last_error
FROM testing.test_runs WHERE evaluation_attempts > 0;
```

Diagnostics contain exception class names, rather than transport/model exception
payloads that may include secrets. Diagnose the underlying provider, evidence, or
configuration failure first. After correcting it, recover one selected row by
ID in a transaction; review the affected row and commit only the intended reset:

```sql
BEGIN;
SELECT id, attempts, last_error FROM integration.outbox_events
WHERE id = :event_id AND published_at IS NULL FOR UPDATE;
UPDATE integration.outbox_events
SET attempts = 0, next_attempt_at = NULL, quarantined_at = NULL, last_error = NULL
WHERE id = :event_id AND published_at IS NULL AND quarantined_at IS NOT NULL;
COMMIT;
```

For evaluation recovery, pause the evaluation worker first (including diagnostic
scripts), then reset one retained run and restart the worker:

```sql
BEGIN;
SELECT id, evaluation_attempts, evaluation_last_error FROM testing.test_runs
WHERE id = :test_run_id FOR UPDATE;
UPDATE testing.test_runs
SET evaluation_attempts = 0, evaluation_next_attempt_at = NULL,
    evaluation_quarantined_at = NULL, evaluation_last_error = NULL
WHERE id = :test_run_id AND evaluation_quarantined_at IS NOT NULL;
COMMIT;
```

Bind `:event_id` / `:test_run_id` using the database client's parameter support.
Neither reset replays browser execution. Provenance snapshots are reused by
semantic hash; incomplete reports are completed in place, and findings/report
changes roll back together if final generation fails.
