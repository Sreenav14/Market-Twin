"""Reuse completed visual judgments even when final report publication rolls back."""

from dataclasses import asdict
from typing import cast
from uuid import UUID

from markettwin_database.models import RunEvent
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from markettwin_evaluation_worker.visual_verifier import (
    VisualVerificationResult,
    VisualVerificationStatus,
)


class VisualResultCache:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def _engine(self) -> AsyncEngine:
        bind = self._session.bind
        return bind.engine if isinstance(bind, AsyncConnection) else bind

    async def get(
        self, *, run_id: UUID, execution_id: UUID, key: str,
    ) -> VisualVerificationResult | None:
        async with AsyncSession(self._engine) as session:
            payload = await session.scalar(select(RunEvent.payload).where(
                RunEvent.test_run_id == run_id,
                RunEvent.execution_id == execution_id,
                RunEvent.event_type == "evaluation.visual.cached",
                RunEvent.payload["cache_key"].astext == key,
            ).order_by(RunEvent.id).limit(1))
        if payload is None:
            return None
        result = cast(dict[str, object], payload["result"])
        return VisualVerificationResult(
            status=cast(VisualVerificationStatus, result["status"]),
            rationale=str(result["rationale"]),
            observed_details=tuple(cast(list[str], result["observed_details"])),
        )

    async def put(
        self, *, run_id: UUID, execution_id: UUID, key: str, result: VisualVerificationResult,
    ) -> None:
        if not result.cacheable:
            return
        async with AsyncSession(self._engine) as session, session.begin():
            await session.execute(text(
                "SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"
            ), {"key": f"markettwin-visual:{run_id}:{execution_id}:{key}"})
            exists = await session.scalar(select(RunEvent.id).where(
                RunEvent.test_run_id == run_id,
                RunEvent.execution_id == execution_id,
                RunEvent.event_type == "evaluation.visual.cached",
                RunEvent.payload["cache_key"].astext == key,
            ).limit(1))
            if exists is None:
                session.add(RunEvent(
                    test_run_id=run_id, execution_id=execution_id,
                    event_type="evaluation.visual.cached",
                    payload={"cache_key": key, "result": asdict(result)},
                ))
