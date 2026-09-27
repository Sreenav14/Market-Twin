"""Database models for durable message delivery."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from markettwin_database.base import Base


class OutboxMessage(Base):
    """Message waiting to be published to an external broker."""

    __tablename__ = "outbox_messages"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'published')",
            name="ck_outbox_messages_status_allowed",
        ),
        CheckConstraint(
            "schema_version >= 1",
            name="ck_outbox_messages_schema_version_positive",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_outbox_messages_attempt_count_nonnegative",
        ),
        Index(
            "ix_outbox_messages_pending",
            "status",
            "created_at",
        ),
        {"schema": "messaging"},
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    topic: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    message_key: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    aggregate_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    aggregate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    schema_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )