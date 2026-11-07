"""W2: the per-app latest completed run summary behind Home's apps rail.

Semantics under test: the verdict is a completed report's own stored
market verdict, read verbatim — never inferred from a run status. A
newer draft or queued run never erases the last real result, and an
application with no completed run that produced a completed report
has no summary at all.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from markettwin_control_api.api import applications as applications_api
from markettwin_control_api.database import DatabaseRuntime
from markettwin_control_api.persistence.repositories import (
    ApplicationRecord,
    LatestRunSummaryRecord,
    WorkspaceAccess,
)
from markettwin_control_api.persistence.repositories.application_repository import (
    ApplicationRepository,
    report_verdict,
)
from markettwin_database.models.evaluation import Report
from markettwin_database.models.testing import TestRun as RunModel
from sqlalchemy import ForeignKeyConstraint, MetaData, Result, Table, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.sql import Executable


@compiles(JSONB, "sqlite")
def _jsonb_as_json(type_: object, compiler: object, **kw: object) -> str:
    """Render PostgreSQL JSONB as plain JSON for the in-memory database."""

    return "JSON"


class SessionAdapter:
    """Use an in-memory SQL database for repository behavior without external writes."""

    def __init__(self, session: Session) -> None:
        self.session = session

    async def execute(self, statement: Executable) -> Result[Any]:
        return self.session.execute(statement)

    async def flush(self) -> None:
        self.session.flush()

    def add(self, record: object) -> None:
        self.session.add(record)


def _sqlite_table(model: type[RunModel] | type[Report]) -> Table:
    """Copy a table for SQLite: no server defaults, no foreign keys.

    The production tables rely on PostgreSQL server defaults (including
    ``'{}'::jsonb`` casts) and composite foreign keys; neither exists in
    SQLite, and neither affects the query semantics under test.
    """

    table = cast(Table, model.__table__).to_metadata(MetaData())

    for column in table.columns:
        column.server_default = None
        column.foreign_keys.clear()

    for constraint in list(table.constraints):
        if isinstance(constraint, ForeignKeyConstraint):
            table.constraints.discard(constraint)

    return table


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        execution_options={
            "schema_translate_map": {"testing": None, "evaluation": None},
        },
    )
    _sqlite_table(RunModel).create(engine)
    _sqlite_table(Report).create(engine)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
WORKSPACE_ID = uuid4()
USER_ID = uuid4()
TARGET_ID = uuid4()

_run_numbers = iter(range(1, 10_000))


def add_run(
    session: Session,
    *,
    application_id: UUID,
    status: str,
    created_at: datetime,
    completed_at: datetime | None = None,
    workspace_id: UUID = WORKSPACE_ID,
) -> RunModel:
    run = RunModel(
        id=uuid4(),
        test_number=next(_run_numbers),
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=TARGET_ID,
        created_by_user_id=USER_ID,
        status=status,
        target_snapshot={},
        configuration_snapshot={},
        created_at=created_at,
        updated_at=created_at,
        completed_at=completed_at,
    )
    session.add(run)
    session.flush()
    return run


def add_report(
    session: Session,
    *,
    run: RunModel,
    version: int = 1,
    status: str = "completed",
    verdict: str | None = "ready",
    generated_at: datetime | None = None,
) -> Report:
    payload: dict[str, object] = (
        {"market_verdict": {"verdict": verdict}} if verdict is not None else {}
    )
    report = Report(
        id=uuid4(),
        test_run_id=run.id,
        version=version,
        status=status,
        executive_summary=None,
        report_payload=payload,
        created_at=generated_at or NOW,
        generated_at=generated_at,
    )
    session.add(report)
    session.flush()
    return report


def repository(session: Session) -> ApplicationRepository:
    return ApplicationRepository(cast(AsyncSession, SessionAdapter(session)))


@pytest.mark.parametrize(
    "verdict",
    ["ready", "ready_with_issues", "not_ready", "insufficient_evidence"],
)
def test_report_verdict_passes_the_stored_word_through_verbatim(
    verdict: str,
) -> None:
    payload = {"market_verdict": {"verdict": verdict, "confirmed_defects": 0}}

    assert report_verdict(payload) == verdict


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"journeys": []},
        {"market_verdict": None},
        {"market_verdict": "ready"},
        {"market_verdict": {}},
        {"market_verdict": {"verdict": None}},
        {"market_verdict": {"verdict": 3}},
    ],
)
def test_report_verdict_is_none_without_a_stored_verdict(
    payload: dict[str, object],
) -> None:
    assert report_verdict(payload) is None


async def test_completed_run_summary_carries_verdict_and_finish_time(
    session: Session,
) -> None:
    application_id = uuid4()
    finished = NOW - timedelta(days=1)
    run = add_run(
        session,
        application_id=application_id,
        status="completed",
        created_at=finished - timedelta(hours=1),
        completed_at=finished,
    )
    add_report(
        session, run=run, verdict="ready_with_issues", generated_at=finished
    )

    summaries = await repository(session).latest_run_summaries(
        workspace_id=WORKSPACE_ID,
        application_ids=[application_id],
    )

    summary = summaries[application_id]
    assert summary.run_id == run.id
    assert summary.run_status == "completed"
    assert summary.verdict == "ready_with_issues"
    assert summary.finished_at is not None
    assert summary.finished_at.replace(tzinfo=UTC) == finished


async def test_app_with_only_unfinished_runs_has_no_summary(
    session: Session,
) -> None:
    application_id = uuid4()
    add_run(
        session,
        application_id=application_id,
        status="draft",
        created_at=NOW - timedelta(days=1),
    )
    add_run(
        session,
        application_id=application_id,
        status="queued",
        created_at=NOW,
    )
    # A failed run finished, but it is not a completed run and has no
    # report verdict to show.
    add_run(
        session,
        application_id=application_id,
        status="failed",
        created_at=NOW - timedelta(hours=2),
        completed_at=NOW - timedelta(hours=1),
    )

    summaries = await repository(session).latest_run_summaries(
        workspace_id=WORKSPACE_ID,
        application_ids=[application_id],
    )

    assert summaries == {}


async def test_newer_draft_does_not_erase_the_last_real_result(
    session: Session,
) -> None:
    application_id = uuid4()
    finished = NOW - timedelta(days=2)
    run = add_run(
        session,
        application_id=application_id,
        status="completed",
        created_at=finished - timedelta(hours=1),
        completed_at=finished,
    )
    add_report(session, run=run, verdict="not_ready", generated_at=finished)
    add_run(
        session,
        application_id=application_id,
        status="draft",
        created_at=NOW,
    )
    add_run(
        session,
        application_id=application_id,
        status="running",
        created_at=NOW - timedelta(hours=3),
    )

    summaries = await repository(session).latest_run_summaries(
        workspace_id=WORKSPACE_ID,
        application_ids=[application_id],
    )

    summary = summaries[application_id]
    assert summary.run_id == run.id
    assert summary.verdict == "not_ready"
    assert summary.finished_at is not None
    assert summary.finished_at.replace(tzinfo=UTC) == finished


async def test_each_application_gets_its_own_latest_summary(
    session: Session,
) -> None:
    first_app, second_app, empty_app = uuid4(), uuid4(), uuid4()

    older_finish = NOW - timedelta(days=3)
    older = add_run(
        session,
        application_id=first_app,
        status="completed",
        created_at=older_finish - timedelta(hours=1),
        completed_at=older_finish,
    )
    add_report(session, run=older, verdict="ready", generated_at=older_finish)

    newer_finish = NOW - timedelta(days=1)
    newer = add_run(
        session,
        application_id=first_app,
        status="completed",
        created_at=newer_finish - timedelta(hours=1),
        completed_at=newer_finish,
    )
    add_report(
        session, run=newer, verdict="not_ready", generated_at=newer_finish
    )

    other_finish = NOW - timedelta(days=2)
    other = add_run(
        session,
        application_id=second_app,
        status="completed",
        created_at=other_finish - timedelta(hours=1),
        completed_at=other_finish,
    )
    add_report(
        session,
        run=other,
        verdict="insufficient_evidence",
        generated_at=other_finish,
    )

    add_run(
        session,
        application_id=empty_app,
        status="draft",
        created_at=NOW,
    )

    summaries = await repository(session).latest_run_summaries(
        workspace_id=WORKSPACE_ID,
        application_ids=[first_app, second_app, empty_app],
    )

    assert summaries[first_app].run_id == newer.id
    assert summaries[first_app].verdict == "not_ready"
    assert summaries[second_app].run_id == other.id
    assert summaries[second_app].verdict == "insufficient_evidence"
    assert empty_app not in summaries


async def test_run_whose_report_is_not_finished_is_skipped(
    session: Session,
) -> None:
    application_id = uuid4()
    older_finish = NOW - timedelta(days=2)
    older = add_run(
        session,
        application_id=application_id,
        status="completed",
        created_at=older_finish - timedelta(hours=1),
        completed_at=older_finish,
    )
    add_report(session, run=older, verdict="ready", generated_at=older_finish)

    newer_finish = NOW - timedelta(hours=5)
    newer = add_run(
        session,
        application_id=application_id,
        status="completed",
        created_at=newer_finish - timedelta(hours=1),
        completed_at=newer_finish,
    )
    add_report(session, run=newer, status="generating", generated_at=None)

    summaries = await repository(session).latest_run_summaries(
        workspace_id=WORKSPACE_ID,
        application_ids=[application_id],
    )

    assert summaries[application_id].run_id == older.id
    assert summaries[application_id].verdict == "ready"


async def test_latest_report_version_wins_within_a_run(
    session: Session,
) -> None:
    application_id = uuid4()
    finished = NOW - timedelta(days=1)
    run = add_run(
        session,
        application_id=application_id,
        status="completed",
        created_at=finished - timedelta(hours=1),
        completed_at=finished,
    )
    add_report(session, run=run, version=1, verdict="ready", generated_at=finished)
    add_report(
        session, run=run, version=2, verdict="not_ready", generated_at=finished
    )

    summaries = await repository(session).latest_run_summaries(
        workspace_id=WORKSPACE_ID,
        application_ids=[application_id],
    )

    assert summaries[application_id].verdict == "not_ready"


async def test_report_without_a_market_verdict_yields_a_verdictless_summary(
    session: Session,
) -> None:
    application_id = uuid4()
    finished = NOW - timedelta(days=1)
    run = add_run(
        session,
        application_id=application_id,
        status="completed",
        created_at=finished - timedelta(hours=1),
        completed_at=finished,
    )
    add_report(session, run=run, verdict=None, generated_at=finished)

    summaries = await repository(session).latest_run_summaries(
        workspace_id=WORKSPACE_ID,
        application_ids=[application_id],
    )

    summary = summaries[application_id]
    assert summary.run_id == run.id
    assert summary.verdict is None
    assert summary.finished_at is not None


async def test_runs_from_another_workspace_are_not_summarised(
    session: Session,
) -> None:
    application_id = uuid4()
    finished = NOW - timedelta(days=1)
    run = add_run(
        session,
        application_id=application_id,
        status="completed",
        created_at=finished - timedelta(hours=1),
        completed_at=finished,
        workspace_id=uuid4(),
    )
    add_report(session, run=run, verdict="ready", generated_at=finished)

    summaries = await repository(session).latest_run_summaries(
        workspace_id=WORKSPACE_ID,
        application_ids=[application_id],
    )

    assert summaries == {}


async def test_no_applications_means_no_summaries(session: Session) -> None:
    summaries = await repository(session).latest_run_summaries(
        workspace_id=WORKSPACE_ID,
        application_ids=[],
    )

    assert summaries == {}


"""Endpoint shape: the list payload carries the summary per application,
fetched in one repository call for the whole list."""


class AsyncContext:
    """Minimal async context manager used by the endpoint tests."""

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


class FakeDatabaseSession:
    def begin(self) -> AsyncContext:
        return AsyncContext(None)


class FakeApplicationRepository:
    def __init__(
        self,
        applications: list[ApplicationRecord],
        summaries: dict[UUID, LatestRunSummaryRecord],
    ) -> None:
        self._applications = applications
        self._summaries = summaries
        self.summary_calls: list[tuple[UUID, list[UUID]]] = []

    async def list_for_workspace(
        self, *, workspace_id: UUID
    ) -> list[ApplicationRecord]:
        return self._applications

    async def latest_run_summaries(
        self, *, workspace_id: UUID, application_ids: list[UUID]
    ) -> dict[UUID, LatestRunSummaryRecord]:
        self.summary_calls.append((workspace_id, application_ids))
        return self._summaries


class FakeWorkspaceRepository:
    def __init__(self, workspace: WorkspaceAccess) -> None:
        self._workspace = workspace

    async def get_for_user(
        self, *, workspace_id: UUID, user_id: UUID
    ) -> WorkspaceAccess | None:
        return self._workspace


async def test_list_applications_carries_the_summary_per_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    workspace_id = WORKSPACE_ID
    finished = NOW - timedelta(days=1)
    with_summary = ApplicationRecord(
        application_id=uuid4(),
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        name="Thread & Co.",
        description=None,
        status="active",
    )
    without_summary = ApplicationRecord(
        application_id=uuid4(),
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        name="New app",
        description=None,
        status="active",
    )
    run_id = uuid4()
    fake_repository = FakeApplicationRepository(
        [with_summary, without_summary],
        {
            with_summary.application_id: LatestRunSummaryRecord(
                run_id=run_id,
                run_status="completed",
                verdict="not_ready",
                finished_at=finished,
            )
        },
    )

    def application_repository(session: object) -> FakeApplicationRepository:
        return fake_repository

    def workspace_repository(session: object) -> FakeWorkspaceRepository:
        return FakeWorkspaceRepository(
            WorkspaceAccess(
                workspace_id=workspace_id,
                name="Workspace",
                status="active",
                role="owner",
            )
        )

    def session_factory() -> AsyncContext:
        return AsyncContext(FakeDatabaseSession())

    database = SimpleNamespace(session_factory=session_factory)

    async def authenticated_user_id(*, request: Request) -> UUID:
        return user_id

    def database_runtime(request: Request) -> DatabaseRuntime:
        return cast(DatabaseRuntime, database)

    monkeypatch.setattr(
        applications_api, "get_authenticated_user_id", authenticated_user_id
    )
    monkeypatch.setattr(
        applications_api, "get_database_runtime", database_runtime
    )
    monkeypatch.setattr(
        applications_api, "ApplicationRepository", application_repository
    )
    monkeypatch.setattr(
        applications_api, "WorkspaceRepository", workspace_repository
    )

    responses = await applications_api.list_applications(
        workspace_id,
        cast(Request, SimpleNamespace()),
    )

    assert len(responses) == 2

    summary = responses[0].latest_run_summary
    assert summary is not None
    assert summary.latest_run_id == run_id
    assert summary.latest_run_status == "completed"
    assert summary.verdict == "not_ready"
    assert summary.finished_at == finished

    assert responses[1].latest_run_summary is None

    # One summaries call for the whole list — no per-application fetch.
    assert fake_repository.summary_calls == [
        (
            workspace_id,
            [with_summary.application_id, without_summary.application_id],
        )
    ]
