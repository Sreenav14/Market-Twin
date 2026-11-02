"""Persist worker readiness signals.

Revision ID: b3f8a24c910e
Revises: a7d8e9201b34
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b3f8a24c910e"
down_revision = "a7d8e9201b34"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("service", sa.String(64), primary_key=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        schema="integration",
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeats", schema="integration")
