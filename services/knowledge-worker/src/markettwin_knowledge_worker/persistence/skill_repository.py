"""Persistence for generated MarketTwin product Skills."""

from uuid import UUID

from markettwin_database.models import (
    Skill,
    SkillEvidenceReference,
    SkillVersion,
)
from markettwin_shared.knowledge import GeneratedSkillDraft
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class SkillRepository:
    """Persist generated Skill drafts and their evidence grounding."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def persist_draft(
        self,
        *,
        workspace_id: UUID,
        blueprint_id: UUID,
        blueprint_version_id: UUID,
        created_by_user_id: UUID,
        draft: GeneratedSkillDraft,
        evidence_ids_by_ordinal: dict[int, UUID],
    ) -> UUID:
        """Persist one generated Skill draft and return its SkillVersion ID."""

        missing_ordinals = (
            set(draft.evidence_ordinals)
            - evidence_ids_by_ordinal.keys()
        )

        if missing_ordinals:
            raise ValueError(
                "Generated Skill references evidence that was not persisted: "
                f"{sorted(missing_ordinals)}"
            )

        skill = await self._get_or_create_skill(
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            created_by_user_id=created_by_user_id,
            name=draft.name,
        )

        version_number = await self._next_version_number(
            workspace_id=workspace_id,
            skill_id=skill.id,
        )

        skill_version = SkillVersion(
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            blueprint_version_id=blueprint_version_id,
            skill_id=skill.id,
            version_number=version_number,
            status="draft",
            grounding_confidence=draft.grounding_confidence,
            definition_json=draft.definition.model_dump(
                mode="json",
            ),
            generation_metadata={
                "warnings": list(draft.warnings),
            },
            created_by_user_id=created_by_user_id,
        )

        self._session.add(skill_version)
        await self._session.flush()

        for ordinal in draft.evidence_ordinals:
            self._session.add(
                SkillEvidenceReference(
                    workspace_id=workspace_id,
                    blueprint_id=blueprint_id,
                    skill_version_id=skill_version.id,
                    evidence_unit_id=evidence_ids_by_ordinal[
                        ordinal
                    ],
                )
            )

        await self._session.flush()

        return skill_version.id

    async def _get_or_create_skill(
        self,
        *,
        workspace_id: UUID,
        blueprint_id: UUID,
        created_by_user_id: UUID,
        name: str,
    ) -> Skill:
        """Reuse the stable Skill identity when it already exists."""

        statement = select(Skill).where(
            Skill.workspace_id == workspace_id,
            Skill.blueprint_id == blueprint_id,
            Skill.name == name,
        )

        result = await self._session.execute(statement)

        skill = result.scalar_one_or_none()

        if skill is not None:
            return skill

        skill = Skill(
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            created_by_user_id=created_by_user_id,
            name=name,
            status="active",
        )

        self._session.add(skill)
        await self._session.flush()

        return skill

    async def _next_version_number(
        self,
        *,
        workspace_id: UUID,
        skill_id: UUID,
    ) -> int:
        """Return the next version number for one logical Skill."""

        statement = select(
            func.coalesce(
                func.max(SkillVersion.version_number),
                0,
            )
        ).where(
            SkillVersion.workspace_id == workspace_id,
            SkillVersion.skill_id == skill_id,
        )

        result = await self._session.execute(statement)

        current_version = result.scalar_one()

        return int(current_version) + 1