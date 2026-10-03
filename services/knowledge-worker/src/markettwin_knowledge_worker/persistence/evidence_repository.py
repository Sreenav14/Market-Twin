"""Persistence for extracted product knowledge."""

from uuid import UUID

from markettwin_database.models import EvidenceUnit
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_knowledge_worker.extraction import ExtractionResult


class EvidenceRepository:
    """Persist extracted source evidence."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def persist(
        self,
        *,
        workspace_id: UUID,
        blueprint_id: UUID,
        asset_version_id: UUID,
        extraction: ExtractionResult,
    ) -> dict[int, UUID]:
        """Persist extracted units and return ordinal -> database ID."""

        rows: list[tuple[int, EvidenceUnit]] = []

        for unit in extraction.units:
            row = EvidenceUnit(
                workspace_id=workspace_id,
                blueprint_id=blueprint_id,
                asset_version_id=asset_version_id,
                evidence_type=unit.evidence_type,
                ordinal=unit.ordinal,
                content_text=unit.content_text,
                content_json=unit.content_json,
                source_locator=unit.source_locator,
                extractor_name=unit.extractor_name,
                extractor_version=unit.extractor_version,
            )

            self._session.add(row)

            rows.append(
                (
                    unit.ordinal,
                    row,
                )
            )

        await self._session.flush()

        return {
            ordinal: row.id
            for ordinal, row in rows
        }