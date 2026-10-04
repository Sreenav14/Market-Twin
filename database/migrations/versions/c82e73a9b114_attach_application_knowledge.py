"""Attach reviewed knowledge sets to applications.

Revision ID: c82e73a9b114
Revises: b41d7c210a33
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c82e73a9b114"
down_revision: str | Sequence[str] | None = "b41d7c210a33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_ingestion_entries_workspace_id_id", "ingestion_entries", ["workspace_id", "id"],
        schema="knowledge",
    )
    op.create_table(
        "application_knowledge_entries",
        sa.Column("workspace_id", sa.Uuid(), primary_key=True),
        sa.Column("application_id", sa.Uuid(), primary_key=True),
        sa.Column("ingestion_entry_id", sa.Uuid(), primary_key=True),
        sa.Column("attached_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "application_id"],
            ["testing.applications.workspace_id", "testing.applications.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "ingestion_entry_id"],
            ["knowledge.ingestion_entries.workspace_id", "knowledge.ingestion_entries.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["attached_by_user_id"], ["core.users.id"], ondelete="RESTRICT"),
        schema="knowledge",
    )


def downgrade() -> None:
    op.drop_table("application_knowledge_entries", schema="knowledge")
    op.drop_constraint(
        "uq_ingestion_entries_workspace_id_id", "ingestion_entries", schema="knowledge"
    )
