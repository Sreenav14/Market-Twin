from dataclasses import replace
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

    async def get_for_user(self, *, test_run_id, user_id):  # noqa: ANN001, ANN202
        return self._record if test_run_id == self._record.test_run_id else None

    async def update_configuration_snapshot(
        self, *, test_run_id, configuration_snapshot,  # noqa: ANN001
    ) -> None:
        self.updated_snapshot = configuration_snapshot


def _record(status: str = "queued") -> TestRunRecord:
    now = datetime.now(UTC)
    snapshot: dict[str, object] = {
        "execution_mode": "harness_v1",
        "harness_state": {
            "states": {
                "s1": {"state_id": "s1", "url": "https://example.test/app"},
            },
            "items": {
                "i1": {
                    "item_id": "i1", "state_id": "s1", "case_id": "c1",
                    "role": "button", "name": "Save", "status": "pending",
                    "blocker": None, "attempts": 0,
                },
                "i2": {
                    "item_id": "i2", "state_id": "s1", "case_id": "c2",
                    "role": "link", "name": "Help", "status": "worked",
                    "blocker": None, "attempts": 1,
                },
            },
        },
    }
    return TestRunRecord(
        test_run_id=uuid4(),
        workspace_id=uuid4(),
        application_id=uuid4(),
        target_id=uuid4(),
        created_by_user_id=uuid4(),
        status=status,
        target_snapshot={},
        configuration_snapshot=snapshot,
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


def test_board_response_counts_and_pages() -> None:
    record = _record()
    response = test_run_api._board_response(record)
    assert response.run_kind == "explore_test"
    assert response.total == 2
    assert response.counts == {"pending": 1, "worked": 1}
    assert response.items[0].page_url == "https://example.test/app"


@pytest.mark.asyncio
async def test_disable_pending_item_marks_owner_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record()
    repository = _install(monkeypatch, record)
    response = await test_run_api.disable_board_item(
        record.test_run_id, "i1", _Request(),  # type: ignore[arg-type]
    )
    assert response.counts.get("owner_disabled") == 1
    assert repository.updated_snapshot is not None


@pytest.mark.asyncio
async def test_disable_pending_item_in_a_list_shaped_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Audit fix (N6): the GET path serves list-shaped items too, so
    # disabling must accept that shape and write it back as a list —
    # it used to 404 with "no board".
    record = _record()
    board = record.configuration_snapshot["harness_state"]
    list_items = list(board["items"].values())
    record = replace(
        record,
        configuration_snapshot={
            **record.configuration_snapshot,
            "harness_state": {**board, "items": list_items},
        },
    )
    repository = _install(monkeypatch, record)
    response = await test_run_api.disable_board_item(
        record.test_run_id, "i1", _Request(),  # type: ignore[arg-type]
    )
    assert response.counts.get("owner_disabled") == 1
    assert repository.updated_snapshot is not None
    written_items = repository.updated_snapshot["harness_state"]["items"]
    assert isinstance(written_items, list)
    assert written_items[0]["status"] == "owner_disabled"
    assert written_items[1]["status"] == "worked"


@pytest.mark.asyncio
async def test_disable_refused_while_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record(status="running")
    _install(monkeypatch, record)
    with pytest.raises(HTTPException) as exc:
        await test_run_api.disable_board_item(
            record.test_run_id, "i1", _Request(),  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_disable_refused_for_finished_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record()
    _install(monkeypatch, record)
    with pytest.raises(HTTPException) as exc:
        await test_run_api.disable_board_item(
            record.test_run_id, "i2", _Request(),  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 409


def _parked_record() -> TestRunRecord:
    record = _record(status="awaiting_human")
    parked_at = datetime.now(UTC)
    snapshot = {
        **record.configuration_snapshot,
        "harness_park": {
            "parked_at": parked_at.isoformat(),
            "deadline_at": parked_at.isoformat(),
            "item_id": "i1",
        },
    }
    return replace(record, configuration_snapshot=snapshot)


@pytest.mark.asyncio
async def test_extend_park_moves_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _parked_record()
    repository = _install(monkeypatch, record)
    response = await test_run_api.extend_park(
        record.test_run_id, _Request(),  # type: ignore[arg-type]
    )
    assert response.deadline_at > record.configuration_snapshot[
        "harness_park"
    ]["deadline_at"]  # type: ignore[index]
    assert repository.updated_snapshot is not None


@pytest.mark.asyncio
async def test_extend_park_refuses_a_run_that_is_not_parked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record(status="running")
    _install(monkeypatch, record)
    with pytest.raises(HTTPException) as exc:
        await test_run_api.extend_park(
            record.test_run_id, _Request(),  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 409
