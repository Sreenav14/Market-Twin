"""Verify frozen-contract failures only against owned evidence and a linked replay."""

import asyncio
import base64
import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from uuid import UUID

from markettwin_database.models import (
    AgentExecution,
    Artifact,
    ExecutionStep,
    PersonaJourney,
    RunEvent,
    RunPersona,
)
from markettwin_shared.contract_execution import contract_case
from markettwin_shared.deep_testing import CaseExecutionResult
from markettwin_shared.discovery_contract import DiscoveryMap, TestContract
from markettwin_shared.feature_plan import TestCaseSpec
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_evaluation_worker.contract_replay import replay_decision
from markettwin_evaluation_worker.deep_evaluator import valid_case_evidence
from markettwin_evaluation_worker.experience_evaluator import (
    assess_experience,
    extract_persona_facts,
)
from markettwin_evaluation_worker.market_verdict import market_verdict
from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
    EvidenceReference,
    VisualArtifactRecord,
)
from markettwin_evaluation_worker.persistence.report_repository import ReportRepository
from markettwin_evaluation_worker.visual_artifact_storage import VisualArtifactStorage


def _completed_action_step_count(
    result: CaseExecutionResult,
    steps: Mapping[int, ExecutionStep],
) -> int:
    return sum(
        (step := steps.get(step_id)) is not None
        and step.execution_id == result.execution_id
        and step.status == "completed"
        and step.action_type != "assertion"
        for step_id in result.action_step_ids
    )


async def evaluate_contract_run(
    *, test_run_id: UUID, contract: TestContract, discovery: DiscoveryMap,
    session: AsyncSession,
) -> tuple[tuple[UUID, ...], UUID]:
    if (contract.test_run_id != test_run_id or contract.status != "frozen"
            or contract.approved_by_user_id is None or contract.approved_at is None):
        raise ValueError("Evaluation requires this run's approved frozen contract.")
    events = tuple((await session.scalars(select(RunEvent).where(
        RunEvent.test_run_id == test_run_id,
        RunEvent.event_type.in_(("contract.execution_plan", "contract.case.completed",
                                "test_case.replay", "contract.journey.skipped")),
    ).order_by(RunEvent.id))).all())
    plans = [e for e in events if e.event_type == "contract.execution_plan"]
    identity = {"contract_id": str(contract.contract_id), "contract_version": contract.version,
                "contract_hash": contract.content_hash()}
    if len(plans) != 1 or any(plans[0].payload.get(k) != v for k, v in identity.items()):
        raise ValueError("Executed contract plan does not match the frozen contract.")
    approved = {j.journey_key: j for j in contract.journeys if not j.excluded
                and any(not a.excluded for a in j.assertions)}
    cases: dict[str, TestCaseSpec] = {}
    for payload in cast(list[dict[str, object]], plans[0].payload.get("cases", [])):
        case = TestCaseSpec.model_validate(payload)
        if case.case_id not in approved or case != contract_case(
            approved[case.case_id], discovery.target_origin,
        ):
            raise ValueError("Executed case differs from its approved journey.")
        if case.case_id in cases:
            raise ValueError("Duplicate case in the executed contract plan.")
        cases[case.case_id] = case
    journeys = {j.id: j for j in (await session.scalars(select(PersonaJourney).where(
        PersonaJourney.test_run_id == test_run_id,
    ))).all()}
    executions = {e.id: e for e in (await session.scalars(select(AgentExecution).where(
        AgentExecution.journey_id.in_(tuple(journeys)),
    ))).all()}
    personas = {p.id: p for p in (await session.scalars(select(RunPersona).where(
        RunPersona.test_run_id == test_run_id,
    ))).all()}
    steps = {s.id: s for s in (await session.scalars(select(ExecutionStep).where(
        ExecutionStep.execution_id.in_(tuple(executions)),
    ))).all()}
    artifacts = {a.id: a for a in (await session.scalars(select(Artifact).where(
        Artifact.execution_id.in_(tuple(executions)),
    ))).all()}
    groups: dict[tuple[str, int], list[tuple[RunEvent, CaseExecutionResult, bool]]]
    groups = defaultdict(list)
    for event in events:
        if event.event_type != "contract.case.completed":
            continue
        try:
            result = CaseExecutionResult.model_validate(event.payload.get("result"))
        except ValidationError:
            continue
        case = cases.get(result.case_id)
        execution = executions.get(result.execution_id)
        persona_index = event.payload.get("persona_index")
        if (case is None or execution is None or type(persona_index) is not int
                or persona_index not in {0, 1, 2}
                or event.execution_id != result.execution_id
                or event.journey_id != execution.journey_id
                or execution.status != result.execution_status
                or event.payload.get("attempt") != execution.attempt_number
                or journeys[execution.journey_id].persona_id not in personas
                or personas[journeys[execution.journey_id].persona_id].attributes.get(
                    "contract_persona"
                ) != persona_index
                or any(event.payload.get(k) != v for k, v in identity.items())):
            continue
        valid = valid_case_evidence(case, result, steps, artifacts)
        groups[(result.case_id, persona_index)].append((event, result, valid))
    finding_ids: list[UUID] = []
    confirmed_keys: dict[tuple[str, str], UUID] = {}
    observations: list[dict[str, object]] = []
    entries: list[dict[str, object]] = []
    completed_personas: set[int] = set()
    seen_cases: set[str] = set()
    for (key, persona), attempts in groups.items():
        original_rows = [row for row in attempts if row[0].payload.get("attempt") == 1]
        if len(original_rows) != 1:
            continue
        event, original, valid = original_rows[0]
        seen_cases.add(key)
        if valid:
            completed_personas.add(persona)
        replays = [row for row in attempts if row[0].payload.get("attempt") == 2]
        replay = replays[0] if len(replays) == 1 else None
        linked = replay is not None and any(
            e.event_type == "test_case.replay" and e.execution_id == replay[1].execution_id
            and e.journey_id == event.journey_id
            and e.payload.get("replay_of_execution_id") == str(original.execution_id)
            and all(e.payload.get(k) == v for k, v in identity.items()) for e in events
        )
        blocked_reason = (
            "authentication_required" if original.blocker == "authentication_challenge_blocked"
            else "time_budget" if original.execution_status == "timed_out"
            else "policy_blocked" if original.execution_status == "policy_blocked"
            else "execution_incomplete" if not valid else None
        )
        entries.append({"journey_key": key, "persona_index": persona,
                        "verdict": original.verdict if valid else "unverified",
                        "execution_status": original.execution_status,
                        "reason": blocked_reason,
                        "execution_id": str(original.execution_id),
                        "completed_steps": _completed_action_step_count(original, steps),
                        "planned_steps": len(cases[key].steps) + 1,
                        "assertions": [a.model_dump(mode="json")
                                       for a in original.assertion_results]})
        for assertion in original.assertion_results:
            if assertion.status != "not_satisfied":
                continue
            assertion_step = steps.get(assertion.step_id)
            if (assertion_step is None or assertion_step.execution_id != original.execution_id
                    or assertion_step.status != "completed"
                    or assertion_step.action_type != "assertion"
                    or not assertion.artifact_ids
                    or any(a not in artifacts or artifacts[a].execution_id != original.execution_id
                           or artifacts[a].step_id != assertion.step_id
                           for a in assertion.artifact_ids)):
                continue
            try:
                if json.loads(assertion_step.observation_summary or "null") != assertion.model_dump(
                    mode="json",
                ):
                    continue
            except (ValueError, TypeError):
                continue
            decision = replay_decision(
                assertion_id=assertion.assertion_id, original=original,
                replay=replay[1] if replay else None,
                original_evidence_valid=valid, replay_evidence_valid=replay[2] if replay else False,
                same_frozen_contract=linked,
            )
            check = next((a for a in approved[key].assertions
                          if a.assertion_id == assertion.assertion_id and not a.excluded), None)
            if check is None:
                continue
            record: dict[str, object] = {
                "journey_key": key, "persona_index": persona,
                "assertion_id": assertion.assertion_id,
                "check": check.plain_language, "reason": decision,
                "step_id": assertion.step_id, "execution_id": str(original.execution_id),
                "artifact_ids": [str(a) for a in assertion.artifact_ids],
                "screenshot_artifact_ids": [str(a) for a in assertion.artifact_ids
                                            if a in artifacts
                                            and artifacts[a].artifact_type == "screenshot"],
            }
            if decision != "reproduced":
                observations.append(record)
                continue
            assert event.journey_id is not None and replay is not None
            replay_assertion = next(a for a in replay[1].assertion_results
                                    if a.assertion_id == assertion.assertion_id)
            finding_id = confirmed_keys.get((key, assertion.assertion_id))
            if finding_id is None:
                finding_id = await EvaluationRepository(session).create_linked_finding(
                    test_run_id=test_run_id, journey_ids=(event.journey_id,), severity="medium",
                    category="deterministic_assertion", title=check.plain_language[:200],
                    summary="The approved check failed again on re-check in a fresh browser.",
                    recommendation="Inspect the linked original and confirmation evidence.",
                    evidence=tuple(EvidenceReference(
                        step_id=assertion.step_id, artifact_id=a,
                        execution_id=original.execution_id,
                    ) for a in assertion.artifact_ids) + tuple(EvidenceReference(
                        step_id=replay_assertion.step_id, artifact_id=a,
                        execution_id=replay[1].execution_id,
                    ) for a in replay_assertion.artifact_ids),
                )
                finding_ids.append(finding_id)
                confirmed_keys[(key, assertion.assertion_id)] = finding_id
            record.update(finding_id=str(finding_id), verification="verified_deterministic",
                          replay_execution_id=str(replay[1].execution_id),
                          replay_step_id=replay_assertion.step_id,
                          replay_artifact_ids=[str(a) for a in replay_assertion.artifact_ids])
            record["replay_screenshot_artifact_ids"] = [
                str(a) for a in replay_assertion.artifact_ids
                if a in artifacts and artifacts[a].artifact_type == "screenshot"
            ]
            observations.append(record)
        if blocked_reason:
            observations.append({
                "journey_key": key, "persona_index": persona, "reason": blocked_reason,
                "execution_id": str(original.execution_id),
                "completed_steps": _completed_action_step_count(original, steps),
                "planned_steps": len(cases[key].steps) + 1,
            })
    for key in approved:
        for persona in range(3):
            if any(e["journey_key"] == key and e["persona_index"] == persona for e in entries):
                continue
            reason = next((e.payload.get("reason") for e in events
                           if e.event_type == "contract.journey.skipped"
                           and e.payload.get("journey_key") == key), "missing_execution")
            entries.append({"journey_key": key, "persona_index": persona, "verdict": "not_run",
                            "execution_status": "not_run", "reason": reason,
                            "execution_id": None, "assertions": [], "completed_steps": 0,
                            "planned_steps": len(approved[key].steps) + 1})
    experience: list[dict[str, object]] = []
    persona_means: dict[str, float] = {}
    for persona, name in enumerate(("First-time user", "Experienced user", "Mobile user")):
        persona_rows = [row for (_key, index), attempts in groups.items() if index == persona
                        for row in attempts]
        if not persona_rows:
            continue
        execution_ids = {row[1].execution_id for row in persona_rows}
        owned_steps = [s for s in steps.values() if s.execution_id in execution_ids]
        facts: dict[str, object] = {
            "journeys_attempted": sum(row[0].payload.get("attempt") == 1 for row in persona_rows),
            "journeys_completed": sum(row[0].payload.get("attempt") == 1 and row[2]
                                       for row in persona_rows),
            "total_steps": len(owned_steps),
            "failed_actions": sum(s.status == "failed" for s in owned_steps),
            "blocked_steps": sum(s.status == "policy_blocked" for s in owned_steps),
            "timeouts": sum(row[1].execution_status == "timed_out" for row in persona_rows),
            "retries": sum(row[0].payload.get("attempt") == 2 for row in persona_rows),
            "journey_elapsed_ms": {str(row[1].execution_id): row[1].elapsed_ms
                                   for row in persona_rows},
            "stuck_points": [s.id for s in owned_steps if s.status in {"failed", "policy_blocked"}],
        }
        extracted = extract_persona_facts(
            persona_key=str(persona), persona_name=name, journey_records=[{
                "status": result.execution_status, "duration_seconds": result.elapsed_ms / 1000,
                "steps": [{"step_number": s.step_number, "action_type": s.action_type,
                           "status": s.status, "action_summary": s.action_summary}
                          for s in sorted(owned_steps, key=lambda s: s.step_number)
                          if s.execution_id == result.execution_id],
            } for _event, result, _valid in persona_rows],
        )
        facts["stuck_points"] = extracted.stuck_points
        facts["checks_failed"] = sum(a.status == "not_satisfied" for _, r, _ in persona_rows
                                     for a in r.assertion_results)
        facts["checks_passed"] = sum(a.status == "satisfied" for _, r, _ in persona_rows
                                     for a in r.assertion_results)
        images: list[str] = []
        screenshots = [a for a in artifacts.values() if a.execution_id in execution_ids
                       and a.artifact_type == "screenshot" and a.content_type == "image/png"
                       and a.step_id is not None][:3]
        try:
            storage = VisualArtifactStorage.from_environment() if screenshots else None
            with TemporaryDirectory(prefix="markettwin-experience-") as directory:
                for artifact in screenshots:
                    assert storage is not None and artifact.step_id is not None
                    path = await storage.download(artifact=VisualArtifactRecord(
                        artifact_id=artifact.id, step_id=artifact.step_id, kind="viewport",
                        storage_provider=artifact.storage_provider, bucket=artifact.bucket,
                        object_key=artifact.object_key, content_type=artifact.content_type,
                    ), directory=Path(directory))
                    if path.stat().st_size <= 8_000_000:
                        data = await asyncio.to_thread(path.read_bytes)
                        if data.startswith(b"\x89PNG\r\n\x1a\n"):
                            images.append(
                                "data:image/png;base64," + base64.b64encode(data).decode(),
                            )
        except Exception:
            images = []
        assessment = await assess_experience(persona_name=name, facts=facts,
                                             screenshot_data_urls=images)
        experience.append({"persona_index": persona, "persona_name": name, **assessment})
        if assessment.get("status") == "completed":
            persona_means[name] = float(cast(float, assessment["mean"]))
    verdict = market_verdict(
        journeys_executed=len(seen_cases), journeys_approved=len(approved),
        personas_completed=len(completed_personas),
        confirmed_severities=["medium"] * len(finding_ids), persona_means=persona_means,
    )
    works = [key for key in approved if sum(e["journey_key"] == key for e in entries) == 3
             and all(e["verdict"] == "satisfied" for e in entries if e["journey_key"] == key)]
    journey_details = [{
        "journey_key": key, "title": journey.title, "feature_key": journey.feature_key,
        "checks": [{"assertion_id": a.assertion_id, "plain_language": a.plain_language}
                   for a in journey.assertions if not a.excluded],
    } for key, journey in approved.items()]
    works_details = [{
        **next(j for j in journey_details if j["journey_key"] == key),
        "evidence": [{"persona_index": entry["persona_index"],
                      "execution_id": entry["execution_id"], "assertions": entry["assertions"]}
                     for entry in entries if entry["journey_key"] == key],
    } for key in works]
    summary = (f"Tested {len(seen_cases)} of {len(approved)} approved journeys; "
               f"{len(finding_ids)} confirmed problems.") if approved else (
                   "No approved tests — nothing was verified."
               )
    confirmed_records: dict[str, dict[str, object]] = {}
    for observation in observations:
        if observation.get("verification"):
            confirmed_records.setdefault(str(observation["finding_id"]), observation)
    report_id = await ReportRepository(session).create_completed_report(
        test_run_id=test_run_id, executive_summary=summary, report_payload={
            "schema_version": 1, "mode": "discovery_contract_v1", **identity,
            "cases": entries, "what_works": works,
            "journeys": journey_details, "what_works_details": works_details,
            "confirmed": list(confirmed_records.values()),
            "confirmed_occurrences": [o for o in observations if o.get("verification")],
            "unverified": [o for o in observations if not o.get("verification")],
            "experience": {"personas": experience}, "market_verdict": asdict(verdict),
            "coverage": {"executed": len(seen_cases), "approved": len(approved),
                         "discovered_features": len(discovery.features),
                         "tested_features": len({approved[key].feature_key for key in seen_cases}),
                         "verified_findings": len(finding_ids)},
        },
    )
    return tuple(finding_ids), report_id
