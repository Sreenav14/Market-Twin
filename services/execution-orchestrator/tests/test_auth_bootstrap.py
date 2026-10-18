"""Protected planning never receives page context before identity verification."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from markettwin_execution_orchestrator.browser.contracts import BrowserSessionHandle
from markettwin_execution_orchestrator.workflow import auth_bootstrap
from markettwin_shared.auth_verification import AuthVerificationPolicy


@pytest.mark.parametrize("verified", [False, True])
async def test_discovery_requires_verification_and_cleans_up(monkeypatch, verified):
    order = []
    record = SimpleNamespace(journey_id=uuid4(), persona_id=uuid4(), mission_id=uuid4(),
                             journey_key="human_auth__auth_bootstrap")
    plans = SimpleNamespace(create_auth_bootstrap=AsyncMock(return_value=record))
    executions = SimpleNamespace(create_agent_execution=AsyncMock(), create_browser_session=AsyncMock(),
                                 mark_browser_session_closed=AsyncMock(), finish_agent_execution=AsyncMock())
    monkeypatch.setattr(auth_bootstrap, "PlanRepository", lambda _: plans)
    monkeypatch.setattr(auth_bootstrap, "ExecutionRepository", lambda _: executions)
    monkeypatch.setattr(auth_bootstrap, "RunStateRepository", lambda _: SimpleNamespace(mark_running=AsyncMock()))

    async def verify(**_kwargs):
        order.append("verify")
        if not verified:
            raise RuntimeError("Identity not verified")

    monkeypatch.setattr(auth_bootstrap, "verify_or_request_login", verify)
    controller = MagicMock()
    controller.create_session = AsyncMock(return_value=BrowserSessionHandle(uuid4(), record.journey_id, uuid4()))
    controller.navigate = AsyncMock()
    controller.close_session = AsyncMock()

    async def observe(**_kwargs):
        order.append("observe")
        return SimpleNamespace(observation=SimpleNamespace(to_dict=lambda: {"title": "Protected feature"}))

    controller.get_state = AsyncMock(side_effect=observe)
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(),
                              scalar=AsyncMock(return_value=None), execute=AsyncMock(),
                              flush=AsyncMock())
    request = SimpleNamespace(run_id=uuid4(), runtime_human_assistance=False,
                               allowed_origins=(), network_policy="local_development",
                               start_url="http://127.0.0.1", auth_mode="required", auth_verification=AuthVerificationPolicy(
                                   origin="http://127.0.0.1", marker_selector="#identity",
                                   expected_marker="member", role="member", account_reference="fixture-member",
                               ))
    if verified:
        assert await auth_bootstrap.authenticated_discovery(
            request=request, controller=controller, session=session, auth_scope=object(),
        ) == {"title": "Protected feature"}
        assert order == ["verify", "observe"]
    else:
        with pytest.raises(RuntimeError, match="Identity not verified"):
            await auth_bootstrap.authenticated_discovery(
                request=request, controller=controller, session=session, auth_scope=object(),
            )
        controller.get_state.assert_not_awaited()
    controller.close_session.assert_awaited_once()
    assert executions.finish_agent_execution.call_args.kwargs["outcome"] is None
    plans.create_auth_bootstrap.assert_awaited_once_with(
        test_run_id=request.run_id, requires_identity_verification=True,
    )
    assert executions.create_agent_execution.call_args.kwargs["runtime_name"] == (
        "human_auth_bootstrap_v1"
    )


async def test_public_runtime_discovery_never_requests_unconditional_human_help(monkeypatch):
    record = SimpleNamespace(
        journey_id=uuid4(), persona_id=uuid4(), mission_id=uuid4(),
        journey_key="browser_discovery__observe_starting_page",
    )
    plans = SimpleNamespace(create_auth_bootstrap=AsyncMock(return_value=record))
    executions = SimpleNamespace(
        create_agent_execution=AsyncMock(), create_browser_session=AsyncMock(),
        mark_browser_session_closed=AsyncMock(), finish_agent_execution=AsyncMock(),
    )
    monkeypatch.setattr(auth_bootstrap, "PlanRepository", lambda _: plans)
    monkeypatch.setattr(auth_bootstrap, "ExecutionRepository", lambda _: executions)
    monkeypatch.setattr(auth_bootstrap, "RunStateRepository", lambda _: SimpleNamespace(
        mark_running=AsyncMock(),
    ))
    runtime_help, verify_identity = AsyncMock(), AsyncMock()
    monkeypatch.setattr(auth_bootstrap, "request_runtime_assistance", runtime_help)
    monkeypatch.setattr(auth_bootstrap, "verify_or_request_login", verify_identity)
    controller = MagicMock()
    controller.create_session = AsyncMock(return_value=BrowserSessionHandle(
        uuid4(), record.journey_id, uuid4(),
    ))
    controller.navigate, controller.close_session = AsyncMock(), AsyncMock()
    controller.get_state = AsyncMock(return_value=SimpleNamespace(
        observation=SimpleNamespace(to_dict=lambda: {"title": "Public page"}),
    ))
    request = SimpleNamespace(
        run_id=uuid4(), runtime_human_assistance=True, allowed_origins=(),
        network_policy="local_development", start_url="http://127.0.0.1",
        auth_mode="required", auth_verification=None, target_snapshot={"target_id": str(uuid4())},
    )
    result = await auth_bootstrap.authenticated_discovery(
        request=request, controller=controller,
        session=SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(),
                                scalar=AsyncMock(return_value=None), execute=AsyncMock(),
                                flush=AsyncMock()), auth_scope=None,
    )
    assert result == {"title": "Public page"}
    runtime_help.assert_not_awaited()
    verify_identity.assert_not_awaited()
    controller.bind_authentication_handler.assert_called_once()
    controller.navigate.assert_awaited_once()
    controller.get_state.assert_awaited_once()
    assert executions.create_agent_execution.call_args.kwargs["runtime_name"] == (
        "browser_discovery_v1"
    )
    plans.create_auth_bootstrap.assert_awaited_once_with(
        test_run_id=request.run_id, requires_identity_verification=False,
    )
    assert executions.finish_agent_execution.call_args.kwargs["status"] == "completed"
