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

import asyncio
import statistics
import time
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

from markettwin_database.models import AgentExecution, ExecutionStep, PersonaJourney, RunMission, TestRun
from markettwin_database.models.knowledge import (
    MapConflict,
    MapExpectation,
    MapExpectationEvent,
    SkillVersion,
)
from markettwin_shared.deep_testing import CaseExecutionResult
from markettwin_shared.run_failure import failure_site
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from markettwin_execution_orchestrator.agents.schemas.test_case import (
    FeatureScope,
    PlanBudget,
    TestCaseSpec,
)
from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.workflow.offsite_browsing import configure_offsite
from markettwin_execution_orchestrator.workflow.knowledge_loading import open_knowledge_file
from markettwin_execution_orchestrator.workflow.lead_review import review_checkpoint
from markettwin_execution_orchestrator.workflow.map_lookup import (
    find_journey,
    find_page,
    find_skill,
    get_expectations,
    page_elements,
)
from markettwin_execution_orchestrator.browser.auth_session_broker import (
    AuthSessionScope,
)
from markettwin_execution_orchestrator.browser.auth_verifier import is_account_entry_route
from markettwin_execution_orchestrator.browser.contracts import (
    BrowserSessionHandle,
)
from markettwin_execution_orchestrator.browser.errors import (
    BrowserActionError, BrowserDiscoveryEmptyError,
    BrowserDiscoveryCheckpointError, BrowserPolicyError,
    BrowserSessionNotFoundError, HumanAssistanceSkipped,
)
from markettwin_execution_orchestrator.browser.policy import validate_target_url
from markettwin_execution_orchestrator.browser.discovery_checkpoint import is_discovery_checkpoint
from markettwin_execution_orchestrator.persistence import (
    ExecutionRepository,
    PlanRepository,
)
from markettwin_execution_orchestrator.persistence.plan_repository import (
    AUTH_BOOTSTRAP_ORDINAL,
)
from markettwin_execution_orchestrator.persistence.run_event_repository import (
    RunEventRepository,
)
from markettwin_execution_orchestrator.persistence.run_state_repository import (
    RunStateRepository,
)
from markettwin_execution_orchestrator.workflow.case_execution import (
    AuthenticationVerificationBlocked,
    BrowserHandoffExecution,
    PersonaJourneyExecutionRequest,
    execute_skill_replay,
    execute_test_case,
    request_browser_handoff,
)
from markettwin_execution_orchestrator.workflow.cooperative_pause import cooperative_pause_checkpoint
from markettwin_execution_orchestrator.workflow.feature_scope import (
    case_journey,
    default_scope,
)
from markettwin_execution_orchestrator.workflow.harness_items import (
    ACTION_ROLES,
    FIELD_ROLES,
    NOT_EXERCISED_UNAPPROVED_DATA,
    RunSafetyMode,
    case_for_expectation,
    case_for_item,
    case_id_for,
    classify_action,
    execution_allowed,
    expectation_assertion,
    ingest_page_index,
    missing_test_value_keys,
    run_safety_mode,
    safety_of,
    skip_reason,
    structural_reason,
)
from markettwin_execution_orchestrator.workflow.harness_state import (
    TERMINAL_STATUSES,
    HarnessItem,
    HarnessState,
    ItemStatus,
    canonical_url,
    item_id_for,
    load_harness_state,
    new_harness_state,
    persist_harness_state,
    state_id_for,
)
from markettwin_execution_orchestrator.workflow.coverage_delta import (
    build_coverage_delta,
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

# Phase 1a section 10.4: a map-seeded crawl may visit its whole seeded
# frontier plus this many additionally discovered pages, in place of
# the flat 20-page discovery cap. Unmapped runs keep the flat cap.
MAP_CRAWL_DISCOVERY_ALLOWANCE = 25
ITEMS_BETWEEN_INVENTORY_PAGES = 4

# Speed S2 (doc 18 section 11.2): total executor lanes for a harness
# run, the Room included (the Room is lane 0). [J] — acting is
# riskier than observing, so explore_test starts narrower than slop.
HARNESS_LANE_COUNT = 2
# Board item kinds that are sequential-class regardless of safety
# class (doc 18 section 11.4, pin K8): lanes never claim them; the
# absorber executes them on the Room through the ordinary path.
SEQUENTIAL_ITEM_KINDS = frozenset({"skill_replay", "login", "setup"})

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


def _note_expectation(item: HarnessItem, entry: dict[str, object]) -> None:
    """Record an expectation on a board item (doc 21 section 8.3):
    the first id is the citation id; the full stamped entries ride
    the locator so a resumed run rebuilds the same oracles."""
    entries = item.locator.get("expectations")
    entries = list(entries) if isinstance(entries, list) else []
    entries.append(entry)
    item.locator["expectations"] = entries
    if not item.locator.get("expectation_id"):
        item.locator["expectation_id"] = entry.get("id")


def _seed_expectation_items(
    state: HarnessState, cases: dict[str, TestCaseSpec], *,
    app_map: dict, feature_key: str, start_url: str,
    safety_mode: RunSafetyMode,
) -> list[tuple[HarnessItem, TestCaseSpec]]:
    """Seed the map's verdict-eligible expectations onto the Board
    (doc 21 section 8.3), at Board-build time.

    An element expectation whose element already has an inventory
    item on its page attaches to that item as an additional oracle.
    Every other eligible expectation becomes a dedicated Board item
    (item_kind='expectation') with its compiled case. Not seeded, by
    the spec's own rules: ineligible or conflicted records (the
    eligibility stamp already excludes them), statement-only records
    (named 'uncompilable' in the brief), journey_terminal records
    (they ride the skill-replay path), and field_validation records
    outside standard mode (section 5.6).
    """
    entries = app_map.get("expectations")
    if not isinstance(entries, list):
        return []
    seeded: list[tuple[HarnessItem, TestCaseSpec]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("verdict_eligible"):
            continue
        assertion = entry.get("assertion")
        if not isinstance(assertion, dict):
            continue
        kind = assertion.get("kind")
        if kind == "journey_terminal":
            continue
        if kind == "field_validation" and safety_mode != "standard":
            continue
        if expectation_assertion(entry) is None:
            continue
        page_url = entry.get("page_url")
        page_url = page_url if isinstance(page_url, str) and page_url else start_url
        subject = assertion.get("subject")
        subject = subject if isinstance(subject, dict) else {}
        role, name = subject.get("role"), subject.get("name")
        attached: HarnessItem | None = None
        if (
            entry.get("subject_kind") == "element"
            and isinstance(role, str) and isinstance(name, str)
        ):
            for candidate in state.ordered_items():
                owner = state.states.get(candidate.state_id)
                if (
                    owner is not None and owner.url == page_url
                    and candidate.role == role and candidate.name == name
                ):
                    attached = candidate
                    break
        if attached is not None:
            base = cases.get(attached.case_id)
            oracle = expectation_assertion(entry)
            if base is not None and oracle is not None:
                cases[attached.case_id] = base.model_copy(
                    update={"expected": base.expected + (oracle,)}
                )
            _note_expectation(attached, entry)
            continue
        page_state = state.add_state(
            url=page_url,
            elements=[(role, name)] if isinstance(role, str) and isinstance(name, str) else [],
            form_fields=(),
        )
        item_role = (
            role if isinstance(role, str) and role
            else "textbox" if kind == "field_validation" else "page"
        )
        item_name = (
            name if isinstance(name, str) and name
            else str(subject.get("label") or entry.get("statement", ""))[:80]
        )
        item = state.add_item(
            state_id=page_state.state_id,
            case_id=case_id_for(item_id_for(page_state.state_id, item_role, item_name, 0)),
            role=item_role, name=item_name, occurrence_index=0,
        )
        if item.case_id in cases:
            continue
        case = case_for_expectation(
            entry=entry, item=item, state_url=page_url,
            feature_key=feature_key, start_url=start_url,
        )
        cases[item.case_id] = case
        safety = (
            classify_action(role=item_role, name=item_name)
            if kind == "navigation"
            else "reversible" if kind == "field_validation" else "read"
        )
        item.locator = {
            **item.locator,
            "item_kind": "expectation",
            "safety_class": safety,
        }
        _note_expectation(item, entry)
        seeded.append((item, case))
    return seeded
def _seed_skill_items(
    state: HarnessState, *, app_map: dict, replay_items: list,
) -> list[tuple[HarnessItem, TestCaseSpec]]:
    """Seed one skill_replay Board item per planned replay item
    (doc 22 section 8.2). The item carries everything a resumed run
    needs on its locator; the served definition comes from the
    pinned snapshot's skills block, never from a live query. The
    journey's pages keep their ordinary element items — a replay
    item replaces only the journey's per-step path items, which
    this engine never emitted (items are per-element)."""
    entries = {
        str(entry.get("skill_version_id")): entry
        for entry in app_map.get("skills") or []
        if isinstance(entry, dict)
    }
    seeded: list[tuple[HarnessItem, TestCaseSpec]] = []
    for replay in replay_items:
        if not isinstance(replay, dict):
            continue
        entry = entries.get(str(replay.get("skill_version_id")))
        if entry is None:
            continue
        definition = entry.get("definition")
        if not isinstance(definition, dict):
            continue
        journey_name = str(replay.get("journey_name") or entry.get("name") or "")
        terminal_url = replay.get("terminal_url")
        if not isinstance(terminal_url, str) or not terminal_url:
            assertion = definition.get("success_assertion")
            terminal_url = assertion.get("url") if isinstance(assertion, dict) else None
        if not isinstance(terminal_url, str) or not terminal_url:
            key = "skills_not_seeded_missing_terminal_url"
            state.budget_counters[key] = state.budget_counters.get(key, 0) + 1
            continue
        page_state = state.add_state(
            url=terminal_url,
            elements=(), form_fields=(),
        )
        item = state.add_item(
            state_id=page_state.state_id,
            case_id=f"skill_replay:{replay.get('skill_id')}",
            role="page", name=journey_name, occurrence_index=0,
        )
        if item.locator.get("skill_item"):
            continue  # already seeded (idempotent re-entry)
        native = {
            key: definition[key]
            for key in ("case_id", "feature_key", "title", "kind",
                        "steps", "expected")
            if key in definition
        }
        native.setdefault("safety", "non_destructive")
        native.setdefault("estimated_seconds", 60)
        spec = TestCaseSpec.model_validate(native)
        item.locator = {
            **item.locator,
            "item_kind": "skill_replay",
            "skill_item": True,
            "skill_id": replay.get("skill_id"),
            "skill_version_id": replay.get("skill_version_id"),
            "journey_name": journey_name,
            "terminal_url": terminal_url,
        }
        seeded.append((item, spec))
    return seeded




def _result_status(result: CaseExecutionResult) -> ItemStatus:
    """Map one executor result onto the §1.4 item statuses (code decides)."""

    if result.blocker in {"human_takeover_required", "authentication_challenge_blocked"}:
        return "needs_human_login"
    if result.execution_status == "completed" and result.verdict == "satisfied":
        if any(assertion.status == "satisfied" and assertion.oracle not in {"visible", "enabled"}
               for assertion in result.assertion_results):
            return "worked"
        return "could_not_check"
    if result.execution_status == "completed" and result.verdict == "not_satisfied":
        return "broken"
    if result.execution_status == "policy_blocked" or result.blocker == "policy_blocked":
        return "blocked"
    return "could_not_check"
def _item_kind(item: HarnessItem) -> str:
    """The Board item's kind, readable at claim time (pin K8).

    Phase 3 stamps the kind on the item's locator ("item_kind" —
    the locator-stamp precedent Phase 2's expectation wiring set);
    an item carrying none is an ordinary exploration item.
    """

    stamped = item.locator.get("item_kind")
    return stamped if isinstance(stamped, str) and stamped else "exploration"


def _lane_eligible(
    item: HarnessItem, *, safety_mode: RunSafetyMode, inventory_driven: bool,
) -> bool:
    """Whether the absorber may hand this item to a worker lane.

    Kind first (pin K8), then safety class: only read and reversible
    items lane (doc 18 section 11.4; the irreversible class never
    executes in any mode). Inventory items arrive here only after
    the loop's guard has closed the ones this run will not exercise;
    planned items keep today's Room behaviour when the mode gate
    would refuse them, so the gate is consulted for them directly.
    """

    if _item_kind(item) in SEQUENTIAL_ITEM_KINDS:
        return False
    safety = safety_of(item)
    if safety not in {"read", "reversible"}:
        return False
    if not inventory_driven and not execution_allowed(safety, safety_mode):
        return False
    return True


def _new_lane_session(session: AsyncSession) -> AsyncSession:
    """A sibling DB session for one worker lane.

    execute_test_case commits and rolls back on its session
    throughout, so two concurrent executions can never share one
    (R-3). The lane's session rides the same engine; the absorber's
    session stays the Board's only writer.
    """

    return async_sessionmaker(bind=session.bind, expire_on_commit=False)()




_CLICK_ROLES = frozenset({"button", "link", "tab", "menuitem"})


async def _drain_js_baseline(
    controller: BrowserController, session_id: UUID,
    baseline: dict[tuple[str, int | UUID], set[tuple[str, str]]],
    *, lane_key: int | UUID,
) -> None:
    """Fold the session's buffered JS records into the per-route baseline.

    Records that predate an item's action are the route's own history,
    never that item's outcome (research §3.3 baseline rule). A failed
    drain degrades to no evidence, never a failed run.
    """

    if lane_key != 0:
        # A fresh context starts from the route's known history: the
        # Room's crawl baselined what each route throws on its own
        # (lane 0), and a lane or proof context loading the same
        # route throws the same — baselined there too, never the
        # item's outcome. The flow is one-directional: this context's
        # own records fold only into its own key below, so a lane's
        # baseline never speaks for the Room (doc 18 section 11.2).
        for (known_url, key), signatures in list(baseline.items()):
            if key == 0:
                baseline.setdefault((known_url, lane_key), set()).update(
                    signatures)
    try:
        records = await controller.harvest_js_records(session_id=session_id)
        diagnostics = getattr(controller, "js_capture_diagnostics", None)
        if callable(diagnostics) and diagnostics(session_id=session_id).get(
            "last_rejection_harvest_failed"
        ) is True:
            raise RuntimeError("JS baseline harvest unavailable")
    except Exception:
        baseline[("__baseline_unknown__", lane_key)] = set()
        return
    baseline.pop(("__baseline_unknown__", lane_key), None)
    for record in records:
        # One malformed record must not lose the rest of the drain:
        # harvest is a cumulative peek, so a later successful drain can retry.
        try:
            baseline.setdefault((canonical_url(record.url), lane_key), set()).add(
                (record.kind, record.message)
            )
        except Exception:
            continue


async def _observe_item_outcome(
    *, controller: BrowserController, handle: BrowserSessionHandle,
    item: HarnessItem, state_url: str,
    state_elements: frozenset[str], state_form_fields: frozenset[str],
    baseline: dict[tuple[str, int | UUID], set[tuple[str, str]]],
    authenticated: bool, lane_key: int | UUID,
) -> dict[str, object]:
    """The driver's post-action re-observation (Issue 3).

    case_for_item's contract: a click's outcome is proven by the
    driver's re-observation, never by a fabricated assertion. This
    reads the settled page (index + URL, polled until stable) and the
    JS records the action produced, and classifies the outcome:
    navigated / view_changed / js_error / no_effect. Any failure
    returns "unobserved" — the item keeps the verdict its assertions
    earned; observation never breaks a run.
    """

    try:
        seen_entries: set[tuple[int, str, str]] = set()
        collected: list[dict[str, object]] = []

        async def collect() -> str:
            """One index pass (cursor-guarded); returns the current URL."""

            url = state_url
            cursor = 0
            seen_cursors: set[int] = set()
            while cursor not in seen_cursors and len(seen_cursors) <= 200:
                seen_cursors.add(cursor)
                result = await controller.get_page_index(
                    session_id=handle.session_id,
                    execution_id=handle.execution_id,
                    journey_id=handle.journey_id, cursor=cursor,
                    authenticated_session=authenticated,
                )
                url = result.observation.url
                for entry in result.page_index or ():
                    key = (
                        int(entry.get("ordinal", 0) or 0),
                        str(entry.get("role", "")),
                        str(entry.get("name", "")),
                    )
                    if key not in seen_entries:
                        seen_entries.add(key)
                        collected.append(dict(entry))
                if result.next_cursor is None:
                    break
                cursor = result.next_cursor
            return url

        def signatures() -> tuple[frozenset[str], frozenset[str], str]:
            pairs: list[tuple[str, str]] = []
            form_fields: list[str] = []
            for entry in collected:
                role = str(entry.get("role", ""))
                name = str(entry.get("name", ""))[:160]
                if role not in ACTION_ROLES:
                    continue
                pairs.append((role, name))
                if role in FIELD_ROLES and name and name not in form_fields:
                    form_fields.append(name)
            elements = frozenset(f"{role}|{name}" for role, name in pairs)
            form = frozenset(f"field|{label}" for label in form_fields)
            return elements, form, state_id_for(
                observed_url, pairs, form_fields)

        observed_url = state_url
        observed_state_id = item.state_id
        previous: tuple[str, str] | None = None
        for round_index in range(3):
            # A settled state must exclude controls from an earlier render.
            seen_entries.clear()
            collected.clear()
            observed_url = await collect()
            _, _, observed_state_id = signatures()
            current = (canonical_url(observed_url), observed_state_id)
            if current == previous:
                break
            previous = current
            if round_index < 2:
                await asyncio.sleep(0.3)
        new_errors: list[dict[str, object]] = []
        seen_errors: set[tuple[str, str]] = set()
        try:
            window = await controller.harvest_js_records(
                session_id=handle.session_id,
            )
        except Exception:
            window = []
        for record in window:
            if ("__baseline_unknown__", lane_key) in baseline:
                continue
            signature = (record.kind, record.message)
            if signature in baseline.get((canonical_url(record.url), lane_key), set()):
                continue
            if signature in seen_errors:
                continue
            seen_errors.add(signature)
            new_errors.append({
                "kind": record.kind, "message": record.message,
                "stack": record.stack,
            })
        if new_errors:
            outcome = "js_error"
        elif canonical_url(observed_url) != canonical_url(state_url):
            outcome = "navigated"
        elif observed_state_id == item.state_id:
            outcome = "no_effect"
        else:
            elements, form, _ = signatures()
            if elements <= state_elements and form <= state_form_fields:
                # The inventory fingerprint was built with the
                # scroll-reveal; this read has not scrolled yet, so a
                # strict subset may be a reveal artifact rather than
                # an effect. Re-read with the reveal before calling
                # it a change.
                try:
                    for _ in range(5):
                        await controller.scroll(
                            session_id=handle.session_id, direction="down",
                            amount=600, execution_id=handle.execution_id,
                            journey_id=handle.journey_id,
                        )
                        before = len(collected)
                        observed_url = await collect()
                        elements, form, observed_state_id = signatures()
                        if observed_state_id == item.state_id:
                            break
                        if not (elements <= state_elements
                                and form <= state_form_fields):
                            break
                        if len(collected) == before:
                            break
                except Exception:
                    pass
                outcome = (
                    "no_effect" if observed_state_id == item.state_id
                    else "view_changed"
                )
            else:
                outcome = "view_changed"
        return {"outcome": outcome, "js_errors": new_errors,
                "signatures": seen_errors, "observed_url": observed_url,
                "observed_state_id": observed_state_id, "entries": collected}
    except Exception:
        return {"outcome": "unobserved", "js_errors": [],
                "signatures": set(), "observed_url": None}


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
    js_errors: list[dict[str, object]] | None = None,
    test_value_key: str | None = None,
    skill_record: dict[str, object] | None = None,
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
    payload: dict[str, object] = {
        "board_version": 2,
        "run_kind": "explore_test",
        "board_item_id": item.item_id,
        "state_id": item.state_id,
        "journey_id": item.journey_id,
        "execution_id": str(execution_id) if execution_id else None,
        "board_status": item.status,
        "blocker": item.blocker,
        "safety_class": safety_of(item),
        "test_value_key": test_value_key,
        "attempts": item.attempts,
        "duration_ms": result.elapsed_ms if result is not None else 0,
        "evidence_refs": evidence_refs,
        "assertions": assertions,
        "requirement_refs": requirement_refs,
        "quotes": [],
        "verdict_rows": [],
        "js_errors": list(js_errors or []),
    }
    # Section 8.4: a reproduced failure (and every other terminal
    # result) on an expectation item cites the Expectation ID.
    expectation_id = item.locator.get("expectation_id")
    if expectation_id:
        payload["expectation_id"] = str(expectation_id)
    # Doc 22 section 8.3: a skill item's Board result carries the
    # replay provenance record (outcome, ids, per-step, terminal
    # match). It cites no Expectation ID and enters no defect path.
    if skill_record is not None:
        payload["skill_replay"] = skill_record
    await RunEventRepository(session).create(
        test_run_id=run_id,
        event_type="board.item.result",
        journey_id=UUID(str(item.journey_id)) if item.journey_id else None,
        execution_id=execution_id,
        payload=payload,
    )
async def _run_skill_item(
    *, session: AsyncSession, request, state: HarnessState,
    item: HarnessItem, controller, room_handle, executions,
    scope, started_wall: float, entry_override: dict | None = None,
) -> str:
    """Execute one skill_replay Board item (doc 22 sections 8.2-8.4).

    The replay itself (records, demotion/quarantine, usage events)
    is execute_skill_replay's; this wrapper owns the Board side:
    the T-N2 live re-check, the level-2 body_md attach, the item's
    terminal bookkeeping, the section 8.3 Board record, and the
    divergence fallback event."""
    skill_record: dict[str, object] | None = None
    execution_id: UUID | None = None
    outcome_status = "not_checked"
    entry = entry_override if entry_override is not None else next(
        (
            candidate
            for candidate in (request.app_map or {}).get("skills") or []
            if isinstance(candidate, dict)
            and str(candidate.get("skill_version_id"))
            == str(item.locator.get("skill_version_id"))
        ),
        None,
    )
    version = await session.get(
        SkillVersion, UUID(str(item.locator.get("skill_version_id")))
    )
    if entry is None or version is None or version.lifecycle_status != "active":
        # T-N2: a version demoted mid-run (or no longer served) is
        # never re-selected; the item closes unexercised, named.
        item.status = "not_checked"
        item.blocker = (
            "skill version no longer active — not replayed"
            if entry is not None
            else "skill no longer served in the run snapshot"
        )
    else:
        item.status = "running"
        item.attempts += 1
        state.budget_counters["items_started"] += 1
        run = await session.get(TestRun, request.run_id, populate_existing=True)
        assert run is not None
        await persist_harness_state(
            session, run, state,
            event_type="harness.item.started", stage="testing",
            journey_id=UUID(str(item.journey_id)),
            payload={"item_id": item.item_id, "case_id": item.case_id},
        )
        await session.commit()
        execution_id = uuid4()
        await executions.create_agent_execution(
            execution_id=execution_id,
            journey_id=UUID(str(item.journey_id)),
            attempt_number=item.attempts, runtime_name="harness_v1",
        )
        await session.commit()
        item_handle = await controller.rebind_session(
            session_id=room_handle.session_id,
            execution_id=execution_id,
            journey_id=UUID(str(item.journey_id)),
        )
        await executions.rebind_browser_session(
            browser_session_id=room_handle.session_id,
            execution_id=execution_id,
        )
        await session.commit()
        # Section 8.2: attach the version's level-2 body to the item
        # record before executing — the run's evidence shows what
        # the executor was told. Never brief/checkpoint context.
        package = entry.get("package")
        if isinstance(package, dict) and isinstance(package.get("body_md"), str):
            item.locator["skill_body_md"] = package["body_md"]
        definition = entry["definition"]
        native = {
            key: definition[key]
            for key in ("case_id", "feature_key", "title", "kind",
                        "steps", "expected")
            if key in definition
        }
        native.setdefault("safety", "non_destructive")
        native.setdefault("estimated_seconds", 60)
        spec = TestCaseSpec.model_validate(native)
        outcome = await execute_skill_replay(
            request=PersonaJourneyExecutionRequest(
                test_run_id=request.run_id,
                execution_id=execution_id,
                journey_id=UUID(str(item.journey_id)),
                persona_id=UUID(str(state.persona_id)),
                mission_id=UUID(str(item.mission_id)),
                journey=case_journey(spec),
                start_url=request.start_url,
                allowed_origins=request.allowed_origins,
                network_policy=request.network_policy,
                max_duration_seconds=_item_wall_clock_seconds(state),
                runtime_human_assistance=True,
                runtime_target_id=UUID(str(request.target_snapshot["target_id"]))
                    if request.target_snapshot.get("target_id") is not None else None,
                fixture_action_rules=request.fixture_action_rules,
            ),
            controller=controller, handle=item_handle, session=session,
            skill_entry=entry, board_item_ref=item.item_id,
        )
        await session.commit()
        outcome_status = str(outcome["status"])
        skill_record = {
            "outcome": (
                "satisfied_by_replay"
                if outcome["status"] == "passed"
                else "diverged"
            ),
            "skill_id": item.locator.get("skill_id"),
            "skill_version_id": item.locator.get("skill_version_id"),
            "version_number": entry.get("version_number"),
            "app_map_id": (request.app_map or {}).get("map_id"),
            "context": "run",
            "per_step": outcome.get("per_step"),
            "terminal_state_match": outcome.get("terminal_state_match"),
        }
        if outcome["status"] == "passed":
            item.status = "worked"
            item.blocker = None
        elif outcome["status"] == "mode_filtered":
            item.status = "not_checked"
            item.blocker = str(outcome.get("reason") or "mode_filter")
            skill_record = None  # nothing replayed, nothing recorded
        elif outcome["status"] == "failed":
            item.status = "could_not_check"
            item.blocker = (
                f"skill replay failed at step {outcome.get('failure_step')} "
                f"({outcome.get('failure_site')}) — version demoted to "
                "suspect; journey falls back to live exploration"
            )
        else:  # diverged (assertion-shaped)
            item.status = "could_not_check"
            item.blocker = (
                "skill terminal assertion diverged — version quarantined; "
                "journey falls back to live exploration"
            )
        if outcome["status"] in ("failed", "diverged"):
            # C6 fallback, run-side: name the divergence and the
            # fallback on the run's own record. The journey's pages
            # keep their live element items (the Board's coverage of
            # the path); in a non-inventory run INT must ALSO emit
            # exploration items for the journey's pages here, in the
            # same run, before continuing the loop.
            await RunEventRepository(session).create(
                test_run_id=request.run_id,
                event_type="harness.skill.diverged",
                journey_id=UUID(str(item.journey_id)),
                execution_id=execution_id,
                payload={
                    "skill_id": item.locator.get("skill_id"),
                    "skill_version_id": item.locator.get("skill_version_id"),
                    "journey_name": item.locator.get("journey_name"),
                    "replay_id": outcome.get("replay_id"),
                    "shape": (
                        "locator" if outcome["status"] == "failed"
                        else "assertion"
                    ),
                    "fallback": "live_exploration",
                },
            )
            await session.commit()
        await executions.finish_agent_execution(
            execution_id=execution_id,
            status="completed",
            outcome="satisfied" if item.status == "worked" else None,
            error_code=item.blocker,
        )
    # Terminal bookkeeping, mirroring the normal item tail. On the
    # matcher path (entry_override set), a replay that did not pass
    # leaves the item open instead: the loop falls through and the
    # case is explored live, whose own tail does this bookkeeping
    # once. The replay's record (row, usage, divergence event)
    # already stands.
    defer_close = (
        entry_override is not None
        and outcome_status not in ("passed", "not_checked")
    )
    if not defer_close:
        state.budget_counters["items_finished"] += 1
        item.durations_ms.append(int((time.monotonic() - started_wall) * 1000))
        await _publish_board_item_result(
            session=session, run_id=request.run_id, item=item,
            execution_id=execution_id,
            skill_record=skill_record,
        )
        item.locator["board_result_published"] = True
        run = await session.get(TestRun, request.run_id, populate_existing=True)
        assert run is not None
        await persist_harness_state(
            session, run, state,
            event_type="harness.item.finished", stage="testing",
            journey_id=UUID(str(item.journey_id)) if item.journey_id else None,
            payload={
                "item_id": item.item_id,
                "case_id": item.case_id,
                "status": item.status,
            },
        )
        await session.commit()
    return outcome_status




async def _record_expectation_check(
    *, session: AsyncSession, run_id: UUID, item: HarnessItem,
) -> None:
    """Expectation feedback (doc 21 section 8.5) + run-time conflict
    opening (section 9.1 point 3).

    Only worked/broken write anything -- a could-not-check outcome is
    not evidence about the expectation. A passing documentation or
    owner-rule record moves unverified -> replay-verified; a failure
    never demotes, and no write here can move an observation or
    model-draft record toward eligibility. A reproduced failure of a
    documentation expectation (this publish point is post-reproduction)
    opens an oracle_check_failed conflict. Feedback failures are
    recorded as a run event, never raised into the run.
    """
    if item.status not in {"worked", "broken"}:
        return
    entries = item.locator.get("expectations")
    if not isinstance(entries, list):
        return
    result = "passed" if item.status == "worked" else "failed"
    try:
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            row = await session.get(MapExpectation, UUID(str(entry["id"])))
            if row is None:
                continue
            row.last_checked_at = datetime.now(UTC)
            row.last_check_result = result
            if (
                result == "passed"
                and row.oracle_source in {"documentation", "owner-rule"}
                and row.status == "unverified"
            ):
                row.status = "replay-verified"
            session.add(MapExpectationEvent(
                id=uuid4(),
                workspace_id=row.workspace_id,
                application_id=row.application_id,
                target_id=row.target_id,
                app_map_id=row.app_map_id,
                expectation_id=row.id,
                event_type="checked",
                payload={
                    "actor": "run",
                    "run_id": str(run_id),
                    "board_item_id": item.item_id,
                    "outcome": item.status,
                },
            ))
            if result == "failed" and row.oracle_source == "documentation":
                existing = await session.execute(
                    select(MapConflict).where(
                        MapConflict.expectation_id == row.id,
                        MapConflict.status == "open",
                        MapConflict.conflict_kind == "oracle_check_failed",
                    )
                )
                if existing.scalars().first() is None:
                    session.add(MapConflict(
                        id=uuid4(),
                        workspace_id=row.workspace_id,
                        application_id=row.application_id,
                        target_id=row.target_id,
                        app_map_id=row.app_map_id,
                        expectation_id=row.id,
                        observed_behaviour=(
                            "A Board check reproduced a failure of this "
                            "documented expectation in a fresh browser "
                            "context."
                        ),
                        evidence_refs=list(item.evidence_refs),
                        status="open",
                        conflict_kind="oracle_check_failed",
                        detection_source="run",
                        run_id=run_id,
                    ))
                    row.status = "conflicted"
                    session.add(MapExpectationEvent(
                        id=uuid4(),
                        workspace_id=row.workspace_id,
                        application_id=row.application_id,
                        target_id=row.target_id,
                        app_map_id=row.app_map_id,
                        expectation_id=row.id,
                        event_type="conflicted",
                        payload={
                            "actor": "run",
                            "run_id": str(run_id),
                            "detection_source": "run",
                        },
                    ))
        await session.flush()
    except Exception as exc:
        await session.rollback()
        await RunEventRepository(session).create(
            test_run_id=run_id,
            event_type="harness.expectation_feedback_failed",
            journey_id=None,
            execution_id=None,
            payload={
                "board_item_id": item.item_id,
                "error_type": type(exc).__name__,
                "message": str(exc)[:500],
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

    journeys: list[PersonaJourney] = []
    for offset, (item, case) in enumerate(pairs):
        mission_id, journey_id = uuid4(), uuid4()
        session.add(RunMission(
            id=mission_id, test_run_id=run_id,
            ordinal=first_ordinal + offset,
            title=case.title[:200], objective=case.title,
            success_criteria=[a.assertion_id for a in case.expected],
            priority=case.priority,
        ))
        journeys.append(PersonaJourney(
            id=journey_id, test_run_id=run_id,
            persona_id=persona_id, mission_id=mission_id,
            ordinal=first_ordinal + offset,
        ))
        item.mission_id, item.journey_id = str(mission_id), str(journey_id)
    # These mappers have no ORM relationship to order the composite FK.
    # Persist every parent mission before flushing its journey.
    await session.flush()
    for journey in journeys:
        session.add(journey)
    await session.flush()


async def _absorb_inventory(
    *, controller: BrowserController, handle: BrowserSessionHandle,
    session: AsyncSession, state: HarnessState, state_url: str,
    scope: FeatureScope, request: MarketTwinRunRequest,
    persona_id: UUID, first_ordinal: int, authenticated: bool,
    cases: dict[str, TestCaseSpec],
    reveal: bool = True,
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
    for _ in range(5 if reveal else 0):
        await controller.scroll(
            session_id=handle.session_id, direction="down", amount=600,
            execution_id=handle.execution_id, journey_id=handle.journey_id,
        )
        if await collect() == 0:
            break
    new_items = ingest_page_index(state, url=state_url, entries=collected)
    _enforce_item_budget(state)
    for item in state.ordered_items():
        # Skill items carry no native case: their case_id is not a
        # TestCaseSpec id and the claim loop's skill branch hands
        # them to the replay path before any case is read (doc 22
        # section 8.2).
        if item.case_id not in cases and not item.locator.get("skill_item"):
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


@asynccontextmanager
async def _inventory_execution_cleanup(
    session: AsyncSession, executions: ExecutionRepository,
) -> AsyncIterator[dict[str, UUID]]:
    """Finish the inventory record even when Room startup or discovery raises."""
    tracked: dict[str, UUID] = {}
    error: BaseException | None = None
    try:
        yield tracked
    except BaseException as caught:
        error = caught
        await session.rollback()
        raise
    finally:
        if "execution_id" in tracked:
            code = (
                "browser_discovery_checkpoint" if isinstance(error, BrowserDiscoveryCheckpointError)
                else "browser_discovery_empty" if isinstance(error, BrowserDiscoveryEmptyError)
                else "execution_failed"
            )
            await executions.finish_agent_execution(
                execution_id=tracked["execution_id"],
                status="failed" if error else "completed",
                **({"error_code": code} if error else {}),
            )
            if error and "browser_session_id" in tracked:
                await executions.mark_browser_session_closed(
                    browser_session_id=tracked["browser_session_id"],
                )
            await session.commit()


def _signature_entries(signature: object) -> list[str]:
    """Normalise a stored signature to its entry strings.

    The stored form (Phase 1a section 10.4) is the harness's own joined
    format — "role|name" entries joined by ";" for elements,
    "field|label" entries joined by ";" for forms — or a list of the
    same entries. Anything else yields no entries.
    """

    if isinstance(signature, str):
        return [entry for entry in signature.split(";") if entry]
    if isinstance(signature, list):
        return [str(entry) for entry in signature if str(entry)]
    return []


def _signature_pairs(signature: object) -> list[tuple[str, str]]:
    """Element signature entries back to (role, name) pairs."""

    pairs: list[tuple[str, str]] = []
    for entry in _signature_entries(signature):
        role, _, name = entry.partition("|")
        pairs.append((role, name))
    return pairs


def _signature_labels(signature: object) -> list[str]:
    """Form signature entries back to bare field labels."""

    return [
        entry[len("field|"):] if entry.startswith("field|") else entry
        for entry in _signature_entries(signature)
    ]


def _seed_known_states(harness_state: HarnessState, app_map: dict) -> int:
    """Register the map's signature-bearing states as Board claim states.

    A census map carries NULL signatures (decision D4), so this seeds
    nothing until a harvest writes real signatures; then each claimed
    state is registered through HarnessState.add_state — minting the
    same state_id a live observation of the same page would — and
    mints no Board items (items come only from the live page index).
    Returns the number of states seeded.
    """

    seeded = 0
    pages = app_map.get("pages") if isinstance(app_map, dict) else None
    if not isinstance(pages, list):
        return 0
    for page in pages:
        if not isinstance(page, dict):
            continue
        url = page.get("url")
        states = page.get("states")
        if not isinstance(url, str) or not isinstance(states, list):
            continue
        for entry in states:
            if not isinstance(entry, dict):
                continue
            element_signature = entry.get("element_signature")
            form_signature = entry.get("form_signature")
            if element_signature is None or form_signature is None:
                continue
            harness_state.add_state(
                url=url,
                elements=_signature_pairs(element_signature),
                form_fields=_signature_labels(form_signature),
            )
            seeded += 1
    return seeded


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
    learning_task = run.configuration_snapshot.get("learn_task") is True
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
            await session.flush()
            session.add(PersonaJourney(
                id=journey_id, test_run_id=request.run_id,
                persona_id=record.persona_id, mission_id=mission_id,
                ordinal=ordinal,
            ))
            item.mission_id, item.journey_id = str(mission_id), str(journey_id)
        await session.flush()
        seeded_pairs = []
        # Expectation seeding (doc 21 section 8.3): the pinned map's
        # verdict-eligible expectations join the Board before the
        # first persist, so coverage counts them from the start.
        if isinstance(request.app_map, dict) and not learning_task:
            seeded_pairs = _seed_expectation_items(
                state, cases, app_map=request.app_map,
                feature_key=scope.feature_key, start_url=request.start_url,
                safety_mode=run_safety_mode(run.configuration_snapshot),
            )
            if seeded_pairs:
                await _register_items(
                    session=session, run_id=request.run_id,
                    persona_id=record.persona_id,
                    first_ordinal=len(entries) + 1, pairs=seeded_pairs,
                )
        # Skill seeding (doc 22 section 8.2): one replay item per
        # journey the pinned snapshot serves an active skill for.
        if isinstance(request.app_map, dict) and not learning_task:
            plan = getattr(request, "app_plan", None) or {}
            skills_section = plan.get("skills")
            if not isinstance(skills_section, dict):
                from markettwin_execution_orchestrator.workflow.skill_filter import (
                    plan_skills_section,
                )

                skills_section = plan_skills_section(
                    request.app_map,
                    mode=run_safety_mode(run.configuration_snapshot),
                    approved_keys={
                        entry.key for entry in request.approved_test_data
                    },
                )
            skill_pairs = _seed_skill_items(
                state,
                app_map=request.app_map,
                replay_items=skills_section.get("replay_items") or [],
            )
            if skill_pairs:
                await _register_items(
                    session=session, run_id=request.run_id,
                    persona_id=record.persona_id,
                    first_ordinal=len(entries) + len(seeded_pairs) + 1
                    if seeded_pairs else len(entries) + 1,
                    pairs=skill_pairs,
                )
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
                if item.locator.get("skill_item"):
                    continue  # replayed via execute_skill_replay, no case
                if item.locator.get("item_kind") == "expectation":
                    continue  # rebuilt as expectation cases below
                owner = state.states[item.state_id]
                cases[item.case_id] = case_for_item(
                    item=item, state_url=owner.url,
                    feature_key=scope.feature_key, start_url=request.start_url,
                )
        # Expectation cases rebuild deterministically from the stamped
        # entries on the item locators (doc 21 section 8.3): dedicated
        # items get their compiled case; attached items get their
        # oracle(s) re-appended to the rebuilt base case.
        for item in state.ordered_items():
            stamped = item.locator.get("expectations")
            if not isinstance(stamped, list) or not stamped:
                continue
            if item.case_id in cases:
                extra = tuple(
                    oracle
                    for stamped_entry in stamped
                    if isinstance(stamped_entry, dict)
                    for oracle in (expectation_assertion(stamped_entry),)
                    if oracle is not None
                )
                if extra:
                    cases[item.case_id] = cases[item.case_id].model_copy(
                        update={
                            "expected": cases[item.case_id].expected + extra
                        }
                    )
            else:
                owner = state.states[item.state_id]
                cases[item.case_id] = case_for_expectation(
                    entry=stamped[0], item=item, state_url=owner.url,
                    feature_key=scope.feature_key,
                    start_url=request.start_url,
                )
        # Action steps are committed before dispatch to the browser. If
        # a worker dies before the Board result commits, an input step
        # may already have taken effect even when it still says running.
        for item in state.ordered_items():
            if item.status != "running":
                continue
            dispatched = item.journey_id and await session.scalar(
                select(ExecutionStep.id)
                .join(AgentExecution, AgentExecution.id == ExecutionStep.execution_id)
                .where(
                    AgentExecution.journey_id == UUID(item.journey_id),
                    ExecutionStep.action_type.in_(
                        ("click", "fill", "select", "check", "uncheck", "registration_submit"),
                    ),
                    ExecutionStep.status != "policy_blocked",
                )
                .limit(1)
            )
            if dispatched is not None and item.journey_id:
                item.status = "could_not_check"
                item.blocker = (
                    "The worker stopped after recording an input step. "
                    "Verify the effect in the app before retrying this check."
                )
            else:
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
    safety_mode: RunSafetyMode = run_safety_mode(run.configuration_snapshot)
    # The run-mode audit event (doc 17 section 7.2): exactly one per
    # dispatch, carrying the mode, its source, and the approved-data
    # KEYS — never a value (C5).
    await RunEventRepository(session).create(
        test_run_id=request.run_id,
        event_type="harness.run_mode",
        journey_id=None,
        execution_id=None,
        payload={
            "mode": safety_mode,
            "source": "configuration_snapshot",
            "approved_test_data_keys": sorted(
                entry.key for entry in request.approved_test_data
            ),
        },
    )
    # The lane count in force is part of the run's snapshot record
    # (doc 18 section 12: every gate measurement is reproducible
    # against its configuration). Rides the inventory execution's
    # commit, like the discovery-frontier writes below.
    run.configuration_snapshot = {
        **(run.configuration_snapshot or {}),
        "harness_lane_count": HARNESS_LANE_COUNT,
    }
    async with _inventory_execution_cleanup(session, executions) as inventory, BrowserController() as controller:
        await configure_offsite(controller, run, session)
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
        # Room persistence needs a real agent_executions row (FK) and that
        # row needs the bootstrap discovery journey (FK to persona_journeys).
        inv_journey_id = await session.scalar(
            select(PersonaJourney.id).where(
                PersonaJourney.test_run_id == request.run_id,
                PersonaJourney.ordinal == AUTH_BOOTSTRAP_ORDINAL,
            )
        )
        if inv_journey_id is None:
            raise ValueError(
                "Harness Room requires the browser-discovery bootstrap journey."
            )
        inv_execution_id = uuid4()
        # Discovery accounting already owns attempt 1; resumed Rooms also
        # need a fresh attempt. The worker's run claim serializes allocation.
        last_attempt = await session.scalar(
            select(func.max(AgentExecution.attempt_number)).where(
                AgentExecution.journey_id == inv_journey_id,
            )
        )
        await executions.create_agent_execution(
            execution_id=inv_execution_id,
            journey_id=inv_journey_id,
            attempt_number=(last_attempt or 0) + 1,
            runtime_name="harness_inventory_v1",
        )
        inventory["execution_id"] = inv_execution_id
        await session.commit()
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
        inventory["browser_session_id"] = room_handle.session_id
        await session.commit()
        inventory_route: str | None = None

        def bind_inventory_handoff(handle: BrowserSessionHandle) -> None:
            if not request.runtime_human_assistance:
                return
            identity = BrowserHandoffExecution(
                request.run_id, inv_execution_id, inv_journey_id, request.allowed_origins,
            )

            async def request_help() -> None:
                nonlocal inv_authenticated
                route = inventory_route
                await request_browser_handoff(
                    request=identity, controller=controller, handle=handle, session=session,
                    expected_url=route if route and not is_account_entry_route(route) else None,
                    policy=request.auth_verification, auth_scope=_auth_session_scope(request),
                )
                inv_authenticated = True

            async def operator_checkpoint() -> None:
                await cooperative_pause_checkpoint(
                    request=identity, controller=controller, handle=handle, session=session,
                    policy=request.auth_verification,
                )

            controller.bind_authentication_handler(handle, request_help)
            controller.bind_cooperative_pause_handler(handle, operator_checkpoint)

        bind_inventory_handoff(room_handle)
        frontier = (run.configuration_snapshot or {}).get("discovery_frontier", {})
        visited: set[str] = set(frontier.get("visited", ()))
        from markettwin_execution_orchestrator.workflow.app_plan import planned_routes, next_planned_item
        if request.app_map is not None and "pending" not in frontier:
            # Map-seeded frontier (Phase 1a section 10.4): the map's
            # routes first, then any planned routes the map does not
            # carry, canonical-deduped — map over sitemap precedence.
            # The merged list is this run's discovery_frontier.pending;
            # a persisted frontier from an earlier segment already
            # carries the seeding and is used exactly as stored.
            map_routes = request.app_map.get("routes")
            if not isinstance(map_routes, list):
                map_routes = []
            seeded_queue: list[str] = []
            seeded_keys: set[str] = set()
            for candidate in [*map_routes, *planned_routes(request)]:
                if not isinstance(candidate, str):
                    continue
                key = canonical_url(candidate)
                if key not in seeded_keys:
                    seeded_keys.add(key)
                    seeded_queue.append(candidate)
            queue: list[str] = seeded_queue
        else:
            queue = list(frontier.get("pending", planned_routes(request)))
        # The crawl bound (section 10.4): a mapped run may visit its
        # whole seeded frontier plus a discovery allowance; an unmapped
        # run keeps the flat cap of 20, byte-identical to before.
        visited_limit = (
            len(queue) + MAP_CRAWL_DISCOVERY_ALLOWANCE
            if request.app_map is not None else 20
        )
        crawl_failed: list[str] = []
        if request.app_map is not None:
            _seed_known_states(state, request.app_map)
        # Baselines are per (route, executing context): the Room is
        # lane 0, worker lanes are 1..N, and a proof context keys by
        # its own session id (doc 18 section 11.2; prep OQ3) — a
        # lane's baseline never speaks for another context.
        js_baseline: dict[tuple[str, int | UUID], set[tuple[str, str]]] = {}
        # Issue 3's outcome layer observes through the JS-error channel
        # (U-P6-03); a controller without it predates outcome evidence,
        # and its runs keep the assertion-only verdicts unchanged.
        outcome_layer = hasattr(controller, "harvest_js_records")

        async def _return_to_inventory() -> BrowserSessionHandle:
            nonlocal inventory_route
            handle = await controller.rebind_session(
                session_id=room_handle.session_id,
                execution_id=inv_execution_id, journey_id=inv_journey_id,
            )
            await executions.rebind_browser_session(
                browser_session_id=room_handle.session_id, execution_id=inv_execution_id,
            )
            await session.commit()
            inventory_route = None
            bind_inventory_handoff(handle)
            return handle

        items_since_inventory = 0

        async def _crawl_inventory(*, authenticated: bool) -> None:
            nonlocal ordinal, items_since_inventory, inventory_route
            items_since_inventory = 0
            # Inventory-driven generation: index the start state, then
            # follow read-classified links in the inventory session —
            # each landed state is indexed and appended the same way.
            while queue and len(visited) < visited_limit:
                current_url = queue.pop(0)
                if canonical_url(current_url) in visited:
                    continue
                if (
                    request.runtime_human_assistance
                    and canonical_url(current_url) != canonical_url(request.start_url)
                    and is_account_entry_route(current_url)
                ):
                    continue
                inventory_route = current_url
                visited.add(canonical_url(current_url))
                try:
                    await controller.navigate(
                        session_id=inv_handle.session_id, url=current_url,
                    )
                except (AuthenticationVerificationBlocked, HumanAssistanceSkipped) as error:
                    raise BrowserDiscoveryCheckpointError(
                        "The required step did not establish a verified discovery continuation.",
                    ) from error
                except (BrowserActionError, BrowserPolicyError) as error:
                    # A page that cannot be loaded (browser failure,
                    # policy refusal, unresolvable host) is accounted
                    # for and never retried in this crawl (its URL is
                    # already in visited); the crawl moves on to the
                    # next queued page. The bot-wall checkpoint below
                    # raises a different error type and still parks.
                    crawl_failed.append(canonical_url(current_url))
                    await RunEventRepository(session).create(
                        test_run_id=request.run_id,
                        event_type="harness.inventory.page_failed",
                        journey_id=None, execution_id=None,
                        payload={"url": current_url,
                                 "error_site": failure_site(error)},
                    )
                    continue
                signals = await controller.discovery_page_signals(session_id=inv_handle.session_id)
                if is_discovery_checkpoint(**signals):
                    raise BrowserDiscoveryCheckpointError("The site showed a bot-check page.")
                try:
                    ordinal = await _absorb_inventory(
                        controller=controller, handle=inv_handle,
                        session=session, state=state, state_url=current_url,
                        scope=scope, request=request,
                        persona_id=UUID(str(state.persona_id)),
                        first_ordinal=ordinal,
                        authenticated=authenticated or inv_authenticated, cases=cases,
                    )
                except (AuthenticationVerificationBlocked, HumanAssistanceSkipped) as error:
                    raise BrowserDiscoveryCheckpointError(
                        "The required step did not establish a verified discovery continuation.",
                    ) from error
                except (BrowserActionError, BrowserPolicyError) as error:
                    # The page loaded but could not be indexed (e.g.
                    # a wedged challenge inspection inside
                    # get_page_index): accounted exactly like a failed
                    # navigation above — never retried in this crawl,
                    # and the frontier persists without it.
                    crawl_failed.append(canonical_url(current_url))
                    await RunEventRepository(session).create(
                        test_run_id=request.run_id,
                        event_type="harness.inventory.page_failed",
                        journey_id=None, execution_id=None,
                        payload={"url": current_url,
                                 "error_site": failure_site(error)},
                    )
                else:
                    if outcome_layer:
                        # Discovery's own page loads define what is
                        # pre-existing on this route (the JS baseline).
                        await _drain_js_baseline(
                            controller, inv_handle.session_id, js_baseline,
                            lane_key=0)
                    queued_keys = {canonical_url(url) for url in queue}
                    for destination in await controller.page_links(session_id=inv_handle.session_id):
                        try:
                            validate_target_url(destination, request.allowed_origins, request.network_policy)
                        except BrowserPolicyError:
                            continue
                        key = canonical_url(destination)
                        if key not in visited and key not in queued_keys:
                            queue.append(destination)
                            queued_keys.add(key)
                # Test this page before expanding the frontier.
                break
            run = await session.get(TestRun, request.run_id, populate_existing=True)
            assert run is not None
            await persist_harness_state(
                session, run, state,
                event_type="harness.inventory.absorbed", stage="exploring",
                payload={"states": len(state.states), "items": len(state.items)},
            )
            run.configuration_snapshot = {
                **run.configuration_snapshot,
                "discovery_frontier": {"visited": sorted(visited), "pending": queue},
            }
            await session.commit()

        # Speed S2 (doc 18 section 11): lane bookkeeping. The loop
        # below is the absorber — the Board's only writer (I4). A
        # worker lane is a task that only executes and observes,
        # returning its raw outcome for the absorber to classify,
        # proof, and publish through the shared tail.
        lane_handles: dict[int, BrowserSessionHandle] = {}
        lane_tasks: dict[str, asyncio.Task] = {}
        lane_subjects: dict[str, dict[str, object]] = {}
        lane_items_finished: dict[int, int] = {0: 0}
        lanes_stale = False
        stop_after_drain = False
        park_pending = False
        owner_stopped = False

        async def _check_owner_stop() -> bool:
            """Owner stop (the Stop run button): ctl records the
            request in the run's configuration snapshot, and the
            engine honours it at an item boundary with the Lead-stop
            drain — pending items close named not_checked, in-flight
            items finish, and the run closes cancelled."""
            nonlocal owner_stopped, stop_after_drain
            if owner_stopped:
                return True
            fresh = await session.get(
                TestRun, request.run_id, populate_existing=True)
            if fresh is None:
                return False
            flag = (fresh.configuration_snapshot or {}).get("owner_stop")
            if not isinstance(flag, dict):
                return False
            owner_stopped = True
            for pending in state.ordered_items():
                if pending.status == "pending":
                    pending.status = "not_checked"
                    pending.blocker = "stopped by owner"
            await RunEventRepository(session).create(
                test_run_id=request.run_id,
                event_type="harness.run.owner_stop",
                journey_id=None, execution_id=None,
                payload={"requested_at": flag.get("requested_at")},
            )
            await session.commit()
            stop_after_drain = True
            return True

        async def _open_lane(lane_id: int) -> BrowserSessionHandle:
            handle = await controller.create_worker_session(
                room_session_id=room_handle.session_id,
                execution_id=inv_execution_id, journey_id=inv_journey_id,
                lane_index=lane_id,
            )
            await executions.create_browser_session(
                browser_session_id=handle.session_id,
                execution_id=inv_execution_id,
                test_run_id=request.run_id,
                session_role="worker",
            )
            await session.commit()
            lane_handles[lane_id] = handle
            return handle

        async def _close_lanes() -> None:
            for handle in lane_handles.values():
                try:
                    await controller.close_session(
                        session_id=handle.session_id)
                except BrowserSessionNotFoundError:
                    # The lane's session was already closed and
                    # removed (case execution closes a session it
                    # fatally errors on): the close goal is already
                    # met, so still mark the row closed below and
                    # continue with the remaining lanes.
                    pass
                await executions.mark_browser_session_closed(
                    browser_session_id=handle.session_id)
            lane_handles.clear()
            await session.commit()

        async def _execute_item_once(
            *, handle: BrowserSessionHandle, db_session: AsyncSession,
            lane_key: int, item: HarnessItem, case: TestCaseSpec,
            execution_id: UUID, journey_id: UUID, persona_id: UUID,
            mission_id: UUID, human_assistance: bool,
            reuse_auth_session: bool,
        ) -> tuple[CaseExecutionResult, int]:
            """Drain, then execute one item on the given session.

            The only part of an item's life a worker lane performs:
            browser work on its own context, bookkeeping on its own
            DB session. The Room path calls this with the absorber's
            session and lane_key 0, so both paths run one procedure.
            """

            if outcome_layer and inventory_driven:
                # Everything buffered before the case runs predates
                # the item's action: baseline, never outcome evidence.
                await _drain_js_baseline(
                    controller, handle.session_id, js_baseline,
                    lane_key=lane_key)
            started = time.monotonic()
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
                    # Login handover (U-P4) is offered on the Room,
                    # whose session the human drives; a lane never
                    # waits for a human (doc 18 section 11.2) — a
                    # wall in a lane returns as this item's blocker.
                    runtime_human_assistance=human_assistance,
                    runtime_target_id=(
                        UUID(str(request.target_snapshot["target_id"]))
                        if human_assistance
                        and request.target_snapshot.get("target_id") is not None
                        else None
                    ),
                    fixture_action_rules=request.fixture_action_rules,
                ),
                session_handle=handle,
                case=case,
                scope=scope,
                budget=PlanBudget(max_steps=32),
                controller=controller,
                session=db_session,
                auth_verification=request.auth_verification,
                auth_mode=request.auth_mode,
                auth_session_scope=auth_session_scope,
                reuse_auth_session=reuse_auth_session,
            )
            elapsed_ms = result.elapsed_ms or int(
                (time.monotonic() - started) * 1000)
            return result, elapsed_ms

        async def _run_lane_item(
            *, lane_id: int, item: HarnessItem, case: TestCaseSpec,
            execution_id: UUID, journey_id: UUID, persona_id: UUID,
            mission_id: UUID,
        ) -> tuple[CaseExecutionResult, int, dict[str, object] | None,
                   list[dict[str, object]], set[tuple[str, str]]]:
            """Execute + observe one item on a worker lane.

            Returns the raw outcome for the absorber. Raises only
            when the lane itself failed; the absorber absorbs that
            as a named could-not-check and retires the lane.
            """

            handle = await controller.rebind_session(
                session_id=lane_handles[lane_id].session_id,
                execution_id=execution_id, journey_id=journey_id,
            )
            lane_db = _new_lane_session(session)
            try:
                result, elapsed_ms = await _execute_item_once(
                    handle=handle, db_session=lane_db, lane_key=lane_id,
                    item=item, case=case, execution_id=execution_id,
                    journey_id=journey_id, persona_id=persona_id,
                    mission_id=mission_id, human_assistance=False,
                    reuse_auth_session=True,
                )
            finally:
                await lane_db.close()
            item_outcome: dict[str, object] | None = None
            item_js_errors: list[dict[str, object]] = []
            item_error_signatures: set[tuple[str, str]] = set()
            if (outcome_layer and inventory_driven
                    and "safety_class" in item.locator
                    and result.execution_status == "completed"):
                item_outcome = await _observe_item_outcome(
                    controller=controller, handle=handle, item=item,
                    state_url=state.states[item.state_id].url,
                    state_elements=frozenset(
                        state.states[item.state_id].element_signature),
                    state_form_fields=frozenset(
                        state.states[item.state_id].form_signature),
                    baseline=js_baseline, authenticated=inv_authenticated,
                    lane_key=lane_id,
                )
                item_js_errors = cast(
                    list[dict[str, object]], item_outcome["js_errors"])
                item_error_signatures = cast(
                    set[tuple[str, str]], item_outcome["signatures"])
            return (result, elapsed_ms, item_outcome, item_js_errors,
                    item_error_signatures)
        if inventory_driven:
            if not await _check_owner_stop():
                await _crawl_inventory(authenticated=inv_authenticated)
        last_reviewed_finished = state.budget_counters.get("last_reviewed_finished", 0)
        while True:
            if not stop_after_drain and not park_pending:
                await _check_owner_stop()
            # Absorb a finished lane item before claiming new work:
            # its tail runs below with the execution prefilled. The
            # loop only ever exits drained — a stop or a park first
            # absorbs everything in flight (claims frozen).
            subject: dict[str, object] | None = None
            for pending_id, pending_task in list(lane_tasks.items()):
                if pending_task.done():
                    subject = lane_subjects.pop(pending_id)
                    del lane_tasks[pending_id]
                    break
            if subject is None and lane_tasks and (
                stop_after_drain or park_pending
            ):
                oldest_id = next(iter(lane_tasks))
                subject = lane_subjects.pop(oldest_id)
                del lane_tasks[oldest_id]
            if subject is None and (stop_after_drain or park_pending):
                break
            if subject is None:
                can_expand_inventory = inventory_driven and queue and len(visited) < visited_limit
                inventory_due = can_expand_inventory and (
                    items_since_inventory >= ITEMS_BETWEEN_INVENTORY_PAGES
                )
                item = None if inventory_due else next_planned_item(state, request)
                if item is None:
                    if lane_tasks:
                        oldest_id = next(iter(lane_tasks))
                        subject = lane_subjects.pop(oldest_id)
                        del lane_tasks[oldest_id]
                    elif can_expand_inventory:
                        inv_handle = await _return_to_inventory()
                        await _crawl_inventory(authenticated=inv_authenticated)
                        continue
                    else:
                        if inventory_driven and not state.items:
                            raise BrowserDiscoveryEmptyError(
                                "Browser discovery found no testable controls."
                            )
                        break
                else:
                    items_since_inventory += 1
                    if item.locator.get("skill_item"):
                        await _run_skill_item(
                            session=session, request=request, state=state,
                            item=item, controller=controller,
                            room_handle=room_handle, executions=executions,
                            scope=scope, started_wall=time.monotonic(),
                        )
                        continue
                    if item.case_id not in cases:
                        owner = state.states[item.state_id]
                        cases[item.case_id] = case_for_item(
                            item=item, state_url=owner.url,
                            feature_key=scope.feature_key, start_url=request.start_url,
                        )
                    case = cases[item.case_id]
                    if inventory_driven:
                        structural = structural_reason(item)
                        reason = structural or skip_reason(
                            safety_of(item), safety_mode
                        )
                        if reason is None and missing_test_value_keys(
                            case, scope.safe_test_data,
                        ):
                            # The data guard (doc 17 section 6.4): a case whose
                            # fill/select key no approved value resolves is
                            # accounted for with the gate's own shape, never
                            # executed into the by-key lookup without a value.
                            reason = NOT_EXERCISED_UNAPPROVED_DATA
                        if reason is not None:
                            # The safety gate: inventoried and reported,
                            # never executed. The item is accounted for.
                            # A structural item (an unnamed control) closes
                            # as could_not_check instead: no locator
                            # strategy can target it by name (doc 24
                            # section 6.2).
                            item.status = (
                                "could_not_check"
                                if structural is not None
                                else "not_checked"
                            )
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
                    # Lane routing (doc 18 section 11.4): kind
                    # first, then safety class. The guard above has
                    # already closed the items this run will not
                    # exercise at all.
                    if isinstance(request.app_map, dict) and request.app_map.get("skills"):
                        from markettwin_execution_orchestrator.workflow.skill_filter import (
                            match_task_skill,
                        )

                        match = match_task_skill(
                            request.app_map, case, mode=safety_mode,
                            approved_values={
                                value.key: value.value
                                for value in scope.safe_test_data
                            },
                            start_url=request.start_url,
                        )
                        if match is not None and match.status == "not_selected":
                            # The matcher declined, with its reason
                            # named on the run's record (doc 29
                            # section 7.2); the case falls through
                            # to live execution below.
                            run = await session.get(
                                TestRun, request.run_id, populate_existing=True,
                            )
                            assert run is not None
                            await persist_harness_state(
                                session, run, state,
                                event_type="harness.skill.not_selected",
                                stage="testing",
                                journey_id=UUID(str(item.journey_id)),
                                payload={
                                    "item_id": item.item_id,
                                    "case_id": case.case_id,
                                    "feature_key": case.feature_key,
                                    "reason": match.reason,
                                },
                            )
                            await session.commit()
                        elif match is not None and match.status == "matched":
                            version_id = match.skill_version_id
                            skill_entry = match.entry
                            task_version = await session.get(SkillVersion, version_id, populate_existing=True)
                            if (
                                task_version is not None
                                and task_version.lifecycle_status == "active"
                                and str(task_version.app_map_id) == request.app_map.get("map_id")
                            ):
                                item.locator.update(
                                    item_kind="skill_replay",
                                    skill_id=skill_entry["skill_id"],
                                    skill_version_id=str(version_id),
                                    journey_name=case.title,
                                )
                                outcome_status = await _run_skill_item(
                                    session=session, request=request, state=state,
                                    item=item, controller=controller,
                                    room_handle=room_handle, executions=executions,
                                    scope=scope, started_wall=time.monotonic(),
                                    entry_override=skill_entry,
                                )
                                if outcome_status in ("passed", "not_checked"):
                                    continue
                                # The replay failed, diverged or was
                                # mode-filtered: the item is still
                                # open -- fall through and explore
                                # the case live.
                    worker_lane: int | None = None
                    if HARNESS_LANE_COUNT > 1 and _lane_eligible(
                        item, safety_mode=safety_mode,
                        inventory_driven=inventory_driven,
                    ):
                        in_use = {
                            cast(int, s["lane_id"])
                            for s in lane_subjects.values()
                        }
                        for candidate in range(1, HARNESS_LANE_COUNT):
                            if candidate not in in_use:
                                worker_lane = candidate
                                break
                        if lanes_stale and lane_tasks:
                            # No new lane claims until the stale
                            # lanes have drained and closed.
                            worker_lane = None
                    if lanes_stale and not lane_tasks:
                        # Re-seed after a re-authentication (section
                        # 11.2): stale lanes close before any new
                        # claim can open fresh ones.
                        await _close_lanes()
                        lanes_stale = False
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
                    if worker_lane is not None:
                        if worker_lane not in lane_handles:
                            await _open_lane(worker_lane)
                        lane_task = asyncio.create_task(_run_lane_item(
                            lane_id=worker_lane, item=item, case=case,
                            execution_id=execution_id,
                            journey_id=journey_id, persona_id=persona_id,
                            mission_id=mission_id))
                        lane_tasks[item.item_id] = lane_task
                        lane_subjects[item.item_id] = {
                            "task": lane_task, "item": item, "case": case,
                            "execution_id": execution_id,
                            "journey_id": journey_id,
                            "persona_id": persona_id,
                            "mission_id": mission_id,
                            "lane_id": worker_lane,
                        }
                        continue
                    item_js_errors: list[dict[str, object]] = []
                    item_error_signatures: set[tuple[str, str]] = set()
                    item_outcome: dict[str, object] | None = None
                    subject_lane = 0
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
                    result, elapsed_ms = await _execute_item_once(
                        handle=item_handle, db_session=session,
                        lane_key=0, item=item, case=case,
                        execution_id=execution_id, journey_id=journey_id,
                        persona_id=persona_id, mission_id=mission_id,
                        human_assistance=True,
                        reuse_auth_session=bool(results) or (
                            request.auth_verification is not None
                            and request.feature_plan is None
                            and not request.synthetic_fixture_approval_enabled
                        ),
                    )
                    was_authenticated = inv_authenticated
            if subject is not None:
                item = cast(HarnessItem, subject["item"])
                case = cast(TestCaseSpec, subject["case"])
                journey_id = cast(UUID, subject["journey_id"])
                persona_id = cast(UUID, subject["persona_id"])
                mission_id = cast(UUID, subject["mission_id"])
                execution_id = cast(UUID, subject["execution_id"])
                subject_lane = cast(int, subject["lane_id"])
                was_authenticated = inv_authenticated
                lane_task = cast(asyncio.Task, subject["task"])
                try:
                    (result, elapsed_ms, item_outcome, item_js_errors,
                     item_error_signatures) = await lane_task
                except Exception as error:
                    # The lane died mid-item: the item is absorbed
                    # as a named could-not-check, the lane is
                    # retired (never replaced mid-run), and the run
                    # continues on the lanes that remain.
                    item.status = "could_not_check"
                    item.blocker = "lane_session_failed"
                    await executions.finish_agent_execution(
                        execution_id=execution_id, status="failed",
                        outcome=None, error_code="lane_session_failed",
                    )
                    state.budget_counters["items_finished"] += 1
                    lane_items_finished[subject_lane] = (
                        lane_items_finished.get(subject_lane, 0) + 1)
                    await _publish_board_item_result(
                        session=session, run_id=request.run_id,
                        item=item, execution_id=execution_id,
                    )
                    item.locator["board_result_published"] = True
                    dead_handle = lane_handles.pop(subject_lane, None)
                    if dead_handle is not None:
                        await controller.close_session(
                            session_id=dead_handle.session_id)
                        await executions.mark_browser_session_closed(
                            browser_session_id=dead_handle.session_id)
                    run = await session.get(
                        TestRun, request.run_id, populate_existing=True)
                    assert run is not None
                    await persist_harness_state(
                        session, run, state,
                        event_type="harness.item.finished",
                        stage="testing", journey_id=journey_id,
                        payload={
                            "item_id": item.item_id,
                            "case_id": case.case_id,
                            "status": item.status,
                            "error_site": failure_site(error),
                        },
                    )
                    await session.commit()
                    continue
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
            if subject_lane > 0 and item.status == "needs_human_login":
                # A lane never parks the run (doc 18 section 11.2):
                # the wall is this item's could-not-check, recorded
                # with its authentication blocker; the Room's own
                # flow owns any handoff.
                item.status = "could_not_check"
            item.blocker = result.blocker
            if (item.status == "could_not_check" and result.verdict == "satisfied"
                    and result.execution_status == "completed"):
                item.locator = {**item.locator, "tier": "outcome_not_established"}
            if (outcome_layer and inventory_driven
                    and "safety_class" in item.locator
                    and result.execution_status == "completed"):
                # Issue 3: judge the item by what its action did,
                # observed after the fact — the outcome layer.
                if item_outcome is None:
                    item_outcome = await _observe_item_outcome(
                        controller=controller, handle=item_handle,
                        item=item,
                        state_url=state.states[item.state_id].url,
                        state_elements=frozenset(
                            state.states[item.state_id].element_signature),
                        state_form_fields=frozenset(
                            state.states[item.state_id].form_signature),
                        baseline=js_baseline,
                        authenticated=inv_authenticated,
                        lane_key=0,
                    )
                    item_js_errors = cast(
                        list[dict[str, object]], item_outcome["js_errors"])
                    item_error_signatures = cast(
                        set[tuple[str, str]], item_outcome["signatures"])
                outcome = str(item_outcome["outcome"])
                if outcome != "unobserved":
                    item.locator = {**item.locator, "outcome": outcome}
                failed_visible_only = [
                    assertion for assertion in result.assertion_results
                    if assertion.status == "not_satisfied"
                ]
                if (item.status == "broken" and failed_visible_only
                        and all(
                            assertion.assertion_id == "target_visible"
                            for assertion in failed_visible_only)
                        and outcome in {"navigated", "view_changed"}
                        and not item_js_errors):
                    # The control's disappearance is explained by its
                    # effect (a link that navigates, a button that
                    # closes its own dialog): visible-after was the
                    # wrong post-condition (§2.2 contracts).
                    item.status = "worked"
                elif (item.status == "could_not_check"
                        and item.locator.get("tier")
                        == "outcome_not_established"):
                    if item.role in _CLICK_ROLES:
                        if outcome in {"navigated", "view_changed"}:
                            item.status = "worked"
                            item.locator.pop("tier", None)
                        elif outcome in {"js_error", "no_effect"}:
                            # A suspect, not yet a defect: the
                            # attempt-2 reproduction below decides.
                            item.status = "broken"
                            item.locator = {
                                **item.locator,
                                "outcome_suspicion": outcome,
                            }
                    elif item.role in FIELD_ROLES:
                        if outcome == "js_error":
                            item.status = "broken"
                            item.locator = {
                                **item.locator,
                                "outcome_suspicion": "js_error",
                            }
                        elif outcome != "unobserved":
                            # The fill/select action's own success is
                            # the field's outcome; the value read-back
                            # stays unverified under the privacy
                            # contract in browser/assertions.py.
                            item.status = "worked"
                            item.locator.pop("tier", None)
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
                if outcome_layer and "outcome_suspicion" in item.locator:
                    await _drain_js_baseline(
                        controller, proof_handle.session_id, js_baseline,
                        lane_key=proof_handle.session_id)
                # Proof is an unattended reproduction: unlike the item
                # path it does not force handover — it runs on the
                # Room's seeded storage state and the run's own
                # assistance setting, because a proof that needs a
                # fresh human login is not a reproduction.
                proof_failed = False
                confirm_outcome: dict[str, object] | None = None
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
                    if outcome_layer:
                        # Observe inside the try: the finally below
                        # closes the proof session. The deciding
                        # attempt's JS errors are the ones published
                        # (§2.5), whatever the suspicion state.
                        confirm_outcome = await _observe_item_outcome(
                            controller=controller, handle=proof_handle,
                            item=item,
                            state_url=state.states[item.state_id].url,
                            state_elements=frozenset(
                                state.states[item.state_id]
                                .element_signature),
                            state_form_fields=frozenset(
                                state.states[item.state_id]
                                .form_signature),
                            baseline=js_baseline,
                            authenticated=inv_authenticated,
                            lane_key=proof_handle.session_id,
                        )
                        item_js_errors = cast(
                            list[dict[str, object]],
                            confirm_outcome["js_errors"])
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
                failed_assertions = {
                    (assertion.assertion_id, assertion.oracle)
                    for assertion in result.assertion_results
                    if assertion.status == "not_satisfied"
                }
                repeated_failures = {
                    (assertion.assertion_id, assertion.oracle)
                    for assertion in confirm.assertion_results
                    if assertion.status == "not_satisfied"
                }
                if outcome_layer and "outcome_suspicion" in item.locator:
                    # Outcome suspicions reproduce by outcome, not by
                    # assertion: the proof run must show the same
                    # absence of effect (or the same new JS error) in
                    # its fresh context, with its assertions satisfied.
                    suspicion = str(item.locator["outcome_suspicion"])
                    if suspicion == "js_error":
                        # The SAME error must repeat: a fresh-context
                        # load error the item never produced cannot
                        # confirm its suspicion.
                        confirm_signatures = (
                            cast(set[tuple[str, str]],
                                 confirm_outcome["signatures"])
                            if confirm_outcome is not None else set()
                        )
                        repeated_outcome = (
                            confirm_outcome is not None
                            and confirm.execution_status == "completed"
                            and confirm.verdict == "satisfied"
                            and str(confirm_outcome["outcome"]) == "js_error"
                            and bool(item_error_signatures
                                     & confirm_signatures)
                        )
                    else:
                        repeated_outcome = (
                            confirm_outcome is not None
                            and confirm.execution_status == "completed"
                            and confirm.verdict == "satisfied"
                            and str(confirm_outcome["outcome"]) == suspicion
                        )
                    if repeated_outcome:
                        await executions.record_reproduced_failure(
                            execution_id=execution_id, proof_id=confirm_id,
                        )
                        item.locator["tier"] = (
                            "same_browser_error_on_both_attempts" if suspicion == "js_error" else
                            "no_visible_effect_on_either_attempt"
                        )
                    else:
                        item.status = "could_not_check"
                        item.locator = {**item.locator, "tier": "observed_once"}
                        item.locator.pop("outcome_suspicion", None)
                elif (_result_status(confirm) != "broken"
                        or not failed_assertions.intersection(repeated_failures)):
                    item.status = "could_not_check"
                    item.locator = {**item.locator, "tier": "observed_once"}
                final_result, final_execution_id = confirm, confirm_id
            if item.status != "needs_human_login":
                state.budget_counters["items_finished"] += 1
                lane_items_finished[subject_lane] = (
                    lane_items_finished.get(subject_lane, 0) + 1)
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
                park_pending = True
                continue
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
                    js_errors=item_js_errors,
                    test_value_key=next(
                        (
                            step.test_value_key
                            for step in case.steps
                            if step.action in {"fill", "select"}
                            and step.test_value_key is not None
                        ),
                        None,
                    ),
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
            if item.status == "worked" and item_outcome and item_outcome["outcome"] == "navigated":
                destination = item_outcome["observed_url"]
                if isinstance(destination, str):
                    try:
                        validate_target_url(destination, request.allowed_origins, request.network_policy)
                    except BrowserPolicyError:
                        pass
                    else:
                        key = canonical_url(destination)
                        if key not in visited and all(canonical_url(url) != key for url in queue):
                            queue.append(destination)
                            run.configuration_snapshot = {
                                **run.configuration_snapshot,
                                "discovery_frontier": {"visited": sorted(visited), "pending": list(queue)},
                            }
            if (item.status == "worked" and item_outcome
                    and item_outcome["outcome"] == "view_changed"
                    and item_outcome["observed_state_id"] not in state.states
                    and safety_of(item) == "read" and item.role in _CLICK_ROLES):
                entry_steps = tuple(step for step in case.steps if step.action == "click")
                if entry_steps and len(entry_steps) <= 3:
                    source_state = state.states[item.state_id]
                    revealed = ingest_page_index(
                        state, url=source_state.url,
                        entries=cast(list[dict[str, object]], item_outcome["entries"]),
                        entry_steps=entry_steps, previous_elements=source_state.element_signature,
                    )
                    _enforce_item_budget(state)
                    for child in revealed:
                        cases[child.case_id] = case_for_item(
                            item=child, state_url=source_state.url, start_url=request.start_url,
                            feature_key=scope.feature_key,
                        )
                    await _register_items(
                        session=session, run_id=request.run_id, persona_id=UUID(str(state.persona_id)),
                        first_ordinal=ordinal, pairs=[(child, cases[child.case_id]) for child in revealed],
                    )
                    ordinal += len(revealed)
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
            # Publish the result and its resume checkpoint before optional feedback.
            if item.locator.get("expectation_id"):
                await _record_expectation_check(
                    session=session, run_id=request.run_id, item=item,
                )
            if (
                final_result.human_wait_ms > 0
                and final_result.execution_status != "completed"
                and final_result.blocker != "human_assistance_timeout"
            ):
                stop = {"decision": "stop", "source": "handoff",
                    "reason": "Human handoff did not return verified agent control. Remaining work was not attempted."}
                for remaining in state.ordered_items():
                    if remaining.status == "pending":
                        remaining.status = "not_checked"
                        remaining.blocker = stop["reason"]
                run.configuration_snapshot = {**run.configuration_snapshot, "lead_stop": stop,
                    "discovery_frontier": {"visited": sorted(visited), "pending": list(queue)}}
                stop_after_drain = True
                continue
            if (state.budget_counters["items_finished"] % 5 == 0
                    and state.budget_counters["items_finished"] > last_reviewed_finished):
                finished_now = state.budget_counters["items_finished"]
                counts_now = state.counts()
                checkpoint_evidence = {
                    "items_finished": finished_now,
                    "checked_delta": finished_now - last_reviewed_finished,
                    "discovered_items": len(state.items),
                    "remaining_items": counts_now["pending"],
                    "counts": counts_now, "last_item": item.name,
                    "last_status": item.status,
                    "lane_items_finished": {
                        str(lane_id): count
                        for lane_id, count in sorted(
                            lane_items_finished.items())
                    },
                }
                if isinstance(getattr(request, "app_map", None), dict):
                    # Phase 1b section 8: the Lead sees what the run's
                    # pinned map knows about the current page. Pure
                    # lookups over the snapshot block; expectations are
                    # the labelled empty set until Phase 2.
                    current_state = state.states.get(item.state_id)
                    current_url = (
                        current_state.url if current_state is not None
                        else request.start_url
                    )
                    map_page = find_page(request.app_map, current_url)
                    map_elements = page_elements(request.app_map, current_url)
                    map_journey = find_journey(request.app_map)
                    map_skill = find_skill(request.app_map)
                    expectations = get_expectations(
                        request.app_map, current_url)
                    checkpoint_evidence["map_lookups"] = {
                        "page_known": map_page is not None,
                        "elements_known": (
                            len(map_elements)
                            if map_elements is not None else None
                        ),
                        "journey": (
                            map_journey.get("name") if map_journey else None
                        ),
                        "skill": map_skill.get("name") if map_skill else None,
                        "expectations": len(expectations),
                        "expectations_source": expectations.source,
                    }
                pending_for_review = [
                    {
                        "id": pending.item_id,
                        "label": pending.name,
                        "skill_item": bool(pending.locator.get("skill_item")),
                    }
                    for pending in state.ordered_items()
                    if pending.status == "pending"
                ]
                knowledge_section = (request.app_plan or {}).get("source_knowledge") or {}
                loaded_ids = {e.get("file_id") for e in knowledge_section.get("files") or []}
                knowledge_candidates = [
                    {"file_id": e["file_id"], "title": e.get("title") or e["slug"],
                     "description": e.get("description") or ""}
                    for c in knowledge_section.get("collections") or []
                    for e in c.get("manifest") or []
                    if e.get("file_id") not in loaded_ids
                ]
                review = await review_checkpoint(
                    objective=request.study_brief,
                    evidence=checkpoint_evidence,
                    pending_items=pending_for_review,
                    knowledge_candidates=knowledge_candidates or None,
                )
                if request.app_plan is not None:
                    for file_id in review.get("knowledge_open_requests") or []:
                        await open_knowledge_file(
                            session=session, run_id=request.run_id,
                            plan=request.app_plan, file_id=file_id,
                        )
                board_order = review.get("board_order")
                if board_order:
                    # Adopt the Lead's order for pending NON-skill
                    # items only (review_checkpoint never ranks skill
                    # items): the ranked items move, in the Lead's
                    # sequence, to where the first of them stood;
                    # every other item keeps its place. The order
                    # rides the persisted checkpoint payload via
                    # `review` (board_order + board_order_source).
                    rank = {
                        item_id: index
                        for index, item_id in enumerate(board_order)
                    }
                    ranked = sorted(
                        (
                            pending
                            for pending in state.ordered_items()
                            if pending.item_id in rank
                            and not pending.locator.get("skill_item")
                        ),
                        key=lambda pending: rank[pending.item_id],
                    )
                    ranked_ids = {pending.item_id for pending in ranked}
                    reordered: list = []
                    emitted = False
                    for current in state.ordered_items():
                        if current.item_id in ranked_ids:
                            if not emitted:
                                reordered.extend(ranked)
                                emitted = True
                            continue
                        reordered.append(current)
                    state.items = {
                        current.item_id: current for current in reordered
                    }
                last_reviewed_finished = finished_now
                state.budget_counters["last_reviewed_finished"] = finished_now
                await persist_harness_state(
                    session, run, state, event_type="lead.checkpoint", stage="testing",
                    payload=review,
                )
                await session.commit()
                if review["decision"] == "stop":
                    for remaining in state.ordered_items():
                        if remaining.status == "pending":
                            remaining.status = "not_checked"
                            remaining.blocker = review["reason"]
                    run.configuration_snapshot = {**run.configuration_snapshot,
                        "lead_stop": review,
                        "discovery_frontier": {"visited": sorted(visited), "pending": list(queue)}}
                    stop_after_drain = True
                    continue
            if (
                final_result.human_wait_ms > 0
                and final_result.blocker != "human_assistance_timeout"
            ):
                # Human control marks this Room authenticated immediately.
                # Set the authorized handover flag before either re-index path.
                inv_authenticated = True
            if (
                inventory_driven and inv_handle is not None
                and item.role in {"link", "button"}
                and final_result.human_wait_ms == 0
            ):
                # Generation interleaved with execution: the action
                # may have changed the app state — re-inventory the
                # start state and append whatever is new (fingerprint
                # dedupe makes a repeat index a no-op) before the
                # next pending item is taken. The Room is bound to the
                # item right now; rebind it back to the Room anchor
                # first (single-writer rule).
                inv_handle = await _return_to_inventory()
                try:
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
                        reveal=False,
                    )
                except (BrowserActionError, BrowserPolicyError) as error:
                    # The return navigation or the re-index failed
                    # (policy refusal, unresolvable host, page load
                    # failure, wedged challenge inspection): the
                    # finished item's result already stands, so the
                    # re-index is skipped and accounted here, and the
                    # run continues. One page's failure is never
                    # run-fatal (MT-000160, MT-000161, MT-000169).
                    await RunEventRepository(session).create(
                        test_run_id=request.run_id,
                        event_type="harness.inventory.page_failed",
                        journey_id=None, execution_id=None,
                        payload={"url": request.start_url,
                                 "error_site": failure_site(error)},
                    )
            if (
                inventory_driven and inv_handle is not None
                and final_result.human_wait_ms > 0
                and final_result.blocker != "human_assistance_timeout"
            ):
                # A human logged in during this item (U-P4): the app
                # behind the wall was never inventoried. Re-crawl in
                # the SAME Room session, now authenticated, so the
                # post-login states and items join the Board instead
                # of staying an unchecked bucket.
                inv_handle = await _return_to_inventory()
                inv_authenticated = True
                visited.clear()
                queue[:] = planned_routes(request)
                await _crawl_inventory(authenticated=True)
            if inv_authenticated and not was_authenticated:
                # The Room re-authenticated during this item (U-P4):
                # lanes seeded from the old storage state are stale
                # and re-seed before their next claim (doc 18
                # section 11.2) — S2-10 closes them at the head.
                lanes_stale = True

    # Lane contexts close with the run (D-S1). In-flight is empty
    # here by construction — the loop only exits drained — and a
    # parked run closes its lanes before returning, like its Room
    # row, rather than leaving them to the startup reaper.
    await _close_lanes()

    if park_pending:
        # The login-wall park (its record was persisted at the wall):
        # the run releases the worker exactly as the in-loop return
        # did, now with every lane item absorbed. Absorbed items
        # finish after the wall item and their tails persist
        # stage="testing" — the park is this dispatch's final state,
        # so its stage is re-asserted last.
        run = await session.get(TestRun, request.run_id, populate_existing=True)
        assert run is not None
        run.configuration_snapshot["harness_stage"] = "needs_login"
        await session.commit()
        return tuple(results)

    # A confirmation can defer one item while other items finish. It is
    # still nonterminal: the Boss may not close the run around it.
    waiting = next((item for item in state.ordered_items()
                    if item.status == "needs_human_login"), None)
    if waiting is not None:
        run = await session.get(TestRun, request.run_id, populate_existing=True)
        assert run is not None
        park_seconds = run.configuration_snapshot.get("harness_park_seconds", 900)
        if not isinstance(park_seconds, int) or isinstance(park_seconds, bool):
            park_seconds = 900
        parked_at = datetime.now(UTC)
        run.configuration_snapshot = {
            **run.configuration_snapshot,
            "harness_park": {
                "parked_at": parked_at.isoformat(),
                "deadline_at": (parked_at + timedelta(
                    seconds=max(60, min(1800, park_seconds)),
                )).isoformat(),
                "item_id": waiting.item_id,
            },
        }
        run.status = "awaiting_human"
        await persist_harness_state(
            session, run, state, event_type="harness.run.needs_login",
            stage="needs_login", journey_id=UUID(str(waiting.journey_id)),
        )
        await session.commit()
        return tuple(results)

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
    if inventory_driven and queue:
        # Completion accounting (Issue 2): pages the discovery crawl
        # found but never visited are named in the record, never
        # silently dropped from the coverage denominator.
        await persist_harness_state(
            session, run, state,
            event_type="harness.coverage.frontier", stage="evaluating",
            payload={"visited_count": len(visited), "not_visited": list(queue),
                     "reason": "discovery_cap" if len(visited) >= visited_limit else "frontier_remaining"},
        )
    if request.app_map is not None:
        # Coverage delta (Phase 1a section 10.4): reconcile the map's
        # expected pages against the states this run actually absorbed.
        # Seeded claim states live on the same board, so a seeded page
        # counts as absorbed only if the crawl reached its URL (the
        # start URL, absorbed by re-inventory, excepted); when a seeded
        # and a divergent live state share a URL, the live one is the
        # honest comparison for the delta's changed category.
        seeded_state_ids: dict[str, str] = {}
        map_pages = request.app_map.get("pages")
        if isinstance(map_pages, list):
            for map_page in map_pages:
                if not isinstance(map_page, dict):
                    continue
                page_url = map_page.get("url")
                page_states = map_page.get("states")
                if not isinstance(page_url, str) or not isinstance(page_states, list):
                    continue
                for state_entry in page_states:
                    if isinstance(state_entry, dict) and isinstance(
                        state_entry.get("state_id"), str
                    ):
                        seeded_state_ids[canonical_url(page_url)] = (
                            state_entry["state_id"]
                        )
        absorbed: dict[str, str] = {}
        start_key = canonical_url(request.start_url)
        for page_state in state.states.values():
            state_key = canonical_url(page_state.url)
            if state_key not in visited and state_key != start_key:
                continue
            current = absorbed.get(state_key)
            if current is None or (
                current == seeded_state_ids.get(state_key)
                and page_state.state_id != current
            ):
                absorbed[state_key] = page_state.state_id
        await RunEventRepository(session).create(
            test_run_id=request.run_id, event_type="harness.coverage.delta",
            journey_id=None, execution_id=None,
            payload=build_coverage_delta(
                map_block=request.app_map, absorbed=absorbed,
                attempted_failed=crawl_failed, frontier_remaining=list(queue),
            ),
        )
    await persist_harness_state(
        session, run, state,
        event_type="harness.run.evaluating", stage="evaluating",
    )
    if owner_stopped:
        await states.mark_cancelled(test_run_id=request.run_id)
        await persist_harness_state(
            session, run, state,
            event_type="harness.run.cancelled", stage="done",
        )
    else:
        await states.mark_completed(test_run_id=request.run_id)
        await persist_harness_state(
            session, run, state,
            event_type="harness.run.completed", stage="done",
        )
    await session.commit()
    # Doc 29 section 5 (OD-2): at run close, every captured task
    # trace compiles into a draft task skill. Compilation is
    # library work after the run's own close: it never fails the
    # run, and its rejections are recorded on the run by the
    # compiler itself.
    try:
        from markettwin_execution_orchestrator.harvest.task_compile import (
            compile_run_traces,
        )

        await compile_run_traces(
            session_factory=async_sessionmaker(
                bind=session.bind, expire_on_commit=False
            ),
            run_id=request.run_id,
        )
    except Exception as error:
        await session.rollback()
        await RunEventRepository(session).create(
            test_run_id=request.run_id, event_type="harness.task_compile_failed",
            journey_id=None, execution_id=None,
            payload={"error_type": type(error).__name__},
        )
        await session.commit()
    return tuple(results)
