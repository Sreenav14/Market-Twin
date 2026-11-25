"""Deterministic skill outcome checks, shared by verification and consumption."""

from markettwin_shared.feature_plan import TestCaseSpec

from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle


async def check_skill_assertions(
    controller: BrowserController, handle: BrowserSessionHandle, spec: TestCaseSpec,
    *, checkpoint: int | None,
    approved_values: tuple[str, ...] = (), run_mode: str | None = None,
) -> str | None:
    """Return the first unproven assertion's ID; never repair an outcome."""
    for assertion in spec.expected:
        if assertion.after_step_ordinal != checkpoint:
            continue
        _, observation = await controller.read_assertion(
            session_id=handle.session_id,
            execution_id=handle.execution_id,
            journey_id=handle.journey_id,
            assertion=assertion,
            approved_values=approved_values,
            run_mode=run_mode,
        )
        if observation.status != "satisfied":
            return assertion.assertion_id
    return None
