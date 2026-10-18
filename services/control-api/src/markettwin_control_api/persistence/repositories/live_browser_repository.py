"""Authorized, read-only browser selection and safe durable activity projection."""

import base64
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, TypeVar
from typing import cast as typed_cast
from uuid import UUID

from markettwin_database.models import (
    ActionApprovalRequest,
    AgentExecution,
    ApplicationTarget,
    BrowserSession,
    ExecutionPauseRequest,
    ExecutionStep,
    HumanActionRequest,
    PersonaJourney,
    Report,
    RunEvent,
    RunMission,
    RunPersona,
    TargetAllowedOrigin,
    TargetAuthorization,
    TestRun,
    User,
    Workspace,
    WorkspaceMember,
)
from sqlalchemy import Row, Select, String, and_, cast, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from markettwin_control_api.persistence.repositories.test_run_results_repository import (
    safe_action_summary,
)

RowValues = TypeVar("RowValues", bound=tuple[Any, ...])

EVENTS = {
    "agent.runtime": ("planner", "completed", "Agent runtime recorded."),
    "test_plan.created": ("planner", "completed", "Feature plan saved."),
    "test_case.started": ("deterministic_case", "started", "Feature case started."),
    "test_case.completed": ("deterministic_case", "completed", "Feature case recorded."),
    "test_case.skipped": ("deterministic_case", "skipped", "Feature case not run."),
    "journey.result": ("system", "completed", "Journey result recorded."),
    "run.collection": ("system", "completed", "Execution outputs collected."),
}


def decode_cursor(value: str | None) -> tuple[datetime, str] | None:
    if value is None:
        return None
    try:
        decoded: object = json.loads(base64.b64decode(value, altchars=b"-_", validate=True))
        if not isinstance(decoded, list):
            raise ValueError
        raw = typed_cast(list[object], decoded)
        if (len(raw) != 2 or not isinstance(raw[0], str)
                or not isinstance(raw[1], str) or len(raw[1]) > 100):
            raise ValueError
        timestamp = datetime.fromisoformat(raw[0])
        if timestamp.tzinfo is None:
            raise ValueError
        return timestamp, raw[1]
    except (ValueError, TypeError, IndexError, KeyError):
        raise ValueError("Invalid activity cursor.") from None


class LiveBrowserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def authorized_run(self, *, run_id: UUID, actor_id: UUID) -> TestRun | None:
        now = datetime.now(UTC)
        run = await self.session.scalar(
            select(TestRun).join(Workspace, Workspace.id == TestRun.workspace_id)
            .join(WorkspaceMember, and_(WorkspaceMember.workspace_id == Workspace.id,
                                       WorkspaceMember.user_id == actor_id))
            .join(User, User.id == actor_id)
            .join(ApplicationTarget, ApplicationTarget.id == TestRun.target_id)
            .where(
                TestRun.id == run_id, WorkspaceMember.role.in_(("owner", "admin")),
                Workspace.status == "active", Workspace.deleted_at.is_(None),
                User.status == "active", User.deleted_at.is_(None),
                ApplicationTarget.application_id == TestRun.application_id,
                ApplicationTarget.status == "active", ApplicationTarget.deleted_at.is_(None),
                select(TargetAuthorization.id).where(
                    TargetAuthorization.target_id == TestRun.target_id,
                    TargetAuthorization.status == "authorized",
                    TargetAuthorization.revoked_at.is_(None),
                    or_(TargetAuthorization.expires_at.is_(None),
                        TargetAuthorization.expires_at > now),
                ).exists(),
            ).execution_options(populate_existing=True)
        )
        if run is None or run.target_snapshot.get("target_id") != str(run.target_id):
            return None
        frozen = run.target_snapshot.get("allowed_origins")
        if not isinstance(frozen, list) or not frozen:
            return None
        current = (await self.session.scalars(select(TargetAllowedOrigin).where(
            TargetAllowedOrigin.target_id == run.target_id,
        ))).all()
        approved = {(item.scheme, item.hostname, item.port, item.include_subdomains)
                    for item in current}
        for raw_origin in typed_cast(list[object], frozen):
            if not isinstance(raw_origin, dict):
                return None
            origin = typed_cast(dict[str, object], raw_origin)
            if (not isinstance(origin.get("scheme"), str)
                    or not isinstance(origin.get("hostname"), str)
                    or (origin.get("port") is not None and type(origin.get("port")) is not int)
                    or type(origin.get("include_subdomains")) is not bool):
                return None
            if (
                origin.get("scheme"), origin.get("hostname"), origin.get("port"),
                origin.get("include_subdomains"),
            ) not in approved:
                return None
        return run

    async def selected_browser(
        self, *, run: TestRun, browser_session_id: UUID | None,
    ) -> dict[str, object] | None:
        statement = (
            select(BrowserSession, AgentExecution, PersonaJourney,
                   RunMission.title, RunPersona.name)
            .join(AgentExecution, AgentExecution.id == BrowserSession.execution_id)
            .join(PersonaJourney, PersonaJourney.id == AgentExecution.journey_id)
            .join(RunMission, RunMission.id == PersonaJourney.mission_id)
            .join(RunPersona, RunPersona.id == PersonaJourney.persona_id)
            .where(PersonaJourney.test_run_id == run.id, BrowserSession.state == "open")
            .order_by(BrowserSession.created_at.desc(), BrowserSession.id.desc()).limit(1)
            .execution_options(populate_existing=True)
        )
        if browser_session_id is not None:
            statement = statement.where(BrowserSession.id == browser_session_id)
        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            return None
        browser, execution, journey, title, persona = row
        active = run.status in {"planning", "running", "awaiting_human"}
        available = (active and execution.status == "running"
                     and browser.control_mode in {"agent", "human_pending"})
        discovery = execution.runtime_name in {"human_auth_bootstrap_v1", "browser_discovery_v1"}
        return {
            "browser_session_id": browser.id, "execution_id": execution.id,
            "journey_id": journey.id, "generation": browser.control_generation,
            "control_state": browser.control_mode,
            "viewer_state": "available" if available else "suppressed",
            "journey_title": "Browser discovery" if discovery else title,
            "requesting_agent": "Browser discovery" if discovery else persona,
        }

    async def activity(
        self, *, run_id: UUID, cursor: str | None, limit: int,
    ) -> dict[str, object]:
        """Refresh latest window; history cursor never pretends to be a commit watermark."""
        boundary = decode_cursor(cursor)
        items: list[dict[str, object]] = []

        async def rows(
            statement: Select[RowValues], timestamp: InstrumentedAttribute[datetime],
            identifier: InstrumentedAttribute[int] | InstrumentedAttribute[UUID], namespace: str,
        ) -> Sequence[Row[RowValues]]:
            key = (literal(namespace + ":") + cast(identifier, String)).collate("C")
            if boundary is not None:
                statement = statement.where(or_(
                    timestamp < boundary[0],
                    and_(timestamp == boundary[0], key < boundary[1]),
                ))
            return (await self.session.execute(
                statement.order_by(timestamp.desc(), key.desc()).limit(limit + 1)
            )).all()

        def add(identifier: str, timestamp: datetime, source: str, kind: str, status: str,
                title: str, journey: UUID | None = None, execution: UUID | None = None,
                step: int | None = None) -> None:
            items.append({
                "id": identifier, "run_id": run_id, "journey_id": journey,
                "execution_id": execution, "step_id": step, "source": source,
                "kind": kind, "status": status, "occurred_at": timestamp, "title": title,
            })

        for step, execution in await rows(
            select(ExecutionStep, AgentExecution)
            .join(AgentExecution, AgentExecution.id == ExecutionStep.execution_id)
            .join(PersonaJourney, PersonaJourney.id == AgentExecution.journey_id)
            .where(PersonaJourney.test_run_id == run_id),
            ExecutionStep.created_at, ExecutionStep.id, "step",
        ):
            source = ("deterministic_case"
                      if execution.runtime_name == "deterministic_case_steps_v1"
                      else "browser_agent")
            add(f"step:{step.id}", step.created_at, source, "browser_action", step.status,
                safe_action_summary(step), execution.journey_id, execution.id, step.id)
        for (event,) in await rows(
            select(RunEvent).where(RunEvent.test_run_id == run_id,
                                   RunEvent.event_type.in_(tuple(EVENTS))),
            RunEvent.occurred_at, RunEvent.id, "event",
        ):
            source, status, title = EVENTS[event.event_type]
            add(f"event:{event.id}", event.occurred_at, source, event.event_type, status,
                title, event.journey_id, event.execution_id)
        for request, journey_id in await rows(
            select(HumanActionRequest, AgentExecution.journey_id)
            .join(AgentExecution, AgentExecution.id == HumanActionRequest.execution_id)
            .join(PersonaJourney, PersonaJourney.id == AgentExecution.journey_id)
            .where(PersonaJourney.test_run_id == run_id),
            HumanActionRequest.created_at, HumanActionRequest.id, "human",
        ):
            add(f"human:{request.id}", request.created_at, "human_assistance", "human_request",
                request.status, "Human assistance request.", journey_id, request.execution_id)
        for approval, journey_id in await rows(
            select(ActionApprovalRequest, AgentExecution.journey_id)
            .join(AgentExecution, AgentExecution.id == ActionApprovalRequest.execution_id)
            .where(ActionApprovalRequest.test_run_id == run_id),
            ActionApprovalRequest.created_at, ActionApprovalRequest.id, "approval",
        ):
            add(f"approval:{approval.id}", approval.created_at, "approval", "action_approval",
                approval.status, "Sensitive action approval request.",
                journey_id, approval.execution_id, approval.step_id)
        for (report,) in await rows(
            select(Report).where(Report.test_run_id == run_id),
            Report.created_at, Report.id, "report",
        ):
            add(f"report:{report.id}", report.created_at, "report", "report",
                report.status, "Evaluation report.")
        for (pause,) in await rows(
            select(ExecutionPauseRequest).where(ExecutionPauseRequest.test_run_id == run_id),
            ExecutionPauseRequest.created_at, ExecutionPauseRequest.id, "pause",
        ):
            add(f"pause:{pause.id}", pause.created_at, "human_assistance", "execution_pause",
                pause.status, "Operator pause request.", pause.journey_id, pause.execution_id,
                pause.last_durable_step_id)
        items.sort(key=lambda item: (typed_cast(datetime, item["occurred_at"]),
                                     str(item["id"])), reverse=True)
        page = items[:limit]
        next_cursor = None
        if len(items) > limit:
            last = page[-1]
            next_cursor = base64.urlsafe_b64encode(json.dumps([
                typed_cast(datetime, last["occurred_at"]).isoformat(), last["id"],
            ]).encode()).decode()
        return {"items": page, "next_cursor": next_cursor}
