"""Add browser-control generations and token-free suspension cursors.

Revision ID: c7a411f2b903
Revises: f2a931c64780
"""

import sqlalchemy as sa
from alembic import op

revision = "c7a411f2b903"
down_revision = "f2a931c64780"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "browser_sessions",
        sa.Column("control_mode", sa.String(length=32), server_default="agent", nullable=False),
        schema="execution",
    )
    op.add_column(
        "browser_sessions",
        sa.Column("control_generation", sa.BigInteger(), server_default="0", nullable=False),
        schema="execution",
    )
    op.create_check_constraint(
        "ck_browser_sessions_control_mode_allowed",
        "browser_sessions",
        "control_mode IN ('agent', 'human_pending', 'human', 'verifying', 'none')",
        schema="execution",
    )

    op.add_column(
        "human_action_requests",
        sa.Column("idempotency_key", sa.String(length=256), nullable=True),
        schema="execution",
    )
    op.create_index(
        "uq_human_action_requests_execution_idempotency",
        "human_action_requests",
        ["execution_id", "idempotency_key"],
        unique=True,
        schema="execution",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.add_column(
        "human_control_leases",
        sa.Column("generation", sa.BigInteger(), server_default="0", nullable=False),
        schema="execution",
    )
    op.create_check_constraint(
        "ck_human_control_leases_generation_nonnegative",
        "human_control_leases",
        "generation >= 0",
        schema="execution",
    )
    op.create_index(
        "uq_active_human_lease_per_browser",
        "human_control_leases",
        ["browser_session_id"],
        unique=True,
        schema="execution",
        postgresql_where=sa.text("released_at IS NULL"),
    )

    op.create_table(
        "execution_suspensions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("test_run_id", sa.Uuid(), nullable=False),
        sa.Column("journey_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("browser_session_id", sa.Uuid(), nullable=False),
        sa.Column("pending_request_id", sa.Uuid(), nullable=True),
        sa.Column("checkpoint_version", sa.Integer(), nullable=False),
        sa.Column("owner_generation", sa.BigInteger(), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("planned_step_index", sa.Integer(), nullable=False),
        sa.Column("last_durable_step_id", sa.BigInteger(), nullable=True),
        sa.Column("active_deadline_remaining_ms", sa.BigInteger(), nullable=False),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("human_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resume_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="waiting", nullable=False),
        sa.CheckConstraint("checkpoint_version >= 1", name="ck_suspensions_version_positive"),
        sa.CheckConstraint("planned_step_index >= 0", name="ck_suspensions_step_nonnegative"),
        sa.CheckConstraint("resume_count >= 0", name="ck_suspensions_resume_nonnegative"),
        sa.CheckConstraint(
            "active_deadline_remaining_ms >= 0", name="ck_suspensions_deadline_nonnegative",
        ),
        sa.CheckConstraint(
            "status IN ('waiting', 'ready', 'consumed', 'abandoned')",
            name="ck_suspensions_status_allowed",
        ),
        sa.CheckConstraint(
            "phase IN ('auth_preflight', 'case_action', 'assertion')",
            name="ck_suspensions_phase_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["test_run_id"], ["testing.test_runs.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["journey_id"], ["testing.persona_journeys.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id", "browser_session_id"],
            ["execution.browser_sessions.execution_id", "execution.browser_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pending_request_id"], ["execution.human_action_requests.id"], ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["last_durable_step_id"], ["execution.execution_steps.id"], ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_execution_suspensions"),
        sa.UniqueConstraint(
            "test_run_id", "checkpoint_version", name="uq_suspensions_run_version",
        ),
        schema="execution",
    )
    op.create_index(
        "uq_active_suspension_per_run",
        "execution_suspensions",
        ["test_run_id"],
        unique=True,
        schema="execution",
        postgresql_where=sa.text("status IN ('waiting', 'ready')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_active_suspension_per_run", table_name="execution_suspensions", schema="execution",
    )
    op.drop_table("execution_suspensions", schema="execution")
    op.drop_index(
        "uq_active_human_lease_per_browser", table_name="human_control_leases", schema="execution",
    )
    op.drop_constraint(
        "ck_human_control_leases_generation_nonnegative", "human_control_leases",
        schema="execution", type_="check",
    )
    op.drop_column("human_control_leases", "generation", schema="execution")
    op.drop_index(
        "uq_human_action_requests_execution_idempotency",
        table_name="human_action_requests", schema="execution",
    )
    op.drop_column("human_action_requests", "idempotency_key", schema="execution")
    op.drop_constraint(
        "ck_browser_sessions_control_mode_allowed", "browser_sessions",
        schema="execution", type_="check",
    )
    op.drop_column("browser_sessions", "control_generation", schema="execution")
    op.drop_column("browser_sessions", "control_mode", schema="execution")
