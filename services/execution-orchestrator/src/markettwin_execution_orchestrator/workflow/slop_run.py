"""Slop run executor (U-P6-05): crawl the app on the Room, measure
every visited state, publish verdict rows. Judging is deterministic
code (slop/measure.py); aggregation happens in evaluation from the
published rows — the executor emits no percentage of its own.
"""

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_database.models import TestRun

from markettwin_execution_orchestrator.browser import BrowserController
from markettwin_execution_orchestrator.persistence import ExecutionRepository
from markettwin_execution_orchestrator.workflow.harness_state import canonical_url
from markettwin_execution_orchestrator.persistence.run_event_repository import (
    RunEventRepository,
)
from markettwin_execution_orchestrator.slop.measure import (
    dedupe_js_errors,
    measure_state,
)

if TYPE_CHECKING:
    from markettwin_execution_orchestrator.workflow.run_executor import (
        MarketTwinRunRequest,
    )

_MAX_STATES = 20


async def execute_slop_run(
    *, request: "MarketTwinRunRequest", session: AsyncSession,
) -> None:
    from markettwin_execution_orchestrator.persistence.run_state_repository import (
        RunStateRepository,
    )

    run = await session.get(TestRun, request.run_id)
    if run is None:
        raise ValueError("Slop run requires a persisted test run.")
    await RunStateRepository(session).mark_running(test_run_id=request.run_id)
    await session.commit()

    executions = ExecutionRepository(session)
    events = RunEventRepository(session)
    execution_id = uuid4()
    journey_id = uuid4()
    await executions.create_agent_execution(
        execution_id=execution_id, journey_id=journey_id,
        runtime_name="slop_crawl_v1",
    )
    await session.commit()

    async with BrowserController() as controller:
        handle = await controller.open_room_session(
            run_id=request.run_id, execution_id=execution_id,
            journey_id=journey_id, allowed_origins=request.allowed_origins,
            network_policy=request.network_policy, js_capture=True,
        )
        await executions.create_browser_session(
            browser_session_id=handle.session_id, execution_id=execution_id,
            test_run_id=request.run_id, session_role="room",
        )
        await session.commit()
        visited: set[str] = set()
        queue: list[str] = [request.start_url]
        # JS records are attributed by the URL captured ON the record,
        # never by harvest order: a slow timer from page A can fire
        # while page B is being measured, and it still belongs to A.
        consumed_by_url: dict[str, int] = {}
        states: list[dict] = []

        async def fresh_records_for(url: str) -> list[dict]:
            records = await controller.harvest_js_records(
                session_id=handle.session_id,
            )
            key = canonical_url(url)
            mine = [
                r for r in records if canonical_url(r.url) == key
            ]
            start = consumed_by_url.get(key, 0)
            consumed_by_url[key] = len(mine)
            return [
                {"kind": r.kind, "message": r.message, "stack": r.stack}
                for r in mine[start:]
            ]
        crawl_failed = False
        try:
            while queue and len(visited) < _MAX_STATES:
                url = queue.pop(0)
                if canonical_url(url) in visited:
                    continue
                visited.add(canonical_url(url))
                await controller.navigate(session_id=handle.session_id, url=url)
                # Let the page settle: scripts that throw on a timer
                # just after load are part of the visit's evidence.
                await controller.wait(
                    session_id=handle.session_id, milliseconds=300,
                )
                probe = await controller.probe_page(session_id=handle.session_id)
                new_records = await fresh_records_for(url)
                measured = measure_state(probe)
                measured["js_errors"] = dedupe_js_errors(
                    new_records, state_url=url,
                )
                states.append(measured)
                # Follow links the way the harness crawl does: through
                # the observation's visible links.
                state = await controller.get_state(
                    session_id=handle.session_id,
                    execution_id=execution_id, journey_id=journey_id,
                )
                for element in state.observation.visible_elements:
                    if element.role != "link" or not element.name:
                        continue
                    try:
                        landed = await controller.click(
                            session_id=handle.session_id, role="link",
                            name=element.name,
                            execution_id=execution_id, journey_id=journey_id,
                        )
                    except Exception:
                        continue
                    if canonical_url(str(landed.observation.url)) not in visited:
                        queue.append(str(landed.observation.url))
                    await controller.navigate(
                        session_id=handle.session_id, url=url,
                    )
            # Console-error severity pass: a console error that
            # reproduces on a re-visit is serious (catalogue rule);
            # a one-off stays minor.
            for measured in states:
                console_entries = [
                    e for e in measured["js_errors"]
                    if e["rule_id"] == "DEF_JS_CONSOLE_ERROR"
                ]
                if not console_entries:
                    continue
                await controller.navigate(
                    session_id=handle.session_id, url=str(measured["url"]),
                )
                await controller.probe_page(session_id=handle.session_id)
                revisit = await fresh_records_for(str(measured["url"]))
                reproduced = {
                    e["message"] for e in dedupe_js_errors(
                        revisit, state_url=str(measured["url"]),
                    ) if e["rule_id"] == "DEF_JS_CONSOLE_ERROR"
                }
                for entry in console_entries:
                    if entry["message"] in reproduced:
                        entry["severity"] = "serious"
            for measured in states:
                await events.create(
                    test_run_id=request.run_id,
                    event_type="slop.state.result",
                    journey_id=journey_id,
                    execution_id=execution_id,
                    payload={
                        "url": measured["url"],
                        "title": measured.get("title"),
                        "elements": measured["elements"],
                        "page_signals": measured["page_signals"],
                        "js_errors": measured["js_errors"],
                    },
                )
            await session.commit()
        except BaseException:
            crawl_failed = True
            raise
        finally:
            await controller.close_room(run_id=request.run_id)
            await executions.mark_browser_session_closed(
                browser_session_id=handle.session_id,
            )
            await executions.finish_agent_execution(
                execution_id=execution_id,
                status="failed" if crawl_failed else "completed",
                outcome=None,
            )
            await session.commit()
    # Reached only when the crawl finished: like the Board engine,
    # the executor owns the run's terminal state. Without this the
    # run stays "running" forever and a Kafka redelivery would mark
    # the finished run failed.
    await RunStateRepository(session).mark_completed(test_run_id=request.run_id)
    await session.commit()
