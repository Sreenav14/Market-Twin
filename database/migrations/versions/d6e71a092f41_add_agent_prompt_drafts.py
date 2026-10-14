"""Save user prompt edits separately from immutable runtime snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d6e71a092f41"
down_revision: str | Sequence[str] | None = "c82e73a9b114"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_prompt_drafts",
        sa.Column("snapshot_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("prompt_yaml", sa.Text(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["execution.agent_runtime_snapshots.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["core.users.id"], ondelete="CASCADE"),
        schema="execution",
    )


def downgrade() -> None:
    op.drop_table("agent_prompt_drafts", schema="execution")
