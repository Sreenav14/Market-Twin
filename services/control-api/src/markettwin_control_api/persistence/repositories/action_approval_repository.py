"""Transactional, one-time approval decisions for sensitive test actions."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from markettwin_database.models.execution import (
    ActionApprovalReceipt,
    ActionApprovalRequest,
    AgentExecution,
)
from markettwin_database.models.testing import PersonaJourney
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.api.permissions import TARGET_AUTHORIZATION_ROLES
from markettwin_control_api.persistence.models import (
    ApplicationTarget,
    TargetAuthorization,
    TestRun,
    Workspace,
    WorkspaceMember,
)


class ApprovalRejectedError(RuntimeError):
    """Approval is unavailable, expired, unauthorized, or already consumed."""


@dataclass(frozen=True, slots=True)
class ActionApproval:
    id: UUID
    test_run_id: UUID
    action_summary: str
    environment: str
    status: str
    expires_at: datetime


def action_fingerprint(action: dict[str, object]) -> str:
    """Hash a canonical action without persisting its values or credentials."""
    encoded = json.dumps(action, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ActionApprovalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def expire_due(self, *, limit: int = 100) -> int:
        """Move a bounded set of overdue unconsumed approvals to terminal state."""
        if limit < 1 or limit > 1000:
            raise ValueError("Approval expiry batch size must be between 1 and 1000.")
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(ActionApprovalRequest)
            .where(
                ActionApprovalRequest.status.in_(("pending", "approved")),
                ActionApprovalRequest.expires_at <= now,
            )
            .order_by(ActionApprovalRequest.expires_at)
            .limit(limit)
            .with_for_update(of=ActionApprovalRequest, skip_locked=True)
        )
        approvals = result.scalars().all()
        for approval in approvals:
            approval.status = "expired"
        await self._session.flush()
        return len(approvals)

    async def create(
        self,
        *,
        test_run_id: UUID,
        execution_id: UUID,
        step_id: int,
        requested_by_user_id: UUID,
        action: dict[str, object],
        resource: dict[str, object],
        environment: str,
        policy_version: int,
        action_summary: str,
        expires_at: datetime,
    ) -> ActionApproval:
        """Persist only fingerprints and a caller-supplied nonsecret summary."""
        now = datetime.now(UTC)
        if (
            not action
            or not resource
            or policy_version < 1
            or expires_at <= now
            or len(action_summary) > 300
            or environment not in {"local", "development", "staging", "test"}
        ):
            raise ValueError("Invalid bounded approval request.")
        run_context = await self._session.execute(
            select(TestRun.created_by_user_id, ApplicationTarget.environment)
            .join(ApplicationTarget, ApplicationTarget.id == TestRun.target_id)
            .join(PersonaJourney, PersonaJourney.test_run_id == TestRun.id)
            .join(AgentExecution, AgentExecution.journey_id == PersonaJourney.id)
            .where(TestRun.id == test_run_id, AgentExecution.id == execution_id)
        )
        context = run_context.one_or_none()
        if context is None or context[0] != requested_by_user_id or context[1] != environment:
            raise ValueError("Approval context does not match the test run.")
        approval = ActionApprovalRequest(
            id=uuid4(),
            test_run_id=test_run_id,
            execution_id=execution_id,
            step_id=step_id,
            requested_by_user_id=requested_by_user_id,
            action_fingerprint=action_fingerprint(action),
            resource_fingerprint=action_fingerprint(resource),
            environment=environment,
            policy_version=policy_version,
            action_summary=action_summary,
            status="pending",
            expires_at=expires_at,
        )
        self._session.add(approval)
        await self._session.flush()
        return ActionApproval(
            approval.id,
            approval.test_run_id,
            approval.action_summary,
            approval.environment,
            approval.status,
            approval.expires_at,
        )

    async def decide(
        self,
        *,
        approval_id: UUID,
        actor_id: UUID,
        approved: bool,
    ) -> ActionApproval:
        now = datetime.now(UTC)
        row = await self._session.execute(
            select(ActionApprovalRequest)
            .join(TestRun, TestRun.id == ActionApprovalRequest.test_run_id)
            .join(Workspace, Workspace.id == TestRun.workspace_id)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .join(ApplicationTarget, ApplicationTarget.id == TestRun.target_id)
            .join(TargetAuthorization, TargetAuthorization.target_id == ApplicationTarget.id)
            .where(
                ActionApprovalRequest.id == approval_id,
                Workspace.status == "active",
                Workspace.deleted_at.is_(None),
                WorkspaceMember.user_id == actor_id,
                WorkspaceMember.role.in_(TARGET_AUTHORIZATION_ROLES),
                ApplicationTarget.status == "active",
                ApplicationTarget.deleted_at.is_(None),
                TargetAuthorization.status == "authorized",
                TargetAuthorization.revoked_at.is_(None),
                (TargetAuthorization.expires_at.is_(None))
                | (TargetAuthorization.expires_at > now),
            )
            .order_by(TargetAuthorization.created_at.desc())
            .limit(1)
            .with_for_update(of=ActionApprovalRequest)
        )
        approval = row.scalar_one_or_none()
        if approval is None or approval.status != "pending":
            raise ApprovalRejectedError("Approval request is unavailable.")
        if approval.expires_at <= now:
            raise ApprovalRejectedError("Approval request expired.")
        approval.status = "approved" if approved else "rejected"
        approval.decision_by_user_id = actor_id
        approval.decided_at = now
        await self._session.flush()
        return ActionApproval(
            approval.id,
            approval.test_run_id,
            approval.action_summary,
            approval.environment,
            approval.status,
            approval.expires_at,
        )

    async def consume(
        self,
        *,
        approval_id: UUID,
        expected_fingerprint: str,
        expected_resource_fingerprint: str,
        environment: str,
        policy_version: int,
    ) -> ActionApprovalReceipt:
        """Commit this receipt before dispatch; an uncertain dispatch is not replayable."""
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(ActionApprovalRequest)
            .join(TestRun, TestRun.id == ActionApprovalRequest.test_run_id)
            .join(Workspace, Workspace.id == TestRun.workspace_id)
            .join(ApplicationTarget, ApplicationTarget.id == TestRun.target_id)
            .join(TargetAuthorization, TargetAuthorization.target_id == ApplicationTarget.id)
            .where(
                ActionApprovalRequest.id == approval_id,
                Workspace.status == "active",
                Workspace.deleted_at.is_(None),
                ApplicationTarget.status == "active",
                ApplicationTarget.deleted_at.is_(None),
                TargetAuthorization.status == "authorized",
                TargetAuthorization.revoked_at.is_(None),
                (TargetAuthorization.expires_at.is_(None))
                | (TargetAuthorization.expires_at > now),
            )
            .order_by(TargetAuthorization.created_at.desc())
            .limit(1)
            .with_for_update(of=(ActionApprovalRequest, TargetAuthorization))
        )
        approval = result.scalar_one_or_none()
        if (
            approval is None
            or approval.status != "approved"
            or approval.expires_at <= now
            or approval.action_fingerprint != expected_fingerprint
            or approval.resource_fingerprint != expected_resource_fingerprint
            or approval.environment != environment
            or approval.policy_version != policy_version
        ):
            raise ApprovalRejectedError("Approval does not match this action.")
        receipt = ActionApprovalReceipt(
            approval_id=approval.id,
            action_fingerprint=expected_fingerprint,
            dispatch_state="claimed",
        )
        self._session.add(receipt)
        approval.status = "consumed"
        await self._session.flush()
        return receipt

    async def mark_completed(self, *, approval_id: UUID) -> None:
        receipt = await self._session.get(ActionApprovalReceipt, approval_id)
        if receipt is None or receipt.dispatch_state != "claimed":
            raise ApprovalRejectedError("Approval receipt is unavailable.")
        receipt.dispatch_state = "completed"
        receipt.completed_at = datetime.now(UTC)
        await self._session.flush()
