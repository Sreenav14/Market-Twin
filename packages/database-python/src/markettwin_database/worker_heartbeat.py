"""Bounded worker heartbeat publication using independent short transactions."""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from markettwin_database.models.worker_heartbeat import WorkerHeartbeat

logger = logging.getLogger(__name__)


async def publish_worker_heartbeat(
    factory: async_sessionmaker[AsyncSession], service: str, detail: dict[str, object],
) -> None:
    async with factory() as session:
        async with session.begin():
            statement = insert(WorkerHeartbeat).values(
                service=service, last_seen_at=datetime.now(UTC), detail=detail,
            )
            await session.execute(statement.on_conflict_do_update(
                index_elements=[WorkerHeartbeat.service],
                set_={"last_seen_at": statement.excluded.last_seen_at,
                      "detail": statement.excluded.detail},
            ))


async def run_worker_heartbeat(
    factory: async_sessionmaker[AsyncSession], service: str,
    detail: Callable[[], dict[str, object]],
) -> None:
    while True:
        try:
            async with asyncio.timeout(5):
                await publish_worker_heartbeat(factory, service, detail())
        except Exception as error:
            # Missing migrations and transient DB errors must not stop browser work.
            logger.warning("%s heartbeat unavailable (%s)", service, type(error).__name__)
        await asyncio.sleep(10)
