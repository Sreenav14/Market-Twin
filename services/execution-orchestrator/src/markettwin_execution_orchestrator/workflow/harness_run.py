"""The unified Board engine (Explore & Test): the Lead Agent's driver.

Loads the TestRun, opens the run's Browser Room, builds and works the
Board — the live work-list of every discovered interaction — through
execute_test_case, persists the Board into the snapshot at every item
boundary, parks for a human when a login is needed, and marks the run
completed at Close. Attempt-2 defect proofs re-run in a fresh context
inside the Room's browser. This engine produces the only
verdict-bearing results in the product.
"""

from __future__ import annotations

import statistics
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

from markettwin_database.models import PersonaJourney, RunMission, TestRun
from markettwin_shared.deep_testing import CaseExecutionResult
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.agents.schemas.test_case import (
    FeatureScope,
    PlanBudget,
    TestCaseSpec,
)

from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.persistence import (
    ExecutionRepository,
    PlanRepository,
)
from markettwin_execution_orchestrator.persistence.run_event_repository import (
    RunEventRepository,
)
from markettwin_execution_orchestrator.persistence.run_state_repository import (
    RunStateRepository,
)
from markettwin_execution_orchestrator.browser.auth_session_broker import (
    AuthSessionScope,
)
from markettwin_execution_orchestrator.browser.contracts import (
    BrowserSessionHandle,
)
from markettwin_execution_orchestrator.workflow.case_execution import (
    PersonaJourneyExecutionRequest,
    execute_test_case,
)
from markettwin_execution_orchestrator.workflow.feature_scope import (
    case_journey,
    default_scope,
)
from markettwin_execution_orchestrator.workflow.harness_items import (
    RunSafetyMode,
    case_for_item,
    ingest_page_index,
    safety_of,
    skip_reason,
)
from markettwin_execution_orchestrator.workflow.harness_state import (
    TERMINAL_STATUSES,
    HarnessItem,
    HarnessState,
    ItemStatus,
    canonical_url,
    load_harness_state,
    new_harness_state,
    persist_harness_state,
)
if TYPE_CHECKING:
    from markettwin_execution_orchestrator.workflow.run_executor import (
        MarketTwinRunRequest,
    )

# The fixture page's visible interactive elements and form fields, read from
# tests/fixtures/v1_benchmark/index.html. Stage 1 replaces this hand-written
# signature with the live page index.
FIXTURE_ELEMENTS: tuple[tuple[str, str], ...] = (
    ("link", "Open help guide"),
    ("textbox", "Display name"),
    ("button", "Save display name"),
    ("button", "Continue to next step"),
    ("textbox", "Contact address"),
    ("button", "Check contact address"),
    ("link", "Open billing settings"),
    ("button", "Generate preview"),
    ("link", "Open restricted destination"),
)
FIXTURE_FORM_FIELDS: tuple[str, ...] = ("Display name", "Contact address")

# Case verdict -> agent-execution outcome word, shared by the item
# execution and its attempt-2 proof.
_VERDICT_TO_OUTCOME = {
    "satisfied": "passed",
    "not_satisfied": "failed",
    "unverified": "inconclusive",
}


def _case(
    case_id: str,
    title: str,
    kind: str,
    steps: list[dict[str, object]],
    expected: list[dict[str, object]],
) -> dict[str, object]:
    """One work-list entry: a TestCaseSpec in its JSON (snapshot) shape."""

    return {
        "role_name": _ITEM_TARGETS[case_id],
        "case": {
            "case_id": case_id,
            "feature_key": "selected_feature",
            "title": title,
            "kind": kind,
            "priority": "high",
            "steps": steps,
            "expected": expected,
        },
    }


# Item identity (role, name, occurrence_index) for each fixture case.
_ITEM_TARGETS: dict[str, tuple[str, str, int]] = {
    "guide_navigation": ("link", "Open help guide", 0),
    "working_form": ("button", "Save display name", 0),
    "primary_action": ("button", "Continue to next step", 0),
    "contact_validation": ("button", "Check contact address", 0),
    "billing_navigation": ("link", "Open billing settings", 0),
    "preview_confirmation": ("button", "Generate preview", 0),
    "delivery_state": ("status", "Delivery status", 0),
    "restricted_destination": ("link", "Open restricted destination", 0),
}


def v1_benchmark_work_list(start_url: str) -> tuple[dict[str, object], ...]:
    """Hand-written work-list for tests/fixtures/v1_benchmark/index.html.

    The eight entries mirror the encoding the existing benchmark uses for
    the same fixture: one TestCaseSpec per behaviour (the shape
    contract_case produces from a FrozenJourneyContract), with
    user_approved assertions. The four seeded defects are the scoring
    module's DEFECTS (disabled_primary_button, missing_validation,
    incorrect_navigation, missing_confirmation); the good twin is the
    same page with those four behaviours repaired, served by the
    benchmark harness's FixtureHandler patch in
    scripts/run_contract_fixture_benchmark.py.
    """

    return (
        _case(
            "guide_navigation", "Open help guide", "happy_path",
            [{"action": "click", "target": {"role": "link", "name": "Open help guide"}}],
            [{
                "assertion_id": "guide_heading", "oracle": "visible_text",
                "target": {"role": "heading", "name": "Help guide"},
                "expected_value": "Help guide", "origin": "user_approved",
            }],
        ),
        _case(
            "working_form", "Save display name", "happy_path",
            [
                {"action": "fill", "target": {"label": "Display name"},
                 "test_value_key": "valid_name"},
                {"action": "click", "target": {"role": "button", "name": "Save display name"}},
            ],
            [{
                "assertion_id": "saved_confirmation", "oracle": "visible_text",
                "target": {"text": "Display name saved successfully."},
                "expected_value": "Display name saved successfully.",
                "origin": "user_approved",
            }],
        ),
        _case(
            "primary_action", "Continue to next step", "happy_path",
            [{"action": "click", "target": {"role": "button", "name": "Continue to next step"}}],
            [
                {
                    "assertion_id": "primary_enabled", "oracle": "enabled",
                    "target": {"role": "button", "name": "Continue to next step"},
                    "expected_value": True, "origin": "user_approved",
                    "after_step_ordinal": 0,
                },
                {
                    "assertion_id": "next_step_shown", "oracle": "visible_text",
                    "target": {"text": "Next step"}, "expected_value": "Next step",
                    "origin": "user_approved",
                },
            ],
        ),
        _case(
            "contact_validation", "Check contact address", "negative",
            [{"action": "click", "target": {"role": "button", "name": "Check contact address"}}],
            [{
                "assertion_id": "contact_required", "oracle": "visible_text",
                "target": {"text": "Contact address is required"},
                "expected_value": "Contact address is required",
                "origin": "user_approved",
            }],
        ),
        _case(
            "billing_navigation", "Open billing settings", "happy_path",
            [{"action": "click", "target": {"role": "link", "name": "Open billing settings"}}],
            [{
                "assertion_id": "billing_heading", "oracle": "visible_text",
                "target": {"role": "heading", "name": "Billing settings"},
                "expected_value": "Billing settings", "origin": "user_approved",
            }],
        ),
        _case(
            "preview_confirmation", "Generate preview", "happy_path",
            [{"action": "click", "target": {"role": "button", "name": "Generate preview"}}],
            [{
                "assertion_id": "preview_ready", "oracle": "visible_text",
                "target": {"text": "Preview ready"}, "expected_value": "Preview ready",
                "origin": "user_approved",
            }],
        ),
        _case(
            "delivery_state", "Delivery completion evidence", "exploratory",
            [{"action": "navigate", "url": start_url}],
            [{
                "assertion_id": "delivery_complete", "oracle": "visible_text",
                "target": {"text": "Delivery complete"},
                "expected_value": "Delivery complete", "origin": "user_approved",
            }],
        ),
        _case(
            "restricted_destination", "Open restricted destination", "negative",
            [{"action": "click", "target": {"role": "link", "name": "Open restricted destination"}}],
            [{
                "assertion_id": "restricted_shown", "oracle": "visible_text",
                "target": {"text": "Restricted"}, "expected_value": "Restricted",
                "origin": "user_approved",
            }],
        ),
    )


def _initial_work_list(
    run: TestRun, request: MarketTwinRunRequest
) -> tuple[dict[str, object], ...]:
    """Snapshot-provided list first; the fixture list for fixture runs."""

    provided = run.configuration_snapshot.get("harness_work_list")
    if isinstance(provided, list):
        return tuple(cast(list[dict[str, object]], provided))
    if (
        "v1_benchmark" in request.start_url
        or request.fixture_truth
        or request.synthetic_fixture_approval_enabled
    ):
        return v1_benchmark_work_list(request.start_url)
    return ()


def _result_status(result: CaseExecutionResult) -> ItemStatus:
    """Map one executor result onto the §1.4 item statuses (code decides)."""

    if result.blocker in {"human_takeover_required", "authentication_challenge_blocked"}:
        return "needs_human_login"
    if result.execution_status == "completed" and result.verdict == "satisfied":
        return "worked"
    if result.execution_status == "completed" and result.verdict == "not_satisfied":
        return "broken"
    if result.execution_status == "policy_blocked" or result.blocker == "policy_blocked":
        return "blocked"
    return "could_not_check"


_OUTCOME_BY_VERDICT = {
    "satisfied": "passed",
    "not_satisfied": "failed",
    "unverified": "inconclusive",
}

_CRITERION_STATUS = {
    "satisfied": "satisfied",
    "not_satisfied": "unsatisfied",
    "unverified": "unverified",
}


async def _publish_journey_result(
    *, session: AsyncSession, run_id: UUID, journey_id: UUID,
    execution_id: UUID, result: CaseExecutionResult,
) -> None:
    """Publish the journey.result event evaluation reads for every journey.

    Mirrors deep_run's per-case emission (the same CaseExecutionResult
    contract), with the board's D-1 translation: a budget-exhausted
    execution is a timed_out result. Assertion outcomes become criterion
    evidence so findings link the exact steps that failed.
    """

    status = (
        "timed_out" if result.execution_status == "budget_exhausted"
        else result.execution_status
    )
    await RunEventRepository(session).create(
        test_run_id=run_id,
        event_type="journey.result",
        journey_id=journey_id,
        execution_id=execution_id,
        payload={
            **result.model_dump(mode="json"),
            "mode": "harness_v1",
            "status": status,
            "outcome": (
                _OUTCOME_BY_VERDICT[result.verdict]
                if result.execution_status == "completed" else None
            ),
            "journey_key": result.case_id,
            "summary": (
                f"Case {result.case_id}: {result.verdict}."
                + (f" Blocker: {result.blocker}." if result.blocker else "")
            ),
            "criterion_evidence": [
                {
                    "criterion": assertion.assertion_id,
                    "status": _CRITERION_STATUS[assertion.status],
                    "evidence_step_ids": [assertion.step_id],
                }
                for assertion in result.assertion_results
            ],
        },
    )


async def _publish_skipped_journey_result(
    *, session: AsyncSession, executions: ExecutionRepository,
    run_id: UUID, journey_id: UUID, case_id: str, summary: str,
    runtime_name: str, error_code: str | None = None,
) -> UUID:
    """Account for a journey that will never execute, as skipped.

    Evaluation requires one journey.result per registered journey and
    treats status "skipped" as no finding; the execution record is
    created and finished skipped so the journey's surfaces agree.
    """

    execution_id = uuid4()
    await executions.create_agent_execution(
        execution_id=execution_id, journey_id=journey_id,
        runtime_name=runtime_name,
    )
    await executions.finish_agent_execution(
        execution_id=execution_id, status="skipped", error_code=error_code,
    )
    await RunEventRepository(session).create(
        test_run_id=run_id,
        event_type="journey.result",
        journey_id=journey_id,
        execution_id=execution_id,
        payload={
            "mode": "harness_v1",
            "status": "skipped",
            "outcome": None,
            "journey_key": case_id,
            "summary": summary,
        },
    )
    return execution_id


# The unified result contract (UNIFIED_IMPLEMENTATION_PLAN §3.3): one
# board.item.result event per Board item, published by the engine at
# every item boundary. Evaluation for unified kinds reads ONLY these.
_ASSERTION_KIND_BY_ORACLE = {
    "checked": "outcome",
    "visible": "visible",
    "enabled": "enabled",
    "url": "url",
    "url_path_v1": "url",
    "visible_text": "text",
    "title": "text",
    "value": "outcome",
    "count": "outcome",
}


async def _publish_board_item_result(
    *, session: AsyncSession, run_id: UUID, item: HarnessItem,
    execution_id: UUID | None,
    result: CaseExecutionResult | None = None,
) -> None:
    """Publish the unified board.item.result event for one item."""

    assertions: list[dict[str, object]] = []
    evidence_refs: list[str] = list(item.evidence_refs)
    requirement_refs: list[str] = []
    if result is not None:
        for assertion in result.assertion_results:
            assertions.append({
                "assertion_id": assertion.assertion_id,
                "kind": _ASSERTION_KIND_BY_ORACLE.get(
                    assertion.oracle, "outcome"),
                "status": assertion.status,
                "detail": str(assertion.reason) if assertion.reason else "",
            })
            for artifact_id in assertion.artifact_ids:
                if str(artifact_id) not in evidence_refs:
                    evidence_refs.append(str(artifact_id))
            for ref in assertion.requirement_refs:
                if ref not in requirement_refs:
                    requirement_refs.append(ref)
    await RunEventRepository(session).create(
        test_run_id=run_id,
        event_type="board.item.result",
        journey_id=UUID(str(item.journey_id)) if item.journey_id else None,
        execution_id=execution_id,
        payload={
            "board_version": 2,
            "run_kind": "explore_test",
            "board_item_id": item.item_id,
            "state_id": item.state_id,
            "journey_id": item.journey_id,
            "execution_id": str(execution_id) if execution_id else None,
            "board_status": item.status,
            "blocker": item.blocker,
            "attempts": item.attempts,
            "duration_ms": result.elapsed_ms if result is not None else 0,
            "evidence_refs": evidence_refs,
            "assertions": assertions,
            "requirement_refs": requirement_refs,
            "quotes": [],
            "verdict_rows": [],
            "js_errors": [],
        },
    )


def _item_wall_clock_seconds(state: HarnessState) -> int:
    """Per-item budget: max(30s, 10 × median item time); 240s until measured.

    The median is read from the board itself — every finished item's
    durations_ms in harness_state — so before the first item of a run
    completes there is no median and the Stage 0 cap of 240s governs.
    """

    durations = sorted(
        duration / 1000
        for item in state.ordered_items()
        for duration in item.durations_ms
    )
    if not durations:
        return 240
    return max(30, int(10 * statistics.median(durations)))


def _auth_session_scope(
    request: MarketTwinRunRequest,
) -> AuthSessionScope | None:
    """The reuse scope, built exactly as deep_run.py:295-311 builds it."""

    if request.auth_verification is None:
        return None
    try:
        target_id = UUID(str(request.target_snapshot.get("target_id")))
    except (TypeError, ValueError) as error:
        raise ValueError(
            "A frozen target ID is required for authentication reuse."
        ) from error
    return AuthSessionScope(
        run_id=request.run_id,
        target_id=target_id,
        role=request.auth_verification.role,
        account_reference=request.auth_verification.account_reference,
        origin=request.auth_verification.origin,
    )


def _enforce_item_budget(state: HarnessState) -> int:
    """Cap executable items at the board's item budget (U-P1-03).

    The budget was previously stored on the board but never read.
    Items beyond the budget in board (discovery) order that are still
    pending become not_checked with the reason on the item — counted
    honestly in the coverage denominator, never silently dropped.
    Returns how many items this call newly marked.
    """

    budget = int(state.budget_counters.get("item_budget", 300))
    marked = 0
    for position, item in enumerate(state.ordered_items()):
        if position >= budget and item.status == "pending":
            item.status = "not_checked"
            item.blocker = f"over item budget ({budget})"
            marked += 1
    return marked


async def _register_items(
    *, session: AsyncSession, run_id: UUID, persona_id: UUID,
    first_ordinal: int,
    pairs: list[tuple[HarnessItem, TestCaseSpec]],
) -> None:
    """Create the mission/journey rows for newly appended board items."""

    for offset, (item, case) in enumerate(pairs):
        mission_id, journey_id = uuid4(), uuid4()
        session.add(RunMission(
            id=mission_id, test_run_id=run_id,
            ordinal=first_ordinal + offset,
            title=case.title[:200], objective=case.title,
            success_criteria=[a.assertion_id for a in case.expected],
            priority=case.priority,
        ))
        session.add(PersonaJourney(
            id=journey_id, test_run_id=run_id,
            persona_id=persona_id, mission_id=mission_id,
            ordinal=first_ordinal + offset,
        ))
        item.mission_id, item.journey_id = str(mission_id), str(journey_id)
    await session.flush()


async def _absorb_inventory(
    *, controller: BrowserController, handle: BrowserSessionHandle,
    session: AsyncSession, state: HarnessState, state_url: str,
    scope: FeatureScope, request: MarketTwinRunRequest,
    persona_id: UUID, first_ordinal: int, authenticated: bool,
    cases: dict[str, TestCaseSpec],
) -> int:
    """Index one state into the board; returns the next free ordinal.

    The index is read through every cursor page, then the
    scroll-reveal runs: stepwise scroll (a controller action — the
    CaseAction vocabulary has no scroll) → re-inventory → appended
    items only, until a reveal round adds nothing (max 5 rounds).
    Cases are (re)built for every board item from harness_items, so a
    resumed run rebuilds exactly the cases its board implies.
    """

    seen_entries: set[tuple[int, str, str]] = set()
    collected: list[dict[str, object]] = []

    async def collect() -> int:
        added = 0
        cursor = 0
        while True:
            result = await controller.get_page_index(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id, cursor=cursor,
                authenticated_session=authenticated,
            )
            for entry in result.page_index or ():
                key = (
                    int(entry.get("ordinal", 0) or 0),
                    str(entry.get("role", "")), str(entry.get("name", "")),
                )
                if key not in seen_entries:
                    seen_entries.add(key)
                    collected.append(dict(entry))
                    added += 1
            if result.next_cursor is None:
                return added
            cursor = result.next_cursor

    await collect()
    for _ in range(5):
        await controller.scroll(
            session_id=handle.session_id, direction="down", amount=600,
            execution_id=handle.execution_id, journey_id=handle.journey_id,
        )
        if await collect() == 0:
            break
    new_items = ingest_page_index(state, url=state_url, entries=collected)
    _enforce_item_budget(state)
    for item in state.ordered_items():
        if item.case_id not in cases:
            owner = state.states[item.state_id]
            cases[item.case_id] = case_for_item(
                item=item, state_url=owner.url,
                feature_key=scope.feature_key, start_url=request.start_url,
            )
    pairs = [(item, cases[item.case_id]) for item in new_items]
    await _register_items(
        session=session, run_id=request.run_id, persona_id=persona_id,
        first_ordinal=first_ordinal, pairs=pairs,
    )
    return first_ordinal + len(pairs)


async def execute_harness_run(
    *, request: MarketTwinRunRequest, session: AsyncSession
) -> tuple[CaseExecutionResult, ...]:
    """Drive the work-list once, in order, resuming from the snapshot board."""

    run = await session.get(TestRun, request.run_id)
    if run is None:
        raise ValueError("Harness run does not exist.")
    executions = ExecutionRepository(session)
    states = RunStateRepository(session)
    scope = default_scope(request)
    state = await load_harness_state(session, request.run_id)

    if state is None:
        state = new_harness_state()
        entries = _initial_work_list(run, request)
        inventory_driven = not entries
        page = state.add_state(
            url=request.start_url,
            elements=FIXTURE_ELEMENTS,
            form_fields=FIXTURE_FORM_FIELDS,
        )
        record = await PlanRepository(session).create_auth_bootstrap(
            test_run_id=request.run_id, requires_identity_verification=False,
        )
        state.persona_id = str(record.persona_id)
        # The bootstrap journey is never a unit of work in this mode —
        # discovery runs in the driver's inventory session — but the row
        # is registered, so evaluation is owed its result: skipped.
        await _publish_skipped_journey_result(
            session=session, executions=executions,
            run_id=request.run_id, journey_id=record.journey_id,
            case_id=record.journey_key,
            summary=(
                "Browser discovery is carried by the harness inventory "
                "session; this journey holds persona ownership only."
            ),
            runtime_name="browser_discovery_v1",
        )
        cases: dict[str, TestCaseSpec] = {}
        for ordinal, entry in enumerate(entries, start=1):
            case = TestCaseSpec.model_validate(entry["case"])
            cases[case.case_id] = case
            role, name, occurrence = cast(
                tuple[str, str, int], entry["role_name"]
            )
            item = state.add_item(
                state_id=page.state_id, case_id=case.case_id,
                role=role, name=name, occurrence_index=occurrence,
            )
            mission_id, journey_id = uuid4(), uuid4()
            session.add(RunMission(
                id=mission_id, test_run_id=request.run_id, ordinal=ordinal,
                title=case.title[:200], objective=case.title,
                success_criteria=[a.assertion_id for a in case.expected],
                priority=case.priority,
            ))
            session.add(PersonaJourney(
                id=journey_id, test_run_id=request.run_id,
                persona_id=record.persona_id, mission_id=mission_id,
                ordinal=ordinal,
            ))
            item.mission_id, item.journey_id = str(mission_id), str(journey_id)
        await session.flush()
        await persist_harness_state(
            session, run, state,
            event_type="harness.run.initialised", stage="exploring",
        )
    else:
        provided = _initial_work_list(run, request)
        inventory_driven = not provided
        cases = {
            case.case_id: case
            for case in (
                TestCaseSpec.model_validate(entry["case"])
                for entry in provided
            )
        }
        if inventory_driven:
            for item in state.ordered_items():
                owner = state.states[item.state_id]
                cases[item.case_id] = case_for_item(
                    item=item, state_url=owner.url,
                    feature_key=scope.feature_key, start_url=request.start_url,
                )
        # A worker killed mid-item leaves it "running"; it was never
        # finished, so it returns to pending and is executed exactly once
        # by the resumed dispatch.
        for item in state.ordered_items():
            if item.status == "running":
                item.status = "pending"
        # A run that parked at a login wall resumes after the human
        # login: its parked items become pending again and re-execute
        # in the handed-off session. Any other run's recorded items
        # keep their statuses exactly as they were left.
        if run.status == "awaiting_human":
            run.configuration_snapshot.pop("harness_park", None)
            for item in state.ordered_items():
                if item.status == "needs_human_login":
                    item.status = "pending"
        # A resumed board may hold more pending items than the budget
        # (budget lowered, or the board predates enforcement).
        _enforce_item_budget(state)

    if run.status != "running":
        await states.mark_running(test_run_id=request.run_id)
    await session.commit()

    results: list[CaseExecutionResult] = []
    auth_session_scope = _auth_session_scope(request)
    safety_mode: RunSafetyMode = (
        "standard"
        if run.configuration_snapshot.get("harness_run_mode") == "standard"
        else "read_only"
    )
    async with BrowserController() as controller:
        inv_handle: BrowserSessionHandle | None = None
        inv_authenticated = False
        ordinal = len(state.items) + 1
        # The Room (U-P2): ONE browser session for the whole run. The
        # inventory crawl uses it first; every item execution borrows
        # it (rebind per item); attempt-2 proof runs in a fresh context
        # inside the same Chromium. When a human session was handed off
        # earlier (broker snapshot, in memory only), the Room is
        # created from it, so the login serves the entire run.
        auth_snapshot = None
        if (
            request.runtime_human_assistance
            and request.target_snapshot.get("target_id") is not None
        ):
            try:
                auth_snapshot = controller.take_human_session_snapshot(
                    run_id=request.run_id,
                    target_id=UUID(str(request.target_snapshot["target_id"])),
                    case_id="harness_inventory",
                )
            except Exception:
                auth_snapshot = None
        inv_execution_id, inv_journey_id = uuid4(), uuid4()
        room_handle = await controller.open_room_session(
            run_id=request.run_id,
            execution_id=inv_execution_id, journey_id=inv_journey_id,
            allowed_origins=request.allowed_origins,
            network_policy=request.network_policy,
            fixture_action_rules=request.fixture_action_rules,
            auth_snapshot=auth_snapshot,
            authenticated_session=auth_snapshot is not None,
        )
        inv_handle = room_handle
        inv_authenticated = auth_snapshot is not None
        await executions.create_browser_session(
            browser_session_id=room_handle.session_id,
            execution_id=inv_execution_id,
            test_run_id=request.run_id,
            session_role="room",
        )
        await session.commit()
        async def _crawl_inventory(*, authenticated: bool) -> None:
            nonlocal ordinal
            # Inventory-driven generation: index the start state, then
            # follow read-classified links in the inventory session —
            # each landed state is indexed and appended the same way.
            visited: set[str] = set()
            queue: list[str] = [request.start_url]
            while queue and len(visited) < 20:
                current_url = queue.pop(0)
                if canonical_url(current_url) in visited:
                    continue
                visited.add(canonical_url(current_url))
                await controller.navigate(
                    session_id=inv_handle.session_id, url=current_url,
                )
                ordinal = await _absorb_inventory(
                    controller=controller, handle=inv_handle,
                    session=session, state=state, state_url=current_url,
                    scope=scope, request=request,
                    persona_id=UUID(str(state.persona_id)),
                    first_ordinal=ordinal,
                    authenticated=authenticated, cases=cases,
                )
                for item in list(state.ordered_items()):
                    if item.role != "link" or safety_of(item) != "read":
                        continue
                    try:
                        landed = await controller.click(
                            session_id=inv_handle.session_id, role="link",
                            name=item.name,
                            execution_id=inv_handle.execution_id,
                            journey_id=inv_handle.journey_id,
                        )
                    except Exception:
                        continue
                    if canonical_url(str(landed.observation.url)) not in visited:
                        queue.append(str(landed.observation.url))
                    await controller.navigate(
                        session_id=inv_handle.session_id, url=current_url,
                    )
            run = await session.get(TestRun, request.run_id, populate_existing=True)
            assert run is not None
            await persist_harness_state(
                session, run, state,
                event_type="harness.inventory.absorbed", stage="exploring",
                payload={"states": len(state.states), "items": len(state.items)},
            )
            await session.commit()

        if inventory_driven:
            await _crawl_inventory(authenticated=inv_authenticated)
        while True:
            item = state.next_pending()
            if item is None:
                break
            if item.case_id not in cases:
                owner = state.states[item.state_id]
                cases[item.case_id] = case_for_item(
                    item=item, state_url=owner.url,
                    feature_key=scope.feature_key, start_url=request.start_url,
                )
            case = cases[item.case_id]
            if inventory_driven:
                reason = skip_reason(safety_of(item), safety_mode)
                if reason is not None:
                    # The safety gate: inventoried and reported,
                    # never executed. The item is accounted for.
                    item.status = "not_checked"
                    item.blocker = reason
                    state.budget_counters["items_finished"] += 1
                    skipped_execution_id = await _publish_skipped_journey_result(
                        session=session, executions=executions,
                        run_id=request.run_id,
                        journey_id=UUID(str(item.journey_id)),
                        case_id=case.case_id,
                        summary=f"Check {case.case_id} was {reason}.",
                        runtime_name="harness_v1", error_code=reason,
                    )
                    await _publish_board_item_result(
                        session=session, run_id=request.run_id, item=item,
                        execution_id=skipped_execution_id,
                    )
                    item.locator["board_result_published"] = True
                    run = await session.get(
                        TestRun, request.run_id, populate_existing=True,
                    )
                    assert run is not None
                    await persist_harness_state(
                        session, run, state,
                        event_type="harness.item.finished", stage="testing",
                        journey_id=UUID(str(item.journey_id)),
                        payload={
                            "item_id": item.item_id,
                            "case_id": case.case_id,
                            "status": item.status,
                        },
                    )
                    await session.commit()
                    continue
            journey_id = UUID(str(item.journey_id))
            persona_id = UUID(str(state.persona_id))
            mission_id = UUID(str(item.mission_id))
            item.status = "running"
            item.attempts += 1
            state.budget_counters["items_started"] += 1
            run = await session.get(TestRun, request.run_id, populate_existing=True)
            assert run is not None
            await persist_harness_state(
                session, run, state,
                event_type="harness.item.started", stage="testing",
                journey_id=journey_id,
                payload={"item_id": item.item_id, "case_id": case.case_id},
            )
            await session.commit()
            execution_id = uuid4()
            await executions.create_agent_execution(
                execution_id=execution_id, journey_id=journey_id,
                attempt_number=item.attempts,
                runtime_name="harness_v1",
            )
            await session.commit()
            started = time.monotonic()
            # Borrow the Room for this item (single-writer rebind).
            item_handle = await controller.rebind_session(
                session_id=room_handle.session_id,
                execution_id=execution_id,
                journey_id=journey_id,
            )
            # Keep the Room's database row pointing at the borrowing
            # execution so Watch reads the current item (U-P3-03).
            await executions.rebind_browser_session(
                browser_session_id=room_handle.session_id,
                execution_id=execution_id,
            )
            await session.commit()
            result = await execute_test_case(
                request=PersonaJourneyExecutionRequest(
                    test_run_id=request.run_id,
                    execution_id=execution_id,
                    journey_id=journey_id,
                    persona_id=persona_id,
                    mission_id=mission_id,
                    journey=case_journey(case),
                    start_url=request.start_url,
                    allowed_origins=request.allowed_origins,
                    network_policy=request.network_policy,
                    max_duration_seconds=_item_wall_clock_seconds(state),
                    # Unified runs always offer login handover (U-P4):
                    # when a challenge is met, the item execution waits
                    # with the human driving THIS Room session instead
                    # of failing the item.
                    runtime_human_assistance=True,
                    runtime_target_id=UUID(str(request.target_snapshot["target_id"]))
                        if request.target_snapshot.get("target_id") is not None else None,
                    fixture_action_rules=request.fixture_action_rules,
                ),
                session_handle=item_handle,
                case=case,
                scope=scope,
                budget=PlanBudget(max_steps=32),
                controller=controller,
                session=session,
                auth_verification=request.auth_verification,
                auth_mode=request.auth_mode,
                auth_session_scope=auth_session_scope,
                reuse_auth_session=bool(results) or (
                    request.auth_verification is not None and request.feature_plan is None
                    and not request.synthetic_fixture_approval_enabled
                ),
            )
            elapsed_ms = result.elapsed_ms or int((time.monotonic() - started) * 1000)
            await executions.finish_agent_execution(
                execution_id=execution_id,
                status=(
                    "timed_out" if result.execution_status == "budget_exhausted"
                    else result.execution_status
                ),
                outcome=(
                    _VERDICT_TO_OUTCOME[result.verdict]
                    if result.execution_status == "completed"
                    else None
                ),
                error_code=result.blocker,
            )
            item.status = _result_status(result)
            item.blocker = result.blocker
            item.verdict = result.verdict
            item.durations_ms.append(elapsed_ms)
            item.evidence_refs = [str(execution_id)] + [
                str(artifact_id)
                for assertion in result.assertion_results
                for artifact_id in assertion.artifact_ids
            ]
            final_result, final_execution_id = result, execution_id
            # Attempt-2 confirmation (§5 rule 2), for generated checks:
            # a suspected failure is re-executed once. execute_test_case
            # creates a fresh browser context for every call
            # (case_execution.py), so the second call is the
            # fresh-context reproduction. Reproduced → broken stands.
            # Not reproduced → the observed-once tier: harness_state's
            # status set is closed (ITEM_STATUSES), so the tier is a
            # flag on the item — status could_not_check (never counted
            # as a confirmed defect), locator["tier"] = "observed_once",
            # and the full trace of both executions in evidence_refs.
            if item.status == "broken" and "safety_class" in item.locator:
                item.attempts += 1
                state.budget_counters["items_started"] += 1
                confirm_id = uuid4()
                await executions.create_agent_execution(
                    execution_id=confirm_id, journey_id=journey_id,
                    attempt_number=item.attempts,
                    runtime_name="harness_v1",
                )
                await session.commit()
                confirm_started = time.monotonic()
                # Proof runs in a FRESH context inside the Room's
                # browser (U-P2-03): clean state, seeded only with the
                # Room's storage state — never the working session.
                proof_handle = await controller.create_proof_session(
                    room_session_id=room_handle.session_id,
                    execution_id=confirm_id,
                    journey_id=journey_id,
                )
                await executions.create_browser_session(
                    browser_session_id=proof_handle.session_id,
                    execution_id=confirm_id,
                    test_run_id=request.run_id,
                    session_role="proof",
                )
                await session.commit()
                # Proof is an unattended reproduction: unlike the item
                # path it does not force handover — it runs on the
                # Room's seeded storage state and the run's own
                # assistance setting, because a proof that needs a
                # fresh human login is not a reproduction.
                proof_failed = False
                try:
                    confirm = await execute_test_case(
                        request=PersonaJourneyExecutionRequest(
                            test_run_id=request.run_id,
                            execution_id=confirm_id,
                            journey_id=journey_id,
                            persona_id=persona_id,
                            mission_id=mission_id,
                            journey=case_journey(case),
                            start_url=request.start_url,
                            allowed_origins=request.allowed_origins,
                            network_policy=request.network_policy,
                            max_duration_seconds=_item_wall_clock_seconds(state),
                            runtime_human_assistance=request.runtime_human_assistance,
                            runtime_target_id=UUID(str(request.target_snapshot["target_id"]))
                                if request.runtime_human_assistance else None,
                            fixture_action_rules=request.fixture_action_rules,
                        ),
                        case=case,
                        scope=scope,
                        budget=PlanBudget(max_steps=32),
                        controller=controller,
                        session=session,
                        auth_verification=request.auth_verification,
                        auth_mode=request.auth_mode,
                        auth_session_scope=auth_session_scope,
                        reuse_auth_session=True,
                        session_handle=proof_handle,
                    )
                except BaseException:
                    proof_failed = True
                    raise
                finally:
                    # The proof context and its row close even when the
                    # confirmation execution raises; otherwise both
                    # leak until the startup reaper finds them.
                    await controller.close_session(
                        session_id=proof_handle.session_id,
                    )
                    await executions.mark_browser_session_closed(
                        browser_session_id=proof_handle.session_id
                    )
                    if proof_failed:
                        await executions.finish_agent_execution(
                            execution_id=confirm_id, status="failed",
                            outcome=None,
                        )
                    await session.commit()
                confirm_ms = confirm.elapsed_ms or int(
                    (time.monotonic() - confirm_started) * 1000
                )
                await executions.finish_agent_execution(
                    execution_id=confirm_id,
                    status=(
                        "timed_out" if confirm.execution_status == "budget_exhausted"
                        else confirm.execution_status
                    ),
                    outcome=(
                        _VERDICT_TO_OUTCOME[confirm.verdict]
                        if confirm.execution_status == "completed"
                        else None
                    ),
                    error_code=confirm.blocker,
                )
                item.durations_ms.append(confirm_ms)
                state.budget_counters["total_elapsed_ms"] += confirm_ms
                item.evidence_refs = [str(confirm_id)] + item.evidence_refs + [
                    str(artifact_id)
                    for assertion in confirm.assertion_results
                    for artifact_id in assertion.artifact_ids
                ]
                if _result_status(confirm) != "broken":
                    item.status = "could_not_check"
                    item.locator = {**item.locator, "tier": "observed_once"}
                final_result, final_execution_id = confirm, confirm_id
            state.budget_counters["items_finished"] += 1
            state.budget_counters["total_elapsed_ms"] += elapsed_ms
            results.append(result)
            run = await session.get(TestRun, request.run_id, populate_existing=True)
            assert run is not None
            if (
                item.status == "needs_human_login"
                and result.blocker == "authentication_challenge_blocked"
            ):
                # Login wall: the item parks, the run parks, and the
                # remaining items of this state stay pending — deferred
                # behind the wall, not failed. On resume they execute
                # in the handed-off session.
                await persist_harness_state(
                    session, run, state,
                    event_type="harness.item.needs_login", stage="needs_login",
                    journey_id=journey_id, execution_id=execution_id,
                    payload={"item_id": item.item_id, "case_id": case.case_id},
                )
                # Discovery's park pattern: awaiting_human releases the worker.
                run.status = "awaiting_human"
                # Park metadata (U-P4): the deadline the owner sees
                # counting down, extendable up to the 30-minute cap.
                park_seconds = run.configuration_snapshot.get(
                    "harness_park_seconds", 900,
                )
                if not isinstance(park_seconds, int) or isinstance(
                    park_seconds, bool
                ):
                    park_seconds = 900
                park_seconds = max(60, min(1800, park_seconds))
                parked_at = datetime.now(UTC)
                run.configuration_snapshot["harness_park"] = {
                    "parked_at": parked_at.isoformat(),
                    "deadline_at": (
                        parked_at + timedelta(seconds=park_seconds)
                    ).isoformat(),
                    "item_id": item.item_id,
                }
                await session.commit()
                return tuple(results)
            # The item is terminal from here (the login-wall park above
            # returns instead, and its item publishes on resume): publish
            # the result evaluation reads, from the deciding execution.
            await _publish_journey_result(
                session=session, run_id=request.run_id,
                journey_id=journey_id, execution_id=final_execution_id,
                result=final_result,
            )
            if item.status != "needs_human_login":
                # A parked item is not finished: its board result is
                # published when it finally resolves, so each item owns
                # exactly one (terminal) board.item.result.
                await _publish_board_item_result(
                    session=session, run_id=request.run_id, item=item,
                    execution_id=final_execution_id, result=final_result,
                )
                item.locator["board_result_published"] = True
            if item.status == "needs_human_login":
                # An opaque confirmation parks exactly one item; the
                # rest of the list still completes (contrast V10).
                await persist_harness_state(
                    session, run, state,
                    event_type="harness.item.needs_login", stage="testing",
                    journey_id=journey_id, execution_id=execution_id,
                    payload={"item_id": item.item_id, "case_id": case.case_id},
                )
                await session.commit()
                continue
            await persist_harness_state(
                session, run, state,
                event_type="harness.item.finished", stage="testing",
                journey_id=journey_id, execution_id=execution_id,
                payload={
                    "item_id": item.item_id,
                    "case_id": case.case_id,
                    "status": item.status,
                },
            )
            await session.commit()
            if (
                inventory_driven and inv_handle is not None
                and item.role in {"link", "button"}
            ):
                # Generation interleaved with execution: the action
                # may have changed the app state — re-inventory the
                # start state and append whatever is new (fingerprint
                # dedupe makes a repeat index a no-op) before the
                # next pending item is taken. The Room is bound to the
                # item right now; rebind it back to the Room anchor
                # first (single-writer rule).
                inv_handle = await controller.rebind_session(
                    session_id=room_handle.session_id,
                    execution_id=inv_execution_id,
                    journey_id=inv_journey_id,
                )
                await controller.navigate(
                    session_id=inv_handle.session_id, url=request.start_url,
                )
                ordinal = await _absorb_inventory(
                    controller=controller, handle=inv_handle,
                    session=session, state=state, state_url=request.start_url,
                    scope=scope, request=request,
                    persona_id=UUID(str(state.persona_id)),
                    first_ordinal=ordinal,
                    authenticated=inv_authenticated, cases=cases,
                )
            if (
                inventory_driven and inv_handle is not None
                and final_result.human_wait_ms > 0
            ):
                # A human logged in during this item (U-P4): the app
                # behind the wall was never inventoried. Re-crawl in
                # the SAME Room session, now authenticated, so the
                # post-login states and items join the Board instead
                # of staying an unchecked bucket.
                inv_handle = await controller.rebind_session(
                    session_id=room_handle.session_id,
                    execution_id=inv_execution_id,
                    journey_id=inv_journey_id,
                )
                inv_authenticated = True
                await _crawl_inventory(authenticated=True)

    # The run's work is done: close the Room (U-P2). Parked runs return
    # earlier without reaching here — their Room row stays 'open' in
    # the database and the startup reaper (U-P2-04) closes the stale
    # row, since the in-process browser dies with the controller.
    await controller.close_room(run_id=request.run_id)
    await executions.mark_browser_session_closed(
        browser_session_id=room_handle.session_id
    )
    await session.commit()

    # Close sweep (U-P1-04): every terminal Board item must own exactly
    # one board.item.result event. Boundary publishes set the item's
    # board_result_published locator flag in the same commit as the
    # publish, so the flag survives kill/resume; the items this sweep can owe are
    # the ones that became terminal without a boundary publish — the
    # item-budget marks (_enforce_item_budget).
    for item in state.ordered_items():
        if (
            item.status in TERMINAL_STATUSES
            and not item.locator.get("board_result_published")
        ):
            await _publish_board_item_result(
                session=session, run_id=request.run_id, item=item,
                execution_id=None,
            )
            item.locator["board_result_published"] = True

    run = await session.get(TestRun, request.run_id, populate_existing=True)
    assert run is not None
    await persist_harness_state(
        session, run, state,
        event_type="harness.run.evaluating", stage="evaluating",
    )
    await states.mark_completed(test_run_id=request.run_id)
    await persist_harness_state(
        session, run, state,
        event_type="harness.run.completed", stage="done",
    )
    await session.commit()
    return tuple(results)
