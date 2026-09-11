"""Database access for deterministic MarketTwin evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from markettwin_database.models import (
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
    """Best deterministic evidence available for one execution."""

    step_id: int | None = None
    artifact_id: UUID | None = None


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

    async def find_preferred_evidence(
        self,
        *,
        execution_id: UUID,
    ) -> EvidenceReference:
        screenshot = await self._session.scalar(
            select(Artifact)
            .where(
                Artifact.execution_id == execution_id,
                Artifact.artifact_type
                == "screenshot",
            )
            .order_by(Artifact.created_at.desc())
            .limit(1)
        )

        if screenshot is not None:
            return EvidenceReference(
                step_id=screenshot.step_id,
                artifact_id=screenshot.id,
            )

        trace = await self._session.scalar(
            select(Artifact)
            .where(
                Artifact.execution_id == execution_id,
                Artifact.artifact_type == "trace",
            )
            .order_by(Artifact.created_at.desc())
            .limit(1)
        )

        if trace is not None:
            return EvidenceReference(
                artifact_id=trace.id,
            )

        step_id = await self._session.scalar(
            select(ExecutionStep.id)
            .where(
                ExecutionStep.execution_id
                == execution_id
            )
            .order_by(
                ExecutionStep.step_number.desc()
            )
            .limit(1)
        )

        return EvidenceReference(
            step_id=step_id,
        )

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
        evidence: EvidenceReference,
    ) -> UUID:
        return await self.create_linked_finding(
            test_run_id=test_run_id,
            journey_ids=(journey_id,),
            severity=severity,
            category=category,
            title=title,
            summary=summary,
            recommendation=recommendation,
            evidence=(evidence,),
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

        if not valid_evidence:
            raise RuntimeError(
                "Cannot create an authoritative Finding "
                "without execution evidence."
            )

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