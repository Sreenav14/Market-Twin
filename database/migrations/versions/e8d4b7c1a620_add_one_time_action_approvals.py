"""Add action-bound approvals and no-replay receipts.

Revision ID: e8d4b7c1a620
Revises: d7f3c2a9b108
"""

import sqlalchemy as sa
from alembic import op

revision = "e8d4b7c1a620"
down_revision = "d7f3c2a9b108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_approval_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("test_run_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.BigInteger(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("decision_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("action_fingerprint", sa.String(64), nullable=False),
        sa.Column("resource_fingerprint", sa.String(64), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("action_summary", sa.String(300), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired', 'consumed')",
            name="ck_action_approval_requests_status_allowed",
        ),
        sa.CheckConstraint("length(action_fingerprint) = 64", name="ck_action_approval_fingerprint_sha256"),
        sa.CheckConstraint("length(resource_fingerprint) = 64", name="ck_action_approval_resource_sha256"),
        sa.CheckConstraint("policy_version >= 1", name="ck_action_approval_policy_positive"),
        sa.ForeignKeyConstraint(["test_run_id"], ["testing.test_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_id"], ["execution.agent_executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_id", "step_id"], ["execution.execution_steps.execution_id", "execution.execution_steps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["core.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decision_by_user_id"], ["core.users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        schema="execution",
    )
    op.create_index(
        "uq_active_action_approval_per_step",
        "action_approval_requests",
        ["execution_id", "step_id"],
        unique=True,
        schema="execution",
        postgresql_where=sa.text("status IN ('pending', 'approved')"),
    )
    op.create_table(
        "action_approval_receipts",
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("action_fingerprint", sa.String(64), nullable=False),
        sa.Column("dispatch_state", sa.String(32), server_default=sa.text("'claimed'"), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "dispatch_state IN ('claimed', 'completed', 'failed_before_effect')",
            name="ck_action_approval_receipts_state_allowed",
        ),
        sa.ForeignKeyConstraint(["approval_id"], ["execution.action_approval_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("approval_id"),
        schema="execution",
    )


def downgrade() -> None:
    op.drop_table("action_approval_receipts", schema="execution")
    op.drop_index(
        "uq_active_action_approval_per_step",
        table_name="action_approval_requests",
        schema="execution",
    )
    op.drop_table("action_approval_requests", schema="execution")
