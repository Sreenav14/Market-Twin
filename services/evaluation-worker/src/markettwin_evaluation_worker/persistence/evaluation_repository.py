"""Database access for deterministic MarketTwin evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from markettwin_database.models import (
    AgentExecution,
    Artifact,
    ExecutionStep,
    Finding,
    FindingEvidence,
    FindingJourney,
    PersonaJourney,
    RunEvent,
    TestRun,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class JourneyResultRecord:
    """Latest persisted result for one Persona Journey."""

    journey_id: UUID
    persona_id: UUID
    mission_id: UUID
    execution_id: UUID
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """An exact step/artifact reference, optionally pinned to its execution."""

    step_id: int | None = None
    artifact_id: UUID | None = None
    execution_id: UUID | None = None

@dataclass(frozen=True, slots=True)
class VisualArtifactRecord:
    """Stored screenshot metadata needed by the visual verifier."""
    
    artifact_id: UUID
    step_id: int
    kind: str
    
    storage_provider: str
    bucket: str
    object_key: str
    content_type: str
    
    
@dataclass(frozen=True, slots=True)
class VisualEvidenceSet:
    """Viewport and optional focused crop from one browser step."""
    
    step_id: int
    action_type: str | None = None
    step_status: str | None = None
    action_summary: str | None = None
    viewport: VisualArtifactRecord | None = None
    element_crop: VisualArtifactRecord | None = None
    
    @property
    def explicitly_requests_visual_verification(self,) -> bool:
        return self.action_type in {
            "capture_element",
            "take_screenshot",
        }

class EvaluationRepository:
    """Read execution truth and persist evaluation findings."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def validate_run_ready(
        self,
        *,
        test_run_id: UUID,
    ) -> None:
        run = await self._session.get(
            TestRun,
            test_run_id,
        )

        if run is None:
            raise ValueError(
                f'TestRun "{test_run_id}" does not exist.'
            )

        if run.status != "completed":
            raise RuntimeError(
                "Only completed TestRuns can be evaluated. "
                f'Current status is "{run.status}".'
            )

        existing_finding_id = await self._session.scalar(
            select(Finding.id)
            .where(
                Finding.test_run_id == test_run_id
            )
            .limit(1)
        )

        if existing_finding_id is not None:
            raise RuntimeError(
                "Deterministic findings have already been "
                f'created for TestRun "{test_run_id}".'
            )

    async def list_journey_results(
        self,
        *,
        test_run_id: UUID,
    ) -> tuple[JourneyResultRecord, ...]:
        journeys = tuple(
            (
                await self._session.scalars(
                    select(PersonaJourney)
                    .where(
                        PersonaJourney.test_run_id
                        == test_run_id
                    )
                    .order_by(
                        PersonaJourney.ordinal
                    )
                )
            ).all()
        )

        events = tuple(
            (
                await self._session.scalars(
                    select(RunEvent)
                    .where(
                        RunEvent.test_run_id
                        == test_run_id,
                        RunEvent.event_type
                        == "journey.result",
                    )
                    .order_by(RunEvent.id)
                )
            ).all()
        )

        latest_by_journey: dict[
            UUID,
            tuple[UUID, dict[str, object]],
        ] = {}

        for event in events:
            if (
                event.journey_id is None
                or event.execution_id is None
            ):
                continue

            latest_by_journey[event.journey_id] = (
                event.execution_id,
                event.payload,
            )

        missing = [
            journey.id
            for journey in journeys
            if journey.id not in latest_by_journey
        ]

        if missing:
            raise RuntimeError(
                "Completed TestRun is missing "
                f"{len(missing)} journey.result event(s)."
            )

        results: list[JourneyResultRecord] = []

        for journey in journeys:
            execution_id, payload = (
                latest_by_journey[journey.id]
            )
            
            results.append(
                JourneyResultRecord(
                    journey_id=journey.id,
                    persona_id=journey.persona_id,
                    mission_id=journey.mission_id,
                    execution_id=execution_id,
                    payload=payload,
                )
            )

        return tuple(results)
    
    
    async def list_visual_evidence(
        self,
        *,
        execution_id: UUID,
        step_ids: tuple[int, ...],
    ) -> tuple[VisualEvidenceSet, ...]:
        """Return viewport/crop evidence for the requested execution steps."""

        if not step_ids:
            return ()

        artifacts = tuple(
            (
                await self._session.scalars(
                    select(Artifact)
                    .where(
                        Artifact.execution_id
                        == execution_id,
                        Artifact.artifact_type
                        == "screenshot",
                        Artifact.step_id.in_(step_ids),
                    )
                    .order_by(
                        Artifact.step_id,
                        Artifact.created_at,
                    )
                )
            ).all()
        )

        grouped: dict[
            int,
            dict[str, VisualArtifactRecord],
        ] = {}

        steps = tuple(
            (
                await self._session.scalars(
                    select(ExecutionStep)
                    .where(
                        ExecutionStep.execution_id == execution_id,
                        ExecutionStep.id.in_(step_ids),
                    )
                )
            ).all()
        )
        action_by_step = {
            step.id: step.action_type
            for step in steps
        }
        status_by_step = {step.id: step.status for step in steps}
        click_target_by_step = {
            step.id: step.action_summary for step in steps
            if step.action_type == "click"
            and step.action_summary.startswith("Click semantic target ")
        }
        
        for artifact in artifacts:
            if artifact.step_id not in action_by_step:
                continue

            raw_kind = artifact.metadata_json.get(
                "kind"
            )

            if not isinstance(raw_kind, str) or raw_kind not in {
                "viewport",
                "element_crop",
            }:
                continue

            record = VisualArtifactRecord(
                artifact_id=artifact.id,
                step_id=artifact.step_id,
                kind=raw_kind,
                storage_provider=(
                    artifact.storage_provider
                ),
                bucket=artifact.bucket,
                object_key=artifact.object_key,
                content_type=artifact.content_type,
            )

            grouped.setdefault(
                artifact.step_id,
                {},
            )[raw_kind] = record

        return tuple(
            VisualEvidenceSet(
                step_id=step_id,
                action_type=action_by_step.get(
                    step_id
                ),
                step_status=status_by_step.get(step_id),
                action_summary=click_target_by_step.get(step_id),
                viewport=grouped.get(
                    step_id,
                    {},
                ).get("viewport"),
                element_crop=grouped.get(
                    step_id,
                    {},
                ).get("element_crop"),
            )
            for step_id in step_ids
            if step_id in action_by_step
        )

    async def find_reported_evidence(
        self,
        *,
        execution_id: UUID,
        step_ids: tuple[int, ...],
    ) -> tuple[EvidenceReference, ...]:
        """Link recorded steps cited by a claim; linkage alone does not verify it."""
        evidence_sets = await self.list_visual_evidence(
            execution_id=execution_id, step_ids=step_ids,
        )
        references: list[EvidenceReference] = []
        for evidence in evidence_sets:
            images = tuple(image for image in (evidence.viewport, evidence.element_crop)
                           if image is not None)
            if images:
                references.extend(EvidenceReference(
                    step_id=evidence.step_id, artifact_id=image.artifact_id,
                    execution_id=execution_id,
                ) for image in images)
            else:
                references.append(EvidenceReference(
                    step_id=evidence.step_id, execution_id=execution_id,
                ))
        return tuple(references)

    async def create_finding(
        self,
        *,
        test_run_id: UUID,
        journey_id: UUID,
        severity: str,
        category: str,
        title: str,
        summary: str,
        recommendation: str,
        evidence: tuple[EvidenceReference, ...],
    ) -> UUID:
        return await self.create_linked_finding(
            test_run_id=test_run_id,
            journey_ids=(journey_id,),
            severity=severity,
            category=category,
            title=title,
            summary=summary,
            recommendation=recommendation,
            evidence=evidence,
        )

    async def create_linked_finding(
        self,
        *,
        test_run_id: UUID,
        journey_ids: tuple[UUID, ...],
        severity: str,
        category: str,
        title: str,
        summary: str,
        recommendation: str,
        evidence: tuple[EvidenceReference, ...],
    ) -> UUID:
        """Create one Finding linked to one or more Journeys."""

        unique_journey_ids = tuple(
            dict.fromkeys(journey_ids)
        )

        if not unique_journey_ids:
            raise ValueError(
                "A Finding must reference at least one Journey."
            )

        valid_evidence = tuple(
            reference
            for reference in evidence
            if (
                reference.step_id is not None
                or reference.artifact_id is not None
            )
        )

        owned_journey_ids = set((await self._session.scalars(
            select(PersonaJourney.id).where(
                PersonaJourney.test_run_id == test_run_id,
                PersonaJourney.id.in_(unique_journey_ids),
            )
        )).all())
        if owned_journey_ids != set(unique_journey_ids):
            raise ValueError("Finding journeys must belong to the specified TestRun.")

        if not valid_evidence and category == "visual_criterion":
            raise RuntimeError(
                "Cannot create an authoritative Finding "
                "without execution evidence."
            )

        if valid_evidence:
            execution_ids = set((await self._session.scalars(
                select(AgentExecution.id).where(
                    AgentExecution.journey_id.in_(unique_journey_ids),
                )
            )).all())
            artifact_ids = {
                ref.artifact_id for ref in valid_evidence if ref.artifact_id is not None
            }
            artifacts = {artifact.id: artifact for artifact in (await self._session.scalars(
                select(Artifact).where(Artifact.id.in_(artifact_ids))
            )).all()}
            if set(artifacts) != artifact_ids:
                raise ValueError("Finding references a nonexistent artifact.")
            step_ids = {ref.step_id for ref in valid_evidence if ref.step_id is not None}
            step_ids.update(artifact.step_id for artifact in artifacts.values()
                            if artifact.step_id is not None)
            steps = {step.id: step for step in (await self._session.scalars(
                select(ExecutionStep).where(ExecutionStep.id.in_(step_ids))
            )).all()}
            if set(steps) != step_ids:
                raise ValueError("Finding references a nonexistent execution step.")
            for ref in valid_evidence:
                step = steps.get(ref.step_id) if ref.step_id is not None else None
                artifact = artifacts.get(ref.artifact_id) if ref.artifact_id is not None else None
                if step is not None and step.execution_id not in execution_ids:
                    raise ValueError("Finding step belongs to another journey execution.")
                if artifact is not None:
                    if artifact.execution_id not in execution_ids:
                        raise ValueError("Finding artifact belongs to another journey execution.")
                    if artifact.step_id is not None:
                        if steps[artifact.step_id].execution_id != artifact.execution_id:
                            raise ValueError(
                                "Finding artifact and step belong to different executions."
                            )
                    if step is not None and (
                        artifact.step_id != step.id or artifact.execution_id != step.execution_id
                    ):
                        raise ValueError("Finding artifact does not belong to the specified step.")
                if ref.execution_id is not None and (
                    ref.execution_id not in execution_ids
                    or (step is not None and step.execution_id != ref.execution_id)
                    or (artifact is not None and artifact.execution_id != ref.execution_id)
                ):
                    raise ValueError("Finding evidence does not belong to the specified execution.")
                if category == "visual_criterion" and (
                    artifact is None or artifact.artifact_type != "screenshot"
                    or artifact.step_id is None
                ):
                    raise ValueError("Visual findings require screenshots of exact recorded steps.")

        finding = Finding(
            test_run_id=test_run_id,
            severity=severity,
            category=category,
            title=title,
            summary=summary,
            recommendation=recommendation,
            status="open",
        )

        self._session.add(finding)
        await self._session.flush()

        for journey_id in unique_journey_ids:
            self._session.add(
                FindingJourney(
                    finding_id=finding.id,
                    journey_id=journey_id,
                )
            )

        seen_step_ids: set[int] = set()
        seen_artifact_ids: set[UUID] = set()

        for reference in valid_evidence:
            if (
                reference.step_id is not None
                and reference.step_id
                not in seen_step_ids
            ):
                seen_step_ids.add(reference.step_id)

                self._session.add(
                    FindingEvidence(
                        finding_id=finding.id,
                        step_id=reference.step_id,
                        artifact_id=None,
                    )
                )

            if (
                reference.artifact_id is not None
                and reference.artifact_id
                not in seen_artifact_ids
            ):
                seen_artifact_ids.add(
                    reference.artifact_id
                )

                self._session.add(
                    FindingEvidence(
                        finding_id=finding.id,
                        step_id=None,
                        artifact_id=(
                            reference.artifact_id
                        ),
                    )
                )

        await self._session.flush()

        return finding.id
