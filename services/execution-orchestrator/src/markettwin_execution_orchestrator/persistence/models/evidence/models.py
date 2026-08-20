"""SQLAlchemy models for MarketTwin evidence metadata."""

from datetime import datetime
from uuid import UUID, uuid4

from markettwin_database import Base
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint(
            "artifact_type IN "
            "('screenshot', 'html', 'trace', 'video', 'network_log', "
            "'console_log', 'other')",
            name="ck_artifacts_type_allowed",
        ),
        CheckConstraint(
            "storage_provider IN ('minio', 's3')",
            name="ck_artifacts_storage_provider_allowed",
        ),
        CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="ck_artifacts_size_nonnegative",
        ),
        ForeignKeyConstraint(
            ["execution_id", "step_id"],
            ["execution.execution_steps.execution_id", "execution.execution_steps.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "storage_provider",
            "bucket",
            "object_key",
            name="uq_artifacts_storage_location",
        ),
        {"schema": "evidence"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

    execution_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("execution.agent_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    step_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)

    storage_provider: Mapped[str] = mapped_column(String(16), nullable=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)

    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    metadata_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )