"""The grounding job (doc 21 section 6): lifecycle twin of the harvest.

Trigger (control-api) flips grounding_status to 'building'; this
poller claims the map with one atomic UPDATE, runs the eight stages
in order -- each stage's writes commit before the next stage runs --
heartbeats grounding_metrics per stage, and lands the section 15
gate, from which grounding_status itself derives (section 15.2).
Stage failures are recorded in the metrics failures list and the job
continues where honest; a job-level crash closes the map 'failed'
with the ORIGINAL error retained (Step 1 discipline).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from markettwin_database.models.knowledge import AppMap
from markettwin_shared.app_map_common import (
    ORACLE_SOURCES,
    compute_expectation_gate,
    expectation_coverage,
    expectation_verdict_eligible,
)

from . import authoring
from .adjudicate import AdjudicationLedger, adjudicate_match, draft_expectation
from .expectations_repository import GroundingRepository, SessionFactory
from .grounding import (
    Candidate,
    GraphIndex,
    MatchResult,
    ObservationFact,
    Subject,
    assemble_journeys,
    compile_assertion,
    extract_candidates,
    match_candidate,
    observation_facts,
    verify_assertion_against_graph,
)

# Doc 21 section 16 settings, as module constants (prep OQ1).
GROUNDING_POLL_SECONDS = 20  # [J]
GROUNDING_SLOTS = 1
GROUNDING_ORPHAN_MINUTES = 30
GROUNDING_UNMATCHED_LIST_CAP = 100
GROUNDING_FAILURE_LIST_CAP = 50

_KNOWN_STATUSES = ("unverified", "replay-verified", "owner-confirmed", "conflicted")


def empty_metrics() -> dict:
    """The section 6.4 closed metrics shape."""
    return {
        "candidates_total": 0,
        "candidates_by_source": {
            "documentation": 0,
            "observation": 0,
            "model-draft": 0,
        },
        "matched_deterministic": 0,
        "matched_adjudicated": 0,
        "unmatched_candidates": [],
        "authored_by_source_status": {},
        "assertions_compiled": {
            "deterministic": 0,
            "model-drafted": 0,
            "owner-entered": 0,
            "none": 0,
        },
        "adjudication_calls": 0,
        "adjudication_deferred": 0,
        "probes": {
            "attempted": 0,
            "probed": 0,
            "unprobed_destructive": 0,
            "skipped_no_standard_mode": 0,
        },
        "conflicts_opened": 0,
        "journeys_assembled": 0,
        "journey_terminals_named": 0,
        "promotions_at_grounding": 0,
        "failures": [],
        "gate": None,
    }


@dataclass
class GroundingContext:
    repository: GroundingRepository
    app_map: AppMap
    door: object | None = None
    ledger: AdjudicationLedger = field(default_factory=AdjudicationLedger)
    index: GraphIndex | None = None
    candidates: list[Candidate] = field(default_factory=list)
    facts: list[ObservationFact] = field(default_factory=list)
    matched: list[tuple[Candidate, Subject, dict | None]] = field(default_factory=list)
    drafts: list[tuple[Candidate, Subject, str, dict | None, float]] = field(
        default_factory=list
    )
    ambiguous: list[tuple[Candidate, MatchResult]] = field(default_factory=list)
    metrics: dict = field(default_factory=empty_metrics)
    open_conflicts_at_start: int = 0
    final_status: str | None = None

    @property
    def failures(self) -> list:
        return self.metrics["failures"]

    def record_failure(self, stage: str, exc: BaseException) -> None:
        failures = self.metrics["failures"]
        if len(failures) < GROUNDING_FAILURE_LIST_CAP:
            failures.append(
                {
                    "stage": stage,
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:500],
                }
            )
        elif failures and failures[-1].get("stage") == "overflow":
            failures[-1]["count"] = int(failures[-1].get("count", 0)) + 1
        else:
            failures.append({"stage": "overflow", "count": 1})

    def record_unmatched(self, candidate: Candidate, reason: str) -> None:
        unmatched = self.metrics["unmatched_candidates"]
        entry = {
            "entry_id": str(candidate.entry_id),
            "ordinal": candidate.ordinal,
            "reason": reason,
        }
        if len(unmatched) < GROUNDING_UNMATCHED_LIST_CAP:
            unmatched.append(entry)
        elif unmatched and unmatched[-1].get("reason") == "overflow":
            unmatched[-1]["count"] = int(unmatched[-1].get("count", 0)) + 1
        else:
            unmatched.append(
                {"entry_id": None, "ordinal": None, "reason": "overflow", "count": 1}
            )


@dataclass(frozen=True)
class GroundingStages:
    candidates: Callable[[GroundingContext], Awaitable[None]]
    match: Callable[[GroundingContext], Awaitable[None]]
    adjudicate: Callable[[GroundingContext], Awaitable[None]]
    author: Callable[[GroundingContext], Awaitable[None]]
    probe: Callable[[GroundingContext], Awaitable[None]]
    journeys: Callable[[GroundingContext], Awaitable[None]]
    conflicts: Callable[[GroundingContext], Awaitable[None]]
    gate: Callable[[GroundingContext], Awaitable[None]]

    def ordered(self) -> list[tuple[str, Callable[[GroundingContext], Awaitable[None]]]]:
        return [
            ("candidates", self.candidates),
            ("match", self.match),
            ("adjudicate", self.adjudicate),
            ("author", self.author),
            ("probe", self.probe),
            ("journeys", self.journeys),
            ("conflicts", self.conflicts),
            ("gate", self.gate),
        ]


# -- production stages -------------------------------------------------------


async def _stage_candidates(ctx: GroundingContext) -> None:
    repository = ctx.repository
    app_map = ctx.app_map
    entries = await repository.load_approved_entries(app_map.application_id)
    ctx.candidates = extract_candidates(entries)
    index = GraphIndex(
        pages=await repository.list_pages(app_map.id),
        states=await repository.list_states(app_map.id),
        elements=await repository.list_elements(app_map.id),
        forms=await repository.list_forms(app_map.id),
        fields=await repository.list_fields(app_map.id),
        transitions=await repository.list_transitions(app_map.id),
        journeys=await repository.list_journeys(app_map.id),
    )
    ctx.index = index
    ctx.facts = observation_facts(index)
    by_source = ctx.metrics["candidates_by_source"]
    by_source["documentation"] = len(ctx.candidates)
    by_source["observation"] = len(ctx.facts)
    ctx.metrics["candidates_total"] = len(ctx.candidates) + len(ctx.facts)


async def _stage_match(ctx: GroundingContext) -> None:
    assert ctx.index is not None
    for candidate in ctx.candidates:
        result = match_candidate(candidate, ctx.index)
        if result.outcome == "matched" and result.subject is not None:
            assertion = compile_assertion(candidate, result.subject, ctx.index)
            ctx.matched.append((candidate, result.subject, assertion))
        elif result.outcome == "ambiguous":
            ctx.ambiguous.append((candidate, result))
        else:
            ctx.record_unmatched(candidate, "no_subject_match")
    ctx.metrics["matched_deterministic"] = len(ctx.matched)


async def _stage_adjudicate(ctx: GroundingContext) -> None:
    assert ctx.index is not None
    if ctx.door is None:
        for candidate, _result in ctx.ambiguous:
            ctx.record_unmatched(candidate, "ambiguous_unresolved")
        ctx.ambiguous = []
        return
    still_matched: list[tuple[Candidate, Subject, dict | None]] = []
    for candidate, subject, assertion in ctx.matched:
        if assertion is not None:
            still_matched.append((candidate, subject, assertion))
            continue
        drafted = await draft_expectation(
            ctx.door, candidate, subject, ctx.index, ctx.ledger
        )
        if drafted is None:
            still_matched.append((candidate, subject, None))
            continue
        statement, drafted_assertion, confidence = drafted
        ctx.drafts.append(
            (candidate, subject, statement, drafted_assertion, confidence)
        )
    ctx.matched = still_matched
    for candidate, result in ctx.ambiguous:
        chosen, _confidence = await adjudicate_match(
            ctx.door, candidate, result.candidates, ctx.ledger
        )
        if chosen is None:
            ctx.record_unmatched(candidate, "ambiguous_unresolved")
            continue
        ctx.metrics["matched_adjudicated"] += 1
        assertion = compile_assertion(candidate, chosen, ctx.index)
        if assertion is not None:
            ctx.matched.append((candidate, chosen, assertion))
            continue
        drafted = await draft_expectation(
            ctx.door, candidate, chosen, ctx.index, ctx.ledger
        )
        if drafted is None:
            ctx.matched.append((candidate, chosen, None))
        else:
            statement, drafted_assertion, confidence = drafted
            ctx.drafts.append(
                (candidate, chosen, statement, drafted_assertion, confidence)
            )
    ctx.ambiguous = []
    ctx.metrics["adjudication_calls"] = ctx.ledger.calls
    ctx.metrics["adjudication_deferred"] = ctx.ledger.deferred


async def _stage_author(ctx: GroundingContext) -> None:
    assert ctx.index is not None
    repository = ctx.repository
    rejected = await repository.rejected_keys(ctx.app_map.id)
    authored = ctx.metrics["authored_by_source_status"]
    compiled = ctx.metrics["assertions_compiled"]

    def bump(source: str, status: str) -> None:
        key = f"{source}:{status}"
        authored[key] = int(authored.get(key, 0)) + 1

    for candidate, subject, assertion in ctx.matched:
        outcome = await authoring.author_expectation(
            repository,
            ctx.app_map,
            subject_kind=subject.kind,
            subject_id=subject.id,
            statement=candidate.content,
            oracle_source="documentation",
            source_ref=candidate.source_ref,
            confidence="high" if assertion is not None else "medium",
            assertion=assertion,
            assertion_origin="deterministic" if assertion is not None else None,
            rejected_keys=rejected,
            events=(
                ("authored", {"actor": "grounding"}),
                ("matched", {"actor": "grounding", "via": "deterministic"}),
            ),
            check_contradiction=True,
            index=ctx.index,
        )
        if outcome.created:
            bump("documentation", "unverified")
            compiled["deterministic" if assertion is not None else "none"] += 1
    for candidate, subject, statement, assertion, confidence in ctx.drafts:
        outcome = await authoring.author_expectation(
            repository,
            ctx.app_map,
            subject_kind=subject.kind,
            subject_id=subject.id,
            statement=statement,
            oracle_source="model-draft",
            source_ref=candidate.source_ref,
            confidence="medium" if confidence >= 0.5 else "low",
            assertion=assertion,
            assertion_origin="model-drafted" if assertion is not None else None,
            rejected_keys=rejected,
            events=(
                ("authored", {"actor": "grounding"}),
                ("adjudicated", {"actor": "grounding", "via": "draft_expectation"}),
            ),
            # Section 9.1 point 1: a drafted assertion can contradict
            # the graph (e.g. navigation to a different real page);
            # deterministic assertions derive from the graph itself.
            check_contradiction=True,
            index=ctx.index,
        )
        if outcome.created:
            bump("model-draft", "unverified")
            ctx.metrics["candidates_by_source"]["model-draft"] += 1
            compiled["model-drafted" if assertion is not None else "none"] += 1
    for fact in ctx.facts:
        outcome = await authoring.author_expectation(
            repository,
            ctx.app_map,
            subject_kind=fact.subject_kind,
            subject_id=fact.subject_id,
            statement=fact.statement,
            oracle_source="observation",
            source_ref=fact.source_ref,
            confidence="medium",
            assertion=fact.assertion,
            assertion_origin="deterministic",
            rejected_keys=rejected,
            events=(("authored", {"actor": "grounding"}),),
        )
        if outcome.created:
            bump("observation", "unverified")
            compiled["deterministic"] += 1


async def _stage_probe(ctx: GroundingContext) -> None:
    """Section 7 probing hook: preconditions absent -> the stage
    completes as skipped_no_standard_mode in metrics, not a failure."""
    assert ctx.index is not None
    forms_with_fields = [
        form
        for form in ctx.index.forms.values()
        if any(f.form_id == form.id for f in ctx.index.fields.values())
    ]
    trigger = {}
    if isinstance(ctx.app_map.grounding_metrics, dict):
        raw = ctx.app_map.grounding_metrics.get("trigger")
        if isinstance(raw, dict):
            trigger = raw
    approved = trigger.get("approved_test_data")
    if trigger.get("probe") is not True or not isinstance(approved, dict) or not approved:
        ctx.metrics["probes"]["skipped_no_standard_mode"] = len(forms_with_fields)
        return
    from . import probing

    outcome = await probing.run_probing(ctx, approved_test_data=approved)
    ctx.metrics["probes"] = outcome


async def _stage_journeys(ctx: GroundingContext) -> None:
    assert ctx.index is not None
    from markettwin_execution_orchestrator.harvest.harvest_skill import (
        CONVERSION_SEGMENTS,
    )

    terminals: dict[UUID, str] = {}
    for page in ctx.index.pages.values():
        if any(segment in page.canonical_url for segment in CONVERSION_SEGMENTS):
            terminals[page.id] = ""
    expectations = await ctx.repository.list_expectations(ctx.app_map.id)
    for expectation in expectations:
        if not isinstance(expectation.assertion, dict):
            continue
        if expectation.assertion.get("kind") != "journey_terminal":
            continue
        journey = ctx.index.journeys.get(expectation.subject_id)
        if journey is None:
            continue
        state = ctx.index.states.get(journey.success_state_id)
        if state is not None:
            terminals[state.map_page_id] = journey.name
    assembly = assemble_journeys(
        ctx.app_map, ctx.index, terminal_page_ids=terminals
    )
    for journey in assembly.journeys:
        await ctx.repository.insert_journey(ctx.app_map, journey)
    ctx.metrics["journeys_assembled"] = assembly.assembled
    ctx.metrics["journey_terminals_named"] = assembly.terminals_named


async def _stage_conflicts(ctx: GroundingContext) -> None:
    assert ctx.index is not None
    expectations = await ctx.repository.list_expectations(ctx.app_map.id)
    for expectation in expectations:
        if expectation.status == "conflicted" or expectation.superseded_by_id:
            continue
        verdict = verify_assertion_against_graph(expectation, ctx.index)
        if verdict is None:
            continue
        conflict_kind, observed, observed_subject_id = verdict
        already = await ctx.repository.find_open_conflict(
            expectation_id=expectation.id,
            conflict_kind=conflict_kind,
            observed_subject_id=observed_subject_id,
        )
        if already is None:
            await ctx.repository.insert_conflict(
                ctx.app_map,
                expectation,
                conflict_kind=conflict_kind,
                detection_source="verification",
                observed_behaviour=observed,
                observed_subject_id=observed_subject_id,
            )
    open_now = len(
        [
            conflict
            for conflict in await ctx.repository.list_conflicts(ctx.app_map.id)
            if conflict.status == "open"
        ]
    )
    ctx.metrics["conflicts_opened"] = max(
        0, open_now - ctx.open_conflicts_at_start
    )


async def _stage_gate(ctx: GroundingContext) -> None:
    assert ctx.index is not None
    repository = ctx.repository
    expectations = await repository.list_expectations(ctx.app_map.id)
    journeys = await repository.list_journeys(ctx.app_map.id)
    subjects_by_state: dict[UUID, set[str]] = {}
    for element in ctx.index.elements.values():
        subjects_by_state.setdefault(element.map_page_state_id, set()).add(str(element.id))
    for field_row in ctx.index.fields.values():
        form = ctx.index.forms.get(field_row.form_id)
        if form is not None:
            subjects_by_state.setdefault(form.map_page_state_id, set()).add(str(field_row.id))
    journey_inputs = []
    for journey in journeys:
        traversed: set[str] = set()
        subjects = set(subjects_by_state.get(journey.success_state_id, ()))
        for step in journey.steps or []:
            if not isinstance(step, dict):
                continue
            element_id = step.get("element_id")
            element = (
                ctx.index.elements.get(UUID(element_id))
                if isinstance(element_id, str)
                else None
            )
            if element is not None:
                traversed.add(str(element.map_page_id))
                subjects.add(str(element.id))
            state_id = step.get("map_page_state_id")
            state = (
                ctx.index.states.get(UUID(state_id))
                if isinstance(state_id, str)
                else None
            )
            if state is not None:
                traversed.add(str(state.map_page_id))
                subjects.update(subjects_by_state.get(state.id, ()))
        journey_inputs.append(
            {
                "id": str(journey.id),
                "intent": journey.intent,
                "traversed_page_ids": traversed,
                "subject_ids": subjects,
            }
        )
    subject_page: dict[str, str] = {}
    for element in ctx.index.elements.values():
        subject_page[str(element.id)] = str(element.map_page_id)
    for field_row in ctx.index.fields.values():
        form = ctx.index.forms.get(field_row.form_id)
        if form is not None:
            subject_page[str(field_row.id)] = str(form.map_page_id)
    expectation_inputs = [
        {
            "subject_kind": row.subject_kind,
            "subject_id": str(row.subject_id),
            "subject_page_id": subject_page.get(str(row.subject_id)),
            "oracle_source": row.oracle_source,
            "status": row.status,
            "assertion": row.assertion,
            "assertion_origin": row.assertion_origin,
            "promoted_by": row.promoted_by,
            "superseded_by_id": row.superseded_by_id,
        }
        for row in expectations
        if row.superseded_by_id is None
    ]
    coverage = expectation_coverage(
        journeys=journey_inputs, expectations=expectation_inputs
    )
    eligible_with_assertion = 0
    taxonomy_violations = 0
    for row in expectations:
        record = {
            "oracle_source": row.oracle_source,
            "status": row.status,
            "superseded_by_id": row.superseded_by_id,
            "assertion": row.assertion,
            "assertion_origin": row.assertion_origin,
            "promoted_by": row.promoted_by,
        }
        if expectation_verdict_eligible(record) and row.assertion is not None:
            eligible_with_assertion += 1
        if row.oracle_source not in ORACLE_SOURCES or row.status not in _KNOWN_STATUSES:
            taxonomy_violations += 1
        elif row.promoted_by is not None and row.status != "owner-confirmed":
            taxonomy_violations += 1
    conflicts_open = len(
        [
            conflict
            for conflict in await repository.list_conflicts(ctx.app_map.id)
            if conflict.status == "open"
        ]
    )
    gate = compute_expectation_gate(
        coverage,
        {
            "eligible_with_assertion": eligible_with_assertion,
            "conflicts_open": conflicts_open,
            # No audit has run yet: the grounding sweep's own count
            # governs, labelled as such (section 15.1).
            "taxonomy_violations_open": None,
            "sweep_violations": taxonomy_violations,
            "grounding_completed": True,
            "accounting_complete": (
                ctx.metrics["adjudication_calls"] == ctx.ledger.calls
            ),
        },
    )
    ctx.metrics["gate"] = gate.metrics()["expectation_gate"]
    status = "ready" if gate.release_scope == "expectations" else "partial"
    ctx.final_status = status
    await repository.complete_grounding(
        ctx.app_map.id, status=status, metrics=ctx.metrics
    )


def production_stages(door: object | None) -> GroundingStages:
    return GroundingStages(
        candidates=_stage_candidates,
        match=_stage_match,
        adjudicate=_stage_adjudicate,
        author=_stage_author,
        probe=_stage_probe,
        journeys=_stage_journeys,
        conflicts=_stage_conflicts,
        gate=_stage_gate,
    )


# -- lifecycle -----------------------------------------------------------------


async def execute_grounding(
    repository: GroundingRepository,
    app_map: AppMap,
    stages: GroundingStages,
    *,
    door: object | None = None,
) -> str:
    """Run one claimed grounding to its gate (or an honest failure)."""
    ctx = GroundingContext(repository=repository, app_map=app_map, door=door)
    previous_calls = (app_map.grounding_metrics or {}).get("adjudication_calls", 0)
    if isinstance(previous_calls, int) and not isinstance(previous_calls, bool):
        ctx.ledger.calls = max(0, previous_calls)
    ctx.metrics["adjudication_calls"] = ctx.ledger.calls
    try:
        ctx.open_conflicts_at_start = len(
            [
                conflict
                for conflict in await repository.list_conflicts(app_map.id)
                if conflict.status == "open"
            ]
        )
        for name, stage in stages.ordered():
            if name == "gate":
                continue
            try:
                await stage(ctx)
            except Exception as exc:  # per-stage: recorded, job continues
                ctx.record_failure(name, exc)
            ctx.metrics["adjudication_calls"] = ctx.ledger.calls
            ctx.metrics["adjudication_deferred"] = ctx.ledger.deferred
            await repository.save_grounding_metrics(app_map.id, ctx.metrics)
        await stages.gate(ctx)
        return ctx.final_status or "partial"
    except Exception as exc:
        await repository.fail_grounding(
            app_map.id,
            failure_code=type(exc).__name__,
            failure_message=str(exc),
            failure_site="grounding_job.execute_grounding",
            metrics=ctx.metrics,
        )
        return "failed"


async def _reap_orphans(
    repository: GroundingRepository,
    running: dict[UUID, asyncio.Task],
    *,
    now: datetime | None = None,
) -> None:
    """Fail groundings wedged in 'building' past the orphan window."""
    now = now or datetime.now(UTC)
    for app_map in await repository.list_building_grounding():
        started = app_map.grounding_started_at
        if started is None:
            continue
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        completed = app_map.grounding_completed_at
        if completed is not None:
            if completed.tzinfo is None:
                completed = completed.replace(tzinfo=UTC)
            if completed >= started:
                continue
        if now - started < timedelta(minutes=GROUNDING_ORPHAN_MINUTES):
            continue
        task = running.pop(app_map.id, None)
        if task is not None and not task.done():
            task.cancel()
        await repository.fail_grounding(
            app_map.id,
            failure_code="grounding_orphaned",
            failure_message=(
                "Grounding was claimed but never completed inside the "
                f"{GROUNDING_ORPHAN_MINUTES}-minute window; closed as an "
                "orphan so the map can be re-grounded."
            ),
            failure_site="grounding_job._reap_orphans",
        )


async def _supervise(
    repository: GroundingRepository,
    stages: GroundingStages,
    running: dict[UUID, asyncio.Task],
    *,
    door: object | None = None,
) -> None:
    # Finished tasks drop out; execute_grounding records its own failures.
    for map_id in [mid for mid, task in running.items() if task.done()]:
        running.pop(map_id)
    await _reap_orphans(repository, running)
    while len(running) < GROUNDING_SLOTS:
        claimed = await repository.claim_next_grounding_job()
        if claimed is None:
            break
        running[claimed.id] = asyncio.create_task(
            execute_grounding(repository, claimed, stages, door=door)
        )


_knowledge_storage = None  # S3ArtifactStorage, built lazily on first read


async def _knowledge_file_text(object_key: str) -> str:
    """Read one approved knowledge file's Markdown (doc 33 step 6 wiring).

    The storage client is built once, from the worker's S3 environment.
    A missing configuration raises here, so the grounding job fails
    loudly instead of silently authoring no documentation candidates.
    """
    global _knowledge_storage
    if _knowledge_storage is None:
        from ..persistence.artifact_storage import S3ArtifactStorage

        _knowledge_storage = S3ArtifactStorage.from_environment()
    return await _knowledge_storage.download_text(object_key=object_key)


async def run_grounding_poller(
    session_factory: SessionFactory,
    *,
    door: object | None = None,
    poll_seconds: int = GROUNDING_POLL_SECONDS,
) -> None:
    """Worker entry point: supervise grounding jobs until cancelled."""
    if door is None:
        from .adjudicate import AskAdjudicationDoor

        door = AskAdjudicationDoor()
    repository = GroundingRepository(
        session_factory, knowledge_text=_knowledge_file_text
    )
    stages = production_stages(door)
    running: dict[UUID, asyncio.Task] = {}
    while True:
        try:
            await _supervise(repository, stages, running, door=door)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # next poll retries; claims are atomic
        await asyncio.sleep(poll_seconds)
