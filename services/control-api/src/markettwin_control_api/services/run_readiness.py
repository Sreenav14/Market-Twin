"""Read-only readiness and stall reasons; no provider calls or run-state mutation."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from markettwin_database.models import Report, RunEvent, WorkerHeartbeat
from markettwin_shared.messaging import KafkaProducer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.config import Settings


class ReadinessCheck(BaseModel):
    name: str
    ready: bool
    reason: str


class RunPreflight(BaseModel):
    ready: bool
    checks: list[ReadinessCheck]


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
            rows = list((await session.scalars(select(WorkerHeartbeat))).all())
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
    checks.append(ReadinessCheck(name="model", ready=configured,
                                 reason="The model provider is configured." if configured else
                                 "The model provider is not configured. Add its key and try again."
                                 ))
    return RunPreflight(ready=all(item.ready for item in checks), checks=checks)


async def require_run_ready(session: AsyncSession, settings: Settings) -> None:
    result = await run_preflight(session, settings)
    if not result.ready:
        raise HTTPException(503, detail={
            "code": "run_preflight_failed",
            "reason": next(item.reason for item in result.checks if not item.ready),
            "checks": [item.model_dump() for item in result.checks],
        })


async def stalled_run_reason(
    session: AsyncSession, *, run_id: UUID, status: str, created_at: datetime,
) -> str | None:
    if status == "failed":
        event = await session.scalar(select(RunEvent).where(
            RunEvent.test_run_id == run_id, RunEvent.event_type == "run.failed",
        ).order_by(RunEvent.id.desc()).limit(1))
        if event is not None and event.payload.get("code") == "interrupted":
            return (
                "This run was interrupted (the runner restarted) and was not resumed. "
                "Start a new run."
            )
        return None
    if status not in {"queued", "planning", "running", "completed"}:
        return None
    if status == "completed" and await session.scalar(select(Report.id).where(
        Report.test_run_id == run_id, Report.status == "completed",
    ).limit(1)) is not None:
        return None
    latest = await session.scalar(select(RunEvent.occurred_at).where(
        RunEvent.test_run_id == run_id,
    ).order_by(RunEvent.occurred_at.desc()).limit(1))
    if (datetime.now(UTC) - (latest or created_at)).total_seconds() <= 60:
        return None
    workers = {item.service: item for item in await worker_statuses(session)}
    if status == "completed":
        return "Waiting for the report writer" if not workers["evaluation"].ready else (
            "The report writer is still preparing this report"
        )
    if not workers["execution"].ready:
        return "Waiting for the test runner"
    if status == "queued":
        return "Runner is busy with another test"
    return "The test runner has not reported progress for over a minute"
