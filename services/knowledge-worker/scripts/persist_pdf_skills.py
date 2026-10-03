"""Generate and persist draft Skills from one local PDF."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

from markettwin_database import (
    create_database_engine,
    create_session_factory,
)
from markettwin_knowledge_worker.extraction import PdfExtractor
from markettwin_knowledge_worker.persistence import (
    EvidenceRepository,
    SkillRepository,
)
from markettwin_knowledge_worker.services import (
    KnowledgeIngestionService,
)
from markettwin_knowledge_worker.skill_generator import SkillGenerator


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    parser.add_argument(
        "pdf",
        type=Path,
    )
    parser.add_argument(
        "--workspace-id",
        type=UUID,
        required=True,
    )
    parser.add_argument(
        "--blueprint-id",
        type=UUID,
        required=True,
    )
    parser.add_argument(
        "--blueprint-version-id",
        type=UUID,
        required=True,
    )
    parser.add_argument(
        "--asset-version-id",
        type=UUID,
        required=True,
    )
    parser.add_argument(
        "--created-by-user-id",
        type=UUID,
        required=True,
    )

    args = parser.parse_args()

    database_url = os.environ.get(
        "DATABASE_URL"
    )

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required."
        )

    # Extraction happens before any database work.
    extraction = PdfExtractor().extract(
        args.pdf
    )

    engine = create_database_engine(
        database_url
    )
    session_factory = create_session_factory(
        engine
    )

    try:
        async with session_factory() as session:
            service = KnowledgeIngestionService(
                skill_generator=SkillGenerator(),
                evidence_repository=EvidenceRepository(
                    session
                ),
                skill_repository=SkillRepository(
                    session
                ),
            )

            try:
                result = await service.ingest(
                    workspace_id=args.workspace_id,
                    blueprint_id=args.blueprint_id,
                    blueprint_version_id=(
                        args.blueprint_version_id
                    ),
                    asset_version_id=(
                        args.asset_version_id
                    ),
                    created_by_user_id=(
                        args.created_by_user_id
                    ),
                    extraction=extraction,
                )

                await session.commit()

            except Exception:
                await session.rollback()
                raise

        print(
            json.dumps(
                {
                    "evidence_unit_ids": {
                        str(ordinal): str(
                            evidence_id
                        )
                        for ordinal, evidence_id
                        in result.evidence_unit_ids.items()
                    },
                    "skill_version_ids": [
                        str(skill_version_id)
                        for skill_version_id
                        in result.skill_version_ids
                    ],
                },
                indent=2,
            )
        )

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())