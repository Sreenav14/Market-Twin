"""Authorization tests for the Agent Transparency API."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from markettwin_control_api.api import agents


class AsyncContext:
    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> bool:
        return False


def request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
        }
    )


@pytest.mark.asyncio
async def test_inaccessible_test_run_never_reads_agent_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_run_id = uuid4()
    user_id = uuid4()

    test_run_repository = SimpleNamespace(
        get_for_user=AsyncMock(return_value=None)
    )
    observability_factory = Mock()

    monkeypatch.setattr(
        agents,
        "get_authenticated_user_id",
        AsyncMock(return_value=user_id),
    )
    monkeypatch.setattr(
        agents,
        "get_database_runtime",
        lambda _request: SimpleNamespace(
            session_factory=lambda: AsyncContext(object())
        ),
    )
    monkeypatch.setattr(
        agents,
        "TestRunRepository",
        lambda _session: test_run_repository,
    )
    monkeypatch.setattr(
        agents,
        "AgentObservabilityRepository",
        observability_factory,
    )

    with pytest.raises(HTTPException) as error:
        await agents.list_test_run_agents(
            test_run_id=test_run_id,
            request=request(),
        )

    assert error.value.status_code == 404
    test_run_repository.get_for_user.assert_awaited_once_with(
        test_run_id=test_run_id,
        user_id=user_id,
    )
    observability_factory.assert_not_called()
