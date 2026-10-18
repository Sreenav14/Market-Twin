"""Persist explicitly skipped human assistance independently of cancellation."""

import sqlalchemy as sa
from alembic import op

revision = "6b0e2ac784d1"
down_revision = "31d4ef097a2b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "human_action_requests", sa.Column("terminal_generation", sa.BigInteger(), nullable=True),
        schema="execution",
    )
    op.drop_constraint(
        "ck_agent_executions_status_allowed", "agent_executions", schema="execution",
    )
    op.create_check_constraint(
        "ck_agent_executions_status_allowed", "agent_executions",
        "status IN ('pending', 'queued', 'running', 'completed', 'failed', "
        "'timed_out', 'cancelled', 'policy_blocked', 'skipped')",
        schema="execution",
    )
    op.drop_constraint(
        "ck_human_action_requests_status_allowed", "human_action_requests", schema="execution",
    )
    op.create_check_constraint(
        "ck_human_action_requests_status_allowed", "human_action_requests",
        "status IN ('pending', 'leased', 'completed', 'cancelled', 'expired', 'skipped')",
        schema="execution",
    )


def downgrade() -> None:
    # A downgrade cannot silently convert skipped work into cancelled work.
    # PostgreSQL rejects this constraint if skipped records still exist.
    op.drop_constraint(
        "ck_agent_executions_status_allowed", "agent_executions", schema="execution",
    )
    op.create_check_constraint(
        "ck_agent_executions_status_allowed", "agent_executions",
        "status IN ('pending', 'queued', 'running', 'completed', 'failed', "
        "'timed_out', 'cancelled', 'policy_blocked')",
        schema="execution",
    )
    op.drop_constraint(
        "ck_human_action_requests_status_allowed", "human_action_requests", schema="execution",
    )
    op.create_check_constraint(
        "ck_human_action_requests_status_allowed", "human_action_requests",
        "status IN ('pending', 'leased', 'completed', 'cancelled', 'expired')",
        schema="execution",
    )
    op.drop_column("human_action_requests", "terminal_generation", schema="execution")
