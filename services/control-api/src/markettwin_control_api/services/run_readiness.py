"""Read-only readiness and stall reasons; no provider calls or run-state mutation."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from markettwin_database.models import OutboxEvent, Report, RunEvent, WorkerHeartbeat
from markettwin_shared.messaging import KafkaProducer
from markettwin_shared.run_failure import public_failure_details
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.config import Settings
from markettwin_control_api.knowledge import map_repository
from markettwin_control_api.persistence.repositories import TestRunRecord


class ReadinessCheck(BaseModel):
    name: str
    ready: bool
    reason: str
    advisory: bool = False


class RunPreflight(BaseModel):
    ready: bool
    checks: list[ReadinessCheck]


async def draft_map_readiness(session, run, settings):
    block = run.configuration_snapshot.get("app_map") or {}
    freshness = block.get("freshness") or {}
    if run.status != "draft" or freshness.get("preflight_status") != "preparing":
        return None, None
    receipt = await map_repository.get_preflight(session, UUID(freshness["last_preflight_id"]))
    if receipt is None or str(receipt.app_map_id) != block["map_id"]:
        return None, ReadinessCheck(name="app_map", ready=False, reason="The map preparation receipt is unavailable.")
    expired = datetime.now(UTC) >= run.created_at + timedelta(seconds=settings.preflight_wait_seconds)
    if receipt.status in ("ready", "partial"):
        return receipt, ReadinessCheck(name="app_map", ready=True, reason="Map preparation completed.")
    if receipt.status == "failed" or expired:
        return receipt, ReadinessCheck(name="app_map", ready=True, advisory=True,
                                      reason="The map check failed or expired. Start will use the saved map.")
    return receipt, ReadinessCheck(name="app_map", ready=False, reason="The app map is still preparing.")


class WorkerStatus(BaseModel):
    service: str
    ready: bool
    last_seen_at: datetime | None = None
    detail: dict[str, object] = Field(default_factory=dict[str, object])


async def worker_statuses(session: AsyncSession) -> list[WorkerStatus]:
    rows: list[WorkerHeartbeat] = []
    try:
        # A missing migration must not poison a surrounding authorization transaction.
        async with session.begin_nested():
            rows = list((await session.scalars(select(WorkerHeartbeat).where(
                WorkerHeartbeat.service.in_(("execution", "evaluation")),
            ))).all())
    except SQLAlchemyError:
        pass
    by_service = {row.service: row for row in rows}
    now = datetime.now(UTC)
    result: list[WorkerStatus] = []
    for service in ("execution", "evaluation"):
        row = by_service.get(service)
        fresh = row is not None and 0 <= (now - row.last_seen_at).total_seconds() < 30
        connected = row is not None and row.detail.get("connected") is True
        result.append(WorkerStatus(
            service=service, ready=fresh and connected,
            last_seen_at=row.last_seen_at if row else None,
            detail={key: value for key, value in row.detail.items()
                    if key in {"connected", "capacity", "active"} and type(value) in {bool, int}}
            if row else {},
        ))
    return result


async def kafka_reachable(settings: Settings) -> bool:
    producer = None
    try:
        async with asyncio.timeout(5):
            producer = KafkaProducer(settings.kafka_producer_settings)
            await producer.start()
        return True
    except Exception:
        return False
    finally:
        if producer is not None:
            try:
                async with asyncio.timeout(2):
                    await producer.stop()
            except Exception:
                pass


def provider_configured(settings: Settings) -> bool:
    model = (settings.model_name or "").strip()
    provider = settings.model_provider.strip().casefold()
    if provider == "ollama" or model.startswith(("ollama/", "ollama_chat/")):
        return bool(model or settings.ollama_model_name)
    key = settings.model_api_key or settings.openai_api_key
    return bool(key is not None and key.get_secret_value().strip())


async def run_preflight(session: AsyncSession, settings: Settings) -> RunPreflight:
    workers = {item.service: item for item in await worker_statuses(session)}
    kafka = await kafka_reachable(settings)
    checks = [
        ReadinessCheck(name="dispatch", ready=settings.outbox_relay_enabled,
                       reason="Run dispatch is ready." if settings.outbox_relay_enabled else
                       "Run dispatch is disabled. Enable the outbox relay and try again."),
        ReadinessCheck(name="kafka", ready=kafka, reason="The message broker is reachable."
                       if kafka else "The message broker is unavailable. Check Kafka and try again."
                       ),
        ReadinessCheck(name="execution", ready=workers["execution"].ready,
                       reason="The test runner is ready." if workers["execution"].ready else
                       "The test runner is not running. Start the execution worker and try again."),
        ReadinessCheck(name="evaluation", ready=workers["evaluation"].ready,
                       reason="The report writer is ready." if workers["evaluation"].ready else
                       "The report writer is not running. "
                       "Start the evaluation worker and try again."
                       ),
    ]
    configured = provider_configured(settings)
    checks.append(ReadinessCheck(
        name="model", ready=configured, advisory=True,
        reason=("The API environment has model configuration. " if configured else
                "The API environment has no model configuration. ")
               + "This is advisory; the worker's model configuration has not been verified.",
    ))
    return RunPreflight(ready=all(item.ready or item.advisory for item in checks), checks=checks)


async def require_run_ready(session: AsyncSession, settings: Settings) -> None:
    result = await run_preflight(session, settings)
    if not result.ready:
        raise HTTPException(503, detail={
            "code": "run_preflight_failed",
            "reason": next(item.reason for item in result.checks if not item.ready and not item.advisory),
            "checks": [item.model_dump() for item in result.checks],
        })


@dataclass(frozen=True)
class _StallFacts:
    latest: datetime | None
    failure_message: str | None
    report_completed: bool
    dispatch_quarantined: bool


def _terminal_stall_message(payload: object) -> str | None:
    details = public_failure_details(payload)
    if details["code"] in {"execution_stalled", "interrupted"}:
        return details["message"]
    return None


def _quarantined_dispatches(run_ids: list[UUID]):
    return select(OutboxEvent.aggregate_id).where(
        OutboxEvent.aggregate_id.in_(run_ids),
        OutboxEvent.event_type == "run.requested",
        OutboxEvent.published_at.is_(None),
        OutboxEvent.quarantined_at.is_not(None),
    )


async def stalled_run_reasons(
    session: AsyncSession, runs: list[TestRunRecord],
) -> dict[UUID, str | None]:
    """Batch the page's evidence, and read heartbeats at most once."""
    if not runs:
        return {}
    ids = [run.test_run_id for run in runs]
    latest = dict((await session.execute(select(
        RunEvent.test_run_id, func.max(RunEvent.occurred_at),
    ).where(RunEvent.test_run_id.in_(ids)).group_by(RunEvent.test_run_id))).all())
    completed = set((await session.scalars(select(Report.test_run_id).where(
        Report.test_run_id.in_(ids), Report.status == "completed",
    ))).all())
    failures = select(
        RunEvent.test_run_id, RunEvent.payload,
        func.row_number().over(partition_by=RunEvent.test_run_id,
                               order_by=RunEvent.id.desc()).label("position"),
    ).where(RunEvent.test_run_id.in_(ids), RunEvent.event_type == "run.failed").subquery()
    failure_messages = {run_id: _terminal_stall_message(payload) for run_id, payload in (await session.execute(select(
        failures.c.test_run_id, failures.c.payload,
    ).where(failures.c.position == 1))).all()}
    queued = [run.test_run_id for run in runs if run.status == "queued"]
    quarantined = (
        set((await session.scalars(_quarantined_dispatches(queued))).all()) if queued else set()
    )
    now = datetime.now(UTC)
    needs_workers = any(
        run.status in {"queued", "planning", "running", "completed"}
        and run.test_run_id not in quarantined
        and not (run.status == "completed" and run.test_run_id in completed)
        and (now - (latest.get(run.test_run_id) or run.created_at)).total_seconds() > 60
        for run in runs
    )
    workers = await worker_statuses(session) if needs_workers else []
    return {run.test_run_id: await stalled_run_reason(
        session, run_id=run.test_run_id, status=run.status, created_at=run.created_at,
        _facts=_StallFacts(latest.get(run.test_run_id), failure_messages.get(run.test_run_id),
                           run.test_run_id in completed, run.test_run_id in quarantined),
        _workers=workers,
    ) for run in runs}


async def stalled_run_reason(
    session: AsyncSession, *, run_id: UUID, status: str, created_at: datetime,
    _facts: _StallFacts | None = None, _workers: list[WorkerStatus] | None = None,
) -> str | None:
    if status == "failed":
        if _facts is not None:
            return _facts.failure_message
        event = await session.scalar(select(RunEvent).where(
            RunEvent.test_run_id == run_id, RunEvent.event_type == "run.failed",
        ).order_by(RunEvent.id.desc()).limit(1))
        return _terminal_stall_message(event.payload) if event is not None else None
    if status not in {"queued", "planning", "running", "completed"}:
        return None
    if status == "queued":
        dispatch_quarantined = (
            _facts.dispatch_quarantined if _facts is not None else
            await session.scalar(_quarantined_dispatches([run_id]).limit(1)) is not None
        )
        if dispatch_quarantined:
            return "Dispatch stopped after repeated failures. Ask your workspace operator to recover dispatch."
    if status == "completed" and (_facts.report_completed if _facts else
            await session.scalar(select(Report.id).where(
        Report.test_run_id == run_id, Report.status == "completed",
    ).limit(1)) is not None):
        return None
    latest = _facts.latest if _facts else await session.scalar(select(RunEvent.occurred_at).where(
        RunEvent.test_run_id == run_id,
    ).order_by(RunEvent.occurred_at.desc()).limit(1))
    if (datetime.now(UTC) - (latest or created_at)).total_seconds() <= 60:
        return None
    workers = {item.service: item for item in
               (_workers if _workers is not None else await worker_statuses(session))}
    if status == "completed":
        return "Waiting for the report writer" if not workers["evaluation"].ready else (
            "The report writer is still preparing this report"
        )
    if not workers["execution"].ready:
        return "The test runner is offline. No test actions are running. Start or restart the execution worker."
    if status == "queued":
        return "Runner is busy with another test"
    return "The test runner has not reported progress for over a minute"
