"""SQLAlchemy models for MarketTwin test planning."""

from datetime import datetime
from uuid import UUID, uuid4

from markettwin_database import Base
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_applications_status_allowed",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_applications_workspace_id_id",
        ),
        {"schema": "testing"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("core.workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("core.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default=text("'active'"),
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
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApplicationTarget(Base):
    __tablename__ = "application_targets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_application_targets_status_allowed",
        ),
        UniqueConstraint(
            "application_id",
            "id",
            name="uq_application_targets_application_id_id",
        ),
        {"schema": "testing"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("testing.applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    requires_auth: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default=text("'active'"),
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
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TargetAllowedOrigin(Base):
    __tablename__ = "target_allowed_origins"
    __table_args__ = (
        CheckConstraint(
            "scheme IN ('http', 'https')",
            name="ck_target_allowed_origins_scheme_allowed",
        ),
        CheckConstraint(
            "port IS NULL OR (port >= 1 AND port <= 65535)",
            name="ck_target_allowed_origins_port_range",
        ),
        Index(
            "uq_target_allowed_origins_scope",
            "target_id",
            "scheme",
            "hostname",
            "port",
            "include_subdomains",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        {"schema": "testing"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("testing.application_targets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scheme: Mapped[str] = mapped_column(String(16), nullable=False)
    hostname: Mapped[str] = mapped_column(String(253), nullable=False)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    include_subdomains: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TargetAuthorization(Base):
    __tablename__ = "target_authorizations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'authorized', 'revoked', 'expired')",
            name="ck_target_authorizations_status_allowed",
        ),
        {"schema": "testing"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    target_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("testing.application_targets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("core.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    authorized_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("core.users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    authorization_basis: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TestRun(Base):
    __tablename__ = "test_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('draft', 'planning', 'queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_test_runs_status_allowed",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "application_id"],
            ["testing.applications.workspace_id", "testing.applications.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["application_id", "target_id"],
            ["testing.application_targets.application_id", "testing.application_targets.id"],
            ondelete="RESTRICT",
        ),
        {"schema": "testing"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("core.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="draft",
        server_default=text("'draft'"),
    )
    target_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    configuration_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
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
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunPersona(Base):
    __tablename__ = "run_personas"
    __table_args__ = (
        CheckConstraint("ordinal >= 1", name="ck_run_personas_ordinal_positive"),
        UniqueConstraint("test_run_id", "ordinal", name="uq_run_personas_run_ordinal"),
        UniqueConstraint("test_run_id", "id", name="uq_run_personas_run_id"),
        {"schema": "testing"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    test_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("testing.test_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    attributes: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RunMission(Base):
    __tablename__ = "run_missions"
    __table_args__ = (
        CheckConstraint("ordinal >= 1", name="ck_run_missions_ordinal_positive"),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high')",
            name="ck_run_missions_priority_allowed",
        ),
        UniqueConstraint("test_run_id", "ordinal", name="uq_run_missions_run_ordinal"),
        UniqueConstraint("test_run_id", "id", name="uq_run_missions_run_id"),
        {"schema": "testing"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    test_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("testing.test_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    success_criteria: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PersonaJourney(Base):
    __tablename__ = "persona_journeys"
    __table_args__ = (
        CheckConstraint("ordinal >= 1", name="ck_persona_journeys_ordinal_positive"),
        ForeignKeyConstraint(
            ["test_run_id", "persona_id"],
            ["testing.run_personas.test_run_id", "testing.run_personas.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["test_run_id", "mission_id"],
            ["testing.run_missions.test_run_id", "testing.run_missions.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "test_run_id",
            "persona_id",
            "mission_id",
            name="uq_persona_journeys_combination",
        ),
        UniqueConstraint(
            "test_run_id",
            "ordinal",
            name="uq_persona_journeys_run_ordinal",
        ),
        UniqueConstraint(
            "test_run_id",
            "id",
            name="uq_persona_journeys_run_id",
        ),
        {"schema": "testing"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    test_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    persona_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    mission_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )