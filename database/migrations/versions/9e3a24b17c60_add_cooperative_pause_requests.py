"""Persist cooperative pause intent separately from human control leases."""

import sqlalchemy as sa
from alembic import op

revision = "9e3a24b17c60"
down_revision = "6b0e2ac784d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pause_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("test_run_id", sa.Uuid(), nullable=False),
        sa.Column("journey_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("browser_session_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("resume_requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("human_request_id", sa.Uuid(), nullable=True),
        sa.Column("last_durable_step_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('requested', 'paused', 'resume_requested', 'resumed', 'skipped', "
            "'cancelled', 'expired', 'unavailable')", name="ck_pause_requests_status_allowed",
        ),
        sa.CheckConstraint("generation >= 0", name="ck_pause_requests_generation_nonnegative"),
        sa.ForeignKeyConstraint(["test_run_id"], ["testing.test_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["journey_id"], ["testing.persona_journeys.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id", "browser_session_id"],
            ["execution.browser_sessions.execution_id", "execution.browser_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["core.users.id"], ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["resume_requested_by_user_id"], ["core.users.id"], ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["human_request_id"], ["execution.human_action_requests.id"], ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["last_durable_step_id"], ["execution.execution_steps.id"], ondelete="SET NULL",
        ),
        schema="execution",
    )
    op.create_index(
        "uq_active_pause_per_browser", "pause_requests", ["browser_session_id"], unique=True,
        postgresql_where=sa.text("status IN ('requested', 'paused', 'resume_requested')"),
        schema="execution",
    )


def downgrade() -> None:
    op.drop_table("pause_requests", schema="execution")
