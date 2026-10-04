"""SQLAlchemy models for MarketTwin product knowledge."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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

class SkillVersion(Base):
    """Versioned Skill definition grounded in one BlueprintVersion."""

    __tablename__ = "skill_versions"
    __table_args__ = (
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
