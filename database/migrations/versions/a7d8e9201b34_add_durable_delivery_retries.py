"""Retain and quarantine failing outbox messages and evaluations.

Revision ID: a7d8e9201b34
Revises: 9e3a24b17c60
"""

import sqlalchemy as sa
from alembic import op

revision = "a7d8e9201b34"
down_revision = "9e3a24b17c60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("next_attempt_at", "quarantined_at"):
        op.add_column(
            "outbox_events", sa.Column(name, sa.DateTime(timezone=True)), schema="integration"
        )
    op.create_index(
        "ix_outbox_pending_retry",
        "outbox_events",
        ["id", "next_attempt_at"],
        schema="integration",
        postgresql_where=sa.text("published_at IS NULL AND quarantined_at IS NULL"),
    )
    op.add_column(
        "test_runs",
        sa.Column("evaluation_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        schema="testing",
    )
    for name in ("evaluation_next_attempt_at", "evaluation_quarantined_at"):
        op.add_column("test_runs", sa.Column(name, sa.DateTime(timezone=True)), schema="testing")
    op.add_column("test_runs", sa.Column("evaluation_last_error", sa.Text()), schema="testing")


def downgrade() -> None:
    for name in (
        "evaluation_last_error",
        "evaluation_quarantined_at",
        "evaluation_next_attempt_at",
        "evaluation_attempts",
    ):
        op.drop_column("test_runs", name, schema="testing")
    op.drop_index("ix_outbox_pending_retry", table_name="outbox_events", schema="integration")
    for name in ("quarantined_at", "next_attempt_at"):
        op.drop_column("outbox_events", name, schema="integration")
