"""Workspace scoping and attempt provenance for the agent/results directory."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from markettwin_control_api.api import agent_prompts, test_run_results
from markettwin_control_api.persistence.repositories.test_run_results_repository import (
    TestRunResultsRepository as ResultsRepository,
)


class Context:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_):
        return False


@pytest.mark.parametrize("accessible", [True, False])
async def test_workspace_agent_directory_scopes_dates_and_timing(monkeypatch, accessible):
    workspace_id, user_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    queried = []
    snapshot = SimpleNamespace(
        id=uuid4(),
        test_run_id=uuid4(),
        created_at=now,
        agent_role="persona",
        runtime_agent_name="Assigned persona",
        model_name="configured/model",
        persona_snapshot={"name": "First user"},
        mission_snapshot={"name": "Find information"},
    )
    execution = SimpleNamespace(started_at=now, completed_at=now + timedelta(seconds=7))

    class Session:
        async def execute(self, statement):
            queried.append(statement)
            return SimpleNamespace(all=lambda: [(snapshot, execution, {"study_brief": "A goal"})])

        async def scalars(self, _):
            return SimpleNamespace(all=lambda: [])

    async def auth(**_):
        return user_id

    async def workspace(**kwargs):
        assert kwargs == {"workspace_id": workspace_id, "user_id": user_id}
        return SimpleNamespace(role="viewer") if accessible else None

    monkeypatch.setattr(agent_prompts, "get_authenticated_user_id", auth)
    monkeypatch.setattr(
        agent_prompts,
        "get_database_runtime",
        lambda _: SimpleNamespace(
            session_factory=lambda: Context(Session()),
        ),
    )
    monkeypatch.setattr(
        agent_prompts,
        "WorkspaceRepository",
        lambda _: SimpleNamespace(
            get_for_user=workspace,
        ),
    )
    arguments = dict(
        workspace_id=workspace_id,
        request=SimpleNamespace(),
        created_after=now,
        created_before=now + timedelta(days=1),
        order="oldest",
    )
    if not accessible:
        with pytest.raises(HTTPException) as error:
            await agent_prompts.list_workspace_agents(**arguments)
        assert error.value.status_code == 404
        assert not queried
        return
    response = await agent_prompts.list_workspace_agents(**arguments)
    assert response["limit"] == 100
    assert response["agents"][0]["duration_seconds"] == 7
    assert response["agents"][0]["snapshot"]["id"] == str(snapshot.id)
    assert "yaml" not in response["agents"][0]
    sql = str(queried[0])
    assert "testing.test_runs.workspace_id =" in sql
    assert "agent_runtime_snapshots.created_at >=" in sql
    assert "agent_runtime_snapshots.created_at <" in sql
    assert "agent_runtime_snapshots.created_at ASC" in sql
    assert queried[0].compile().params["workspace_id_1"] == workspace_id


@pytest.mark.parametrize(
    "start,end",
    [
        (datetime(2026, 1, 1), None),
        (datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)),
    ],
)
async def test_agent_directory_rejects_ambiguous_date_ranges(monkeypatch, start, end):
    async def auth(**_):
        return uuid4()

    monkeypatch.setattr(agent_prompts, "get_authenticated_user_id", auth)
    with pytest.raises(HTTPException) as error:
        await agent_prompts.list_workspace_agents(
            uuid4(),
            SimpleNamespace(),
            created_after=start,
            created_before=end,
        )
    assert error.value.status_code == 422


@pytest.mark.parametrize("accessible", [True, False])
async def test_journey_results_available_before_evaluation_and_scoped(monkeypatch, accessible):
    run_id, user_id = uuid4(), uuid4()
    called = []

    async def auth(**_):
        return user_id

    async def run(**kwargs):
        assert kwargs == {"test_run_id": run_id, "user_id": user_id}
        return SimpleNamespace(status="running") if accessible else None

    async def results(**kwargs):
        called.append(kwargs)
        return []

    monkeypatch.setattr(test_run_results, "get_authenticated_user_id", auth)
    monkeypatch.setattr(
        test_run_results,
        "get_database_runtime",
        lambda _: SimpleNamespace(
            session_factory=lambda: Context(object()),
        ),
    )
    monkeypatch.setattr(
        test_run_results, "TestRunRepository", lambda _: SimpleNamespace(get_for_user=run)
    )
    monkeypatch.setattr(
        test_run_results,
        "TestRunResultsRepository",
        lambda _: SimpleNamespace(list_journeys=results),
    )
    if accessible:
        assert await test_run_results.get_test_run_journeys(run_id, SimpleNamespace()) == []
        assert called == [{"test_run_id": run_id}]
    else:
        with pytest.raises(HTTPException) as error:
            await test_run_results.get_test_run_journeys(run_id, SimpleNamespace())
        assert error.value.status_code == 404
        assert not called


async def test_journey_result_matches_latest_attempt_not_previous_payload():
    run_id, journey_id, new_execution_id, old_execution_id = (uuid4() for _ in range(4))
    journey = SimpleNamespace(id=journey_id, ordinal=1)

    def execution(identifier, attempt):
        return SimpleNamespace(
            id=identifier,
            journey_id=journey_id,
            attempt_number=attempt,
            status="completed",
            outcome="passed",
            started_at=None,
            completed_at=None,
            error_message=None,
        )

    queries = []

    class Session:
        async def execute(self, statement):
            queries.append(statement)
            if "count(" in str(statement):
                return SimpleNamespace(all=lambda: [(new_execution_id, 3)])
            return SimpleNamespace(all=lambda: [(
                journey, "Persona", "Perspective", "Mission", "Objective", ["Criterion"],
            )])

        async def scalars(self, statement):
            queries.append(statement)
            if "run_events" in str(statement):
                rows = [
                    SimpleNamespace(execution_id=old_execution_id, payload={"summary": "Old"}),
                    SimpleNamespace(execution_id=new_execution_id, payload={"summary": "New"}),
                ]
            else:
                rows = [execution(new_execution_id, 2), execution(old_execution_id, 1)]
            return SimpleNamespace(all=lambda: rows)

    result = await ResultsRepository(Session()).list_journeys(test_run_id=run_id)
    assert result[0]["execution_id"] == new_execution_id
    assert result[0]["result"] == {"summary": "New"}
    assert result[0]["attempt_number"] == 2
    assert result[0]["step_count"] == 3
    assert result[0]["artifact_count"] == 3
    assert result[0]["persona_perspective"] == "Perspective"
    assert run_id in queries[0].compile().params.values()
    assert all(str(new_execution_id) in str(query.compile().params) or
               run_id in query.compile().params.values() for query in queries)


def test_flow_uses_actual_assignments_status_and_changes_revision():
    journeys = [
        {
            "id": uuid4(),
            "persona_name": "Assigned user",
            "mission_title": "A mission",
            "execution_status": "running",
        }
    ]
    first = test_run_results.build_run_flow(
        run_status="running",
        journeys=journeys,
        collected=False,
        report_status=None,
    )
    assert [node["kind"] for node in first["nodes"]] == [
        "meta",
        "journey",
        "collector",
        "evaluation",
        "report",
    ]
    assert first["nodes"][1]["label"] == "Assigned user · A mission"
    assert first["nodes"][1]["status"] == "running"
    assert len(first["edges"]) == len(first["nodes"]) - 1
    journeys[0]["execution_status"] = "completed"
    second = test_run_results.build_run_flow(
        run_status="completed",
        journeys=journeys,
        collected=True,
        report_status="completed",
    )
    assert second["revision"] != first["revision"]
    assert all(node["status"] == "completed" for node in second["nodes"])
    historical = test_run_results.build_run_flow(
        run_status="completed",
        journeys=journeys,
        collected=False,
        report_status="completed",
    )
    assert historical["nodes"][2]["status"] == "not_recorded"
    pending = test_run_results.build_run_flow(
        run_status="completed", journeys=journeys, collected=True, report_status=None
    )
    assert pending["nodes"][3]["status"] == "awaiting_report"


@pytest.mark.parametrize("endpoint", ["flow", "collection", "evaluation_agents"])
async def test_flow_collection_evaluation_reads_reject_foreign_runs(monkeypatch, endpoint):
    async def auth(**_):
        return uuid4()

    async def missing(**_):
        return None

    monkeypatch.setattr(test_run_results, "get_authenticated_user_id", auth)
    monkeypatch.setattr(
        test_run_results,
        "get_database_runtime",
        lambda _: SimpleNamespace(
            session_factory=lambda: Context(object()),
        ),
    )
    monkeypatch.setattr(
        test_run_results, "TestRunRepository", lambda _: SimpleNamespace(get_for_user=missing)
    )
    name = (
        f"get_test_run_{endpoint}" if endpoint != "evaluation_agents" else "get_evaluation_agents"
    )
    with pytest.raises(HTTPException) as error:
        await getattr(test_run_results, name)(uuid4(), SimpleNamespace())
    assert error.value.status_code == 404
