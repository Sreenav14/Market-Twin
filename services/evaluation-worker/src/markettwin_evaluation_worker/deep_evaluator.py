"""Verify deep-case events against their frozen oracles and recorded execution."""

from collections import Counter
from collections.abc import Mapping
from typing import cast
from uuid import UUID

from markettwin_database.models import (
    AgentExecution,
    Artifact,
    ExecutionStep,
    PersonaJourney,
    RunEvent,
)
from markettwin_shared.case_evidence import ArtifactEvidence, StepEvidence
from markettwin_shared.case_evidence import valid_case_evidence as validate_evidence
from markettwin_shared.deep_testing import CaseExecutionResult
from markettwin_shared.discovery_contract import ContractAssertion, TestContract
from markettwin_shared.feature_plan import (
    DeepFeaturePlan,
    ExpectedAssertion,
    FeatureScope,
    TestCaseSpec,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
    EvidenceReference,
)
from markettwin_evaluation_worker.persistence.report_repository import ReportRepository


def valid_case_evidence(
    case: TestCaseSpec, result: CaseExecutionResult, steps: dict[int, ExecutionStep],
    artifacts: dict[UUID, Artifact], frozen_contract: TestContract | None = None,
    expected_contract_hash: str | None = None,
) -> bool:
    # SQLAlchemy instance attributes have these values; its class descriptors
    # expose Mapped types to structural protocol checks.
    return validate_evidence(
        case, result, cast(Mapping[int, StepEvidence], steps),
        cast(Mapping[UUID, ArtifactEvidence], artifacts), frozen_contract, expected_contract_hash,
    )


def _contract_matches_assertion(ca: ContractAssertion, assertion: ExpectedAssertion) -> bool:
    if ca.oracle != assertion.oracle:
        return False
    role = assertion.target.role if assertion.target else None
    name = assertion.target.name if assertion.target else None
    if (ca.target_role, ca.target_name) != (role, name):
        return False
    if (type(ca.expected_value) is not type(assertion.expected_value)
            or ca.expected_value != assertion.expected_value):
        return False
    return True

def grounded_failure(
    case: TestCaseSpec,
    plan: DeepFeaturePlan,
    trusted_scope: FeatureScope | None,
    frozen_contract: TestContract | None = None,
) -> bool:
    grounded = [item for item in case.expected if item.origin != "inferred"]
    if not grounded or case.preconditions:
        return False

    user_approved = [item for item in grounded if item.origin == "user_approved"]
    if user_approved:
        if frozen_contract is None or frozen_contract.status != "frozen":
            return False
        contract_assertions: list[ContractAssertion] = [
            a for journey in frozen_contract.journeys if not journey.excluded
            for a in journey.assertions if a.origin == "user_approved" and not a.excluded
        ]
        for assertion in user_approved:
            if not any(_contract_matches_assertion(ca, assertion) for ca in contract_assertions):
                return False
        if len(user_approved) == len(grounded):
            return True

    if trusted_scope is None or plan.scope != trusted_scope:
        return False
    requirements = {item.requirement_id: item for item in trusted_scope.requirements}
    for assertion in grounded:
        if assertion.origin == "user_approved":
            continue
        refs = [requirements.get(reference) for reference in assertion.requirement_refs]
        source = "fixture" if assertion.origin == "fixture_truth" else "approved_knowledge"
        if not refs or any(item is None or item.source != source for item in refs):
            return False
        definitions = [
            definition for item in refs if item is not None for definition in item.assertions
        ]
        if not any(
            (definition.oracle, definition.target, definition.expected_value)
            == (
                assertion.oracle,
                assertion.target,
                assertion.expected_value,
            )
            for definition in definitions
        ):
            return False
    return True


async def evaluate_deep_run(
    *,
    test_run_id: UUID,
    session: AsyncSession,
    trusted_scope: FeatureScope | None,
    frozen_contract: TestContract | None = None,
) -> tuple[tuple[UUID, ...], UUID]:
    events = tuple(
        (
            await session.scalars(
                select(RunEvent)
                .where(
                    RunEvent.test_run_id == test_run_id,
                    RunEvent.event_type.in_(
                        ("test_plan.created", "test_case.completed", "test_case.skipped")
                    ),
                )
                .order_by(RunEvent.id)
            )
        ).all()
    )
    plans = [event for event in events if event.event_type == "test_plan.created"]
    if len(plans) != 1:
        raise ValueError("Deep runs require exactly one frozen feature plan.")
    plan = DeepFeaturePlan.model_validate(plans[0].payload)
    contract_valid = frozen_contract is None or (
        frozen_contract.test_run_id == test_run_id
        and frozen_contract.status == "frozen"
        and frozen_contract.approved_by_user_id is not None
        and frozen_contract.approved_at is not None
        and plan.contract_id == frozen_contract.contract_id
        and plan.contract_version == frozen_contract.version
        and plan.contract_hash == frozen_contract.content_hash()
    )
    results = {
        event.payload.get("case_id"): event
        for event in events
        if event.event_type == "test_case.completed"
    }
    journeys = {
        item.id: item
        for item in (
            await session.scalars(
                select(PersonaJourney).where(
                    PersonaJourney.test_run_id == test_run_id,
                )
            )
        ).all()
    }
    executions = {
        item.id: item
        for item in (
            await session.scalars(
                select(AgentExecution).where(
                    AgentExecution.journey_id.in_(tuple(journeys)),
                )
            )
        ).all()
    }
    steps = {
        item.id: item
        for item in (
            await session.scalars(
                select(ExecutionStep).where(
                    ExecutionStep.execution_id.in_(tuple(executions)),
                )
            )
        ).all()
    }
    artifacts = {
        item.id: item
        for item in (
            await session.scalars(
                select(Artifact).where(
                    Artifact.execution_id.in_(tuple(executions)),
                )
            )
        ).all()
    }
    counts: Counter[str] = Counter()
    entries: list[dict[str, object]] = []
    finding_ids: list[UUID] = []
    groups: dict[str, list[tuple[UUID, str, str, tuple[EvidenceReference, ...]]]] = {}
    repository = EvaluationRepository(session)
    for case_ordinal, case in enumerate(plan.cases, start=1):
        event = results.get(case.case_id)
        entry: dict[str, object] = {
            "case_id": case.case_id,
            "title": case.title,
            "kind": case.kind,
            "verdict": "not_run",
            "assertions": [],
        }
        result = None
        if event is not None:
            try:
                result = CaseExecutionResult.model_validate(event.payload)
            except ValidationError:
                entry["verdict"] = "unverified"
        if result is not None and event is not None:
            execution = executions.get(result.execution_id)
            owned = (
                event.execution_id == result.execution_id
                and event.journey_id is not None
                and event.journey_id in journeys
                and execution is not None
                and execution.journey_id == event.journey_id
                and journeys[event.journey_id].ordinal == case_ordinal
            )
            valid = bool(owned and contract_valid and valid_case_evidence(
                case, result, steps, artifacts, frozen_contract, plan.contract_hash,
            ))
            verdict = result.verdict if valid else "unverified"
            if owned and result.execution_status == "skipped":
                verdict = "not_run"
                entry["reason"] = "human_assistance_skipped"
                counts["human_assistance_skipped"] += 1
            if owned and result.execution_status == "policy_blocked":
                verdict = "blocked"
                if result.blocker == "authentication_challenge_blocked":
                    entry["reason"] = result.blocker
            entry.update(
                verdict=verdict,
                execution_id=str(result.execution_id) if owned else None,
                journey_id=str(event.journey_id) if owned else None,
                execution_status=result.execution_status if owned else "unverified",
                assertions=[item.model_dump(mode="json") for item in result.assertion_results]
                if valid
                else [],
            )
            if valid and grounded_failure(case, plan, trusted_scope, frozen_contract):
                for assertion in result.assertion_results:
                    if assertion.status != "not_satisfied" or assertion.origin == "inferred":
                        continue
                    assert event.journey_id is not None
                    requirements = [
                        item
                        for item in plan.scope.requirements
                        if item.requirement_id in assertion.requirement_refs
                    ]
                    declared = {item.defect_key for item in requirements if item.defect_key}
                    key = f"{case.case_id}:{assertion.assertion_id}"
                    title = f"{case.title}: {assertion.assertion_id}"[:200]
                    if len(declared) == 1 and all(item.defect_key for item in requirements):
                        defect = next(iter(declared))
                        key = (
                            ",".join(sorted({item.source_id for item in requirements}))
                            + ":"
                            + str(defect)
                        )
                        title = str(defect).replace("_", " ").capitalize()
                    groups.setdefault(key, []).append(
                        (
                            event.journey_id,
                            title,
                            f"{case.case_id}: expected {assertion.expected_value!r}; observed "
                            f"{assertion.observed_value!r}.",
                            tuple(
                                EvidenceReference(
                                    step_id=assertion.step_id,
                                    artifact_id=artifact_id,
                                    execution_id=result.execution_id,
                                )
                                for artifact_id in assertion.artifact_ids
                            ),
                        )
                    )
        counts[str(entry["verdict"])] += 1
        entries.append(entry)
    for skipped in plan.skipped:
        counts["not_run"] += 1
        entries.append(
            {
                "case_id": skipped.case.case_id,
                "title": skipped.case.title,
                "kind": skipped.case.kind,
                "verdict": "not_run",
                "reason": skipped.reason,
            }
        )
    for observations in groups.values():
        finding_ids.append(
            await repository.create_linked_finding(
                test_run_id=test_run_id,
                journey_ids=tuple(dict.fromkeys(item[0] for item in observations)),
                severity="medium",
                category="deterministic_assertion",
                title=observations[0][1],
                summary="\n".join(item[2] for item in observations)[:2000],
                recommendation="Reproduce the linked cases and check their source requirements.",
                evidence=tuple(reference for item in observations for reference in item[3]),
            )
        )
    coverage = {
        "planned": len(entries),
        "executed": sum(
            entry.get("execution_id") is not None and entry.get("execution_status") != "skipped"
            for entry in entries
        ),
        "passed": counts["satisfied"],
        "failed_assertions": sum(
            assertion.get("status") == "not_satisfied"
            for entry in entries
            for assertion in cast(list[dict[str, object]], entry.get("assertions", []))
        ),
        "blocked": counts["blocked"],
        "inconclusive": counts["unverified"],
        "not_run": counts["not_run"],
        "human_assistance_skipped": counts["human_assistance_skipped"],
        "verified_findings": len(finding_ids),
    }
    summary = (
        f"Feature testing: {coverage['planned']} cases planned, {coverage['passed']} passed, "
        f"{coverage['failed_assertions']} failed assertions, {coverage['blocked']} blocked, "
        f"{coverage['inconclusive']} inconclusive, {coverage['not_run']} not run. "
        f"{len(finding_ids)} assertion-grounded findings. Coverage is limited to this feature."
    )
    report_id = await ReportRepository(session).create_completed_report(
        test_run_id=test_run_id,
        executive_summary=summary,
        report_payload={
            "schema_version": 1,
            "mode": "deep_feature_v1",
            "coverage": coverage,
            "cases": entries,
            "unknown_requirements": list(plan.scope.unknown_requirements),
            "coverage_gaps": list(plan.coverage_gaps),
        },
    )
    return tuple(finding_ids), report_id
