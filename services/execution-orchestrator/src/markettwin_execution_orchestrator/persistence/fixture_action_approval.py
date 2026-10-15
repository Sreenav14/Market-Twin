"""Approval lifecycle for the single local synthetic registration action."""

import asyncio
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID

from markettwin_database.models.core import Workspace, WorkspaceMember
from markettwin_database.models.execution import ActionApprovalReceipt, ActionApprovalRequest
from markettwin_database.models.testing import (
    ApplicationTarget,
    TargetAuthorization,
    TestRun,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class FixtureApprovalRejected(RuntimeError):
    """The exact synthetic action was unavailable, rejected, expired, or replayed."""


class FixtureActionApproval:
    POLICY_VERSION = 1
    ACTION = {"action_id": "registration_submit", "case_id": "valid", "button": "Save"}
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def fingerprint(value: Mapping[str, object]) -> str:
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @classmethod
    def resource_fingerprint(
        cls, *, run_id: UUID, target_id: UUID, environment: str
    ) -> str:
        return cls.fingerprint(
            {
                "fixture": "deep-testing-app",
                "route": "/registration",
                "test_run_id": str(run_id),
                "target_id": str(target_id),
                "environment": environment,
            }
        )

    async def create(
        self,
        *,
        run_id: UUID,
        execution_id: UUID,
        step_id: int,
        owner_id: UUID,
        environment: str,
    ) -> UUID:
        authorized = await self.session.execute(
            select(TestRun.id, TestRun.target_id)
            .join(Workspace, Workspace.id == TestRun.workspace_id)
            .join(ApplicationTarget, ApplicationTarget.id == TestRun.target_id)
            .join(TargetAuthorization, TargetAuthorization.target_id == TestRun.target_id)
            .where(
                TestRun.id == run_id,
                TestRun.created_by_user_id == owner_id,
                TestRun.synthetic_fixture_approval_enabled.is_(True),
                Workspace.status == "active",
                Workspace.deleted_at.is_(None),
                ApplicationTarget.status == "active",
                ApplicationTarget.deleted_at.is_(None),
                ApplicationTarget.environment == environment,
                ApplicationTarget.environment.in_(("local", "test")),
                ApplicationTarget.status == "active",
                ApplicationTarget.deleted_at.is_(None),
                TargetAuthorization.status == "authorized",
                TargetAuthorization.revoked_at.is_(None),
                (TargetAuthorization.expires_at.is_(None))
                | (TargetAuthorization.expires_at > datetime.now(UTC)),
            )
            .limit(1)
        )
        context = authorized.one_or_none()
        if context is None:
            raise FixtureApprovalRejected(
                "Fixture approval capability or target authorization expired."
            )
        row = ActionApprovalRequest(
            test_run_id=run_id,
            execution_id=execution_id,
            step_id=step_id,
            requested_by_user_id=owner_id,
            action_fingerprint=self.fingerprint(self.ACTION),
            resource_fingerprint=self.resource_fingerprint(
                run_id=run_id,
                target_id=context.target_id,
                environment=environment,
            ),
            environment=environment,
            policy_version=self.POLICY_VERSION,
            action_summary="Submit the synthetic local registration fixture.",
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.commit()
        return row.id

    async def wait(self, *, approval_id: UUID, timeout_seconds: float = 600) -> None:
        deadline = asyncio.get_running_loop().time() + min(timeout_seconds, 600)
        while True:
            row = await self.session.get(ActionApprovalRequest, approval_id)
            if row is None or row.expires_at <= datetime.now(UTC):
                raise FixtureApprovalRejected("Fixture action approval expired.")
            await self.session.refresh(row)
            if row.expires_at <= datetime.now(UTC):
                raise FixtureApprovalRejected("Fixture action approval expired.")
            if row.status == "approved":
                return
            if row.status != "pending":
                raise FixtureApprovalRejected("Fixture action approval was rejected or consumed.")
            if asyncio.get_running_loop().time() >= deadline:
                raise FixtureApprovalRejected("Fixture action approval timed out.")
            await asyncio.sleep(0.25)

    async def consume(self, *, approval_id: UUID, environment: str) -> None:
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(ActionApprovalRequest, TestRun.target_id)
            .join(TestRun, TestRun.id == ActionApprovalRequest.test_run_id)
            .join(Workspace, Workspace.id == TestRun.workspace_id)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == TestRun.workspace_id)
            .join(ApplicationTarget, ApplicationTarget.id == TestRun.target_id)
            .join(TargetAuthorization, TargetAuthorization.target_id == TestRun.target_id)
            .where(
                ActionApprovalRequest.id == approval_id,
                ActionApprovalRequest.status == "approved",
                ActionApprovalRequest.decision_by_user_id == WorkspaceMember.user_id,
                WorkspaceMember.role.in_(("owner", "admin")),
                Workspace.status == "active",
                Workspace.deleted_at.is_(None),
                ActionApprovalRequest.expires_at > now,
                ActionApprovalRequest.action_fingerprint == self.fingerprint(self.ACTION),
                ActionApprovalRequest.environment == environment,
                ActionApprovalRequest.policy_version == self.POLICY_VERSION,
                TestRun.synthetic_fixture_approval_enabled.is_(True),
                ApplicationTarget.environment == environment,
                ApplicationTarget.environment.in_(("local", "test")),
                TargetAuthorization.status == "authorized",
                TargetAuthorization.revoked_at.is_(None),
                (TargetAuthorization.expires_at.is_(None)) | (TargetAuthorization.expires_at > now),
            )
            .order_by(TargetAuthorization.created_at.desc())
            .limit(1)
            .with_for_update(of=(ActionApprovalRequest, TargetAuthorization))
        )
        match = result.one_or_none()
        if match is None:
            raise FixtureApprovalRejected("Approval is stale, unauthorized, or mismatched.")
        row, target_id = match
        if row.resource_fingerprint != self.resource_fingerprint(
            run_id=row.test_run_id,
            target_id=target_id,
            environment=environment,
        ):
            raise FixtureApprovalRejected("Approval resource fingerprint does not match.")
        receipt = ActionApprovalReceipt(
            approval_id=approval_id,
            action_fingerprint=self.fingerprint(self.ACTION),
            dispatch_state="claimed",
        )
        self.session.add(receipt)
        row.status = "consumed"
        await self.session.flush()
        await self.session.commit()

    async def mark_completed(self, *, approval_id: UUID) -> None:
        receipt = await self.session.get(ActionApprovalReceipt, approval_id)
        if receipt is None or receipt.dispatch_state != "claimed":
            raise FixtureApprovalRejected("One-time action receipt is unavailable.")
        receipt.dispatch_state = "completed"
        receipt.completed_at = datetime.now(UTC)
        await self.session.commit()

    async def mark_uncertain(self, *, approval_id: UUID) -> None:
        receipt = await self.session.get(ActionApprovalReceipt, approval_id)
        if receipt is None or receipt.dispatch_state != "claimed":
            raise FixtureApprovalRejected("One-time action receipt is unavailable.")
        receipt.dispatch_state = "uncertain"
        await self.session.commit()
