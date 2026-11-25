"""Task-trace capture for explore_test case executions (doc 29
section 4, consults C1-C3).

The recorder is observational: it sits beside the step recorder in
execute_test_case and remembers what a later compile needs -- the
spec steps in execution order with their full semantic targets and
input KEYS (never values), the assertions the case evaluated, and
the terminal state. It writes nothing itself; the caller persists
``payload(...)`` as the run's single ``test_case.task_trace`` event.

Consult C1: assertion records carry assertion_id + oracle + status
only -- never expected_value literals (a value oracle's expected
value IS a field value). Full predicates are recovered host-side
from the executed spec by assertion_id. Consult C2: each step
records ``source_page_url`` -- the page the browser was on
immediately BEFORE the action dispatched (tracked from the previous
action's observation, never from the action's own result, which may
describe the destination) -- and the FULL SemanticTarget from the
spec step. Consult C3: locator_strategy is whatever the browser
reported; for fill/select/check it is None today and is recorded
honestly as None.
"""

from typing import Any

from markettwin_shared.feature_plan import TestCaseSpec

from markettwin_execution_orchestrator.workflow.task_spec_store import redact_task_spec


class TaskTraceRecorder:
    """Accumulates one case execution's task trace."""

    def __init__(self, *, case: TestCaseSpec, start_url: str) -> None:
        self._case_id = case.case_id
        self._spec = case.model_dump(mode="json")
        self._start_url = start_url
        self._last_url = start_url
        self._steps: list[dict[str, Any]] = []
        self._assertions: dict[str, dict[str, Any]] = {}
        self._segments: list[dict[str, Any]] = []
        self._terminal: dict[str, Any] | None = None

    def record_step(
        self,
        *,
        action_type: str,
        case_action: Any | None,
        locator_strategy: str | None,
        outcome: str,
    ) -> None:
        """Record one executed action. ``source_page_url`` is the
        URL tracked BEFORE this action dispatched (C2); the tracked
        URL advances only via :meth:`observe_url` after the action
        completes."""
        target = None
        test_value_key = None
        url = None
        approval_gated = False
        if case_action is not None:
            if case_action.target is not None:
                target = case_action.target.model_dump(
                    mode="json", exclude_none=True
                )
            test_value_key = case_action.test_value_key
            url = case_action.url
            # The schema's only approval-gated identity today: a
            # step carrying an action_id executes only through the
            # sensitive-action approval path (consult D3).
            approval_gated = bool(case_action.action_id)
        elif action_type == "navigate":
            url = self._start_url
        self._steps.append(
            {
                "ordinal": len(self._steps),
                "action": action_type,
                "target": target,
                "url": url,
                "test_value_key": test_value_key,
                "locator_strategy": locator_strategy,
                "source_page_url": self._last_url,
                "outcome": outcome,
                "approval_gated": approval_gated,
            }
        )

    def observe_url(self, url: str | None) -> None:
        if url:
            self._last_url = url

    def record_assertion(self, *, assertion_id: str, oracle: str, status: str) -> None:
        """C1: id + oracle + status only. A later evaluation of the
        same assertion replaces the earlier record."""
        self._assertions[assertion_id] = {
            "assertion_id": assertion_id,
            "oracle": oracle,
            "status": status,
        }

    def note_segment(
        self,
        *,
        kind: str,
        from_step: int | None,
        to_step: int | None,
        reason_code: str | None = None,
    ) -> None:
        self._segments.append(
            {
                "kind": kind,
                "from_step": from_step,
                "to_step": to_step,
                "reason_code": reason_code,
            }
        )

    def set_terminal(self, terminal: dict[str, Any]) -> None:
        self._terminal = terminal

    def payload(self, *, case_status: str) -> dict[str, Any]:
        """The persisted trace. ``complete`` is mechanical (consult
        D1's definition of a successful case): the case completed,
        every spec assertion was recorded satisfied, no executed
        step failed, and the terminal state was captured."""
        spec_assertions = (
            self._spec.get("expected") if isinstance(self._spec, dict) else None
        ) or []
        all_satisfied = bool(spec_assertions) and all(
            self._assertions.get(str(entry.get("assertion_id")), {}).get("status")
            == "satisfied"
            for entry in spec_assertions
            if isinstance(entry, dict)
        )
        complete = (
            case_status == "completed"
            and all_satisfied
            and all(step["outcome"] != "failed" for step in self._steps)
            and self._terminal is not None
        )
        return {
            "case_id": self._case_id,
            "spec": redact_task_spec(self._spec),
            "start_url": self._start_url,
            "spec_steps": list(self._steps),
            "assertions": list(self._assertions.values()),
            "segments": list(self._segments),
            "terminal": self._terminal,
            "complete": complete,
        }
