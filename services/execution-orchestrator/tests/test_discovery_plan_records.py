"""Discovery presentation describes configured identity verification accurately."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from markettwin_database.models import PersonaJourney, RunMission, RunPersona
from markettwin_execution_orchestrator.persistence.plan_repository import PlanRepository


@pytest.mark.parametrize("identity_policy", [False, True])
async def test_discovery_records_do_not_imply_unconfigured_authentication(identity_policy):
    session = SimpleNamespace(add_all=Mock(), add=Mock(), flush=AsyncMock())
    record = await PlanRepository(session).create_auth_bootstrap(
        test_run_id=uuid4(), requires_identity_verification=identity_policy,
    )
    persona, mission = session.add_all.call_args.args[0]
    assert isinstance(persona, RunPersona)
    assert isinstance(mission, RunMission)
    assert isinstance(session.add.call_args.args[0], PersonaJourney)
    assert persona.attributes["executor_role"] is False
    assert mission.success_criteria == []  # Discovery is not a feature test outcome.
    if identity_policy:
        assert persona.name == "Human authentication prerequisite"
        assert mission.title == "Verify identity before protected discovery"
        assert persona.attributes["auth_bootstrap"] is True
        assert record.journey_key == "human_auth__auth_bootstrap"
    else:
        assert persona.name == "Browser discovery"
        assert mission.title == "Observe approved starting page"
        assert persona.attributes["browser_discovery"] is True
        assert "auth_bootstrap" not in persona.attributes
        assert record.journey_key == "browser_discovery__observe_starting_page"
