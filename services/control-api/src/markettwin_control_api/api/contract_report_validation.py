"""Recheck confirmation proofs before exposing a contract report as verified."""

from collections.abc import Mapping
from math import isclose
from typing import Literal, cast
from uuid import UUID

from fastapi import HTTPException
from markettwin_database.models import (
    AgentExecution,
    Artifact,
    ExecutionStep,
    PersonaJourney,
    RunEvent,
)
from markettwin_shared.case_evidence import ArtifactEvidence, StepEvidence, valid_case_evidence
from markettwin_shared.contract_execution import contract_case
from markettwin_shared.deep_testing import CaseExecutionResult
from markettwin_shared.discovery_contract import DiscoveryMap, TestContract
from markettwin_shared.feature_plan import TestCaseSpec
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class ConfirmationProof(BaseModel):
    finding_id: UUID
    journey_key: str
    assertion_id: str
    execution_id: UUID
    replay_execution_id: UUID
    reason: Literal["reproduced"]
    verification: Literal["verified_deterministic"]


async def validate_contract_report(
    *, run_id: UUID, snapshot: dict[str, object], payload: dict[str, object],
    finding_ids: set[UUID], session: AsyncSession,
) -> None:
    try:
        contract = TestContract.model_validate(snapshot.get("frozen_contract"))
        discovery = DiscoveryMap.model_validate(snapshot.get("discovery_map"))
        identity = {"contract_id": str(contract.contract_id), "contract_version": contract.version,
                    "contract_hash": contract.content_hash()}
        if (contract.test_run_id != run_id or contract.status != "frozen"
                or contract.approved_by_user_id is None or contract.approved_at is None
                or snapshot.get("frozen_contract_hash") != contract.content_hash()
                or any(payload.get(k) != v for k, v in identity.items())):
            raise ValueError("Invalid frozen report identity.")
        proofs = [ConfirmationProof.model_validate(p) for p in cast(
            list[object], payload.get("confirmed", []),
        )]
        if {p.finding_id for p in proofs} != finding_ids or len(proofs) != len(finding_ids):
            raise ValueError("Confirmed counts include an unproved finding.")
        events = tuple((await session.scalars(select(RunEvent).where(
            RunEvent.test_run_id == run_id,
            RunEvent.event_type.in_(("contract.execution_plan", "contract.case.completed",
                                    "test_case.replay")),
        ))).all())
        plans = [e for e in events if e.event_type == "contract.execution_plan"]
        if len(plans) != 1 or any(plans[0].payload.get(k) != v for k, v in identity.items()):
            raise ValueError("Frozen executed plan is missing.")
        journeys = {j.journey_key: j for j in contract.journeys if not j.excluded}
        planned_keys: set[str] = set()
        for case_payload in cast(list[object], plans[0].payload.get("cases", [])):
            planned_case = TestCaseSpec.model_validate(case_payload)
            if (planned_case.case_id in planned_keys
                    or planned_case != contract_case(
                        journeys[planned_case.case_id], discovery.target_origin,
                    )):
                raise ValueError("Executed plan differs from approved tests.")
            planned_keys.add(planned_case.case_id)
        for key in cast(list[str], payload.get("what_works", [])):
            if key not in planned_keys:
                raise ValueError("Working journey was not in the executed plan.")
            journey = journeys[key]
            case = contract_case(journey, discovery.target_origin)
            originals = [e for e in events if e.event_type == "contract.case.completed"
                         and e.payload.get("attempt") == 1
                         and cast(dict[str, object], e.payload.get("result", {})).get("case_id")
                         == key]
            if (len(originals) != 3
                    or {e.payload.get("persona_index") for e in originals} != {0, 1, 2}):
                raise ValueError("Working journey was not executed for all three personas.")
            for event in originals:
                result = CaseExecutionResult.model_validate(event.payload.get("result"))
                if (result.execution_status != "completed" or result.verdict != "satisfied"
                        or result.execution_id != event.execution_id
                        or any(event.payload.get(k) != v for k, v in identity.items())):
                    raise ValueError("Working journey contains incomplete or failed checks.")
                owned = await session.scalar(select(AgentExecution.id).join(
                    PersonaJourney, PersonaJourney.id == AgentExecution.journey_id,
                ).where(PersonaJourney.test_run_id == run_id,
                        AgentExecution.id == result.execution_id,
                        AgentExecution.journey_id == event.journey_id,
                        AgentExecution.attempt_number == 1, AgentExecution.status == "completed"))
                if owned is None:
                    raise ValueError("Working journey execution is not owned by this run.")
                steps = {s.id: s for s in (await session.scalars(select(ExecutionStep).where(
                    ExecutionStep.execution_id == result.execution_id,
                ))).all()}
                artifacts = {a.id: a for a in (await session.scalars(select(Artifact).where(
                    Artifact.execution_id == result.execution_id,
                ))).all()}
                if not valid_case_evidence(
                    case, result, cast(Mapping[int, StepEvidence], steps),
                    cast(Mapping[UUID, ArtifactEvidence], artifacts),
                ):
                    raise ValueError("Working journey lacks exact saved passing evidence.")
        for proof in proofs:
            journey = journeys[proof.journey_key]
            case = contract_case(journey, discovery.target_origin)
            if case.model_dump(mode="json") not in cast(
                list[object], plans[0].payload.get("cases", []),
            ):
                raise ValueError("Confirmation case is outside the executed plan.")
            if proof.execution_id == proof.replay_execution_id:
                raise ValueError("Confirmation reused the original browser execution.")
            source_events: list[RunEvent] = []
            for execution_id, attempt in ((proof.execution_id, 1), (proof.replay_execution_id, 2)):
                rows = [e for e in events if e.event_type == "contract.case.completed"
                        and e.execution_id == execution_id and e.payload.get("attempt") == attempt]
                if len(rows) != 1 or any(rows[0].payload.get(k) != v for k, v in identity.items()):
                    raise ValueError("Confirmation execution provenance is missing.")
                event = rows[0]
                result = CaseExecutionResult.model_validate(event.payload.get("result"))
                owned = await session.scalar(select(AgentExecution.id).join(
                    PersonaJourney, PersonaJourney.id == AgentExecution.journey_id,
                ).where(
                    PersonaJourney.test_run_id == run_id,
                    AgentExecution.id == execution_id,
                    AgentExecution.journey_id == event.journey_id,
                    AgentExecution.attempt_number == attempt, AgentExecution.status == "completed",
                ))
                if owned is None or result.execution_id != execution_id:
                    raise ValueError("Execution belongs to another run or attempt.")
                steps = {s.id: s for s in (await session.scalars(select(ExecutionStep).where(
                    ExecutionStep.execution_id == execution_id,
                ))).all()}
                artifacts = {a.id: a for a in (await session.scalars(select(Artifact).where(
                    Artifact.execution_id == execution_id,
                ))).all()}
                if not valid_case_evidence(
                    case, result, cast(Mapping[int, StepEvidence], steps),
                    cast(Mapping[UUID, ArtifactEvidence], artifacts),
                ):
                    raise ValueError("Confirmation evidence is invalid.")
                assertion = next(a for a in result.assertion_results
                                 if a.assertion_id == proof.assertion_id)
                if assertion.status != "not_satisfied" or assertion.origin != "user_approved":
                    raise ValueError("Approved check did not fail in both executions.")
                source_events.append(event)
            if source_events[0].journey_id != source_events[1].journey_id or not any(
                e.event_type == "test_case.replay" and e.execution_id == proof.replay_execution_id
                and e.journey_id == source_events[0].journey_id
                and e.payload.get("replay_of_execution_id") == str(proof.execution_id)
                and all(e.payload.get(k) == v for k, v in identity.items()) for e in events
            ):
                raise ValueError("Confirmation execution is not the linked replay.")
        approved_keys = {j.journey_key for j in contract.journeys if not j.excluded
                         and any(not a.excluded for a in j.assertions)}
        executed_keys: set[str] = set()
        for event in events:
            if (event.event_type != "contract.case.completed" or event.payload.get("attempt") != 1
                    or any(event.payload.get(k) != v for k, v in identity.items())):
                continue
            result = CaseExecutionResult.model_validate(event.payload.get("result"))
            if result.case_id in approved_keys and result.execution_id == event.execution_id:
                executed_keys.add(result.case_id)
        approved = len(approved_keys)
        actual_coverage = len(executed_keys) / approved if approved else 0.0
        coverage = cast(dict[str, object], payload.get("coverage", {}))
        if (coverage.get("executed") != len(executed_keys) or coverage.get("approved") != approved
                or coverage.get("verified_findings") != len(finding_ids)):
            raise ValueError("Report counts differ from saved execution and confirmation records.")
        verdict = cast(dict[str, object], payload.get("market_verdict", {}))
        if (not isclose(float(cast(float, verdict.get("coverage", -1))), actual_coverage)
                or verdict.get("confirmed_defects") != len(finding_ids)):
            raise ValueError("Market verdict inputs differ from actual report coverage.")
        if verdict.get("verdict") == "ready" and (
            not approved or actual_coverage < 0.6
        ):
            raise ValueError("Ready verdict lacks sufficient coverage.")
    except (ValueError, KeyError, TypeError, ValidationError, StopIteration) as error:
        raise HTTPException(
            409, "Report verification data is inconsistent with the approved tests.",
        ) from error
