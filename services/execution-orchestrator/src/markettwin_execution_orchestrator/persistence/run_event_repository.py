"""Persistence for MarketTwin run events."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.persistence.models import (
    RunEvent,
)


class RunEventRepository:
    """Append immutable events to a MarketTwin Testrun."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        test_run_id: UUID,
        event_type: str,
        payload: dict[str, object],
        journey_id: UUID | None,
        execution_id: UUID | None,
    ) -> int:
        event = RunEvent(
            test_run_id=test_run_id,
            journey_id=journey_id,
            execution_id=execution_id,
            event_type=event_type,
            payload=payload,
        )

        self._session.add(event)
        await self._session.flush()

        return event.id
