"""Supervised freedom installs by default (owner decision, 2026-11-13)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from markettwin_execution_orchestrator.workflow.offsite_browsing import configure_offsite


async def test_offsite_supervision_installs_without_opt_in() -> None:
    # A run whose configuration never mentions offsite browsing still gets
    # the Lead-supervised browsing policy attached to its controller.
    controller = SimpleNamespace(offsite=None)
    run = SimpleNamespace(id=uuid4(), configuration_snapshot={})
    session = SimpleNamespace(scalar=AsyncMock(return_value=None), bind=None)
    await configure_offsite(controller, run, session)  # type: ignore[arg-type]
    assert controller.offsite is not None


async def test_legacy_offsite_event_without_state_uses_default_policy() -> None:
    controller = SimpleNamespace(offsite=None)
    run = SimpleNamespace(id=uuid4(), configuration_snapshot={})
    session = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(payload={})),
                              bind=None)
    await configure_offsite(controller, run, session)
    assert controller.offsite.pages == {}
    assert controller.offsite.stopped == {}


async def test_offsite_supervision_installs_with_explicit_opt_in() -> None:
    controller = SimpleNamespace(offsite=None)
    run = SimpleNamespace(
        id=uuid4(),
        configuration_snapshot={"allow_offsite_navigation": True, "study_brief": "Check pricing."},
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=None), bind=None)
    await configure_offsite(controller, run, session)  # type: ignore[arg-type]
    assert controller.offsite is not None
    assert controller.offsite.goal == "Check pricing."
