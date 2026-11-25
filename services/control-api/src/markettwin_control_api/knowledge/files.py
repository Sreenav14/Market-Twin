"""Read seam over the knowledge_files index (doc 33, sections 3.4/3.6).

The table is Step 2's: one row per generated Markdown file version,
the file bytes in S3 are the truth and the row is how you find them.
This module is the run-creation / internal-read side only — it never
writes. It reads through the shared ORM model's table when Step 2
has landed it and through an identical Core table declaration until
then, so run creation can pin files the moment both halves exist.

Object keys are versioned (arbitration A-2): a retry writes version
n+1 files and never mutates a version a run may have pinned by sha.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    select,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

try:  # Step 2's shared model, once landed.
    from markettwin_database.models.knowledge import KnowledgeFile

    KNOWLEDGE_FILES = KnowledgeFile.__table__
except ImportError:  # pragma: no cover - pre-Step-2 trees only.
    KNOWLEDGE_FILES = Table(
        "knowledge_files",
        MetaData(),
        Column("id", PG_UUID(as_uuid=True), primary_key=True),
        Column("workspace_id", PG_UUID(as_uuid=True)),
        Column("ingestion_entry_id", PG_UUID(as_uuid=True)),
        Column("slug", String),
        Column("title", String),
        Column("description", String),
        Column("object_key", String),
        Column("sha256", String),
        Column("token_count", Integer),
        Column("version", Integer),
        Column("status", String),
        schema="knowledge",
    )

_KF = KNOWLEDGE_FILES.c


@dataclass(frozen=True)
class KnowledgeFileRecord:
    """One knowledge_files index row, in the contract's field shape."""

    id: UUID
    workspace_id: UUID
    ingestion_entry_id: UUID
    slug: str
    title: str
    description: str
    object_key: str
    sha256: str
    token_count: int
    version: int
    status: str


def manifest_object_key(workspace_id: UUID, entry_id: UUID, version: int) -> str:
    """The pinned manifest location for one entry version (A-2)."""

    return f"knowledge/{workspace_id}/{entry_id}/files/v{version}/manifest.json"


def _record(row) -> KnowledgeFileRecord:
    return KnowledgeFileRecord(
        id=row["id"],
        workspace_id=row["workspace_id"],
        ingestion_entry_id=row["ingestion_entry_id"],
        slug=row["slug"],
        title=row["title"],
        description=row["description"],
        object_key=row["object_key"],
        sha256=row["sha256"],
        token_count=row["token_count"],
        version=row["version"],
        status=row["status"],
    )


class KnowledgeFileRepository:
    """Approved-file reads, always scoped by workspace (the A-36 rule:
    scope is checked on the read that feeds a mutation, not after)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _rows(self, statement) -> list[KnowledgeFileRecord]:
        result = await self.session.execute(statement)
        return [_record(row) for row in result.mappings().all()]

    def _select(self):
        return select(
            _KF.id,
            _KF.workspace_id,
            _KF.ingestion_entry_id,
            _KF.slug,
            _KF.title,
            _KF.description,
            _KF.object_key,
            _KF.sha256,
            _KF.token_count,
            _KF.version,
            _KF.status,
        )

    async def get_approved_file(
        self, *, workspace_id: UUID, entry_id: UUID, slug: str,
    ) -> KnowledgeFileRecord | None:
        """The latest approved version of one file in one entry."""

        rows = await self._rows(
            self._select()
            .where(
                _KF.workspace_id == workspace_id,
                _KF.ingestion_entry_id == entry_id,
                _KF.slug == slug,
                _KF.status == "approved",
            )
            .order_by(_KF.version.desc())
            .limit(1)
        )
        return rows[0] if rows else None

    async def latest_approved_version(
        self, *, workspace_id: UUID, entry_id: UUID,
    ) -> int | None:
        rows = await self._rows(
            self._select()
            .where(
                _KF.workspace_id == workspace_id,
                _KF.ingestion_entry_id == entry_id,
                _KF.status == "approved",
            )
            .order_by(_KF.version.desc())
            .limit(1)
        )
        return rows[0].version if rows else None

    async def list_files(
        self, *, workspace_id: UUID, entry_id: UUID, version: int | None = None,
    ) -> list[KnowledgeFileRecord]:
        """One entry's file index. With a version: that version's rows
        (approved or superseded — a pinned version stays readable after
        a retry supersedes it). Without: the latest approved version
        of each slug."""

        if version is not None:
            return await self._rows(
                self._select()
                .where(
                    _KF.workspace_id == workspace_id,
                    _KF.ingestion_entry_id == entry_id,
                    _KF.version == version,
                    _KF.status.in_(("approved", "superseded")),
                )
                .order_by(_KF.slug)
            )
        rows = await self._rows(
            self._select()
            .where(
                _KF.workspace_id == workspace_id,
                _KF.ingestion_entry_id == entry_id,
                _KF.status == "approved",
            )
            .order_by(_KF.slug, _KF.version.desc())
        )
        latest: dict[str, KnowledgeFileRecord] = {}
        for row in rows:
            latest.setdefault(row.slug, row)
        return [latest[slug] for slug in sorted(latest)]

    async def list_entry_version(
        self, *, entry_id: UUID, version: int,
    ) -> list[KnowledgeFileRecord]:
        """One entry version's rows, unscoped by workspace — only for
        the internal manifest read, whose caller pins ids and shas in
        the run snapshot and verifies against them."""

        return await self._rows(
            self._select()
            .where(
                _KF.ingestion_entry_id == entry_id,
                _KF.version == version,
                _KF.status.in_(("approved", "superseded")),
            )
            .order_by(_KF.slug)
        )

    async def get_by_id(self, file_id: UUID) -> KnowledgeFileRecord | None:
        """One row by its own id — the internal content read. The id
        names one exact version; the caller's pinned sha is the
        integrity check, so no status filter applies here."""

        rows = await self._rows(self._select().where(_KF.id == file_id).limit(1))
        return rows[0] if rows else None
