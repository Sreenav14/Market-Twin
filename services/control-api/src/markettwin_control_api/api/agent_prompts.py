"""Inspect historical prompts and create an immutable, edited rerun draft."""

import json
from collections.abc import Callable, Iterator
from copy import deepcopy
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

import yaml
from fastapi import APIRouter, HTTPException, Request
from markettwin_database.models.execution import (
    AgentExecution,
    AgentPromptDraft,
    AgentRuntimeSnapshot,
    RunEvent,
)
from markettwin_database.models.testing import PersonaJourney, RunMission, RunPersona, TestRun
from markettwin_shared.agent_configuration import (
    BROWSER_TOOLS,
    default_configuration,
    validate_configuration,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import get_authenticated_user_id
from markettwin_control_api.api.permissions import WORKSPACE_WRITE_ROLES
from markettwin_control_api.api.runtime_snapshots import build_runtime_snapshot_response
from markettwin_control_api.api.test_run import TestRunResponse, test_run_response
from markettwin_control_api.persistence.repositories import (
    RuntimeSnapshotRecord,
    RuntimeSnapshotRepository,
    TargetAuthorizationRepository,
    TargetRepository,
    TestRunRepository,
    WorkspaceRepository,
)

router = APIRouter(tags=["Agent Prompts"])


@router.get("/api/v1/workspaces/{workspace_id}/agent-prompts")
async def list_workspace_agents(
    workspace_id: UUID,
    request: Request,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    order: Literal["newest", "oldest"] = "newest",
) -> dict[str, object]:
    """Find recorded agents by creation time within the authorized workspace."""
    user_id = await get_authenticated_user_id(request=request)
    if any(value is not None and value.tzinfo is None for value in (created_after, created_before)):
        raise HTTPException(422, "Creation date filters must include a timezone.")
    if created_after is not None and created_before is not None and created_after >= created_before:
        raise HTTPException(422, "Choose a valid creation date range.")
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        workspace = await WorkspaceRepository(session).get_for_user(
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if workspace is None:
            raise HTTPException(404, "Workspace not found.")
        statement = (
            select(AgentRuntimeSnapshot, AgentExecution, TestRun.configuration_snapshot)
            .join(
                TestRun,
                TestRun.id == AgentRuntimeSnapshot.test_run_id,
            )
            .outerjoin(AgentExecution, AgentExecution.id == AgentRuntimeSnapshot.execution_id)
            .where(
                TestRun.workspace_id == workspace_id,
                AgentRuntimeSnapshot.agent_role.in_(("meta", "persona")),
            )
        )
        if created_after is not None:
            statement = statement.where(AgentRuntimeSnapshot.created_at >= created_after)
        if created_before is not None:
            statement = statement.where(AgentRuntimeSnapshot.created_at < created_before)
        statement = statement.order_by(
            AgentRuntimeSnapshot.created_at.desc()
            if order == "newest"
            else AgentRuntimeSnapshot.created_at.asc(),
            AgentRuntimeSnapshot.id.desc() if order == "newest" else AgentRuntimeSnapshot.id.asc(),
        ).limit(100)
        rows = (await session.execute(statement)).all()
        timings = await _recorded_timings(session, [snapshot.id for snapshot, _, _ in rows])
    return {
        "limit": 100,
        "agents": [
            {
                "snapshot": {
                    "id": str(snapshot.id),
                    "test_run_id": str(snapshot.test_run_id),
                    "created_at": snapshot.created_at.isoformat(),
                    "agent_role": snapshot.agent_role,
                    "runtime_agent_name": snapshot.runtime_agent_name,
                    "model_name": snapshot.model_name,
                    "persona_snapshot": snapshot.persona_snapshot,
                    "mission_snapshot": snapshot.mission_snapshot,
                },
                "test_brief": str(configuration.get("study_brief", "Test")),
                **_execution_timing(execution, timings.get(str(snapshot.id))),
            }
            for snapshot, execution, configuration in rows
        ],
    }


class PromptYamlDumper(yaml.SafeDumper):
    """Use literal blocks so multiline prompts can be edited naturally."""

    def ignore_aliases(self, data: object) -> bool:
        # Recorded structure and editable configuration can share the same object.
        return True


def _prompt_string(dumper: PromptYamlDumper, value: str) -> yaml.ScalarNode:
    # PyYAML's callback internals have incomplete third-party type annotations.
    represent = cast(Callable[..., yaml.ScalarNode], dumper.represent_scalar)  # pyright: ignore[reportUnknownMemberType]
    return represent("tag:yaml.org,2002:str", value, style="|" if "\n" in value else None)


PromptYamlDumper.add_representer(str, _prompt_string)


def prompt_document(snapshot: RuntimeSnapshotRecord) -> dict[str, object]:
    """Show immutable runtime context alongside editable prompt and rerun YAML."""
    structure_value = snapshot.metadata.get("agent_structure")
    structure: dict[str, object] = (
        cast(dict[str, object], structure_value) if isinstance(structure_value, dict) else {
            "name": snapshot.runtime_agent_name, "agent_type": "LlmAgent", "sub_agents": [],
        }
    )
    return {
        "snapshot_id": str(snapshot.snapshot_id),
        "agent_role": snapshot.agent_role,
        "agent_name": snapshot.runtime_agent_name,
        "agent_type": structure.get("agent_type", "LlmAgent"),
        "agent_structure": structure,
        "model": snapshot.model_name,
        "model_configuration": snapshot.model_configuration,
        "tools": list(snapshot.tools),
        "persona": snapshot.persona_snapshot,
        "mission": snapshot.mission_snapshot,
        "instruction": snapshot.effective_instruction,
        "runtime_prompt": snapshot.runtime_prompt,
        "rerun_configuration": structure.get("configuration") or default_configuration(
            snapshot.runtime_agent_name
            if snapshot.runtime_agent_name and snapshot.runtime_agent_name.startswith("Agent_")
            else "Agent_1",
            snapshot.tools if snapshot.agent_role == "persona" else (),
        ),
    }


class PromptYamlLoader(yaml.SafeLoader):
    """Reject duplicate keys instead of silently discarding user edits."""


def _unique_mapping(loader: PromptYamlLoader, node: yaml.MappingNode) -> dict[str, object]:
    mapping: dict[str, object] = {}
    construct = cast(Callable[[yaml.Node], object], loader.construct_object)  # pyright: ignore[reportUnknownMemberType]
    for key_node, value_node in node.value:
        key = construct(key_node)
        if not isinstance(key, str) or key in mapping:
            raise ValueError("YAML keys must be unique strings.")
        mapping[key] = construct(value_node)
    return mapping


PromptYamlLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def parse_prompt_edit(document: str, snapshot: RuntimeSnapshotRecord) -> dict[str, str]:
    """Validate prompt/rerun edits while preserving the recorded runtime identity."""
    try:
        parse = cast(Callable[[str], Iterator[object]], yaml.parse)  # pyright: ignore[reportUnknownMemberType]
        if any(isinstance(event, yaml.AliasEvent) for event in parse(document)):
            raise ValueError("YAML aliases are not supported in agent prompts.")
        value: object = yaml.load(document, Loader=PromptYamlLoader)
    except (yaml.YAMLError, ValueError, TypeError, RecursionError) as error:
        raise ValueError("Enter valid YAML with unique keys and no aliases.") from error
    expected = prompt_document(snapshot)
    if not isinstance(value, dict):
        raise ValueError(
            "Keep the original YAML fields; edit instruction, runtime_prompt, "
            "and rerun_configuration."
        )
    document_value = cast(dict[str, object], value)
    if "rerun_configuration" not in document_value:
        document_value["rerun_configuration"] = expected["rerun_configuration"]
    for field in ("agent_type", "agent_structure"):
        if field not in document_value:
            document_value[field] = expected[field]
    if set(document_value) != set(expected):
        raise ValueError(
            "Keep the original YAML fields; edit instruction, runtime_prompt, "
            "and rerun_configuration."
        )
    for key in expected:
        if (key not in {"instruction", "runtime_prompt", "rerun_configuration"}
                and document_value[key] != expected[key]):
            raise ValueError(
                f"{key} is read-only. Edit instruction, runtime_prompt, "
                "and rerun_configuration."
            )
    result: dict[str, str] = {}
    for key in ("instruction", "runtime_prompt"):
        text = document_value[key]
        if not isinstance(text, str) or not text.strip() or len(text) > 60_000:
            raise ValueError(f"{key} must contain between 1 and 60,000 characters.")
        result[key] = text
    result["agent_configuration"] = json.dumps(validate_configuration(
        document_value["rerun_configuration"], browser_allowed=snapshot.agent_role == "persona",
    ))
    return result


class AgentPromptResponse(BaseModel):
    test_run_id: UUID
    agents: list[dict[str, object]]


@router.get("/api/v1/test-runs/{test_run_id}/agent-prompts", response_model=AgentPromptResponse)
async def get_agent_prompts(test_run_id: UUID, request: Request) -> AgentPromptResponse:
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        run = await TestRunRepository(session).get_for_user(
            test_run_id=test_run_id, user_id=user_id
        )
        if run is None:
            raise HTTPException(404, "Test run not found.")
        snapshots = await RuntimeSnapshotRepository(session).list_for_run(test_run_id=test_run_id)
        drafts = (
            await session.scalars(
                select(AgentPromptDraft).where(
                    AgentPromptDraft.user_id == user_id,
                    AgentPromptDraft.snapshot_id.in_([item.snapshot_id for item in snapshots]),
                )
            )
        ).all()
        drafts_by_snapshot = {item.snapshot_id: item for item in drafts}
        executions = (
            await session.scalars(
                select(AgentExecution).where(
                    AgentExecution.id.in_(
                        [item.execution_id for item in snapshots if item.execution_id is not None]
                    ),
                )
            )
        ).all()
        executions_by_id = {item.id: item for item in executions}
        timings = await _recorded_timings(session, [item.snapshot_id for item in snapshots])
    return AgentPromptResponse(
        test_run_id=test_run_id,
        agents=[
            {
                "snapshot": build_runtime_snapshot_response(item).model_dump(mode="json"),
                "saved_yaml": drafts_by_snapshot[item.snapshot_id].prompt_yaml
                if item.snapshot_id in drafts_by_snapshot
                else None,
                "saved_at": drafts_by_snapshot[item.snapshot_id].updated_at.isoformat()
                if item.snapshot_id in drafts_by_snapshot
                else None,
                **_execution_timing(
                    executions_by_id.get(item.execution_id)
                    if item.execution_id is not None
                    else None,
                    timings.get(str(item.snapshot_id)),
                ),
                "yaml": yaml.dump(
                    prompt_document(item),
                    Dumper=PromptYamlDumper,
                    sort_keys=False,
                    allow_unicode=True,
                    width=100,
                ),
                "available_tools": list(BROWSER_TOOLS) if item.agent_role == "persona" else [],
                "rerun_configuration": json.loads(parse_prompt_edit(
                    drafts_by_snapshot[item.snapshot_id].prompt_yaml
                    if item.snapshot_id in drafts_by_snapshot
                    else yaml.dump(prompt_document(item), Dumper=PromptYamlDumper), item,
                )["agent_configuration"]) if item.agent_role in {"meta", "persona"} else None,
            }
            for item in snapshots
        ],
    )


async def _recorded_timings(
    session: AsyncSession,
    snapshot_ids: list[UUID],
) -> dict[str, dict[str, object]]:
    events = (
        await session.scalars(
            select(RunEvent)
            .where(
                RunEvent.event_type == "agent.runtime",
                RunEvent.payload["snapshot_id"].astext.in_([str(value) for value in snapshot_ids]),
            )
            .order_by(RunEvent.id.desc())
        )
    ).all()
    timings: dict[str, dict[str, object]] = {}
    for event in events:
        timings.setdefault(str(event.payload.get("snapshot_id")), event.payload)
    return timings


def _execution_timing(
    execution: AgentExecution | None,
    recorded: dict[str, object] | None = None,
) -> dict[str, object]:
    if execution is None and recorded is not None:
        return {
            "execution_started_at": recorded.get("started_at"),
            "execution_completed_at": recorded.get("completed_at"),
            "duration_seconds": recorded.get("duration_seconds"),
        }
    started = execution.started_at if execution is not None else None
    completed = execution.completed_at if execution is not None else None
    return {
        "execution_started_at": started.isoformat() if started is not None else None,
        "execution_completed_at": completed.isoformat() if completed is not None else None,
        "duration_seconds": max(0.0, (completed - started).total_seconds())
        if started is not None and completed is not None
        else None,
    }


class RerunAgentRequest(BaseModel):
    snapshot_id: UUID
    prompt_yaml: str = Field(min_length=1, max_length=150_000)
    agent_configuration: dict[str, object] | None = None


class SavePromptRequest(BaseModel):
    prompt_yaml: str = Field(min_length=1, max_length=150_000)
    agent_configuration: dict[str, object] | None = None


def configured_prompt(
    document: str, settings: dict[str, object] | None, snapshot: RuntimeSnapshotRecord,
) -> str:
    edits = parse_prompt_edit(document, snapshot)
    if settings is None:
        return document
    configuration = validate_configuration(
        settings, browser_allowed=snapshot.agent_role == "persona",
    )
    return yaml.dump(
        {**prompt_document(snapshot), "instruction": edits["instruction"],
         "runtime_prompt": edits["runtime_prompt"], "rerun_configuration": configuration},
        Dumper=PromptYamlDumper, sort_keys=False, allow_unicode=True,
    )


class SavedPromptResponse(BaseModel):
    prompt_yaml: str
    updated_at: datetime


@router.put(
    "/api/v1/test-runs/{test_run_id}/agent-prompts/{snapshot_id}/draft",
    response_model=SavedPromptResponse,
)
async def save_agent_prompt(
    test_run_id: UUID,
    snapshot_id: UUID,
    payload: SavePromptRequest,
    request: Request,
) -> SavedPromptResponse:
    """Save a personal edit without changing or executing the historical agent."""
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        async with session.begin():
            run = await TestRunRepository(session).get_for_user(
                test_run_id=test_run_id,
                user_id=user_id,
            )
            if run is None:
                raise HTTPException(404, "Test run not found.")
            workspace = await WorkspaceRepository(session).get_for_user(
                workspace_id=run.workspace_id,
                user_id=user_id,
            )
            if workspace is None or workspace.role not in WORKSPACE_WRITE_ROLES:
                raise HTTPException(403, "Your workspace role cannot save agent prompts.")
            snapshots = await RuntimeSnapshotRepository(session).list_for_run(
                test_run_id=test_run_id,
            )
            snapshot = next((item for item in snapshots if item.snapshot_id == snapshot_id), None)
            if snapshot is None:
                raise HTTPException(404, "Agent snapshot not found for this test.")
            if snapshot.agent_role not in {"meta", "persona"}:
                raise HTTPException(422, "This agent's recorded context is read-only.")
            try:
                payload.prompt_yaml = configured_prompt(
                    payload.prompt_yaml, payload.agent_configuration, snapshot,
                )
                parse_prompt_edit(payload.prompt_yaml, snapshot)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            statement = (
                insert(AgentPromptDraft)
                .values(
                    snapshot_id=snapshot_id,
                    user_id=user_id,
                    prompt_yaml=payload.prompt_yaml,
                )
                .on_conflict_do_update(
                    index_elements=[AgentPromptDraft.snapshot_id, AgentPromptDraft.user_id],
                    set_={"prompt_yaml": payload.prompt_yaml, "updated_at": func.now()},
                )
                .returning(AgentPromptDraft.updated_at)
            )
            updated_at = (await session.execute(statement)).scalar_one()
    return SavedPromptResponse(prompt_yaml=payload.prompt_yaml, updated_at=updated_at)


@router.post(
    "/api/v1/test-runs/{test_run_id}/agent-reruns", response_model=TestRunResponse, status_code=201
)
async def create_agent_rerun(
    test_run_id: UUID, payload: RerunAgentRequest, request: Request
) -> TestRunResponse:
    """Create a draft: execution still requires the normal explicit Start action."""
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        async with session.begin():
            repository = TestRunRepository(session)
            source = await repository.get_for_user(test_run_id=test_run_id, user_id=user_id)
            if source is None:
                raise HTTPException(404, "Test run not found.")
            workspace = await WorkspaceRepository(session).get_for_user(
                workspace_id=source.workspace_id, user_id=user_id
            )
            if workspace is None or workspace.role not in WORKSPACE_WRITE_ROLES:
                raise HTTPException(403, "Your workspace role cannot create test runs.")
            snapshots = await RuntimeSnapshotRepository(session).list_for_run(
                test_run_id=test_run_id
            )
            snapshot = next(
                (item for item in snapshots if item.snapshot_id == payload.snapshot_id), None
            )
            if snapshot is None:
                raise HTTPException(404, "Agent snapshot not found for this test.")
            if snapshot.agent_role not in {"meta", "persona"}:
                raise HTTPException(422, "Only planner and persona prompts can be rerun here.")
            try:
                payload.prompt_yaml = configured_prompt(
                    payload.prompt_yaml, payload.agent_configuration, snapshot,
                )
                edited = parse_prompt_edit(payload.prompt_yaml, snapshot)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            target = await TargetRepository(session).get_for_user(
                target_id=source.target_id, user_id=user_id
            )
            if (
                target is None
                or await TargetAuthorizationRepository(session).get_active(
                    target_id=source.target_id
                )
                is None
            ):
                raise HTTPException(409, "Target is not currently authorized for testing.")
            config = deepcopy(source.configuration_snapshot)
            # A new fork uses exactly the selected source agent, not an inherited fork's edits.
            config.pop("agent_prompt_overrides", None)
            config.pop("replay_plan", None)
            config["rerun_of_test_run_id"] = str(test_run_id)
            config["source_agent_snapshot_id"] = str(snapshot.snapshot_id)
            key = "meta"
            if snapshot.agent_role == "persona":
                personas = (
                    await session.scalars(
                        select(RunPersona)
                        .where(RunPersona.test_run_id == test_run_id)
                        .order_by(RunPersona.ordinal)
                    )
                ).all()
                missions = (
                    await session.scalars(
                        select(RunMission)
                        .where(RunMission.test_run_id == test_run_id)
                        .order_by(RunMission.ordinal)
                    )
                ).all()
                journey = await session.get(PersonaJourney, snapshot.journey_id)
                persona = next(
                    (item for item in personas if journey and item.id == journey.persona_id), None
                )
                mission = next(
                    (item for item in missions if journey and item.id == journey.mission_id), None
                )
                if (
                    persona is None
                    or mission is None
                    or len(personas) != 3
                    or not 1 <= len(missions) <= 4
                ):
                    raise HTTPException(
                        409, "The source test does not have a complete reusable plan."
                    )
                config["replay_plan"] = {
                    "mission_summary": str(config["study_brief"])[:500],
                    "personas": [
                        {
                            "persona_id": item.attributes["persona_key"],
                            "name": item.name,
                            "perspective": item.description,
                            "behavior_traits": item.attributes["behavior_traits"],
                            "priorities": item.attributes["priorities"],
                        }
                        for item in personas
                    ],
                    "missions": [
                        {
                            "mission_id": f"mission_{item.ordinal}",
                            "name": item.title,
                            "objective": item.objective,
                            "success_criteria": item.success_criteria,
                            "priority": item.priority,
                        }
                        for item in missions
                    ],
                }
                key = f"{persona.attributes['persona_key']}__mission_{mission.ordinal}"
            config["agent_prompt_overrides"] = {key: edited}
            draft = await repository.create(
                workspace_id=source.workspace_id,
                application_id=source.application_id,
                target_id=source.target_id,
                created_by_user_id=user_id,
                target_snapshot=deepcopy(source.target_snapshot),
                configuration_snapshot=config,
            )
    return test_run_response(draft)
