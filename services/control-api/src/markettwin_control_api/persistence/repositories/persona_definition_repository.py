"""Control-api persistence for persona definitions (U-P5-03)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_database.models import ApplicationPersonaDefinition
from markettwin_shared.persona_definitions import PersonaDefinition


class PersonaDefinitionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_application(
        self, *, application_id: UUID,
    ) -> list[ApplicationPersonaDefinition]:
        result = await self._session.execute(
            select(ApplicationPersonaDefinition)
            .where(
                ApplicationPersonaDefinition.application_id == application_id,
            )
            .order_by(ApplicationPersonaDefinition.persona_id)
        )
        return list(result.scalars().all())

    async def get(
        self, *, application_id: UUID, persona_id: str,
    ) -> ApplicationPersonaDefinition | None:
        return await self._session.scalar(
            select(ApplicationPersonaDefinition).where(
                ApplicationPersonaDefinition.application_id == application_id,
                ApplicationPersonaDefinition.persona_id == persona_id,
            )
        )

    async def upsert(
        self, *, application_id: UUID, definition: PersonaDefinition,
        definition_yaml: str,
    ) -> None:
        document = definition.model_dump(mode="json")
        existing = await self.get(
            application_id=application_id,
            persona_id=definition.persona_id,
        )
        if existing is None:
            self._session.add(ApplicationPersonaDefinition(
                application_id=application_id,
                persona_id=definition.persona_id,
                persona_type=definition.type,
                name=definition.name,
                enabled=definition.enabled,
                definition=document,
                definition_yaml=definition_yaml,
                source_run_id=None,
            ))
        else:
            existing.persona_type = definition.type
            existing.name = definition.name
            existing.enabled = definition.enabled
            existing.definition = document
            existing.definition_yaml = definition_yaml
        await self._session.flush()
