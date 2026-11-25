from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from markettwin_control_api.api import test_run as test_run_api
from markettwin_control_api.persistence.repositories import TestRunRecord


class _AsyncContext:
    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeRepository:
    def __init__(self, record: TestRunRecord) -> None:
        self._record = record
        self.updated_snapshot: dict[str, object] | None = None
        self.update_calls = 0

    async def get_for_user(self, *, test_run_id, user_id):  # noqa: ANN001, ANN202
        return self._record if test_run_id == self._record.test_run_id else None

    async def update_configuration_snapshot(
        self, *, test_run_id, configuration_snapshot,  # noqa: ANN001
    ) -> None:
        self.update_calls += 1
        self.updated_snapshot = configuration_snapshot


def _record(
    status: str = "running", snapshot: dict[str, object] | None = None,
) -> TestRunRecord:
    now = datetime.now(UTC)
    return TestRunRecord(
        test_run_id=uuid4(),
        workspace_id=uuid4(),
        application_id=uuid4(),
        target_id=uuid4(),
        created_by_user_id=uuid4(),
        status=status,
        target_snapshot={},
        configuration_snapshot=(
            snapshot
            if snapshot is not None
            else {"execution_mode": "harness_v1"}
        ),
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
        run_kind=None,
    )


def _install(monkeypatch: pytest.MonkeyPatch, record: TestRunRecord) -> _FakeRepository:
    repository = _FakeRepository(record)

    async def fake_user_id(*, request):  # noqa: ANN001, ANN202
        return record.created_by_user_id

    # session.begin() must be an async context manager.
    class _Session:
        def begin(self) -> _AsyncContext:
            return _AsyncContext(object())

    runtime = type(
        "Runtime", (), {"session_factory": lambda self: _AsyncContext(_Session())}
    )()
    monkeypatch.setattr(test_run_api, "get_authenticated_user_id", fake_user_id)
    monkeypatch.setattr(test_run_api, "get_database_runtime", lambda request: runtime)
    monkeypatch.setattr(test_run_api, "TestRunRepository", lambda _: repository)
    return repository


class _Request:
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "run_status", ["draft", "planning", "queued", "running", "awaiting_human"],
)
async def test_stop_records_the_owner_stop_flag(
    monkeypatch: pytest.MonkeyPatch, run_status: str,
) -> None:
    record = _record(status=run_status)
    repository = _install(monkeypatch, record)
    response = await test_run_api.stop_test_run(
        record.test_run_id, _Request(),  # type: ignore[arg-type]
    )
    assert response.test_run_id == record.test_run_id
    assert response.run_status == run_status
    assert repository.updated_snapshot is not None
    flag = repository.updated_snapshot["owner_stop"]
    assert isinstance(flag, dict)
    assert flag["requested_by"] == str(record.created_by_user_id)
    assert flag["requested_at"] == response.stop_requested_at
    # The rest of the snapshot is preserved.
    assert repository.updated_snapshot["execution_mode"] == "harness_v1"


@pytest.mark.asyncio
@pytest.mark.parametrize("run_status", ["completed", "failed", "cancelled"])
async def test_stop_refuses_a_terminal_run(
    monkeypatch: pytest.MonkeyPatch, run_status: str,
) -> None:
    record = _record(status=run_status)
    repository = _install(monkeypatch, record)
    with pytest.raises(HTTPException) as exc:
        await test_run_api.stop_test_run(
            record.test_run_id, _Request(),  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 409
    assert repository.updated_snapshot is None


@pytest.mark.asyncio
async def test_stop_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = "2026-11-18T20:34:00+00:00"
    record = _record(
        snapshot={
            "execution_mode": "harness_v1",
            "owner_stop": {"requested_at": first, "requested_by": "owner"},
        },
    )
    repository = _install(monkeypatch, record)
    response = await test_run_api.stop_test_run(
        record.test_run_id, _Request(),  # type: ignore[arg-type]
    )
    assert response.stop_requested_at == first
    assert repository.update_calls == 0


@pytest.mark.asyncio
async def test_stop_404s_for_a_run_the_user_cannot_see(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record()
    _install(monkeypatch, record)
    with pytest.raises(HTTPException) as exc:
        await test_run_api.stop_test_run(
            uuid4(), _Request(),  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 404
