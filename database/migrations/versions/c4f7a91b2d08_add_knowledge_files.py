"""Add the knowledge files index (doc 33 section 3.4).

Revision ID: c4f7a91b2d08
Revises: a4c8e7d2b915
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4f7a91b2d08"
down_revision: str | Sequence[str] | None = "a4c8e7d2b915"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_files",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_entry_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="generated", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('generated', 'approved', 'superseded')",
            name="ck_knowledge_files_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_entry_id"],
            ["knowledge.ingestion_entries.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "ingestion_entry_id",
            "slug",
            "version",
            name="uq_knowledge_files_entry_slug_version",
        ),
        schema="knowledge",
    )
    op.create_index(
        "ix_knowledge_files_workspace_id",
        "knowledge_files",
        ["workspace_id"],
        schema="knowledge",
    )
    op.create_index(
        "ix_knowledge_files_entry",
        "knowledge_files",
        ["ingestion_entry_id"],
        schema="knowledge",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_files_entry", table_name="knowledge_files", schema="knowledge"
    )
    op.drop_index(
        "ix_knowledge_files_workspace_id",
        table_name="knowledge_files",
        schema="knowledge",
    )
    op.drop_table("knowledge_files", schema="knowledge")
