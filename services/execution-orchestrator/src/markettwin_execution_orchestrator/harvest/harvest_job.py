"""The harvest job (doc 16 section 6): a run-shaped worker job.

A poller claims building harvests under a per-map advisory lock (the
partial unique index on app_maps is the database backstop), drives
the stages — capture, enrichment, compile, replay — inside the wall
budget, and lands the shared gate's verdict. Harvest events double
as the watchdog heartbeat: a supervision pass mirrors the run stall
watchdog (a building harvest silent for the watchdog window is
cancelled once and closed failed with the reason retained), and
orphaned claims — a dead worker's lock is free while the map still
says building with old events — are reaped on 30 minutes of event
silence.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from markettwin_shared.app_map_common import compute_harvest_gate
from sqlalchemy import text

from markettwin_execution_orchestrator.harvest.harvest_repository import (
    HarvestRepository,
    harvest_metric_counts,
)
from markettwin_execution_orchestrator.worker import STALL_WATCHDOG_SECONDS

logger = logging.getLogger(__name__)

HARVEST_POLL_SECONDS = 5  # prep OQ1: no orchestrator config module exists
HARVEST_SLOTS = 1  # one heavy browser job at a time on the host
HARVEST_PAGE_BUDGET_SECONDS = 60  # [J] doc 16 section 13
HARVEST_WALL_BUDGET_SECONDS = 7200  # [J] doc 16 section 13
HARVEST_ORPHAN_EVENT_MINUTES = 30  # doc 16 section 6.2


@dataclass
class HarvestContext:
    """What the stages share: capture fills the graph data, enrichment
    and compile consume it, replay verifies what compile produced."""

    repository: HarvestRepository
    app_map: Any
    group_entries: list[tuple[Any, str | None]] = field(default_factory=list)
    page_exemplars: dict[UUID, Any] = field(default_factory=dict)
    nodes: dict[UUID, Any] = field(default_factory=dict)
    edges: list[Any] = field(default_factory=list)
    base_node: Any | None = None
    wall_cap_reached: bool = False
    wall_unprobed: int = 0
    enrich_result: Any | None = None
    compile_result: Any | None = None


@dataclass
class HarvestStages:
    capture: Any  # async (ctx) -> None
    enrich: Any  # async (ctx) -> EnrichResult
    compile: Any  # async (ctx) -> CompileResult | None
    replay: Any  # async (ctx) -> VerifyResult | None


class AdvisoryClaim:
    """Keep the advisory lock on one checked-out database connection."""

    def __init__(self, session_factory: Any, key: str) -> None:
        self._engine = session_factory.kw["bind"]
        self._key = key
        self._context: Any | None = None
        self._connection: Any | None = None

    async def acquire(self) -> bool:
        context = self._engine.connect()
        connection = await context.__aenter__()
        try:
            locked = await connection.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
                {"key": self._key},
            )
            await connection.commit()
        except BaseException:
            try:
                await connection.invalidate()
            finally:
                await context.__aexit__(None, None, None)
            raise
        if not locked:
            await context.__aexit__(None, None, None)
            return False
        self._context = context
        self._connection = connection
        return True

    async def release(self) -> None:
        connection, context = self._connection, self._context
        self._connection = None
        self._context = None
        if connection is None or context is None:
            return
        try:
            await connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                {"key": self._key},
            )
            await connection.commit()
        except BaseException:
            await connection.invalidate()
            raise
        finally:
            await context.__aexit__(None, None, None)


async def execute_harvest(
    repository: HarvestRepository,
    app_map: Any,
    stages: HarvestStages,
    *,
    wall_seconds: float = HARVEST_WALL_BUDGET_SECONDS,
) -> str:
    """Run one claimed harvest to its gate. Returns the final
    harvest_status. Stage failures land on the map row with the
    original error retained (doc 16 section 12); the gate is never
    evaluated for a crashed job."""
    stage = "capture"
    try:
        counts = await repository.harvest_counts(app_map.id)
        await repository.record_event(
            app_map.id,
            "harvest.started",
            {"pages_total": counts["reachable"]},
        )
        ctx = HarvestContext(repository=repository, app_map=app_map)
        started = time.monotonic()
        await stages.capture(ctx)
        if ctx.wall_cap_reached:
            await repository.record_event(
                app_map.id,
                "harvest.cap.reached",
                {"kind": "wall", "spend": {"unprobed": ctx.wall_unprobed}},
            )
        await repository.record_event(
            app_map.id,
            "harvest.stage.completed",
            {
                "stage": "capture",
                "counts": {"pages_visited": len(ctx.group_entries)},
            },
        )
        stage = "enrichment"
        ctx.enrich_result = await stages.enrich(ctx)
        if ctx.enrich_result is not None and ctx.enrich_result.cap_reached:
            await repository.record_event(
                app_map.id,
                "harvest.cap.reached",
                {
                    "kind": ctx.enrich_result.cap_reached,
                    "spend": {
                        "calls": ctx.enrich_result.spend_calls,
                        "tokens": ctx.enrich_result.spend_tokens,
                    },
                },
            )
        await repository.record_event(
            app_map.id,
            "harvest.stage.completed",
            {
                "stage": "enrichment",
                "counts": {
                    "enriched_groups": (
                        ctx.enrich_result.enriched_groups
                        if ctx.enrich_result is not None
                        else 0
                    )
                },
            },
        )
        stage = "compile"
        ctx.compile_result = await stages.compile(ctx)
        await repository.record_event(
            app_map.id,
            "harvest.stage.completed",
            {
                "stage": "compile",
                "counts": {
                    "compiled": (
                        1
                        if (
                            ctx.compile_result is not None
                            and ctx.compile_result.skill_version is not None
                        )
                        else 0
                    )
                },
            },
        )
        verify = None
        if (
            ctx.compile_result is not None
            and ctx.compile_result.skill_version is not None
        ):
            stage = "replay"
            verify = await stages.replay(ctx)
            if verify is not None and verify.heal is not None:
                await repository.record_event(
                    app_map.id,
                    "harvest.skill.healed",
                    {
                        "step": verify.heal.step,
                        "from_locator": verify.heal.from_locator,
                        "to_locator": verify.heal.to_locator,
                    },
                )
            await repository.record_event(
                app_map.id,
                "harvest.stage.completed",
                {
                    "stage": "replay",
                    "counts": {"attempts": verify.attempts if verify else 0},
                },
            )
        stage = "gate"
        gate_counts = await repository.harvest_counts(app_map.id)
        fresh = await repository.get_map(app_map.id)
        template_groups, enriched_groups = harvest_metric_counts(
            fresh.harvest_metrics if fresh is not None else None
        )
        skill_verified = verify is not None and verify.lifecycle_status in (
            "replay_verified",
            "active",
        )
        skill_reason = _skill_gate_reason(ctx, verify)
        gate_counts.update(
            enriched_groups=enriched_groups,
            template_groups=template_groups,
            spend_calls=(fresh.mapping_spend_calls or 0) if fresh else 0,
            spend_tokens=(fresh.mapping_spend_tokens or 0) if fresh else 0,
            skill_verified=skill_verified,
            skill_reason=skill_reason,
        )
        gate = compute_harvest_gate(gate_counts)
        await repository.apply_gate(app_map.id, gate=gate)
        await repository.record_event(
            app_map.id,
            "harvest.completed",
            {
                "harvest_status": gate.harvest_status,
                "gate_rule": "harvest-1b.1",
            },
        )
        # Phase 3 library stage (doc 22 sections 6.1, 6.2): compile
        # every journey of this map into the library and run the
        # activation pass. Failure-isolated: a library failure never
        # fails the harvest — it is recorded and the poller retries
        # on its own cadence.
        try:
            from markettwin_execution_orchestrator.harvest.skill_library import (
                activate_current_versions,
                compile_all_journeys,
            )

            library_counts = await compile_all_journeys(
                repository,
                app_map,
                application_name=await repository.application_name(
                    app_map.application_id
                ),
            )
            activation_counts = await activate_current_versions(
                repository, app_map
            )
            await repository.record_event(
                app_map.id,
                "harvest.library.completed",
                {
                    "compiled": library_counts["compiled"],
                    "skipped": library_counts["skipped"],
                    "compile_failed": library_counts["failed"],
                    "activated": activation_counts["activated"],
                },
            )
        except Exception:
            logger.exception(
                "Skill library stage failed for harvest %s", app_map.id
            )
            try:
                await repository.record_event(
                    app_map.id,
                    "harvest.library.failed",
                    {"failure_site": "harvest_job:library_stage"},
                )
            except Exception:
                pass
        logger.info(
            "Harvest %s finished: %s in %.1fs",
            app_map.id,
            gate.harvest_status,
            time.monotonic() - started,
        )
        return gate.harvest_status
    except asyncio.CancelledError:
        # The supervision watchdog cancelled us: close the job failed
        # with the reason retained, then let the cancellation stand.
        try:
            await repository.fail_harvest(
                app_map.id,
                failure_code="harvest_stalled",
                failure_message=(
                    "harvest produced no events for the watchdog window"
                ),
                failure_site="harvest_job:stall_watchdog",
            )
            await repository.record_event(
                app_map.id,
                "harvest.failed",
                {
                    "failure_code": "harvest_stalled",
                    "failure_site": "harvest_job:stall_watchdog",
                },
            )
        except Exception:
            pass
        raise
    except Exception as exc:
        site = f"harvest_job:{stage}"
        try:
            await repository.fail_harvest(
                app_map.id,
                failure_code=type(exc).__name__,
                failure_message=str(exc)[:2000],
                failure_site=site,
            )
            await repository.record_event(
                app_map.id,
                "harvest.failed",
                {"failure_code": type(exc).__name__, "failure_site": site},
            )
        except Exception:
            pass
        logger.exception("Harvest %s failed at stage %s", app_map.id, stage)
        return "failed"


def _skill_gate_reason(ctx: HarvestContext, verify: Any | None) -> str | None:
    if verify is not None:
        if verify.lifecycle_status in ("replay_verified", "active"):
            return None
        return "skill_quarantined"
    compile_result = ctx.compile_result
    if compile_result is None:
        return "no_journey_compiled"
    if compile_result.registry_error:
        return f"skill_registry_blocked: {compile_result.registry_error}"[:200]
    if compile_result.skill_version is None:
        return "no_skill_compiled"
    return "skill_not_verified"


# --- production stages -------------------------------------------------------


def production_stages(repository: HarvestRepository) -> HarvestStages:
    """The real stages: browser capture, model enrichment (the one
    model surface), BFS compile, clean-context replay."""
    from markettwin_execution_orchestrator.harvest.harvest_enrich import (
        ModelApiDoor,
        default_accountant,
        enrich_map,
        group_pages,
    )
    from markettwin_execution_orchestrator.harvest.harvest_inventory import (
        visit_page,
    )
    from markettwin_execution_orchestrator.harvest.harvest_replay import (
        CaseExecutionReplayExecutor,
        verify_skill,
    )
    from markettwin_execution_orchestrator.harvest.harvest_skill import (
        JourneyEdge,
        JourneyNode,
        compile_journey,
        select_journey,
    )

    async def capture(ctx: HarvestContext) -> None:
        from markettwin_execution_orchestrator.browser.controller import (
            BrowserController,
        )
        from markettwin_execution_orchestrator.browser.contracts import (
            AllowedOrigin,
        )
        from markettwin_execution_orchestrator.harvest.harvest_capture import (
            NetworkCapture,
        )
        from markettwin_execution_orchestrator.harvest.harvest_enrich import (
            Exemplar,
        )

        app_map = ctx.app_map
        parts = urlsplit(app_map.base_url)
        origin = AllowedOrigin(
            scheme=parts.scheme,
            hostname=parts.hostname or "",
            port=parts.port or (443 if parts.scheme == "https" else 80),
        )
        controller = BrowserController()
        execution_id = uuid4()
        journey_id = uuid4()
        handle = await controller.open_room_session(
            run_id=app_map.id,
            execution_id=execution_id,
            journey_id=journey_id,
            allowed_origins=[origin],
            network_policy="public_only",
            js_capture=True,
        )
        network = NetworkCapture()
        try:
            session = controller._get_session(  # pyright: ignore[reportPrivateUsage]
                session_id=handle.session_id
            )
            network.install(session.context)
            pages = await repository.work_list(app_map)
            wall_deadline = time.monotonic() + HARVEST_WALL_BUDGET_SECONDS
            for index, page in enumerate(pages):
                if time.monotonic() > wall_deadline:
                    ctx.wall_cap_reached = True
                    for remaining in pages[index:]:
                        await repository.mark_page_harvest(
                            remaining.id, "unprobed_budget"
                        )
                        await repository.record_event(
                            app_map.id,
                            "harvest.page.disposition",
                            {
                                "url": remaining.canonical_url,
                                "harvest_status": "unprobed_budget",
                                "reason": "wall_budget",
                            },
                        )
                        ctx.wall_unprobed += 1
                    break
                page_deadline = min(
                    time.monotonic() + HARVEST_PAGE_BUDGET_SECONDS,
                    wall_deadline,
                )
                outcome = await visit_page(
                    controller=controller,
                    handle=handle,
                    repository=repository,
                    store=_evidence_store(),
                    app_map=app_map,
                    page=page,
                    execution_id=execution_id,
                    journey_id=journey_id,
                    network=network,
                    deadline=page_deadline,
                )
                await repository.mark_page_harvest(page.id, outcome.disposition)
                if outcome.disposition == "visited":
                    await repository.record_event(
                        app_map.id,
                        "harvest.page.completed",
                        {
                            "url": page.canonical_url,
                            "states": outcome.states,
                            "elements": outcome.elements,
                            "forms": outcome.forms,
                            "transitions": outcome.transitions,
                            "evidence_objects": outcome.evidence_objects,
                        },
                    )
                    default_state = await repository.get_default_state(page.id)
                    if default_state is not None:
                        ctx.group_entries.append(
                            (page, default_state.dom_structure_hash)
                        )
                        elements = await repository.list_elements_for_state(
                            default_state.id
                        )
                        fields = await repository.list_fields_for_state(
                            default_state.id
                        )
                        ctx.page_exemplars[page.id] = Exemplar(
                            url=page.canonical_url,
                            route_pattern=page.route_pattern,
                            title=page.title or "",
                            element_names=[
                                element.name for element in elements
                            ],
                            form_labels=[field.label for field in fields],
                            aria_excerpt=outcome.aria_excerpt,
                        )
                else:
                    await repository.record_event(
                        app_map.id,
                        "harvest.page.disposition",
                        {
                            "url": page.canonical_url,
                            "harvest_status": outcome.disposition,
                            "reason": outcome.reason,
                        },
                    )
                    if outcome.disposition == "failed":
                        await repository.append_page_failure(
                            app_map.id,
                            {
                                "url": page.canonical_url,
                                "reason": outcome.reason,
                            },
                        )
            await _assemble_graph(ctx)
        finally:
            from markettwin_execution_orchestrator.workflow.slop_run import (
                TEARDOWN_TIMEOUT_SECONDS,
            )

            try:
                async with asyncio.timeout(TEARDOWN_TIMEOUT_SECONDS):
                    await controller.close_room(run_id=app_map.id)
            except Exception:
                pass

    async def _assemble_graph(ctx: HarvestContext) -> None:
        """Nodes and edges for journey selection, from the harvested
        states and transitions (default states only: journeys walk
        defaults, doc 16 section 5.7)."""
        app_map = ctx.app_map
        states = await repository.list_states_for_map(app_map.id)
        pages = await repository.work_list(app_map)
        pages_by_id = {page.id: page for page in pages}
        default_by_page: dict[UUID, Any] = {}
        state_page: dict[UUID, UUID] = {}
        for state in states:
            state_page[state.id] = state.map_page_id
            if state.state_key == "default":
                default_by_page[state.map_page_id] = state
        nodes: dict[UUID, JourneyNode] = {}
        for page_id, state in default_by_page.items():
            page = pages_by_id.get(page_id)
            if page is None:
                continue
            signature = (
                state.element_signature.split(";")
                if state.element_signature
                else []
            )
            nodes[page_id] = JourneyNode(
                page_id=page_id,
                canonical_url=page.canonical_url,
                default_state_id=state.id,
                default_state_identity=state.state_id,
                default_element_signature=signature,
            )
        edges: list[JourneyEdge] = []
        transitions = await repository.list_transitions(app_map.id)
        for transition in transitions:
            from_page = state_page.get(transition.from_state_id)
            to_page = state_page.get(transition.to_state_id)
            if from_page is None or to_page is None or from_page == to_page:
                continue
            if default_by_page.get(from_page) is None:
                continue
            if default_by_page[from_page].id != transition.from_state_id:
                continue
            if default_by_page.get(to_page) is None:
                continue
            if default_by_page[to_page].id != transition.to_state_id:
                continue
            if transition.via_element_id is None:
                continue
            element = await repository.get_element(transition.via_element_id)
            if element is None:
                continue
            edges.append(
                JourneyEdge(
                    from_page_id=from_page,
                    from_state_id=transition.from_state_id,
                    element_id=element.id,
                    role=element.role,
                    name=element.name,
                    locators=list(element.locators or []),
                    to_page_id=to_page,
                )
            )
        ctx.nodes = nodes
        ctx.edges = edges
        base_page = next(
            (page for page in pages if page.canonical_url == app_map.base_url),
            pages[0] if pages else None,
        )
        ctx.base_node = (
            nodes.get(base_page.id) if base_page is not None else None
        )

    async def enrich(ctx: HarvestContext) -> Any:
        groups = group_pages(ctx.group_entries)
        exemplars = {}
        for group_key, group_pages_list in groups.items():
            exemplar_page = sorted(
                group_pages_list, key=lambda page: page.canonical_url
            )[0]
            exemplar = ctx.page_exemplars.get(exemplar_page.id)
            if exemplar is not None:
                exemplars[group_key] = exemplar
        return await enrich_map(
            repository=repository,
            app_map=ctx.app_map,
            groups=groups,
            exemplars=exemplars,
            door=ModelApiDoor(),
            accountant=default_accountant,
        )

    async def compile_stage(ctx: HarvestContext) -> Any:
        if ctx.base_node is None:
            await repository.save_harvest_metrics(
                ctx.app_map.id,
                {
                    "skill_compile": {
                        "result": "failed",
                        "reason": "no_base_page",
                    }
                },
            )
            return None
        owner_terminal = (ctx.app_map.harvest_metrics or {}).get(
            "journey_terminal_url"
        )
        selection = select_journey(
            nodes=ctx.nodes,
            edges=ctx.edges,
            base_page_id=ctx.base_node.page_id,
            owner_terminal_url=owner_terminal,
        )
        if selection is None:
            await repository.save_harvest_metrics(
                ctx.app_map.id,
                {
                    "skill_compile": {
                        "result": "failed",
                        "reason": "no_journey",
                    }
                },
            )
            return None
        await repository.save_harvest_metrics(
            ctx.app_map.id, {"journey_selection": dict(selection.detail)}
        )
        journey_name = _journey_name(ctx, selection)
        application_name = await repository.application_name(
            ctx.app_map.application_id
        )
        return await compile_journey(
            repository=repository,
            app_map=ctx.app_map,
            selection=selection,
            base_node=ctx.base_node,
            nodes=ctx.nodes,
            journey_name=journey_name,
            application_name=application_name,
        )

    async def replay(ctx: HarvestContext) -> Any:
        from markettwin_execution_orchestrator.browser.controller import (
            BrowserController,
        )

        compile_result = ctx.compile_result
        controller = BrowserController()
        executor = CaseExecutionReplayExecutor(
            controller, app_map=ctx.app_map
        )
        return await verify_skill(
            repository=repository,
            app_map=ctx.app_map,
            skill_version=compile_result.skill_version,
            definition=compile_result.definition,
            executor=executor,
            start_state_id=(
                ctx.base_node.default_state_identity
                if ctx.base_node is not None
                else None
            ),
        )

    return HarvestStages(
        capture=capture, enrich=enrich, compile=compile_stage, replay=replay
    )


def _journey_name(ctx: HarvestContext, selection: Any) -> str:
    """The enrichment draft's journey name for the terminal's group
    when one exists; otherwise a name from the terminal's last path
    segment (doc 16 section 5.7)."""
    metrics = ctx.app_map.harvest_metrics or {}
    enrichment = metrics.get("group_enrichment") or {}
    terminal_group = None
    for page, _hash in ctx.group_entries:
        if page.id == selection.terminal.page_id:
            terminal_group = page.template_group
    if terminal_group and isinstance(enrichment, dict):
        draft = enrichment.get(terminal_group) or {}
        if isinstance(draft, dict) and draft.get("journey_name"):
            return str(draft["journey_name"])
    segments = [
        segment
        for segment in urlsplit(selection.terminal.canonical_url).path.split("/")
        if segment
    ]
    if segments:
        return f"Reach {segments[-1].replace('-', ' ')}"
    return "Reach the terminal page"


def _evidence_store() -> Any:
    from markettwin_execution_orchestrator.persistence.artifact_storage import (
        S3ArtifactStorage,
    )
    from markettwin_execution_orchestrator.harvest.harvest_capture import (
        S3EvidenceStore,
    )

    return S3EvidenceStore(S3ArtifactStorage.from_environment())


# --- poller, claim, supervision ------------------------------------------------

_harvest_tasks: dict[UUID, asyncio.Task[None]] = {}
_harvest_cancelling: set[UUID] = set()


async def _run_claimed(
    repository: HarvestRepository,
    app_map: Any,
    claim: AdvisoryClaim,
    stages: HarvestStages,
) -> None:
    try:
        await execute_harvest(repository, app_map, stages)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Harvest %s escaped execute_harvest", app_map.id)
    finally:
        await claim.release()


async def _supervise(repository: HarvestRepository) -> None:
    """Cancel a claimed harvest whose event heartbeat has been silent
    for the watchdog window (mirrors the run stall watchdog)."""
    now = datetime.now(UTC)
    for map_id, task in list(_harvest_tasks.items()):
        if task.done():
            _harvest_tasks.pop(map_id, None)
            _harvest_cancelling.discard(map_id)
            continue
        if map_id in _harvest_cancelling:
            continue
        latest = await repository.latest_event_at(map_id)
        if latest is None:
            continue
        if now - latest > timedelta(seconds=STALL_WATCHDOG_SECONDS):
            _harvest_cancelling.add(map_id)
            task.cancel()


async def _reap_orphans(
    repository: HarvestRepository, session_factory: Any
) -> None:
    """A building harvest with no live claim and 30 minutes of event
    silence belonged to a dead worker: close it failed (doc 16
    section 6.2). The claim attempt is the liveness test — a live
    worker holds its lock."""
    cutoff = datetime.now(UTC) - timedelta(
        minutes=HARVEST_ORPHAN_EVENT_MINUTES
    )
    for app_map in await repository.list_building_harvests():
        if app_map.id in _harvest_tasks:
            continue
        latest = await repository.latest_event_at(app_map.id)
        # Silence is measured from the last sign of life: the latest
        # event, or the harvest's start when no event exists yet. A
        # just-triggered harvest has no events and a fresh start, so
        # it is never reaped before its first claim.
        reference = latest or app_map.harvest_started_at
        if reference is None or reference > cutoff:
            continue
        claim = AdvisoryClaim(session_factory, f"harvest:{app_map.id}")
        if not await claim.acquire():
            continue
        try:
            await repository.fail_harvest(
                app_map.id,
                failure_code="harvest_orphaned",
                failure_message=(
                    "harvest worker disappeared with the job in flight"
                ),
                failure_site="harvest_job:orphan_reaper",
            )
            await repository.record_event(
                app_map.id,
                "harvest.failed",
                {
                    "failure_code": "harvest_orphaned",
                    "failure_site": "harvest_job:orphan_reaper",
                },
            )
        finally:
            await claim.release()


async def _poll_once(
    repository: HarvestRepository,
    session_factory: Any,
    stages_factory: Any,
) -> None:
    await _supervise(repository)
    await _reap_orphans(repository, session_factory)
    if len(_harvest_tasks) >= HARVEST_SLOTS:
        return
    for app_map in await repository.list_building_harvests():
        if len(_harvest_tasks) >= HARVEST_SLOTS:
            break
        if app_map.id in _harvest_tasks:
            continue
        claim = AdvisoryClaim(session_factory, f"harvest:{app_map.id}")
        if not await claim.acquire():
            continue
        stages = stages_factory(repository)
        _harvest_tasks[app_map.id] = asyncio.create_task(
            _run_claimed(repository, app_map, claim, stages)
        )


async def run_harvest_poller(
    session_factory: Any, *, stages_factory: Any = production_stages
) -> None:
    """The worker's harvest loop (doc 16 section 6.1): claim, run,
    supervise, reap — forever, on the poll cadence."""
    repository = HarvestRepository(session_factory)
    while True:
        try:
            await _poll_once(repository, session_factory, stages_factory)
        except Exception:
            logger.exception("Harvest poll failed; continuing")
        await asyncio.sleep(HARVEST_POLL_SECONDS)
