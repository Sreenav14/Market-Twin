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
from markettwin_execution_orchestrator.agents.schemas.test_case import DeepFeaturePlan

# Reserved manual prerequisite record, outside the bounded feature-case ordinals.
AUTH_BOOTSTRAP_ORDINAL = 10000


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

    async def create_auth_bootstrap(self, *, test_run_id: UUID) -> PersistedJourneyRecord:
        """Persist manual login ownership before a generated feature plan exists."""
        persona_id, mission_id, journey_id = uuid4(), uuid4(), uuid4()
        self._session.add_all([
            RunPersona(id=persona_id, test_run_id=test_run_id, ordinal=AUTH_BOOTSTRAP_ORDINAL,
                       name="Human authentication prerequisite",
                       description=("Manual authentication; excluded from feature test coverage."),
                       attributes={"executor_role": False, "auth_bootstrap": True}),
            RunMission(id=mission_id, test_run_id=test_run_id, ordinal=AUTH_BOOTSTRAP_ORDINAL,
                       title="Verify identity before protected discovery",
                       objective="Establish an approved test identity securely.",
                       success_criteria=[], priority="low"),
        ])
        await self._session.flush()
        self._session.add(PersonaJourney(
            id=journey_id, test_run_id=test_run_id, persona_id=persona_id,
            mission_id=mission_id, ordinal=AUTH_BOOTSTRAP_ORDINAL,
        ))
        await self._session.flush()
        return PersistedJourneyRecord(journey_id, persona_id, mission_id,
                                      "human_auth__auth_bootstrap", AUTH_BOOTSTRAP_ORDINAL)

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

        # Persist the parent records first so the composite foreign keys
        # referenced by PersonaJourney exist before journey insertion.
        self._session.add_all(
            [
                *persona_rows,
                *mission_rows,
            ]
        )

        await self._session.flush()

        self._session.add_all(journey_rows)

        await self._session.flush()

        return PersistedPlanRecord(
            test_run_id=test_run_id,
            personas=tuple(persisted_personas),
            missions=tuple(persisted_missions),
            journeys=tuple(persisted_journeys),
        )

    async def create_from_feature_cases(
        self, *, test_run_id: UUID, plan: DeepFeaturePlan,
    ) -> PersistedPlanRecord:
        """One executor role, mission and independent journey per selected case.

        Skipped candidates stay in the frozen event and have no executable rows.
        The caller validates plan authority before persistence and owns commit.
        """
        if await self._session.get(TestRun, test_run_id) is None:
            raise ValueError(f'TestRun "{test_run_id}" does not exist.')
        await self._ensure_plan_not_persisted(test_run_id=test_run_id)
        persona_id = uuid4()
        persona_key = "feature_tester_v1"
        persona = RunPersona(
            id=persona_id, test_run_id=test_run_id, ordinal=1, name="Feature tester",
            description="Bounded deterministic execution of approved feature cases.",
            attributes={"persona_key": persona_key, "executor_role": True,
                        "plan_schema_version": plan.schema_version},
        )
        missions: list[RunMission] = []
        journeys: list[PersonaJourney] = []
        mission_records: list[PersistedMissionRecord] = []
        journey_records: list[PersistedJourneyRecord] = []
        for ordinal, case in enumerate(plan.cases, start=1):
            mission_id, journey_id = uuid4(), uuid4()
            criteria = [f"{item.assertion_id}: {item.oracle} expected {item.expected_value}"
                        for item in case.expected]
            missions.append(RunMission(
                id=mission_id, test_run_id=test_run_id, ordinal=ordinal,
                title=case.title[:100], objective=case.title, success_criteria=criteria,
                priority=case.priority,
            ))
            journeys.append(PersonaJourney(
                id=journey_id, test_run_id=test_run_id, persona_id=persona_id,
                mission_id=mission_id, ordinal=ordinal,
            ))
            mission_records.append(PersistedMissionRecord(
                mission_id=mission_id, mission_key=case.case_id, ordinal=ordinal,
            ))
            journey_records.append(PersistedJourneyRecord(
                journey_id=journey_id, persona_id=persona_id, mission_id=mission_id,
                journey_key=f"{persona_key}__{case.case_id}", ordinal=ordinal,
            ))
        self._session.add_all([persona, *missions])
        await self._session.flush()
        self._session.add_all(journeys)
        await self._session.flush()
        return PersistedPlanRecord(
            test_run_id=test_run_id,
            personas=(PersistedPersonaRecord(persona_id=persona_id,
                                            persona_key=persona_key, ordinal=1),),
            missions=tuple(mission_records), journeys=tuple(journey_records),
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
                RunPersona.test_run_id == test_run_id,
                RunPersona.ordinal != AUTH_BOOTSTRAP_ORDINAL,
            )
            .limit(1)
        )

        mission_id = await self._session.scalar(
            select(RunMission.id)
            .where(
                RunMission.test_run_id == test_run_id,
                RunMission.ordinal != AUTH_BOOTSTRAP_ORDINAL,
            )
            .limit(1)
        )

        journey_id = await self._session.scalar(
            select(PersonaJourney.id)
            .where(
                PersonaJourney.test_run_id == test_run_id,
                PersonaJourney.ordinal != AUTH_BOOTSTRAP_ORDINAL,
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
