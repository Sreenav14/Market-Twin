"""Add workspace knowledge ingestion entries.

Revision ID: b41d7c210a33
Revises: 9edac11ff95c
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b41d7c210a33"
down_revision: str | Sequence[str] | None = "9edac11ff95c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("blueprint_id", sa.Uuid(), nullable=False),
        sa.Column("asset_version_id", sa.Uuid(), nullable=False),
        sa.Column("preview", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "blueprint_id", "id"],
            [
                "knowledge.blueprint_versions.workspace_id",
                "knowledge.blueprint_versions.blueprint_id",
                "knowledge.blueprint_versions.id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "blueprint_id", "asset_version_id"],
            [
                "knowledge.asset_versions.workspace_id",
                "knowledge.asset_versions.blueprint_id",
                "knowledge.asset_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        schema="knowledge",
    )
    op.create_index(
        "ix_ingestion_entries_workspace_id",
        "ingestion_entries",
        ["workspace_id"],
        schema="knowledge",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ingestion_entries_workspace_id", table_name="ingestion_entries", schema="knowledge"
    )
    op.drop_table("ingestion_entries", schema="knowledge")
