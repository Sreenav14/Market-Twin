# Model and budget experiments

Prepared 2026-10-14. This is the T09 record for the deep-feature plan in `MKT.md`.

## Result

No measurable winner. The comparison was not executed.

Running it requires paid model calls, repeated fixture runs, and token or price
data from the configured provider. This session did not start those runs, change
model defaults, or raise output budgets. The existing planner and persona budgets
remain 4096 and 2048.

## Protocol to run later

Hold the deep fixture version, manifest, goal, authorization, and case plan fixed.
Change one variable at a time: output budget, per-case time budget, or supported
model. Repeat the core cases three times. Record completed checks, invalid output,
unrecovered errors, elapsed time, and token or price data when the provider
returns it. Leave cost unknown when usage is absent. Adopt a change only when
verified case coverage or defect precision improves without an unacceptable cost
or latency increase.

## Related limit

T10 authorized form, list/filter, and navigation workflows were also not run.
`services/execution-orchestrator/scripts/run_authorized_feature.py` is only an
operator entry point. It is not evidence of generalization beyond the local fixture.
