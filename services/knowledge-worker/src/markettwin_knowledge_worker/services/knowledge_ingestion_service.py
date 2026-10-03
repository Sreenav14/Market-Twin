"""Application service for turning extracted content into draft Skills."""

from dataclasses import dataclass
from uuid import UUID

from markettwin_knowledge_worker.extraction import ExtractionResult
from markettwin_knowledge_worker.persistence import (
    EvidenceRepository,
    SkillRepository,
)
from markettwin_knowledge_worker.skill_generator import SkillGenerator


@dataclass(frozen=True, slots=True)
class KnowledgeIngestionResult:
    """Persisted result of one knowledge-generation operation."""

    evidence_unit_ids: dict[int, UUID]
    skill_version_ids: tuple[UUID, ...]


class KnowledgeIngestionService:
    """Generate and persist draft product Skills from extracted evidence."""

    def __init__(
        self,
        *,
        skill_generator: SkillGenerator,
        evidence_repository: EvidenceRepository,
        skill_repository: SkillRepository,
    ) -> None:
        self._skill_generator = skill_generator
        self._evidence_repository = evidence_repository
        self._skill_repository = skill_repository

    async def ingest(
        self,
        *,
        workspace_id: UUID,
        blueprint_id: UUID,
        blueprint_version_id: UUID,
        asset_version_id: UUID,
        created_by_user_id: UUID,
        extraction: ExtractionResult,
    ) -> KnowledgeIngestionResult:
        """Generate draft Skills and persist their source grounding."""

        drafts = await self._skill_generator.generate(
            extraction
        )

        evidence_unit_ids = (
            await self._evidence_repository.persist(
                workspace_id=workspace_id,
                blueprint_id=blueprint_id,
                asset_version_id=asset_version_id,
                extraction=extraction,
            )
        )

        skill_version_ids: list[UUID] = []

        for draft in drafts:
            skill_version_id = (
                await self._skill_repository.persist_draft(
                    workspace_id=workspace_id,
                    blueprint_id=blueprint_id,
                    blueprint_version_id=blueprint_version_id,
                    created_by_user_id=created_by_user_id,
                    draft=draft,
                    evidence_ids_by_ordinal=evidence_unit_ids,
                )
            )

            skill_version_ids.append(
                skill_version_id
            )

        return KnowledgeIngestionResult(
            evidence_unit_ids=evidence_unit_ids,
            skill_version_ids=tuple(
                skill_version_ids
            ),
        )