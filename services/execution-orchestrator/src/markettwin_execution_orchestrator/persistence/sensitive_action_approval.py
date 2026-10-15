"""Persistent approval gate for policy-eligible browser mutations."""

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from markettwin_database.models.core import Workspace, WorkspaceMember
from markettwin_database.models.execution import (
    ActionApprovalReceipt,
    ActionApprovalRequest,
    AgentExecution,
    BrowserSession,
    ExecutionSuspension,
)
from markettwin_database.models.testing import (
    ApplicationTarget,
    PersonaJourney,
    TargetAuthorization,
    TestRun,
)
from markettwin_shared.action_approval import SensitiveActionRule
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.browser.errors import BrowserPolicyError
from markettwin_execution_orchestrator.browser.sensitive_action_policy import (
    SensitiveActionIntent,
)

_ALLOWED_ENVIRONMENTS = {"local", "development", "test", "staging"}
_APPROVAL_TIMEOUT_SECONDS = 10 * 60
_POLICY_VERSION = 2


class SensitiveActionApprovalBlocked(BrowserPolicyError):
    """An eligible action did not receive its exact current approval."""


def _fingerprint(value: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SensitiveActionApprovalBlocked("The action target origin is invalid.")
    default_port = 443 if parsed.scheme == "https" else 80
    port = parsed.port
    return f"{parsed.scheme}://{parsed.hostname}" + (
        f":{port}" if port and port != default_port else ""
    )


class SensitiveActionApproval:
    """Create, wait for, consume, and finish one exact approval receipt."""

    def __init__(self, session: AsyncSession, *, execution_id: UUID) -> None:
        self._session = session
        self._execution_id = execution_id

    async def dispatch_authorized(
        self,
        *,
        step_id: int,
        intent: SensitiveActionIntent,
        current_origin: str,
        browser_session_id: UUID,
        revalidate_origin: Callable[[], Awaitable[str]],
        planned_step_index: int = 0,
        remaining_ms: int = 0,
    ) -> UUID:
        now = datetime.now(UTC)
        origin = _origin(current_origin)
        context = await self._session.execute(
            select(TestRun, ApplicationTarget, TargetAuthorization, PersonaJourney)
            .join(PersonaJourney, PersonaJourney.test_run_id == TestRun.id)
            .join(AgentExecution, AgentExecution.journey_id == PersonaJourney.id)
            .join(Workspace, Workspace.id == TestRun.workspace_id)
            .join(ApplicationTarget, ApplicationTarget.id == TestRun.target_id)
            .join(TargetAuthorization, TargetAuthorization.target_id == ApplicationTarget.id)
            .where(
                AgentExecution.id == self._execution_id,
                TestRun.human_action_approvals_enabled.is_(True),
                TestRun.status == "running",
                Workspace.status == "active",
                Workspace.deleted_at.is_(None),
                ApplicationTarget.status == "active",
                ApplicationTarget.deleted_at.is_(None),
                ApplicationTarget.environment.in_(_ALLOWED_ENVIRONMENTS),
                TargetAuthorization.status == "authorized",
                TargetAuthorization.revoked_at.is_(None),
                (TargetAuthorization.expires_at.is_(None))
                | (TargetAuthorization.expires_at > now),
            )
            .order_by(TargetAuthorization.created_at.desc())
            .limit(1)
        )
        row = context.one_or_none()
        if row is None:
            raise SensitiveActionApprovalBlocked(
                "This run is not authorized to request sensitive-action approval."
            )
        run, target, _authorization, journey = row
        raw_rules = run.configuration_snapshot.get("sensitive_action_rules", [])
        rules = [SensitiveActionRule.model_validate(rule) for rule in cast(list[object], raw_rules)]
        rule = next((rule for rule in rules if rule.matches(intent.action)), None)
        fixture_action = (
            run.synthetic_fixture_approval_enabled and target.environment in {"local", "test"}
            and urlsplit(origin).hostname in {"localhost", "127.0.0.1", "::1"}
            and intent.category == "save" and intent.action.get("name") == "Save"
            and intent.action.get("scope_role") == "form"
            and intent.action.get("scope_name") == "Registration"
        )
        if rule is None and not fixture_action:
            raise SensitiveActionApprovalBlocked(
                "This effect has no exact user-declared synthetic action and reset contract."
            )
        resource_reference = rule.resource_reference if rule is not None else "registration-fixture"
        if not self._origin_is_authorized(origin, run.target_snapshot):
            raise SensitiveActionApprovalBlocked(
                "The action is outside the run's authorized target origins."
            )
        if planned_step_index < 0 or remaining_ms < 0:
            raise SensitiveActionApprovalBlocked("The action checkpoint is invalid.")
        browser = await self._session.scalar(
            select(BrowserSession)
            .where(
                BrowserSession.id == browser_session_id,
                BrowserSession.execution_id == self._execution_id,
            )
            .with_for_update()
        )
        if browser is None or browser.state != "open" or browser.control_mode != "agent":
            raise SensitiveActionApprovalBlocked("The browser is not available for approval.")

        expires_at = now + timedelta(seconds=_APPROVAL_TIMEOUT_SECONDS)
        authorization_id = _authorization.id
        resource: dict[str, object] = {
            "test_run_id": str(run.id),
            "requester_id": str(run.created_by_user_id),
            "browser_session_id": str(browser_session_id),
            "target_id": str(target.id),
            "resource_reference": resource_reference,
            "authorization_id": str(authorization_id),
            "policy_version": _POLICY_VERSION,
            "expires_at": expires_at.isoformat(),
            "environment": target.environment,
            "origin": origin,
            "control_generation": browser.control_generation,
        }
        approval = ActionApprovalRequest(
            id=uuid4(),
            test_run_id=run.id,
            execution_id=self._execution_id,
            browser_session_id=browser_session_id,
            step_id=step_id,
            requested_by_user_id=run.created_by_user_id,
            action_fingerprint=_fingerprint(intent.action),
            resource_fingerprint=_fingerprint(resource),
            environment=target.environment,
            policy_version=_POLICY_VERSION,
            control_generation=browser.control_generation,
            action_summary=(
                f"{intent.display_summary} ({urlsplit(origin).hostname}; {resource_reference})"
            ),
            status="pending",
            expires_at=expires_at,
        )
        self._session.add(approval)
        version = int(
            await self._session.scalar(
                select(func.coalesce(func.max(ExecutionSuspension.checkpoint_version), 0))
                .where(ExecutionSuspension.test_run_id == run.id)
            )
            or 0
        ) + 1
        self._session.add(
            ExecutionSuspension(
                id=uuid4(),
                test_run_id=run.id,
                journey_id=journey.id,
                execution_id=self._execution_id,
                browser_session_id=browser_session_id,
                pending_approval_id=approval.id,
                last_durable_step_id=step_id,
                checkpoint_version=version,
                owner_generation=browser.control_generation,
                phase="case_action",
                planned_step_index=planned_step_index,
                active_deadline_remaining_ms=remaining_ms,
                suspended_at=now,
                human_deadline=expires_at,
                resume_count=0,
                status="waiting",
            )
        )
        run.status = "awaiting_human"
        approval_id = approval.id
        await self._session.commit()

        deadline = asyncio.get_running_loop().time() + _APPROVAL_TIMEOUT_SECONDS
        try:
            while True:
                await self._session.refresh(approval)
                await self._session.refresh(run)
                if approval.status == "approved":
                    break
                if (
                    approval.status != "pending"
                    or approval.expires_at <= datetime.now(UTC)
                    or run.status != "awaiting_human"
                ):
                    raise SensitiveActionApprovalBlocked(
                        "The sensitive action approval was rejected, expired, or cancelled."
                    )
                if asyncio.get_running_loop().time() >= deadline:
                    raise SensitiveActionApprovalBlocked(
                        "The sensitive action approval window expired."
                    )
                await asyncio.sleep(0.25)

            if _origin(await revalidate_origin()) != origin:
                raise SensitiveActionApprovalBlocked("The approved page origin changed.")
            return await self._consume(
                approval_id=approval_id,
                action_fingerprint=_fingerprint(intent.action),
                resource_fingerprint=_fingerprint(resource),
                environment=target.environment,
                authorization_id=authorization_id,
            )
        except BaseException:
            await self._session.rollback()
            await asyncio.shield(self._abandon(approval_id=approval_id))
            raise

    async def _abandon(self, *, approval_id: UUID) -> None:
        approval = await self._session.get(ActionApprovalRequest, approval_id)
        if approval is not None and approval.status in {"pending", "approved"}:
            approval.status = "cancelled"
        suspension = await self._session.scalar(
            select(ExecutionSuspension)
            .where(ExecutionSuspension.pending_approval_id == approval_id)
            .with_for_update()
        )
        if suspension is not None and suspension.status == "waiting":
            suspension.status = "abandoned"
        run = await self._session.get(TestRun, approval.test_run_id) if approval else None
        if run is not None and run.status == "awaiting_human":
            run.status = "running"
        await self._session.commit()

    @staticmethod
    def _origin_is_authorized(origin: str, snapshot: dict[str, object]) -> bool:
        raw_origins = snapshot.get("allowed_origins")
        if not isinstance(raw_origins, list):
            return False
        for raw_item in cast(list[object], raw_origins):
            if not isinstance(raw_item, dict):
                continue
            item = cast(dict[str, object], raw_item)
            try:
                scheme = item["scheme"]
                hostname = item["hostname"]
                port = item.get("port")
                candidate = f"{scheme}://{hostname}" + (f":{port}" if port else "")
                if _origin(candidate) == origin:
                    return True
                if item.get("include_subdomains") is True and isinstance(hostname, str):
                    parsed = urlsplit(origin)
                    if parsed.scheme == scheme and parsed.hostname and parsed.hostname.endswith(
                        "." + hostname
                    ):
                        candidate_port = parsed.port
                        if port is not None and not isinstance(port, int):
                            continue
                        declared_port = port if port is not None else (
                            443 if scheme == "https" else 80
                        )
                        actual_port = candidate_port or (
                            443 if parsed.scheme == "https" else 80
                        )
                        if actual_port == declared_port:
                            return True
            except (KeyError, TypeError, ValueError):
                continue
        return False

    async def _consume(
        self,
        *,
        approval_id: UUID,
        action_fingerprint: str,
        resource_fingerprint: str,
        environment: str,
        authorization_id: UUID,
    ) -> UUID:
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(ActionApprovalRequest)
            .join(TestRun, TestRun.id == ActionApprovalRequest.test_run_id)
            .join(Workspace, Workspace.id == TestRun.workspace_id)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .join(BrowserSession, BrowserSession.id == ActionApprovalRequest.browser_session_id)
            .join(ApplicationTarget, ApplicationTarget.id == TestRun.target_id)
            .join(TargetAuthorization, TargetAuthorization.target_id == ApplicationTarget.id)
            .where(
                ActionApprovalRequest.id == approval_id,
                ActionApprovalRequest.execution_id == self._execution_id,
                ActionApprovalRequest.status == "approved",
                ActionApprovalRequest.expires_at > now,
                ActionApprovalRequest.action_fingerprint == action_fingerprint,
                ActionApprovalRequest.resource_fingerprint == resource_fingerprint,
                ActionApprovalRequest.environment == environment,
                ActionApprovalRequest.policy_version == _POLICY_VERSION,
                BrowserSession.control_generation == ActionApprovalRequest.control_generation,
                BrowserSession.execution_id == self._execution_id,
                BrowserSession.state == "open",
                BrowserSession.control_mode == "agent",
                ActionApprovalRequest.decision_by_user_id == WorkspaceMember.user_id,
                WorkspaceMember.role.in_(("owner", "admin")),
                Workspace.status == "active",
                Workspace.deleted_at.is_(None),
                ApplicationTarget.status == "active",
                ApplicationTarget.deleted_at.is_(None),
                ApplicationTarget.environment == environment,
                TestRun.human_action_approvals_enabled.is_(True),
                TargetAuthorization.status == "authorized",
                TargetAuthorization.id == authorization_id,
                TargetAuthorization.revoked_at.is_(None),
                (TargetAuthorization.expires_at.is_(None))
                | (TargetAuthorization.expires_at > now),
            )
            .order_by(TargetAuthorization.created_at.desc())
            .limit(1)
            .with_for_update(of=(ActionApprovalRequest, TargetAuthorization, BrowserSession))
        )
        approval = result.scalar_one_or_none()
        if approval is None:
            raise SensitiveActionApprovalBlocked(
                "The sensitive action approval no longer matches current authorization."
            )
        suspension = await self._session.scalar(
            select(ExecutionSuspension)
            .where(ExecutionSuspension.pending_approval_id == approval_id)
            .with_for_update()
        )
        run = await self._session.scalar(
            select(TestRun).where(TestRun.id == approval.test_run_id).with_for_update()
        )
        if (
            suspension is None
            or suspension.status != "waiting"
            or run is None
            or run.status != "awaiting_human"
        ):
            raise SensitiveActionApprovalBlocked("The durable action checkpoint is unavailable.")
        self._session.add(
            ActionApprovalReceipt(
                approval_id=approval.id,
                action_fingerprint=action_fingerprint,
                dispatch_state="claimed",
            )
        )
        approval.status = "consumed"
        suspension.status = "consumed"
        suspension.resume_count += 1
        run.status = "running"
        await self._session.commit()
        return approval.id

    async def finish(self, *, approval_id: UUID, outcome: str) -> None:
        if outcome not in {"completed", "uncertain"}:
            raise ValueError("Unsupported sensitive action dispatch outcome.")
        receipt = await self._session.get(ActionApprovalReceipt, approval_id)
        if receipt is None or receipt.dispatch_state != "claimed":
            raise SensitiveActionApprovalBlocked("The consumed approval receipt is unavailable.")
        receipt.dispatch_state = outcome
        if outcome == "completed":
            receipt.completed_at = datetime.now(UTC)
        await self._session.commit()
