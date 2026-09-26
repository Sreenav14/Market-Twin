"""add agent runtime snapshots

Revision ID: 8f2e6a1b4c7d
Revises: c3c4b1273287
Create Date: 2026-09-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8f2e6a1b4c7d"
down_revision: str | Sequence[str] | None = "c3c4b1273287"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create execution.agent_runtime_snapshots."""

    op.create_table(
        "agent_runtime_snapshots",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "test_run_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "journey_id",
            sa.Uuid(),
            nullable=True,
        ),
        sa.Column(
            "execution_id",
            sa.Uuid(),
            nullable=True,
        ),
        sa.Column(
            "agent_role",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "runtime_kind",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "runtime_agent_name",
            sa.String(length=200),
            nullable=True,
        ),
        sa.Column(
            "agent_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_schema_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            sa.String(length=200),
            nullable=True,
        ),
        sa.Column(
            "template_version",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "model_provider",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "model_name",
            sa.String(length=200),
            nullable=True,
        ),
        sa.Column(
            "model_configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "base_instruction",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "effective_instruction",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "runtime_prompt",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "persona_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "mission_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "success_criteria",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "tools",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "policy_references",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "observability_backend",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "trace_id",
            sa.String(length=128),
            nullable=True,
        ),
        sa.Column(
            "snapshot_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "agent_role IN ('meta', 'persona', 'visual_verifier')",
            name="ck_agent_runtime_snapshots_role_allowed",
        ),
        sa.CheckConstraint(
            "agent_version >= 1",
            name="ck_agent_runtime_snapshots_agent_version_positive",
        ),
        sa.CheckConstraint(
            "snapshot_schema_version >= 1",
            name="ck_agent_runtime_snapshots_schema_version_positive",
        ),
        sa.CheckConstraint(
            "execution_id IS NULL OR journey_id IS NOT NULL",
            name="ck_agent_runtime_snapshots_execution_requires_journey",
        ),
        sa.ForeignKeyConstraint(
            ["test_run_id"],
            ["testing.test_runs.id"],
            name=op.f(
                "fk_agent_runtime_snapshots_test_run_id_test_runs"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["test_run_id", "journey_id"],
            [
                "testing.persona_journeys.test_run_id",
                "testing.persona_journeys.id",
            ],
            name="fk_agent_runtime_snapshots_run_journey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id", "journey_id"],
            [
                "execution.agent_executions.id",
                "execution.agent_executions.journey_id",
            ],
            name="fk_agent_runtime_snapshots_execution_journey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_agent_runtime_snapshots"),
        ),
        schema="execution",
    )

    op.create_index(
        op.f("ix_agent_runtime_snapshots_test_run_id"),
        "agent_runtime_snapshots",
        ["test_run_id"],
        unique=False,
        schema="execution",
    )

    op.create_index(
        op.f("ix_agent_runtime_snapshots_journey_id"),
        "agent_runtime_snapshots",
        ["journey_id"],
        unique=False,
        schema="execution",
    )

    op.create_index(
        op.f("ix_agent_runtime_snapshots_execution_id"),
        "agent_runtime_snapshots",
        ["execution_id"],
        unique=False,
        schema="execution",
    )

    op.create_index(
        op.f("ix_agent_runtime_snapshots_agent_role"),
        "agent_runtime_snapshots",
        ["agent_role"],
        unique=False,
        schema="execution",
    )

    op.create_index(
        op.f("ix_agent_runtime_snapshots_snapshot_sha256"),
        "agent_runtime_snapshots",
        ["snapshot_sha256"],
        unique=False,
        schema="execution",
    )


def downgrade() -> None:
    """Drop execution.agent_runtime_snapshots."""

    op.drop_index(
        op.f("ix_agent_runtime_snapshots_snapshot_sha256"),
        table_name="agent_runtime_snapshots",
        schema="execution",
    )

    op.drop_index(
        op.f("ix_agent_runtime_snapshots_agent_role"),
        table_name="agent_runtime_snapshots",
        schema="execution",
    )

    op.drop_index(
        op.f("ix_agent_runtime_snapshots_execution_id"),
        table_name="agent_runtime_snapshots",
        schema="execution",
    )

    op.drop_index(
        op.f("ix_agent_runtime_snapshots_journey_id"),
        table_name="agent_runtime_snapshots",
        schema="execution",
    )

    op.drop_index(
        op.f("ix_agent_runtime_snapshots_test_run_id"),
        table_name="agent_runtime_snapshots",
        schema="execution",
    )

    op.drop_table(
        "agent_runtime_snapshots",
        schema="execution",
    )