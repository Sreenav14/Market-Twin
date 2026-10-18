"""Read completed MarketTwin evaluation results."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from markettwin_database.models import (
    AgentExecution,
    Artifact,
    ExecutionStep,
    Finding,
    FindingEvidence,
    FindingJourney,
    PersonaJourney,
    Report,
    RunEvent,
    RunMission,
    RunPersona,
)
from markettwin_shared.deep_testing import AssertionResult
from pydantic import ValidationError
from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class FindingResultRecord:
    """One finding and its recorded evidence references."""

    finding_id: UUID
    severity: str
    category: str
    title: str
    summary: str
    recommendation: str | None
    status: str

    journey_ids: tuple[UUID, ...]
    step_ids: tuple[int, ...]
    artifact_ids: tuple[UUID, ...]
    has_visual_evidence: bool = False


@dataclass(frozen=True, slots=True)
class ReportResultRecord:
    """One persisted MarketTwin report."""

    report_id: UUID
    test_run_id: UUID
    version: int
    status: str
    executive_summary: str | None
    report_payload: dict[str, object]
    generated_at: datetime | None


@dataclass(frozen=True, slots=True)
class TestRunResultsRecord:
    """Complete readable result for one TestRun."""

    report: ReportResultRecord
    findings: tuple[FindingResultRecord, ...]


class TestRunResultsRepository:
    """Read evaluation results for the Control API."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def list_journeys(
        self, *, test_run_id: UUID, journey_id: UUID | None = None,
    ) -> list[dict[str, object]]:
        """Read actual execution and the matching result before report generation."""
        statement = (
                select(
                    PersonaJourney, RunPersona.name, RunPersona.description,
                    RunMission.title, RunMission.objective, RunMission.success_criteria,
                )
                .join(RunPersona, RunPersona.id == PersonaJourney.persona_id)
                .join(RunMission, RunMission.id == PersonaJourney.mission_id)
                .where(PersonaJourney.test_run_id == test_run_id)
                .order_by(PersonaJourney.ordinal)
                .limit(200)
        )
        if journey_id is not None:
            statement = statement.where(PersonaJourney.id == journey_id)
        rows = (await self._session.execute(statement)).all()
        executions = (
            await self._session.scalars(
                select(AgentExecution)
                .join(PersonaJourney, PersonaJourney.id == AgentExecution.journey_id)
                .where(
                    PersonaJourney.test_run_id == test_run_id,
                    PersonaJourney.id.in_(tuple(row[0].id for row in rows)),
                )
                .distinct(AgentExecution.journey_id)
                .order_by(
                    AgentExecution.journey_id, AgentExecution.attempt_number.desc(),
                    AgentExecution.id.desc(),
                )
            )
        ).all()
        latest: dict[UUID, AgentExecution] = {}
        for execution in executions:
            latest.setdefault(execution.journey_id, execution)
        execution_ids = tuple(execution.id for execution in latest.values())
        step_counts = {execution_id: count for execution_id, count in (await self._session.execute(
            select(ExecutionStep.execution_id, func.count(ExecutionStep.id))
            .where(ExecutionStep.execution_id.in_(execution_ids))
            .group_by(ExecutionStep.execution_id)
        )).all()} if execution_ids else {}
        artifact_counts = {
            execution_id: count for execution_id, count in (await self._session.execute(
            select(Artifact.execution_id, func.count(Artifact.id))
            .where(Artifact.execution_id.in_(execution_ids))
            .group_by(Artifact.execution_id)
        )).all()} if execution_ids else {}
        events = (
            await self._session.scalars(
                select(RunEvent)
                .where(
                    RunEvent.test_run_id == test_run_id,
                    RunEvent.event_type.in_(("journey.result", "test_case.diagnostic")),
                    RunEvent.execution_id.in_(execution_ids),
                )
                .distinct(RunEvent.execution_id, RunEvent.event_type)
                .order_by(RunEvent.execution_id, RunEvent.event_type, RunEvent.id.desc())
            )
        ).all()
        results: dict[UUID, dict[str, object]] = {}
        diagnostics: dict[UUID, dict[str, object]] = {}
        for event in events:
            if event.execution_id is not None:
                if event.event_type == "test_case.diagnostic":
                    reason = event.payload.get("reason_code")
                    if reason in {
                        "absent_scope", "ambiguous_scope", "absent_target", "ambiguous_target",
                        "action_failed",
                        "human_assistance_unverified",
                    }:
                        diagnostics[event.execution_id] = {"reason_code": reason}
                else:
                    results.setdefault(event.execution_id, event.payload)
        journeys: list[dict[str, object]] = []
        for journey, persona_name, perspective, mission_title, objective, criteria in rows:
            execution = latest.get(journey.id)
            result = results.get(execution.id) if execution is not None else None
            policy_diagnostic = (
                _safe_policy_diagnostic(execution.error_message) if execution is not None else None
            )
            if policy_diagnostic is not None:
                result = {**(result or {}), "diagnostic": policy_diagnostic}
            if result is not None and execution is not None and execution.id in diagnostics:
                result = {**result, "diagnostic": diagnostics[execution.id]}
            journeys.append(
                {
                    "id": journey.id,
                    "ordinal": journey.ordinal,
                    "persona_name": persona_name,
                    "persona_perspective": perspective,
                    "mission_title": mission_title,
                    "mission_objective": objective,
                    "step_count": step_counts.get(execution.id, 0) if execution else 0,
                    "artifact_count": artifact_counts.get(execution.id, 0) if execution else 0,
                    "evidence_available": bool(artifact_counts.get(execution.id, 0))
                    if execution else False,
                    "summary": result.get("summary") if result else None,
                    "success_criteria": criteria,
                    "execution_id": execution.id if execution is not None else None,
                    "attempt_number": execution.attempt_number if execution is not None else None,
                    "execution_status": execution.status if execution is not None else None,
                    "runtime_name": getattr(execution, "runtime_name", None),
                    "outcome": execution.outcome if execution is not None else None,
                    "started_at": execution.started_at if execution is not None else None,
                    "completed_at": execution.completed_at if execution is not None else None,
                    "error_message": "Not tested—human assistance skipped."
                    if execution is not None and execution.status == "skipped"
                    else "Browser stopped. Review its steps and target policy."
                    if execution is not None and execution.error_message else None,
                    "result": result,
                }
            )
        return journeys

    async def get_journey(
        self, *, test_run_id: UUID, journey_id: UUID, after_step: int, limit: int,
    ) -> dict[str, object] | None:
        """Read one owned journey's latest attempt and bounded evidence metadata."""
        journeys = await self.list_journeys(test_run_id=test_run_id, journey_id=journey_id)
        if not journeys:
            return None
        journey = journeys[0]
        execution_id = journey["execution_id"]
        steps: tuple[ExecutionStep, ...] = tuple((await self._session.scalars(
            select(ExecutionStep).where(
                ExecutionStep.execution_id == execution_id,
                ExecutionStep.step_number > after_step,
            ).order_by(ExecutionStep.step_number).limit(limit + 1)
        )).all()) if execution_id else ()
        has_more = len(steps) > limit
        steps = steps[:limit]
        artifacts = tuple((await self._session.scalars(
            select(Artifact).where(
                Artifact.execution_id == execution_id,
                Artifact.step_id.in_(tuple(step.id for step in steps)),
            ).order_by(Artifact.created_at, Artifact.id).limit(1001)
        )).all()) if steps else ()
        results = await self.get_completed_results(test_run_id=test_run_id, journey_id=journey_id)
        return {
            "journey": journey,
            "steps": [{
                "id": step.id, "step_number": step.step_number,
                "action_type": step.action_type, "action_summary": _safe_action_summary(step),
                "observation_summary": _safe_observation_summary(step), "status": step.status,
                "started_at": step.started_at, "completed_at": step.completed_at,
            } for step in steps],
            "artifacts": [{
                "id": artifact.id, "step_id": artifact.step_id,
                "artifact_type": artifact.artifact_type, "content_type": artifact.content_type,
                "size_bytes": artifact.size_bytes, "created_at": artifact.created_at,
                "kind": artifact.metadata_json.get("kind")
                if isinstance(artifact.metadata_json.get("kind"), str) else None,
            } for artifact in artifacts[:1000]],
            "artifacts_truncated": len(artifacts) > 1000,
            "next_after_step": steps[-1].step_number if has_more and steps else None,
            "findings": tuple(finding for finding in results.findings
                              if journey_id in finding.journey_ids) if results else (),
        }

    async def get_completed_results(
        self,
        *,
        test_run_id: UUID,
        journey_id: UUID | None = None,
    ) -> TestRunResultsRecord | None:
        report = await self._session.scalar(
            select(Report)
            .where(
                Report.test_run_id == test_run_id,
                Report.status == "completed",
            )
            .order_by(Report.version.desc())
            .limit(1)
        )

        if report is None:
            return None

        findings = tuple(
            (
                await self._session.scalars(
                    select(Finding)
                    .where(Finding.test_run_id == test_run_id)
                    .where(Finding.id.in_(select(FindingJourney.finding_id).where(
                        FindingJourney.journey_id == journey_id,
                    )) if journey_id else true())
                    .order_by(
                        Finding.created_at,
                        Finding.id,
                    )
                    .limit(200 if journey_id else None)
                )
            ).all()
        )

        finding_ids = tuple(finding.id for finding in findings)

        journeys_by_finding: dict[
            UUID,
            list[UUID],
        ] = {}

        steps_by_finding: dict[
            UUID,
            list[int],
        ] = {}

        artifacts_by_finding: dict[
            UUID,
            list[UUID],
        ] = {}
        visual_evidence_ids: set[UUID] = set()

        if finding_ids:
            journey_links = tuple(
                (
                    await self._session.scalars(
                        select(FindingJourney).where(FindingJourney.finding_id.in_(finding_ids))
                    )
                ).all()
            )

            for link in journey_links:
                journeys_by_finding.setdefault(
                    link.finding_id,
                    [],
                ).append(link.journey_id)

            evidence_links = tuple(
                (
                    await self._session.scalars(
                        select(FindingEvidence).where(FindingEvidence.finding_id.in_(finding_ids))
                    )
                ).all()
            )

            for link in evidence_links:
                if link.step_id is not None:
                    steps_by_finding.setdefault(
                        link.finding_id,
                        [],
                    ).append(link.step_id)

                if link.artifact_id is not None:
                    artifacts_by_finding.setdefault(
                        link.finding_id,
                        [],
                    ).append(link.artifact_id)

            visual_evidence_ids = set((await self._session.scalars(
                select(FindingEvidence.finding_id)
                .join(Artifact, Artifact.id == FindingEvidence.artifact_id)
                .join(ExecutionStep, (ExecutionStep.id == Artifact.step_id)
                      & (ExecutionStep.execution_id == Artifact.execution_id))
                .join(AgentExecution, AgentExecution.id == Artifact.execution_id)
                .join(FindingJourney, (FindingJourney.finding_id == FindingEvidence.finding_id)
                      & (FindingJourney.journey_id == AgentExecution.journey_id))
                .where(
                    FindingEvidence.finding_id.in_(finding_ids),
                    Artifact.artifact_type == "screenshot",
                )
            )).all())

        finding_records = tuple(
            FindingResultRecord(
                finding_id=finding.id,
                severity=finding.severity,
                category=finding.category,
                title=finding.title,
                summary=finding.summary,
                recommendation=(finding.recommendation),
                status=finding.status,
                has_visual_evidence=finding.id in visual_evidence_ids,
                journey_ids=tuple(
                    journeys_by_finding.get(
                        finding.id,
                        [],
                    )
                ),
                step_ids=tuple(
                    steps_by_finding.get(
                        finding.id,
                        [],
                    )
                ),
                artifact_ids=tuple(
                    artifacts_by_finding.get(
                        finding.id,
                        [],
                    )
                ),
            )
            for finding in findings
        )

        return TestRunResultsRecord(
            report=ReportResultRecord(
                report_id=report.id,
                test_run_id=report.test_run_id,
                version=report.version,
                status=report.status,
                executive_summary=(report.executive_summary),
                report_payload=(report.report_payload),
                generated_at=report.generated_at,
            ),
            findings=finding_records,
        )


def _safe_policy_diagnostic(message: str | None) -> dict[str, str] | None:
    """Expose only a canonical denied origin from the reviewed policy sentence."""
    match = re.fullmatch(r'Target origin "([^"\s]{1,300})" is not allowed\.', message or "")
    if match is None:
        return None
    origin = match.group(1)
    try:
        parsed = urlsplit(origin)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment):
            return None
        _ = parsed.port
    except ValueError:
        return None
    return {"reason_code": "origin_not_authorized", "requested_origin": origin}


def _safe_action_summary(step: ExecutionStep) -> str:
    """Keep entered values, locators and arbitrary historical text out of read APIs."""
    if step.action_type == "navigate":
        return "Navigate to an allowed page."
    return {
        "get_state": "Inspect the current browser state.",
        "click": "Click a semantic page element.",
        "fill": "Fill an approved text field.",
        "select_option": "Select an option from a labelled control.",
        "scroll": "Scroll the page.",
        "go_back": "Navigate back one page.",
        "wait": "Wait for the next observation.",
        "capture_element": "Capture focused element evidence.",
        "screenshot": "Capture screenshot evidence.",
    }.get(step.action_type, "Perform a recorded browser action.")


# Shared fixed projection for both historical steps and live activity.
safe_action_summary = _safe_action_summary


def _safe_observation_summary(step: ExecutionStep) -> str | None:
    """Expose structured context, never raw exception text or page content."""
    if step.status == "policy_blocked":
        policy = _safe_policy_diagnostic(step.observation_summary)
        if policy is not None:
            return json.dumps(policy)
    if step.status != "completed":
        return "Action did not complete. Review its status and available evidence."
    if not step.observation_summary:
        return None
    if step.action_type == "assertion":
        try:
            assertion = AssertionResult.model_validate_json(step.observation_summary)
            if assertion.execution_id != step.execution_id or assertion.step_id != step.id:
                return "Assertion evidence ownership could not be verified."
            return json.dumps(assertion.model_dump(mode="json"))
        except ValidationError:
            return "A valid structured assertion result was not recorded."
    fields = {
        key: value for part in step.observation_summary.split(";")
        for key, _, value in [part.partition("=")]
    }
    context: list[str] = []
    try:
        url = urlsplit(fields.get("url", ""))
        if url.scheme in {"http", "https"} and url.hostname:
            context.append(f"Page: {url.scheme}://{url.hostname}")
    except ValueError:
        pass
    for key in ("console_errors", "page_errors", "failed_requests"):
        count = fields.get(key, "")
        if count.isdecimal() and len(count) <= 6:
            context.append(f"{key.replace('_', ' ')}: {count}")
    return "; ".join(context) or "Browser action completed; inspect the recorded evidence."
