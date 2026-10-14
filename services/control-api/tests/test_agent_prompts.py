"""Historical YAML edits must fork a run without changing its saved history."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml
from fastapi import HTTPException
from markettwin_control_api.api import agent_prompts as api
from markettwin_control_api.persistence.repositories import RuntimeSnapshotRecord
from markettwin_control_api.persistence.repositories import TestRunRecord as RunRecord


@pytest.fixture
def snapshot() -> RuntimeSnapshotRecord:
    return RuntimeSnapshotRecord(
        snapshot_id=uuid4(),
        test_run_id=uuid4(),
        journey_id=uuid4(),
        execution_id=uuid4(),
        agent_role="persona",
        runtime_kind="google_adk",
        runtime_agent_name="persona_one",
        agent_version=1,
        snapshot_schema_version=1,
        template_id=None,
        template_version=None,
        model_provider="openai",
        model_name="openai/example",
        model_configuration={},
        base_instruction=None,
        effective_instruction="Act as the assigned persona.\nUse browser tools.",
        runtime_prompt="Visit the authorized target.",
        persona_snapshot={"name": "First user"},
        mission_snapshot={"name": "Find information"},
        success_criteria=(),
        tools=("browser_click",),
        policy_references=(),
        metadata={"journey_key": "persona_one__original_mission"},
        observability_backend=None,
        trace_id=None,
        snapshot_sha256="a" * 64,
        created_at=datetime.now(UTC),
    )


def test_yaml_roundtrip_and_multiline_edit(snapshot: RuntimeSnapshotRecord) -> None:
    document = api.prompt_document(snapshot)
    document["instruction"] = "Observe navigation.\nRecord genuine confusion."
    edited = api.parse_prompt_edit(yaml.safe_dump(document), snapshot)
    assert edited["instruction"] == document["instruction"]
    assert edited["runtime_prompt"] == snapshot.runtime_prompt


async def test_prompt_view_with_shared_recorded_configuration(monkeypatch, snapshot):
    configuration = api.default_configuration("Agent_1", snapshot.tools)
    snapshot = replace(snapshot, metadata={"agent_structure": {
        "name": "Agent_1", "agent_type": "LlmAgent", "sub_agents": [],
        "configuration": configuration,
    }})

    class Session:
        async def scalars(self, _):
            return SimpleNamespace(all=lambda: [])

    async def user(**_):
        return uuid4()

    async def run(**_):
        return SimpleNamespace()

    async def snapshots(**_):
        return (snapshot,)

    async def timings(*_):
        return {}

    monkeypatch.setattr(api, "get_authenticated_user_id", user)
    monkeypatch.setattr(api, "get_database_runtime", lambda _: SimpleNamespace(
        session_factory=lambda: AsyncContext(Session()),
    ))
    monkeypatch.setattr(api, "TestRunRepository", lambda _: SimpleNamespace(get_for_user=run))
    monkeypatch.setattr(api, "RuntimeSnapshotRepository", lambda _: SimpleNamespace(
        list_for_run=snapshots,
    ))
    monkeypatch.setattr(api, "_recorded_timings", timings)
    response = await api.get_agent_prompts(snapshot.test_run_id, None)
    agent = response.agents[0]
    assert agent["rerun_configuration"] == configuration
    assert not any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(agent["yaml"]))
    edits = api.parse_prompt_edit(agent["yaml"], snapshot)
    assert json.loads(edits["agent_configuration"]) == configuration


def test_rerun_configuration_is_separate_from_immutable_history(snapshot):
    document = api.prompt_document(snapshot)
    settings = {"name": "Agent_2", "agent_type": "SequentialAgent", "temperature": 0.02,
                "tools": ["browser_click"], "sub_agents": [{"name": "Agent_3",
                "agent_type": "LlmAgent", "temperature": 0.05, "tools": [], "sub_agents": [],
                "instruction": "Inspect the recorded user goal."}]}
    saved = api.configured_prompt(yaml.safe_dump(document), settings, snapshot)
    edits = api.parse_prompt_edit(saved, snapshot)
    assert json.loads(edits["agent_configuration"]) == settings
    assert snapshot.runtime_agent_name == "persona_one"
    assert snapshot.tools == ("browser_click",)
    document["agent_name"] = "changed_history"
    with pytest.raises(ValueError, match="read-only"):
        api.configured_prompt(yaml.safe_dump(document), settings, snapshot)


@pytest.mark.parametrize(
    "field", ["snapshot_id", "agent_role", "model", "tools", "persona", "mission"]
)
def test_runtime_identity_and_capabilities_cannot_be_edited(
    snapshot: RuntimeSnapshotRecord, field: str
) -> None:
    document = api.prompt_document(snapshot)
    document[field] = "changed"
    with pytest.raises(ValueError, match="read-only"):
        api.parse_prompt_edit(yaml.safe_dump(document), snapshot)


@pytest.mark.parametrize(
    "document",
    [
        "instruction: [",
        "instruction: first\ninstruction: second",
        "x: &x [1]\ny: *x",
        "!!python/object/apply:os.system ['echo unsafe']",
        "[]",
    ],
)
def test_invalid_or_unsafe_yaml_is_rejected(snapshot: RuntimeSnapshotRecord, document: str) -> None:
    with pytest.raises(ValueError):
        api.parse_prompt_edit(document, snapshot)


class AsyncContext:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_):
        return False


@pytest.mark.parametrize(
    "case,expected",
    [
        ("valid", None),
        ("reader", 403),
        ("missing_run", 404),
        ("wrong_snapshot", 404),
        ("readonly_agent", 422),
        ("invalid_yaml", 422),
    ],
)
async def test_save_prompt_scoped_validated_and_separate_from_history(
    monkeypatch,
    snapshot: RuntimeSnapshotRecord,
    case: str,
    expected: int | None,
) -> None:
    user_id = uuid4()
    saved_queries = []
    now = datetime.now(UTC)
    selected = (
        replace(snapshot, agent_role="visual_verifier") if case == "readonly_agent" else snapshot
    )

    class Session:
        def begin(self):
            return AsyncContext()

        async def execute(self, statement):
            saved_queries.append(statement)
            return SimpleNamespace(scalar_one=lambda: now)

    async def user(**_):
        return user_id

    async def source(**kwargs):
        assert kwargs == {"test_run_id": snapshot.test_run_id, "user_id": user_id}
        return None if case == "missing_run" else SimpleNamespace(workspace_id=uuid4())

    async def workspace(**_):
        return SimpleNamespace(role="viewer" if case == "reader" else "owner")

    async def snapshots(**_):
        return (selected,)

    monkeypatch.setattr(api, "get_authenticated_user_id", user)
    monkeypatch.setattr(
        api,
        "get_database_runtime",
        lambda _: SimpleNamespace(
            session_factory=lambda: AsyncContext(Session()),
        ),
    )
    monkeypatch.setattr(api, "TestRunRepository", lambda _: SimpleNamespace(get_for_user=source))
    monkeypatch.setattr(
        api, "WorkspaceRepository", lambda _: SimpleNamespace(get_for_user=workspace)
    )
    monkeypatch.setattr(
        api, "RuntimeSnapshotRepository", lambda _: SimpleNamespace(list_for_run=snapshots)
    )
    document = api.prompt_document(snapshot)
    document["instruction"] = "Saved new instruction."
    payload = api.SavePromptRequest(
        prompt_yaml="[" if case == "invalid_yaml" else yaml.safe_dump(document)
    )
    arguments = dict(
        test_run_id=snapshot.test_run_id,
        snapshot_id=uuid4() if case == "wrong_snapshot" else snapshot.snapshot_id,
        payload=payload,
        request=SimpleNamespace(),
    )
    if expected is not None:
        with pytest.raises(HTTPException) as error:
            await api.save_agent_prompt(**arguments)
        assert error.value.status_code == expected
        assert not saved_queries
    else:
        result = await api.save_agent_prompt(**arguments)
        assert result.prompt_yaml == payload.prompt_yaml
        assert result.updated_at == now
        assert len(saved_queries) == 1
        statement = str(saved_queries[0])
        assert "INSERT INTO execution.agent_prompt_drafts" in statement
        assert "ON CONFLICT (snapshot_id, user_id) DO UPDATE" in statement
        assert snapshot.effective_instruction == "Act as the assigned persona.\nUse browser tools."


def test_recorded_duration_and_missing_timing_are_distinct() -> None:
    started = datetime.now(UTC)
    recorded = api._execution_timing(
        SimpleNamespace(
            started_at=started,
            completed_at=started + timedelta(seconds=12.25),
        )
    )
    assert recorded["duration_seconds"] == 12.25
    assert api._execution_timing(None)["duration_seconds"] is None
    assert (
        api._execution_timing(SimpleNamespace(started_at=started, completed_at=None))[
            "duration_seconds"
        ]
        is None
    )


async def test_test_agent_flow_includes_readonly_evaluation_agents(monkeypatch, snapshot):
    async def auth(**_):
        return uuid4()

    async def source(**_):
        return SimpleNamespace()

    async def snapshots(**_):
        return (
            snapshot,
            replace(snapshot, snapshot_id=uuid4(), agent_role="visual_verifier"),
            replace(snapshot, snapshot_id=uuid4(), agent_role="evaluator"),
        )

    class Session:
        async def scalars(self, _):
            return SimpleNamespace(all=lambda: [])

    monkeypatch.setattr(api, "get_authenticated_user_id", auth)
    monkeypatch.setattr(
        api,
        "get_database_runtime",
        lambda _: SimpleNamespace(
            session_factory=lambda: AsyncContext(Session()),
        ),
    )
    monkeypatch.setattr(api, "TestRunRepository", lambda _: SimpleNamespace(get_for_user=source))
    monkeypatch.setattr(
        api, "RuntimeSnapshotRepository", lambda _: SimpleNamespace(list_for_run=snapshots)
    )
    result = await api.get_agent_prompts(snapshot.test_run_id, SimpleNamespace())
    assert [item["snapshot"]["agent_role"] for item in result.agents] == [
        "persona", "visual_verifier", "evaluator",
    ]
    assert all(item["rerun_configuration"] is None for item in result.agents[1:])


@pytest.mark.parametrize("agent_role", ["meta", "persona"])
async def test_rerun_freezes_plan_and_preserves_source(
    monkeypatch, snapshot: RuntimeSnapshotRecord, agent_role: str
) -> None:
    snapshot = replace(snapshot, agent_role=agent_role)
    source = RunRecord(
        test_run_id=snapshot.test_run_id,
        workspace_id=uuid4(),
        application_id=uuid4(),
        target_id=uuid4(),
        created_by_user_id=uuid4(),
        status="completed",
        target_snapshot={"base_url": "https://example.com"},
        configuration_snapshot={
            "study_brief": "Review application navigation",
            "testing_depth": "high",
            "knowledge": [{"name": "Approved source"}],
        },
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        started_at=None,
        completed_at=datetime.now(UTC),
    )
    personas = [
        SimpleNamespace(
            id=uuid4(),
            ordinal=index,
            name=f"User {index}",
            description="A realistic user",
            attributes={
                "persona_key": f"persona_{index}",
                "behavior_traits": ["careful"],
                "priorities": ["clarity"],
            },
        )
        for index in range(1, 4)
    ]
    missions = [
        SimpleNamespace(
            id=uuid4(),
            ordinal=1,
            title="Find information",
            objective="Read information",
            success_criteria=["Information is found"],
            priority="high",
        )
    ]

    class Session:
        def begin(self):
            return AsyncContext()

        async def scalars(self, query):
            rows = personas if "run_personas" in str(query) else missions
            return SimpleNamespace(all=lambda: rows)

        async def get(self, *_):
            return SimpleNamespace(persona_id=personas[0].id, mission_id=missions[0].id)

    session = Session()
    created = {}

    async def return_source(**_):
        return source

    async def return_workspace(**_):
        return SimpleNamespace(role="owner")

    async def return_target(**_):
        return SimpleNamespace(target_id=source.target_id)

    async def return_snapshots(**_):
        return (snapshot,)

    async def create(**kwargs):
        created.update(kwargs)
        return replace(
            source,
            test_run_id=uuid4(),
            status="draft",
            configuration_snapshot=kwargs["configuration_snapshot"],
        )

    async def user(**_):
        return source.created_by_user_id

    monkeypatch.setattr(api, "get_authenticated_user_id", user)
    monkeypatch.setattr(
        api,
        "get_database_runtime",
        lambda _: SimpleNamespace(session_factory=lambda: AsyncContext(session)),
    )
    monkeypatch.setattr(
        api,
        "TestRunRepository",
        lambda _: SimpleNamespace(get_for_user=return_source, create=create),
    )
    monkeypatch.setattr(
        api, "WorkspaceRepository", lambda _: SimpleNamespace(get_for_user=return_workspace)
    )
    monkeypatch.setattr(
        api, "TargetRepository", lambda _: SimpleNamespace(get_for_user=return_target)
    )
    monkeypatch.setattr(
        api, "TargetAuthorizationRepository", lambda _: SimpleNamespace(get_active=return_target)
    )
    monkeypatch.setattr(
        api, "RuntimeSnapshotRepository", lambda _: SimpleNamespace(list_for_run=return_snapshots)
    )
    document = api.prompt_document(snapshot)
    document["instruction"] = "Review carefully and record confusion."
    response = await api.create_agent_rerun(
        source.test_run_id,
        api.RerunAgentRequest(
            snapshot_id=snapshot.snapshot_id, prompt_yaml=yaml.safe_dump(document)
        ),
        None,
    )
    config = created["configuration_snapshot"]
    assert response.status == "draft"
    assert response.id != source.test_run_id
    assert "agent_prompt_overrides" not in source.configuration_snapshot
    assert config["testing_depth"] == "high"
    assert config["knowledge"] == source.configuration_snapshot["knowledge"]
    assert config["rerun_of_test_run_id"] == str(source.test_run_id)
    key = "meta" if agent_role == "meta" else "persona_1__mission_1"
    assert config["agent_prompt_overrides"][key]["instruction"] == document["instruction"]
    if agent_role == "persona":
        from markettwin_execution_orchestrator.agents.schemas.plan import MetaAgentPlan

        plan = MetaAgentPlan.model_validate(config["replay_plan"])
        assert len(plan.personas) == 3
        assert plan.missions[0].objective == "Read information"
    else:
        assert "replay_plan" not in config

    other = api.RerunAgentRequest(snapshot_id=uuid4(), prompt_yaml=yaml.safe_dump(document))
    with pytest.raises(HTTPException) as error:
        await api.create_agent_rerun(source.test_run_id, other, None)
    assert error.value.status_code == 404

    async def reader(**_):
        return SimpleNamespace(role="viewer")

    monkeypatch.setattr(api, "WorkspaceRepository", lambda _: SimpleNamespace(get_for_user=reader))
    with pytest.raises(HTTPException) as error:
        await api.create_agent_rerun(source.test_run_id, other, None)
    assert error.value.status_code == 403
