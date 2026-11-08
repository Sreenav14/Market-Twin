"""Persistence for application persona definitions (U-P5-03)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_database.models import ApplicationPersonaDefinition

from markettwin_shared.persona_definitions import (
    PersonaDefinition,
    dump_definition_yaml,
)


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

    async def upsert(
        self, *, application_id: UUID, definition: PersonaDefinition,
        source_run_id: UUID | None,
    ) -> None:
        existing = await self._session.scalar(
            select(ApplicationPersonaDefinition).where(
                ApplicationPersonaDefinition.application_id == application_id,
                ApplicationPersonaDefinition.persona_id == definition.persona_id,
            )
        )
        document = definition.model_dump(mode="json")
        yaml_text = dump_definition_yaml(definition)
        if existing is None:
            self._session.add(ApplicationPersonaDefinition(
                application_id=application_id,
                persona_id=definition.persona_id,
                persona_type=definition.type,
                name=definition.name,
                enabled=definition.enabled,
                definition=document,
                definition_yaml=yaml_text,
                source_run_id=source_run_id,
            ))
        else:
            existing.persona_type = definition.type
            existing.name = definition.name
            existing.enabled = definition.enabled
            existing.definition = document
            existing.definition_yaml = yaml_text
            existing.source_run_id = source_run_id
        await self._session.flush()
