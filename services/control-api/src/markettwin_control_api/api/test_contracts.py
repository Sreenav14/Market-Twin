"""Owner review, edit, approval, and freeze of test contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from markettwin_database.repositories import OutboxRepository
from markettwin_execution_orchestrator.workflow.contract_generation import (
    generate_test_contract,
)
from markettwin_execution_orchestrator.workflow.testing_depth import feature_case_limit
from markettwin_shared.discovery_contract import (
    ContractAssertion,
    DiscoveryMap,
    FrozenJourneyContract,
    TestContract,
)
from pydantic import BaseModel, Field

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import get_authenticated_user_id
from markettwin_control_api.api.permissions import WORKSPACE_WRITE_ROLES
from markettwin_control_api.config import get_settings
from markettwin_control_api.persistence.repositories import (
    TestRunRecord,
    TestRunRepository,
    WorkspaceRepository,
)
from markettwin_control_api.services import RunDispatchService, RunNotQueueableError
from markettwin_control_api.services.run_readiness import require_run_ready

router = APIRouter(tags=["Test Contracts"])


class UpdateJourneyRequest(BaseModel):
    excluded: bool | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    assertions: list[ContractAssertion] | None = None


async def _get_authorized_run_and_workspace(
    *,
    workspace_id: UUID,
    run_id: UUID,
    user_id: UUID,
    session: Any,
    require_write: bool = False,
) -> tuple[TestRunRecord, Any]:
    test_run_repo = TestRunRepository(session)
    run = await test_run_repo.get_for_user(test_run_id=run_id, user_id=user_id)
    if run is None or run.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found.",
        )

    workspace_repo = WorkspaceRepository(session)
    workspace = await workspace_repo.get_for_user(workspace_id=workspace_id, user_id=user_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        )

    if require_write and workspace.role not in WORKSPACE_WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your workspace role cannot modify test contracts.",
        )

    return run, workspace


def _get_or_create_contract(run: TestRunRecord) -> TestContract:
    snapshot = dict(run.configuration_snapshot)
    if "test_contract" in snapshot and snapshot["test_contract"] is not None:
        return TestContract.model_validate(snapshot["test_contract"])

    if "discovery_map" not in snapshot or snapshot["discovery_map"] is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discovery has not completed for this run.",
        )

    discovery_map = DiscoveryMap.model_validate(snapshot["discovery_map"])
    contract = generate_test_contract(
        discovery_map=discovery_map,
        test_run_id=run.test_run_id,
        max_journeys=feature_case_limit(_testing_depth(run)),
    )
    return contract


def _testing_depth(run: TestRunRecord) -> Literal["low", "medium", "high"]:
    value = run.configuration_snapshot.get("testing_depth", "medium")
    if value == "low":
        return "low"
    if value == "medium":
        return "medium"
    if value == "high":
        return "high"
    return "medium"


def _require_contract_within_depth(run: TestRunRecord, contract: TestContract) -> None:
    included = sum(
        not journey.excluded and any(not assertion.excluded for assertion in journey.assertions)
        for journey in contract.journeys
    )
    limit = feature_case_limit(_testing_depth(run))
    if included > limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"This contract includes {included} journeys, but the selected testing depth "
                f"allows at most {limit}. Exclude at least {included - limit} more "
                "journey(s) before approval."
            ),
        )


@router.get(
    "/api/v1/workspaces/{workspace_id}/test-runs/{run_id}/contract",
    response_model=TestContract,
)
async def get_test_contract(
    workspace_id: UUID,
    run_id: UUID,
    request: Request,
) -> TestContract:
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)

    async with database.session_factory() as session:
        async with session.begin():
            run, _ = await _get_authorized_run_and_workspace(
                workspace_id=workspace_id,
                run_id=run_id,
                user_id=user_id,
                session=session,
            )
            contract = _get_or_create_contract(run)
            snapshot = dict(run.configuration_snapshot)
            if "test_contract" not in snapshot or snapshot["test_contract"] is None:
                snapshot["test_contract"] = contract.model_dump(mode="json")
                test_run_repo = TestRunRepository(session)
                await test_run_repo.update_configuration_snapshot(
                    test_run_id=run.test_run_id,
                    configuration_snapshot=snapshot,
                )
            return contract


@router.put(
    "/api/v1/workspaces/{workspace_id}/test-runs/{run_id}/contract/journeys/{journey_key}",
    response_model=TestContract,
)
async def update_journey_contract(
    workspace_id: UUID,
    run_id: UUID,
    journey_key: str,
    payload: UpdateJourneyRequest,
    request: Request,
) -> TestContract:
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)

    async with database.session_factory() as session:
        async with session.begin():
            run, _ = await _get_authorized_run_and_workspace(
                workspace_id=workspace_id,
                run_id=run_id,
                user_id=user_id,
                session=session,
                require_write=True,
            )
            contract = _get_or_create_contract(run)

            if contract.status != "draft":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Cannot edit contract in status '{contract.status}'. "
                        "Only draft contracts can be edited."
                    ),
                )

            found = False
            new_journeys: list[FrozenJourneyContract] = []
            for j in contract.journeys:
                if j.journey_key == journey_key:
                    found = True
                    updates: dict[str, Any] = {}
                    if payload.excluded is not None:
                        if payload.excluded is False:
                            discovery = DiscoveryMap.model_validate(
                                run.configuration_snapshot.get("discovery_map")
                            )
                            original = next((item for item in discovery.journeys
                                             if item.journey_key == journey_key), None)
                            if original is None or not original.completed:
                                raise HTTPException(422, (
                                    "This journey was not completed during exploration "
                                    "and cannot be approved for testing."
                                ))
                        updates["excluded"] = payload.excluded
                    if payload.title is not None:
                        updates["title"] = payload.title
                    if payload.assertions is not None:
                        # Origin remains None while in draft
                        updates["assertions"] = tuple(
                            a.model_copy(update={"origin": None}) for a in payload.assertions
                        )
                    new_journeys.append(j.model_copy(update=updates))
                else:
                    new_journeys.append(j)

            if not found:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Journey '{journey_key}' not found in contract.",
                )

            updated_contract = contract.model_copy(
                update={
                    "version": contract.version + 1,
                    "journeys": tuple(new_journeys),
                }
            )

            snapshot = dict(run.configuration_snapshot)
            snapshot["test_contract"] = updated_contract.model_dump(mode="json")
            test_run_repo = TestRunRepository(session)
            await test_run_repo.update_configuration_snapshot(
                test_run_id=run.test_run_id,
                configuration_snapshot=snapshot,
            )
            return updated_contract


@router.post(
    "/api/v1/workspaces/{workspace_id}/test-runs/{run_id}/contract/approve",
    response_model=TestContract,
)
async def approve_test_contract(
    workspace_id: UUID,
    run_id: UUID,
    request: Request,
) -> TestContract:
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)

    async with database.session_factory() as session:
        async with session.begin():
            run, _ = await _get_authorized_run_and_workspace(
                workspace_id=workspace_id,
                run_id=run_id,
                user_id=user_id,
                session=session,
                require_write=True,
            )
            contract = _get_or_create_contract(run)

            if contract.status not in {"draft", "approved"}:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Cannot approve contract in status '{contract.status}'.",
                )

            _require_contract_within_depth(run, contract)

            # Move status to approved and set origin="user_approved" on non-excluded assertions
            approved_journeys = tuple(
                j.model_copy(
                    update={
                        "assertions": tuple(
                            a.model_copy(update={"origin": "user_approved"})
                            if not a.excluded and not j.excluded
                            else a
                            for a in j.assertions
                        )
                    }
                )
                for j in contract.journeys
            )

            # Approval is idempotent: re-approving an already approved
            # contract must not rewrite who approved it or when, so the
            # original approver stamp of record is preserved.
            approved_contract = contract.model_copy(
                update={
                    "status": "approved",
                    "approved_by_user_id": contract.approved_by_user_id or user_id,
                    "approved_at": contract.approved_at or datetime.now(UTC),
                    "journeys": approved_journeys,
                }
            )

            snapshot = dict(run.configuration_snapshot)
            snapshot["test_contract"] = approved_contract.model_dump(mode="json")
            test_run_repo = TestRunRepository(session)
            await test_run_repo.update_configuration_snapshot(
                test_run_id=run.test_run_id,
                configuration_snapshot=snapshot,
            )
            return approved_contract


@router.post(
    "/api/v1/workspaces/{workspace_id}/test-runs/{run_id}/contract/start",
    response_model=TestContract,
)
async def start_test_contract_execution(
    workspace_id: UUID,
    run_id: UUID,
    request: Request,
) -> TestContract:
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)

    async with database.session_factory() as session:
        async with session.begin():
            run, _ = await _get_authorized_run_and_workspace(
                workspace_id=workspace_id,
                run_id=run_id,
                user_id=user_id,
                session=session,
                require_write=True,
            )
            contract = _get_or_create_contract(run)

            if contract.status != "approved":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Contract must be approved before starting execution "
                        f"(current: {contract.status})."
                    ),
                )

            try:
                _require_contract_within_depth(run, contract)
            except HTTPException as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"{exc.detail} The approved contract cannot be changed; "
                        "create a new draft to adjust its journeys."
                    ),
                ) from exc

            # Freeze contract
            await require_run_ready(session, get_settings())
            frozen_contract = contract.model_copy(update={"status": "frozen"})
            content_hash = frozen_contract.content_hash()

            snapshot = dict(run.configuration_snapshot)
            snapshot["test_contract"] = frozen_contract.model_dump(mode="json")
            snapshot["frozen_contract"] = frozen_contract.model_dump(mode="json")
            snapshot["frozen_contract_hash"] = content_hash
            snapshot["discovery_stage"] = "executing"

            test_run_repo = TestRunRepository(session)
            await test_run_repo.update_configuration_snapshot(
                test_run_id=run.test_run_id,
                configuration_snapshot=snapshot,
            )

            outbox_repo = OutboxRepository(session)
            dispatch = RunDispatchService(
                test_run_repository=test_run_repo,
                outbox_repository=outbox_repo,
            )
            try:
                await dispatch.queue_contract_run(test_run_id=run.test_run_id)
            except RunNotQueueableError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(exc),
                ) from exc

            return frozen_contract
