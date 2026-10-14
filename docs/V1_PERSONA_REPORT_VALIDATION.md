# Persona report validation — TASK 02

The final persona JSON is now checked against assigned mission criteria and
persisted steps and artifacts before a journey result is saved. This is a
deterministic consistency check, not independent proof of product behavior.

Each assigned criterion must appear once. Invented or duplicate criteria,
invalid execution references, incomplete actions, missing recorded evidence,
and contradictory criteria or outcomes make the result inconclusive. Step IDs
must be strictly positive integers. Policy-blocked execution remains a test
execution issue.

Original outcome, criterion evidence, and unmet criteria are preserved alongside
the checked result and readable validation notes. Repeated original claims remain
available to the evaluator under Needs Verification, with only valid execution
references linked. They do not become confirmed defects or gain severity through
agreement. Synthetic preferences remain model observations, not measured human
sentiment.

No schema migration, additional model call, or second evaluator was added.
The browser's failed steps are never rewritten by this validation boundary.

Validation: all 218 execution/evaluation tests passed after implementation;
changed validation production modules passed lint and strict type checking.
Regression cases include missing, duplicate, invented and contradictory criteria,
cross-execution and nonexistent IDs, failed and pending actions, missing artifacts,
policy blocks, and retention of repeated original claims after downgrade.
