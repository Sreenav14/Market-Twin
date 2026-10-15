"""Periodic expiry for durable human-control requests and leases."""

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.persistence.repositories.action_approval_repository import (
    ActionApprovalRepository,
)
from markettwin_control_api.persistence.repositories.human_action_repository import (
    HumanActionRepository,
)

logger = logging.getLogger(__name__)


async def run_human_action_reaper(
    session_factory: Callable[[], AsyncSession],
    *,
    interval_seconds: float = 5,
    batch_size: int = 100,
) -> None:
    """Expire a bounded batch each pass until cancelled during shutdown."""
    if interval_seconds <= 0 or batch_size < 1:
        raise ValueError("The HITL reaper interval and batch size must be positive.")
    while True:
        try:
            async with session_factory() as session:
                async with session.begin():
                    await HumanActionRepository(session).expire_due(limit=batch_size)
                    await ActionApprovalRepository(session).expire_due(limit=batch_size)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("HITL expiry pass failed")
        await asyncio.sleep(interval_seconds)
