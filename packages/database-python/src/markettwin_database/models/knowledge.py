"""SQLAlchemy models for MarketTwin product knowledge."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from markettwin_database.base import Base


class ProductBlueprint(Base):
    """Top-level container for one product's knowledge."""

    __tablename__ = "product_blueprints"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_product_blueprints_status_allowed",
        ),
        UniqueConstraint(
            "workspace_id",
            "name",
            name="uq_product_blueprints_workspace_name",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_product_blueprints_workspace_id_id",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "core.workspaces.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "core.users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default=text("'active'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class IngestionEntry(Base):
    """Generated knowledge awaiting review for one source-backed Blueprint Version."""

    __tablename__ = "ingestion_entries"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_ingestion_entries_workspace_id_id"),
        ForeignKeyConstraint(
            ["workspace_id", "blueprint_id", "id"],
            [
                "knowledge.blueprint_versions.workspace_id",
                "knowledge.blueprint_versions.blueprint_id",
                "knowledge.blueprint_versions.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "blueprint_id", "asset_version_id"],
            [
                "knowledge.asset_versions.workspace_id",
                "knowledge.asset_versions.blueprint_id",
                "knowledge.asset_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    blueprint_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    asset_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    preview: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    application_links: Mapped[list["ApplicationKnowledgeEntry"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class KnowledgeFile(Base):
    """Index row for one understood Markdown file (doc 33 §3.4).

    The file bytes in object storage are the truth; this row is how they
    are found. A retry writes a new version and supersedes the old one, so
    a run pinned to a version by sha is never mutated under it (OD-K3).
    """

    __tablename__ = "knowledge_files"
    __table_args__ = (
        CheckConstraint(
            "status IN ('generated', 'approved', 'superseded')",
            name="ck_knowledge_files_status_allowed",
        ),
        UniqueConstraint(
            "ingestion_entry_id",
            "slug",
            "version",
            name="uq_knowledge_files_entry_slug_version",
        ),
        Index("ix_knowledge_files_entry", "ingestion_entry_id"),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    ingestion_entry_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge.ingestion_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'generated'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ApplicationKnowledgeEntry(Base):
    """Attach a reviewed workspace knowledge set to an application."""

    __tablename__ = "application_knowledge_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "application_id"],
            ["testing.applications.workspace_id", "testing.applications.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "ingestion_entry_id"],
            ["knowledge.ingestion_entries.workspace_id", "knowledge.ingestion_entries.id"],
            ondelete="CASCADE",
        ),
        {"schema": "knowledge"},
    )
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    ingestion_entry_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    attached_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("core.users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BlueprintVersion(Base):
    """One versioned knowledge workspace for a Product Blueprint."""

    __tablename__ = "blueprint_versions"
    __table_args__ = (
        CheckConstraint(
            "version_number >= 1",
            name="ck_blueprint_versions_version_positive",
        ),
        CheckConstraint(
            "status IN ('draft', 'approved')",
            name="ck_blueprint_versions_status_allowed",
        ),
        CheckConstraint(
            "("
            "status = 'draft' "
            "AND approved_by_user_id IS NULL "
            "AND approved_at IS NULL"
            ") OR ("
            "status = 'approved' "
            "AND approved_by_user_id IS NOT NULL "
            "AND approved_at IS NOT NULL"
            ")",
            name="ck_blueprint_versions_approval_consistent",
        ),
        UniqueConstraint(
            "workspace_id",
            "blueprint_id",
            "id",
            name="uq_blueprint_versions_workspace_blueprint_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "blueprint_id",
            "version_number",
            name="uq_blueprint_versions_blueprint_version",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_blueprint_versions_workspace_id_id",
        ),
        ForeignKeyConstraint(
            [
                "workspace_id",
                "blueprint_id",
            ],
            [
                "knowledge.product_blueprints.workspace_id",
                "knowledge.product_blueprints.id",
            ],
            ondelete="CASCADE",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    blueprint_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="draft",
        server_default=text("'draft'"),
    )

    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "core.users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "core.users.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class SourceAsset(Base):
    """Logical source material belonging to a Product Blueprint."""

    __tablename__ = "source_assets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_source_assets_status_allowed",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_source_assets_workspace_id_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "blueprint_id",
            "id",
            name="uq_source_assets_workspace_blueprint_id",
        ),
        ForeignKeyConstraint(
            [
                "workspace_id",
                "blueprint_id",
            ],
            [
                "knowledge.product_blueprints.workspace_id",
                "knowledge.product_blueprints.id",
            ],
            ondelete="CASCADE",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    blueprint_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "core.users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default=text("'active'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AssetVersion(Base):
    """One immutable uploaded revision of a logical Source Asset."""

    __tablename__ = "asset_versions"
    __table_args__ = (
        CheckConstraint(
            "version_number >= 1",
            name="ck_asset_versions_version_positive",
        ),
        CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="ck_asset_versions_size_nonnegative",
        ),
        CheckConstraint(
            "storage_provider IN ('minio', 's3')",
            name="ck_asset_versions_storage_provider_allowed",
        ),
        CheckConstraint(
            "status IN ("
            "'created', "
            "'upload_pending', "
            "'uploaded', "
            "'quarantined', "
            "'validating', "
            "'validated', "
            "'processing', "
            "'extracted', "
            "'normalized', "
            "'included', "
            "'unsupported', "
            "'corrupted', "
            "'infected_or_suspicious', "
            "'password_protected', "
            "'too_large', "
            "'parsing_failed', "
            "'needs_role_confirmation', "
            "'needs_ocr', "
            "'needs_user_review', "
            "'excluded'"
            ")",
            name="ck_asset_versions_status_allowed",
        ),
        UniqueConstraint(
            "workspace_id",
            "source_asset_id",
            "version_number",
            name="uq_asset_versions_asset_version",
        ),
        UniqueConstraint(
            "workspace_id",
            "blueprint_id",
            "id",
            name="uq_asset_versions_workspace_blueprint_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "blueprint_id",
            "source_asset_id",
            "id",
            name="uq_asset_versions_source_asset_identity",
        ),
        UniqueConstraint(
            "storage_provider",
            "bucket",
            "object_key",
            name="uq_asset_versions_storage_location",
        ),
        ForeignKeyConstraint(
            [
                "workspace_id",
                "blueprint_id",
                "source_asset_id",
            ],
            [
                "knowledge.source_assets.workspace_id",
                "knowledge.source_assets.blueprint_id",
                "knowledge.source_assets.id",
            ],
            ondelete="CASCADE",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    blueprint_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    source_asset_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "core.users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    original_filename: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )

    declared_content_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    detected_content_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    storage_provider: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    bucket: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    object_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(48),
        nullable=False,
        default="created",
        server_default=text("'created'"),
    )

    status_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    uploaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class BlueprintVersionAsset(Base):
    """Pin one Source Asset revision into one Blueprint Version."""

    __tablename__ = "blueprint_version_assets"
    __table_args__ = (
        CheckConstraint(
            "cardinality(roles) >= 1",
            name="ck_blueprint_version_assets_roles_nonempty",
        ),
        CheckConstraint(
            "roles <@ ARRAY["
            "'demonstration', "
            "'product_knowledge', "
            "'business_rules', "
            "'safety_policy', "
            "'test_input', "
            "'ground_truth', "
            "'ui_reference', "
            "'persona_evidence', "
            "'environment_configuration'"
            "]::varchar[]",
            name="ck_blueprint_version_assets_roles_allowed",
        ),
        CheckConstraint(
            "("
            "roles_confirmed_by_user_id IS NULL "
            "AND roles_confirmed_at IS NULL"
            ") OR ("
            "roles_confirmed_by_user_id IS NOT NULL "
            "AND roles_confirmed_at IS NOT NULL"
            ")",
            name="ck_blueprint_version_assets_role_confirmation_consistent",
        ),
        UniqueConstraint(
            "workspace_id",
            "blueprint_version_id",
            "source_asset_id",
            name="uq_blueprint_version_assets_source",
        ),
        ForeignKeyConstraint(
            [
                "workspace_id",
                "blueprint_id",
                "blueprint_version_id",
            ],
            [
                "knowledge.blueprint_versions.workspace_id",
                "knowledge.blueprint_versions.blueprint_id",
                "knowledge.blueprint_versions.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [
                "workspace_id",
                "blueprint_id",
                "source_asset_id",
                "asset_version_id",
            ],
            [
                "knowledge.asset_versions.workspace_id",
                "knowledge.asset_versions.blueprint_id",
                "knowledge.asset_versions.source_asset_id",
                "knowledge.asset_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    blueprint_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    blueprint_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    source_asset_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    asset_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    roles: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
    )

    is_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    roles_confirmed_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "core.users.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    roles_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    
class EvidenceUnit(Base):
    """Canonical evidence extracted from one immutable AssetVersion."""

    __tablename__ = "evidence_units"
    __table_args__ = (
        CheckConstraint(
            "evidence_type IN ("
            "'text', "
            "'table', "
            "'image', "
            "'video_segment', "
            "'structured_data'"
            ")",
            name="ck_evidence_units_type_allowed",
        ),
        CheckConstraint(
            "content_text IS NOT NULL OR content_json IS NOT NULL",
            name="ck_evidence_units_content_present",
        ),
        UniqueConstraint(
            "workspace_id",
            "blueprint_id",
            "id",
            name="uq_evidence_units_workspace_blueprint_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "asset_version_id",
            "extractor_name",
            "extractor_version",
            "ordinal",
            name="uq_evidence_units_extraction_position",
        ),
        ForeignKeyConstraint(
            [
                "workspace_id",
                "blueprint_id",
                "asset_version_id",
            ],
            [
                "knowledge.asset_versions.workspace_id",
                "knowledge.asset_versions.blueprint_id",
                "knowledge.asset_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    blueprint_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    asset_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    evidence_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    ordinal: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    content_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    content_json: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    source_locator: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    extractor_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    extractor_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
class Skill(Base):
    """Stable product capability known by MarketTwin."""

    __tablename__ = "skills"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_skills_status_allowed",
        ),
        CheckConstraint(
            "skill_kind IN ('journey', 'platform', 'task')",
            name="ck_skills_skill_kind_allowed",
        ),
        Index(
            "uq_skills_graph_name",
            "workspace_id",
            "application_id",
            "target_id",
            "name",
            unique=True,
            postgresql_where=text("application_id IS NOT NULL"),
        ),
        UniqueConstraint(
            "workspace_id",
            "blueprint_id",
            "name",
            name="uq_skills_blueprint_name",
        ),
        UniqueConstraint(
            "workspace_id",
            "blueprint_id",
            "id",
            name="uq_skills_workspace_blueprint_id",
        ),
        ForeignKeyConstraint(
            [
                "workspace_id",
                "blueprint_id",
            ],
            [
                "knowledge.product_blueprints.workspace_id",
                "knowledge.product_blueprints.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            [
                "knowledge.app_maps.workspace_id",
                "knowledge.app_maps.id",
            ],
            ondelete="RESTRICT",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    blueprint_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )

    created_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "core.users.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default=text("'active'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    application_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    target_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    app_map_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    skill_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="journey",
        server_default=text("'journey'"),
    )

class SkillVersion(Base):
    """Versioned Skill definition grounded in one BlueprintVersion."""

    __tablename__ = "skill_versions"
    __table_args__ = (
        Index(
            "uq_skill_versions_one_active", "skill_id", unique=True,
            postgresql_where=text("lifecycle_status = 'active'"),
        ),
        CheckConstraint(
            "version_number >= 1",
            name="ck_skill_versions_version_positive",
        ),
        CheckConstraint(
            "status IN ('draft', 'approved')",
            name="ck_skill_versions_status_allowed",
        ),
        CheckConstraint(
            "grounding_confidence IS NULL OR "
            "grounding_confidence IN ('low', 'medium', 'high')",
            name="ck_skill_versions_grounding_confidence_allowed",
        ),
        CheckConstraint(
            "lifecycle_status IN ('draft', 'replay_verified', 'active', 'suspect', 'quarantined', 'retired')",
            name="ck_skill_versions_lifecycle_status_allowed",
        ),
        CheckConstraint(
            "last_replay_result IS NULL OR "
            "last_replay_result IN ('passed', 'failed')",
            name="ck_skill_versions_last_replay_result_allowed",
        ),
        CheckConstraint(
            "retired_reason IS NULL OR "
            "retired_reason IN ('superseded', 'journey_absent', 'owner', 'scope_removed')",
            name="ck_skill_versions_retired_reason_allowed",
        ),
        CheckConstraint(
            "("
            "status = 'draft' "
            "AND approved_by_user_id IS NULL "
            "AND approved_at IS NULL"
            ") OR ("
            "status = 'approved' "
            "AND approved_by_user_id IS NOT NULL "
            "AND approved_at IS NOT NULL"
            ")",
            name="ck_skill_versions_approval_consistent",
        ),
        UniqueConstraint(
            "workspace_id",
            "skill_id",
            "version_number",
            name="uq_skill_versions_skill_version",
        ),
        UniqueConstraint(
            "workspace_id",
            "blueprint_version_id",
            "skill_id",
            name="uq_skill_versions_blueprint_version_skill",
        ),
        UniqueConstraint(
            "workspace_id",
            "blueprint_id",
            "id",
            name="uq_skill_versions_workspace_blueprint_id",
        ),
        ForeignKeyConstraint(
            [
                "workspace_id",
                "blueprint_id",
                "skill_id",
            ],
            [
                "knowledge.skills.workspace_id",
                "knowledge.skills.blueprint_id",
                "knowledge.skills.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "workspace_id",
                "blueprint_id",
                "blueprint_version_id",
            ],
            [
                "knowledge.blueprint_versions.workspace_id",
                "knowledge.blueprint_versions.blueprint_id",
                "knowledge.blueprint_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            [
                "knowledge.app_maps.workspace_id",
                "knowledge.app_maps.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["heal_of_version_id"],
            ["knowledge.skill_versions.id"],
            ondelete="RESTRICT",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    blueprint_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )

    blueprint_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )

    skill_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="draft",
        server_default=text("'draft'"),
    )

    grounding_confidence: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    definition_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )

    generation_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    created_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "core.users.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "core.users.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    lifecycle_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="draft",
        server_default=text("'draft'"),
    )

    package: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    verified_fingerprint: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    last_replay_result: Mapped[str | None] = mapped_column(
        String(8),
        nullable=True,
    )

    last_replay_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    heal_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    app_map_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    heal_of_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    replay_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    retired_reason: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

class SkillEvidenceReference(Base):
    """Evidence grounding one SkillVersion."""

    __tablename__ = "skill_evidence_references"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "skill_version_id",
            "evidence_unit_id",
            name="uq_skill_evidence_reference",
        ),
        ForeignKeyConstraint(
            [
                "workspace_id",
                "blueprint_id",
                "skill_version_id",
            ],
            [
                "knowledge.skill_versions.workspace_id",
                "knowledge.skill_versions.blueprint_id",
                "knowledge.skill_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "workspace_id",
                "blueprint_id",
                "evidence_unit_id",
            ],
            [
                "knowledge.evidence_units.workspace_id",
                "knowledge.evidence_units.blueprint_id",
                "knowledge.evidence_units.id",
            ],
            ondelete="RESTRICT",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    blueprint_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    skill_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    evidence_unit_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class AppMap(Base):
    """One versioned application map built by the census for one target."""

    __tablename__ = "app_maps"
    __table_args__ = (
        CheckConstraint(
            "status IN ('building', 'ready', 'failed')",
            name="ck_app_maps_status_allowed",
        ),
        CheckConstraint(
            "release_state IN ('trusted', 'partial', 'failed')",
            name="ck_app_maps_release_state_allowed",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_app_maps_workspace_id_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "application_id",
            "target_id",
            "version_number",
            name="uq_app_maps_version",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "application_id"],
            [
                "testing.applications.workspace_id",
                "testing.applications.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["application_id", "target_id"],
            [
                "testing.application_targets.application_id",
                "testing.application_targets.id",
            ],
            ondelete="RESTRICT",
        ),
        Index(
            "uq_app_maps_single_flight",
            "application_id",
            "target_id",
            unique=True,
            postgresql_where=text("status = 'building'"),
        ),
        Index("ix_app_maps_poll", "status", "started_at"),
        CheckConstraint(
            "harvest_status IN ('not_started', 'building', 'ready', 'partial', 'failed')",
            name="ck_app_maps_harvest_status_allowed",
        ),
        Index(
            "uq_app_maps_harvest_single_flight",
            "application_id",
            "target_id",
            unique=True,
            postgresql_where=text("harvest_status = 'building'"),
        ),
        Index("ix_app_maps_harvest_poll", "harvest_status", "harvest_started_at"),
        CheckConstraint(
            "grounding_status IN ('not_started', 'building', 'ready', 'partial', 'failed')",
            name="ck_app_maps_grounding_status_allowed",
        ),
        Index(
            "uq_app_maps_grounding_single_flight",
            "application_id",
            "target_id",
            unique=True,
            postgresql_where=text("grounding_status = 'building'"),
        ),
        Index("ix_app_maps_grounding_poll", "grounding_status", "grounding_started_at"),
        CheckConstraint(
            "freshness_state IN ('unknown', 'current', 'stale')",
            name="ck_app_maps_freshness_state_allowed",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="building",
        server_default=text("'building'"),
    )

    release_state: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    release_scope: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    base_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    builder_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="census-1a.1",
        server_default=text("'census-1a.1'"),
    )

    census_config: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    census_metrics: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    pattern_stats: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    gate_metrics: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    census_expected_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    census_reachable_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    mapping_spend_calls: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    mapping_spend_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    mapping_spend_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default=text("0"),
    )

    mapping_budget_calls: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    failure_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    failure_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    failure_site: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    harvest_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="not_started",
        server_default=text("'not_started'"),
    )

    harvest_metrics: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    harvest_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    harvest_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    harvest_failure_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    harvest_failure_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    harvest_failure_site: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    mapping_budget_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    grounding_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="not_started",
        server_default=text("'not_started'"),
    )

    grounding_metrics: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    grounding_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    grounding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    grounding_failure_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    grounding_failure_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    grounding_failure_site: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    freshness_state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="unknown",
        server_default=text("'unknown'"),
    )

    last_preflight_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    freshness_metrics: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

class MapPage(Base):
    """One denominator URL of an application map, with its census disposition."""

    __tablename__ = "map_pages"
    __table_args__ = (
        CheckConstraint(
            "crawl_status IN ('fetch_ok', 'redirect', 'blocked_auth', 'blocked_wall', "
            "'gone', 'fetch_error', 'out_of_scope', 'census_incomplete')",
            name="ck_map_pages_crawl_status_allowed",
        ),
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="ck_map_pages_confidence_allowed",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_map_pages_workspace_id_id",
        ),
        UniqueConstraint(
            "app_map_id",
            "canonical_url",
            name="uq_map_pages_canonical",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            [
                "knowledge.app_maps.workspace_id",
                "knowledge.app_maps.id",
            ],
            ondelete="RESTRICT",
        ),
        Index("ix_map_pages_status", "app_map_id", "crawl_status"),
        Index("ix_map_pages_pattern", "app_map_id", "route_pattern"),
        CheckConstraint(
            "harvest_status IN ('pending', 'visited', 'blocked_auth', 'blocked_wall', "
            "'failed', 'unprobed_budget')",
            name="ck_map_pages_harvest_status_allowed",
        ),
        CheckConstraint(
            "purpose_source IS NULL OR purpose_source IN "
            "('documentation', 'owner-rule', 'observation', 'model-draft')",
            name="ck_map_pages_purpose_source_allowed",
        ),
        Index("ix_map_pages_harvest", "app_map_id", "harvest_status"),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    app_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    canonical_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    route_pattern: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    source_kinds: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
    )

    crawl_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="census_incomplete",
        server_default=text("'census_incomplete'"),
    )

    http_status: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    redirect_target: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    content_type: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    title: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    html_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    requires_auth: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    roles_seen: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="census",
        server_default=text("'census'"),
    )

    confidence: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="low",
        server_default=text("'low'"),
    )

    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    harvest_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )

    template_group: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    purpose: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    purpose_source: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

class MapPageState(Base):
    """One state slot of a map page; the census creates exactly one default."""

    __tablename__ = "map_page_states"
    __table_args__ = (
        CheckConstraint(
            "state_kind IN ('default', 'observed')",
            name="ck_map_page_states_state_kind_allowed",
        ),
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="ck_map_page_states_confidence_allowed",
        ),
        UniqueConstraint(
            "map_page_id",
            "state_key",
            name="uq_map_page_states_key",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            [
                "knowledge.app_maps.workspace_id",
                "knowledge.app_maps.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "map_page_id"],
            [
                "knowledge.map_pages.workspace_id",
                "knowledge.map_pages.id",
            ],
            ondelete="RESTRICT",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    app_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    map_page_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    state_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    state_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="default",
        server_default=text("'default'"),
    )

    state_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    element_signature: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    form_signature: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="census",
        server_default=text("'census'"),
    )

    confidence: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="low",
        server_default=text("'low'"),
    )

    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    dom_structure_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    aria_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    screenshot_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    screenshot_phash: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )


class MapElement(Base):
    """One element observed in one harvested page state (Phase 1b)."""

    __tablename__ = "map_elements"
    __table_args__ = (
        CheckConstraint(
            "actionability IN ('click', 'fill', 'select', 'check', 'press', 'toggle', 'readonly')",
            name="ck_map_elements_actionability_allowed",
        ),
        CheckConstraint(
            "safety_class IN ('read', 'reversible', 'irreversible', 'unknown')",
            name="ck_map_elements_safety_class_allowed",
        ),
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="ck_map_elements_confidence_allowed",
        ),
        UniqueConstraint(
            "map_page_state_id",
            "role",
            "name",
            "ordinal",
            name="uq_map_elements_identity",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            [
                "knowledge.app_maps.workspace_id",
                "knowledge.app_maps.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "map_page_id"],
            [
                "knowledge.map_pages.workspace_id",
                "knowledge.map_pages.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["map_page_state_id"],
            ["knowledge.map_page_states.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_map_elements_map_page", "app_map_id", "map_page_id"),
        Index("ix_map_elements_state", "map_page_state_id"),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    app_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    map_page_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    map_page_state_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    ordinal: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    label_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    actionability: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    locators: Mapped[list[object]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    safety_class: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    navigates_to_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    opens_state_key: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="harvest",
        server_default=text("'harvest'"),
    )

    confidence: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="low",
        server_default=text("'low'"),
    )

    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class MapTransition(Base):
    """One observed state-to-state action in the graph (Phase 1b)."""

    __tablename__ = "map_transitions"
    __table_args__ = (
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="ck_map_transitions_confidence_allowed",
        ),
        UniqueConstraint(
            "from_state_id",
            "via_element_id",
            "to_state_id",
            name="uq_map_transitions_edge",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            [
                "knowledge.app_maps.workspace_id",
                "knowledge.app_maps.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["from_state_id"],
            ["knowledge.map_page_states.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["to_state_id"],
            ["knowledge.map_page_states.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["via_element_id"],
            ["knowledge.map_elements.id"],
            ondelete="RESTRICT",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    app_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    from_state_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    to_state_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    via_element_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    via_action: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    observed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="harvest",
        server_default=text("'harvest'"),
    )

    confidence: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="low",
        server_default=text("'low'"),
    )

    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class MapForm(Base):
    """One form observed in one harvested page state (Phase 1b)."""

    __tablename__ = "map_forms"
    __table_args__ = (
        CheckConstraint(
            "probe_status IN ('unprobed_readonly', 'unprobed_destructive', 'probed')",
            name="ck_map_forms_probe_status_allowed",
        ),
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="ck_map_forms_confidence_allowed",
        ),
        UniqueConstraint(
            "map_page_state_id",
            "form_key",
            name="uq_map_forms_key",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            [
                "knowledge.app_maps.workspace_id",
                "knowledge.app_maps.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "map_page_id"],
            [
                "knowledge.map_pages.workspace_id",
                "knowledge.map_pages.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["map_page_state_id"],
            ["knowledge.map_page_states.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["submit_element_id"],
            ["knowledge.map_elements.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["success_transition_id"],
            ["knowledge.map_transitions.id"],
            ondelete="RESTRICT",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    app_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    map_page_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    map_page_state_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    form_key: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    method: Mapped[str | None] = mapped_column(
        String(8),
        nullable=True,
    )

    action_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    submit_element_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    success_transition_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    probe_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unprobed_readonly",
        server_default=text("'unprobed_readonly'"),
    )

    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="harvest",
        server_default=text("'harvest'"),
    )

    confidence: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="low",
        server_default=text("'low'"),
    )

    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class MapField(Base):
    """One field of a harvested form (Phase 1b)."""

    __tablename__ = "map_fields"
    __table_args__ = (
        CheckConstraint(
            "validation_source IN ('dom', 'probed', 'doc')",
            name="ck_map_fields_validation_source_allowed",
        ),
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="ck_map_fields_confidence_allowed",
        ),
        UniqueConstraint(
            "form_id",
            "ordinal",
            name="uq_map_fields_ordinal",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            [
                "knowledge.app_maps.workspace_id",
                "knowledge.app_maps.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["form_id"],
            ["knowledge.map_forms.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["element_id"],
            ["knowledge.map_elements.id"],
            ondelete="RESTRICT",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    app_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    form_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    element_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    label: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    field_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    name_attr: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    constraints: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    options: Mapped[list[object]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    help_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    error_text_observed: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    validation_source: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="dom",
        server_default=text("'dom'"),
    )

    ordinal: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="harvest",
        server_default=text("'harvest'"),
    )

    confidence: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="low",
        server_default=text("'low'"),
    )

    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class MapJourney(Base):
    """A named state sequence assembled from the graph (Phase 1b)."""

    __tablename__ = "map_journeys"
    __table_args__ = (
        CheckConstraint(
            "selection IN ('rule', 'owner')",
            name="ck_map_journeys_selection_allowed",
        ),
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="ck_map_journeys_confidence_allowed",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            [
                "knowledge.app_maps.workspace_id",
                "knowledge.app_maps.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["success_state_id"],
            ["knowledge.map_page_states.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["skill_id"],
            ["knowledge.skills.id"],
            ondelete="RESTRICT",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    app_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    intent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    preconditions: Mapped[list[object]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    steps: Mapped[list[object]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    success_state_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    skill_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    selection: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
    )

    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="harvest",
        server_default=text("'harvest'"),
    )

    confidence: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="low",
        server_default=text("'low'"),
    )

    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class MapExpectation(Base):
    """An expectation over the graph; authored in Phase 2, never in 1b."""

    __tablename__ = "map_expectations"
    __table_args__ = (
        CheckConstraint(
            "subject_kind IN ('page', 'element', 'journey', 'field', 'form')",
            name="ck_map_expectations_subject_kind_allowed",
        ),
        CheckConstraint(
            "oracle_source IN ('documentation', 'owner-rule', 'observation', 'model-draft')",
            name="ck_map_expectations_oracle_source_allowed",
        ),
        CheckConstraint(
            "status IN ('unverified', 'replay-verified', 'conflicted', 'owner-confirmed')",
            name="ck_map_expectations_status_allowed",
        ),
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="ck_map_expectations_confidence_allowed",
        ),
        CheckConstraint(
            "last_check_result IS NULL OR "
            "last_check_result IN ('passed', 'failed')",
            name="ck_map_expectations_last_check_result_allowed",
        ),
        CheckConstraint(
            "assertion_kind IS NULL OR assertion_kind IN "
            "('element_state', 'navigation', 'page_text', 'journey_terminal', "
            "'field_validation')",
            name="ck_map_expectations_assertion_kind_allowed",
        ),
        CheckConstraint(
            "assertion_origin IS NULL OR assertion_origin IN "
            "('deterministic', 'model-drafted', 'owner-entered')",
            name="ck_map_expectations_assertion_origin_allowed",
        ),
        Index(
            "ix_map_expectations_seeding", "app_map_id", "oracle_source", "status"
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            [
                "knowledge.app_maps.workspace_id",
                "knowledge.app_maps.id",
            ],
            ondelete="RESTRICT",
        ),
        Index("ix_map_expectations_subject", "app_map_id", "subject_kind", "subject_id"),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    app_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    subject_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    subject_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    statement: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    oracle_source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    source_ref: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    confidence: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="low",
        server_default=text("'low'"),
    )

    assertion: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    assertion_kind: Mapped[str | None] = mapped_column(
        String(24),
        nullable=True,
    )

    assertion_origin: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    promoted_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    superseded_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "knowledge.map_expectations.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_check_result: Mapped[str | None] = mapped_column(
        String(8),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class MapConflict(Base):
    """A recorded doc-vs-app conflict; workflow arrives in Phase 2."""

    __tablename__ = "map_conflicts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'resolved')",
            name="ck_map_conflicts_status_allowed",
        ),
        CheckConstraint(
            "resolution IS NULL OR resolution IN ('docs-win', 'app-win', 'owner-decided')",
            name="ck_map_conflicts_resolution_allowed",
        ),
        CheckConstraint(
            "conflict_kind IN "
            "('statement_vs_observation', 'oracle_check_failed', "
            "'navigation_mismatch')",
            name="ck_map_conflicts_kind_allowed",
        ),
        CheckConstraint(
            "detection_source IN ('grounding', 'verification', 'run')",
            name="ck_map_conflicts_detection_source_allowed",
        ),
        Index("ix_map_conflicts_open", "app_map_id", "status"),
        ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            [
                "knowledge.app_maps.workspace_id",
                "knowledge.app_maps.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["expectation_id"],
            ["knowledge.map_expectations.id"],
            ondelete="RESTRICT",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    app_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    expectation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    observed_behaviour: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    conflict_kind: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="statement_vs_observation",
        server_default=text("'statement_vs_observation'"),
    )

    detection_source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="grounding",
        server_default=text("'grounding'"),
    )

    observed_subject_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    evidence_refs: Mapped[list[object]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    status: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="open",
        server_default=text("'open'"),
    )

    resolution: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    decided_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class MapEvidenceObject(Base):
    """The Layer-0 index: one row per stored capture object (Phase 1b)."""

    __tablename__ = "map_evidence_objects"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('aria_snapshot', 'element_inventory', 'form_inventory', 'harvest_har', "
            "'screenshot', 'console_log', 'transition_log')",
            name="ck_map_evidence_objects_kind_allowed",
        ),
        CheckConstraint(
            "redaction_status IN ('redacted', 'not_applicable', 'dropped')",
            name="ck_map_evidence_objects_redaction_status_allowed",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            [
                "knowledge.app_maps.workspace_id",
                "knowledge.app_maps.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "map_page_id"],
            [
                "knowledge.map_pages.workspace_id",
                "knowledge.map_pages.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["map_page_state_id"],
            ["knowledge.map_page_states.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_map_evidence_objects_page_kind", "app_map_id", "map_page_id", "kind"),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    app_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    map_page_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    map_page_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    kind: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
    )

    viewport: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    object_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    byte_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    redaction_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    redaction_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SkillReplay(Base):
    """One replay attempt of a compiled skill version (Phase 1b)."""

    __tablename__ = "skill_replays"
    __table_args__ = (
        CheckConstraint(
            "result IN ('passed', 'failed')",
            name="ck_skill_replays_result_allowed",
        ),
        ForeignKeyConstraint(
            ["skill_version_id"],
            ["knowledge.skill_versions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["app_map_id"],
            ["knowledge.app_maps.id"],
            ondelete="RESTRICT",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    skill_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    app_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    result: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
    )

    failure_step: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    failure_site: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    heal_cycle: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    context_kind: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="clean",
        server_default=text("'clean'"),
    )

    model_calls: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    board_item_ref: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )



class SkillUsageEvent(Base):
    """One entry in a skill's append-only usage/lifecycle ledger (Phase 3)."""

    __tablename__ = "skill_usage_events"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('compile', 'verification_replay', 'run_replay', "
            "'heal_attempt', 'heal_diagnosis', 'activation', 'demotion', "
            "'quarantine', 'retirement')",
            name="ck_skill_usage_events_kind_allowed",
        ),
        CheckConstraint(
            "result IS NULL OR "
            "result IN ('passed', 'failed', 'applied', 'refused')",
            name="ck_skill_usage_events_result_allowed",
        ),
        ForeignKeyConstraint(
            ["skill_id"],
            ["knowledge.skills.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["skill_version_id"],
            ["knowledge.skill_versions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["app_map_id"],
            ["knowledge.app_maps.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_skill_usage_events_skill_created", "skill_id", "created_at"),
        Index("ix_skill_usage_events_version_kind", "skill_version_id", "kind"),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    skill_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    skill_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    app_map_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    job_ref: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
    )
    from_status: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    to_status: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    model_calls: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    model_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    result: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

class MapHarvestEvent(Base):
    """The harvest job's event log: watchdog heartbeat + audit trail."""

    __tablename__ = "map_harvest_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["app_map_id"],
            ["knowledge.app_maps.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_map_harvest_events_map_occurred", "app_map_id", "occurred_at"),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    app_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MapExpectationEvent(Base):
    """One entry in an expectation's append-only history (Phase 2).

    Written by the grounding job, the promotion/rejection endpoints and
    Board checks; never updated or deleted. ``oracle_source`` history is
    provable from these rows (an expectation's source never changes --
    supersession writes a NEW expectation plus a ``superseded`` event
    on the old one).
    """

    __tablename__ = "map_expectation_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('authored', 'matched', 'adjudicated', 'promoted', "
            "'rejected', 'conflicted', 'resolved', 'superseded', 'checked', "
            "'refused_non_verdict')",
            name="ck_map_expectation_events_type_allowed",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            [
                "knowledge.app_maps.workspace_id",
                "knowledge.app_maps.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["expectation_id"],
            ["knowledge.map_expectations.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_map_expectation_events_expectation", "expectation_id", "occurred_at"),
        Index("ix_map_expectation_events_map_occurred", "app_map_id", "occurred_at"),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    app_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    expectation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(48),
        nullable=False,
    )

    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class GraphAuditReport(Base):
    """One read-only graph audit report (Phase 2, evaluation worker).

    INSERT-only: the audit proves the graph byte-identical before and
    after its own run via ``graph_fingerprint`` and never writes to any
    graph table.
    """

    __tablename__ = "graph_audit_reports"
    __table_args__ = (
        CheckConstraint(
            "audit_kind IN ('scheduled', 'post_gate', 'on_demand')",
            name="ck_graph_audit_reports_kind_allowed",
        ),
        ForeignKeyConstraint(
            ["app_map_id"],
            ["knowledge.app_maps.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_graph_audit_reports_map_created", "app_map_id", "created_at"),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    application_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    target_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    app_map_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    audit_kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    checks: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    findings: Mapped[list[object]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    graph_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MapPreflight(Base):
    """One freshness preflight job (Phase 4, doc 23 section 5.2).

    The job record for a sweep of one map version: created by run
    creation (``trigger='run_creation'``) or the manual endpoint and
    executed by the orchestrator's freshness poller. Terminal in
    ``ready`` / ``partial`` / ``failed``. ``resulting_map_id`` names
    the reconciled successor when one was minted; the swept version's
    own rows are never edited beyond the section 5.4 list.
    """

    __tablename__ = "map_preflights"
    __table_args__ = (
        CheckConstraint(
            "trigger IN ('run_creation', 'manual')",
            name="ck_map_preflights_trigger_allowed",
        ),
        CheckConstraint(
            "status IN ('building', 'ready', 'partial', 'failed')",
            name="ck_map_preflights_status_allowed",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            [
                "knowledge.app_maps.workspace_id",
                "knowledge.app_maps.id",
            ],
            ondelete="RESTRICT",
        ),
        Index(
            "uq_map_preflights_single_flight",
            "app_map_id",
            unique=True,
            postgresql_where=text("status = 'building'"),
        ),
        Index("ix_map_preflights_poll", "status", "started_at"),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    app_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    resulting_map_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    trigger: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="building",
        server_default=text("'building'"),
    )

    config: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    outcome: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    deferred: Mapped[list[object]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    tier_counts: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    spend_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default=text("0"),
    )

    failure_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    failure_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    failure_site: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class MapPreflightEvent(Base):
    """The preflight job's event log: watchdog heartbeat + audit trail."""

    __tablename__ = "map_preflight_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["preflight_id"],
            ["knowledge.map_preflights.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_map_preflight_events_preflight_occurred", "preflight_id", "occurred_at"),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    preflight_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MapFingerprintHistory(Base):
    """One fingerprint observation of one page state (doc 23 section 5.3).

    Append-only (C9): rows are written by harvest completion, preflight
    tier-2 verification and reconcile re-observation, and never updated
    or deleted, so a page's fingerprint history reads across versions.
    ``map_page_state_id`` is NULL for page-grade observations on
    unharvested maps.
    """

    __tablename__ = "map_fingerprint_history"
    __table_args__ = (
        CheckConstraint(
            "source IN ('harvest', 'preflight', 'reconcile')",
            name="ck_map_fingerprint_history_source_allowed",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            [
                "knowledge.app_maps.workspace_id",
                "knowledge.app_maps.id",
            ],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_map_fingerprint_history_page",
            "application_id",
            "target_id",
            "canonical_url",
            "state_key",
            "observed_at",
        ),
        {
            "schema": "knowledge",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    app_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    map_page_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )

    map_page_state_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    canonical_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    state_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    state_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    dom_structure_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    aria_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    screenshot_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    screenshot_phash: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )

    html_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    preflight_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
