"""SQLAlchemy model for MarketTwin user sessions."""

from datetime import datetime
from uuid import UUID, uuid4

from markettwin_database import Base
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column


class UserSession(Base):
    """A server-side authenticated MarketTwin browser session."""

    __tablename__ = "user_sessions"

    __table_args__ = (
        UniqueConstraint(
            "session_token_hash",
            name="uq_user_sessions_session_token_hash",
        ),
        CheckConstraint(
            "idle_expires_at <= absolute_expires_at",
            name="ck_user_sessions_expiration_order",
        ),
        ForeignKeyConstraint(
            ["user_id", "identity_id"],
            ["auth.user_identities.user_id", "auth.user_identities.id"],
            ondelete="CASCADE",
        ),
        {"schema": "auth"},
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    identity_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    session_token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    idle_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    absolute_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )