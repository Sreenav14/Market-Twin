"""Persistence for Meta Agent planning results."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from markettwin_database.models.testing import (
    PersonaJourney,
    RunMission,
    RunPersona,
    TestRun,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.agents.schemas.plan import (
    MetaAgentPlan,
)


@dataclass(frozen=True, slots=True)
class PersistedPersonaRecord:
    """Identity of one persisted run persona."""

    persona_id: UUID
    persona_key: str
    ordinal: int


@dataclass(frozen=True, slots=True)
class PersistedMissionRecord:
    """Identity of one persisted run mission."""

    mission_id: UUID
    mission_key: str
    ordinal: int


@dataclass(frozen=True, slots=True)
class PersistedJourneyRecord:
    """Identity of one persisted Persona × Mission Journey."""

    journey_id: UUID
    persona_id: UUID
    mission_id: UUID
    journey_key: str
    ordinal: int


@dataclass(frozen=True, slots=True)
class PersistedPlanRecord:
    """Database identities created for one Meta Agent plan."""

    test_run_id: UUID

    personas: tuple[PersistedPersonaRecord, ...]
    missions: tuple[PersistedMissionRecord, ...]
    journeys: tuple[PersistedJourneyRecord, ...]


class PlanRepository:
    """Persist immutable planning output for one MarketTwin TestRun."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_from_plan(
        self,
        *,
        test_run_id: UUID,
        plan: MetaAgentPlan,
    ) -> PersistedPlanRecord:
        """Persist personas, missions, and deterministic journeys."""

        test_run = await self._session.get(
            TestRun,
            test_run_id,
        )

        if test_run is None:
            raise ValueError(
                f'TestRun "{test_run_id}" does not exist.'
            )

        await self._ensure_plan_not_persisted(
            test_run_id=test_run_id,
        )

        persona_rows: list[RunPersona] = []
        mission_rows: list[RunMission] = []
        journey_rows: list[PersonaJourney] = []

        persisted_personas: list[PersistedPersonaRecord] = []
        persisted_missions: list[PersistedMissionRecord] = []
        persisted_journeys: list[PersistedJourneyRecord] = []

        persona_ids: dict[str, UUID] = {}
        mission_ids: dict[str, UUID] = {}

        for ordinal, persona in enumerate(
            plan.personas,
            start=1,
        ):
            persona_db_id = uuid4()

            persona_ids[persona.persona_id] = persona_db_id

            persona_rows.append(
                RunPersona(
                    id=persona_db_id,
                    test_run_id=test_run_id,
                    ordinal=ordinal,
                    name=persona.name,
                    description=persona.perspective,
                    attributes={
                        "persona_key": persona.persona_id,
                        "behavior_traits": list(
                            persona.behavior_traits
                        ),
                        "priorities": list(
                            persona.priorities
                        ),
                    },
                )
            )

            persisted_personas.append(
                PersistedPersonaRecord(
                    persona_id=persona_db_id,
                    persona_key=persona.persona_id,
                    ordinal=ordinal,
                )
            )

        for ordinal, mission in enumerate(
            plan.missions,
            start=1,
        ):
            mission_db_id = uuid4()

            mission_ids[mission.mission_id] = mission_db_id

            mission_rows.append(
                RunMission(
                    id=mission_db_id,
                    test_run_id=test_run_id,
                    ordinal=ordinal,
                    title=mission.name,
                    objective=mission.objective,
                    success_criteria=list(
                        mission.success_criteria
                    ),
                    priority=mission.priority,
                )
            )

            persisted_missions.append(
                PersistedMissionRecord(
                    mission_id=mission_db_id,
                    mission_key=mission.mission_id,
                    ordinal=ordinal,
                )
            )

        journey_ordinal = 1

        for persona in plan.personas:
            for mission in plan.missions:
                journey_db_id = uuid4()

                persona_db_id = persona_ids[
                    persona.persona_id
                ]
                mission_db_id = mission_ids[
                    mission.mission_id
                ]

                journey_key = (
                    f"{persona.persona_id}"
                    f"__{mission.mission_id}"
                )

                journey_rows.append(
                    PersonaJourney(
                        id=journey_db_id,
                        test_run_id=test_run_id,
                        persona_id=persona_db_id,
                        mission_id=mission_db_id,
                        ordinal=journey_ordinal,
                    )
                )

                persisted_journeys.append(
                    PersistedJourneyRecord(
                        journey_id=journey_db_id,
                        persona_id=persona_db_id,
                        mission_id=mission_db_id,
                        journey_key=journey_key,
                        ordinal=journey_ordinal,
                    )
                )

                journey_ordinal += 1

        self._session.add_all(
            [
                *persona_rows,
                *mission_rows,
                *journey_rows,
            ]
        )

        await self._session.flush()

        return PersistedPlanRecord(
            test_run_id=test_run_id,
            personas=tuple(persisted_personas),
            missions=tuple(persisted_missions),
            journeys=tuple(persisted_journeys),
        )

    async def _ensure_plan_not_persisted(
        self,
        *,
        test_run_id: UUID,
    ) -> None:
        """Fail instead of silently duplicating an existing plan."""

        persona_id = await self._session.scalar(
            select(RunPersona.id)
            .where(
                RunPersona.test_run_id == test_run_id
            )
            .limit(1)
        )

        mission_id = await self._session.scalar(
            select(RunMission.id)
            .where(
                RunMission.test_run_id == test_run_id
            )
            .limit(1)
        )

        journey_id = await self._session.scalar(
            select(PersonaJourney.id)
            .where(
                PersonaJourney.test_run_id == test_run_id
            )
            .limit(1)
        )

        if (
            persona_id is not None
            or mission_id is not None
            or journey_id is not None
        ):
            raise RuntimeError(
                "Planning output has already been persisted "
                f'for TestRun "{test_run_id}".'
            )