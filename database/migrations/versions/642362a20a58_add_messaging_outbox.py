"""add messaging outbox

Revision ID: 642362a20a58
Revises: 8f2e6a1b4c7d
Create Date: 2026-09-27 10:46:21.812612

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '642362a20a58'
down_revision: Union[str, Sequence[str], None] = '8f2e6a1b4c7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
    "CREATE SCHEMA IF NOT EXISTS messaging"
    )
    
    op.create_table(
    "outbox_messages",
    sa.Column(
        "id",
        sa.Uuid(),
        nullable=False,
    ),
    sa.Column(
        "topic",
        sa.String(length=200),
        nullable=False,
    ),
    sa.Column(
        "message_key",
        sa.String(length=200),
        nullable=False,
    ),
    sa.Column(
        "event_type",
        sa.String(length=100),
        nullable=False,
    ),
    sa.Column(
        "aggregate_type",
        sa.String(length=100),
        nullable=False,
    ),
    sa.Column(
        "aggregate_id",
        sa.Uuid(),
        nullable=False,
    ),
    sa.Column(
        "schema_version",
        sa.Integer(),
        server_default=sa.text("1"),
        nullable=False,
    ),
    sa.Column(
        "payload",
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    ),
    
    sa.Column(
        "status",
        sa.String(length=32),
        server_default=sa.text("'pending'"),
        nullable=False,
    ),
    sa.Column(
        "attempt_count",
        sa.Integer(),
        server_default=sa.text("0"),
        nullable=False,
    ),
    sa.Column(
        "last_error",
        sa.Text(),
        nullable=True,
    ),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    ),
    sa.Column(
        "published_at",
        sa.DateTime(timezone=True),
        nullable=True,
    ),
    sa.CheckConstraint(
        "status IN ('pending', 'published')",
        name="ck_outbox_messages_status_allowed",
    ),
    sa.CheckConstraint(
        "schema_version >= 1",
        name="ck_outbox_messages_schema_version_positive",
    ),
    sa.CheckConstraint(
        "attempt_count >= 0",
        name="ck_outbox_messages_attempt_count_nonnegative",
    ),
    sa.PrimaryKeyConstraint("id"),
    schema="messaging",
    )
    
    op.create_index(
    "ix_outbox_messages_aggregate_id",
    "outbox_messages",
    ["aggregate_id"],
    schema="messaging",
    )

    op.create_index(
        "ix_outbox_messages_pending",
        "outbox_messages",
        ["status", "created_at"],
        schema="messaging",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
    "ix_outbox_messages_pending",
    table_name="outbox_messages",
    schema="messaging",
    )

    op.drop_index(
    "ix_outbox_messages_aggregate_id",
    table_name="outbox_messages",
    schema="messaging",
    )

    op.drop_table(
        "outbox_messages",
        schema="messaging",
    )

    op.execute(
        "DROP SCHEMA IF EXISTS messaging"
    )
