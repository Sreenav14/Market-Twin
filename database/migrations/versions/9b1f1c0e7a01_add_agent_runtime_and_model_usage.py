"""add agent runtime snapshots and model invocation telemetry

Revision ID: 9b1f1c0e7a01
Revises: c3c4b1273287
Create Date: 2026-09-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9b1f1c0e7a01"
down_revision: str | Sequence[str] | None = "c3c4b1273287"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create immutable agent snapshots and call-level model telemetry."""

    op.create_table(
        "agent_runtime_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("test_run_id", sa.Uuid(), nullable=False),
        sa.Column("journey_id", sa.Uuid(), nullable=True),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("agent_role", sa.String(length=32), nullable=False),
        sa.Column("runtime_agent_name", sa.String(length=200), nullable=False),
        sa.Column("runtime_kind", sa.String(length=64), nullable=False),
        sa.Column("agent_version", sa.String(length=32), nullable=False),
        sa.Column("snapshot_schema_version", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.String(length=100), nullable=True),
        sa.Column("template_version", sa.String(length=32), nullable=True),
        sa.Column("model_provider", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column(
            "model_configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("base_instruction", sa.Text(), nullable=True),
        sa.Column("effective_instruction", sa.Text(), nullable=True),
        sa.Column("runtime_prompt", sa.Text(), nullable=True),
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
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
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
            "snapshot_schema_version >= 1",
            name="ck_agent_runtime_snapshots_schema_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["execution.agent_executions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["journey_id"],
            ["testing.persona_journeys.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["test_run_id"],
            ["testing.test_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="execution",
    )
    op.create_index(
        "ix_agent_runtime_snapshots_test_run_id",
        "agent_runtime_snapshots",
        ["test_run_id"],
        schema="execution",
    )
    op.create_index(
        "ix_agent_runtime_snapshots_journey_id",
        "agent_runtime_snapshots",
        ["journey_id"],
        schema="execution",
    )
    op.create_index(
        "ix_agent_runtime_snapshots_execution_id",
        "agent_runtime_snapshots",
        ["execution_id"],
        schema="execution",
    )
    op.create_index(
        "ix_agent_runtime_snapshots_snapshot_sha256",
        "agent_runtime_snapshots",
        ["snapshot_sha256"],
        schema="execution",
    )

    op.create_table(
        "model_invocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("test_run_id", sa.Uuid(), nullable=False),
        sa.Column("journey_id", sa.Uuid(), nullable=True),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("agent_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("agent_role", sa.String(length=32), nullable=False),
        sa.Column("runtime_agent_name", sa.String(length=200), nullable=True),
        sa.Column("runtime_invocation_id", sa.String(length=200), nullable=True),
        sa.Column("invocation_sequence", sa.Integer(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("model_provider", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column("model_version", sa.String(length=200), nullable=True),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "usage_status",
            sa.String(length=32),
            server_default=sa.text("'unavailable'"),
            nullable=False,
        ),
        sa.Column("input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("cached_input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("output_tokens", sa.BigInteger(), nullable=True),
        sa.Column("reasoning_tokens", sa.BigInteger(), nullable=True),
        sa.Column("tool_input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("provider_total_tokens", sa.BigInteger(), nullable=True),
        sa.Column("request_size_estimate", sa.BigInteger(), nullable=True),
        sa.Column("latency_ms", sa.BigInteger(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "agent_role IN ('meta', 'persona', 'visual_verifier')",
            name="ck_model_invocations_role_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('started', 'completed', 'failed', 'rate_limited', 'cancelled')",
            name="ck_model_invocations_status_allowed",
        ),
        sa.CheckConstraint(
            "usage_status IN ('reported', 'partial', 'unavailable')",
            name="ck_model_invocations_usage_status_allowed",
        ),
        sa.CheckConstraint(
            "invocation_sequence IS NULL OR invocation_sequence >= 1",
            name="ck_model_invocations_sequence_positive",
        ),
        sa.CheckConstraint(
            "attempt_number >= 1",
            name="ck_model_invocations_attempt_positive",
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_model_invocations_input_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "cached_input_tokens IS NULL OR cached_input_tokens >= 0",
            name="ck_model_invocations_cached_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_model_invocations_output_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "reasoning_tokens IS NULL OR reasoning_tokens >= 0",
            name="ck_model_invocations_reasoning_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "tool_input_tokens IS NULL OR tool_input_tokens >= 0",
            name="ck_model_invocations_tool_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "provider_total_tokens IS NULL OR provider_total_tokens >= 0",
            name="ck_model_invocations_total_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "request_size_estimate IS NULL OR request_size_estimate >= 0",
            name="ck_model_invocations_request_size_nonnegative",
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_model_invocations_latency_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["agent_snapshot_id"],
            ["execution.agent_runtime_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["execution.agent_executions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["journey_id"],
            ["testing.persona_journeys.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["test_run_id"],
            ["testing.test_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="execution",
    )
    for column in (
        "test_run_id",
        "journey_id",
        "execution_id",
        "agent_snapshot_id",
    ):
        op.create_index(
            f"ix_model_invocations_{column}",
            "model_invocations",
            [column],
            schema="execution",
        )


def downgrade() -> None:
    """Remove Batch 1 observability tables."""

    op.drop_table("model_invocations", schema="execution")
    op.drop_table("agent_runtime_snapshots", schema="execution")
