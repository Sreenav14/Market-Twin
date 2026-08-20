"""SQLAlchemy models for reliable integration messaging."""

from datetime import datetime
from uuid import UUID

from markettwin_database import Base
from sqlalchemy import BigInteger, DateTime, Identity, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = {"schema": "integration"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)

    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(150), nullable=False)
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    message_key: Mapped[str | None] = mapped_column(String(200), nullable=True)

    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    headers: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"
    __table_args__ = {"schema": "integration"}

    consumer_name: Mapped[str] = mapped_column(String(150), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(200), primary_key=True)

    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    partition: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kafka_offset: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )