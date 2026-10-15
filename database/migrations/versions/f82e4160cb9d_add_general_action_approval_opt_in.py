"""Add explicit per-run authority for policy-eligible action approvals."""

import sqlalchemy as sa
from alembic import op

revision = "f82e4160cb9d"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "test_runs",
        sa.Column(
            "human_action_approvals_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema="testing",
    )
    op.drop_constraint(
        "ck_test_runs_status_allowed", "test_runs", schema="testing", type_="check"
    )
    op.create_check_constraint(
        "ck_test_runs_status_allowed",
        "test_runs",
        "status IN ('draft', 'planning', 'queued', 'running', 'awaiting_human', "
        "'completed', 'failed', 'cancelled')",
        schema="testing",
    )
    op.drop_constraint(
        "ck_action_approval_requests_status_allowed",
        "action_approval_requests",
        schema="execution",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_approval_requests_status_allowed",
        "action_approval_requests",
        "status IN ('pending', 'approved', 'rejected', 'expired', 'consumed', 'cancelled')",
        schema="execution",
    )
    op.add_column(
        "execution_suspensions",
        sa.Column(
            "pending_approval_id",
            sa.Uuid(),
            sa.ForeignKey(
                "execution.action_approval_requests.id",
                name="fk_suspensions_pending_approval",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        schema="execution",
    )
    op.add_column(
        "action_approval_requests",
        sa.Column(
            "control_generation",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="execution",
    )
    op.add_column(
        "action_approval_requests", sa.Column("browser_session_id", sa.Uuid(), nullable=True),
        schema="execution",
    )
    op.create_foreign_key(
        "fk_action_approval_requests_browser_session_id_browser_sessions",
        "action_approval_requests",
        "browser_sessions",
        ["browser_session_id"],
        ["id"],
        source_schema="execution",
        referent_schema="execution",
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_action_approval_generation_nonnegative",
        "action_approval_requests",
        "control_generation >= 0",
        schema="execution",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_action_approval_generation_nonnegative",
        "action_approval_requests",
        schema="execution",
        type_="check",
    )
    op.drop_constraint(
        "fk_action_approval_requests_browser_session_id_browser_sessions",
        "action_approval_requests",
        schema="execution",
        type_="foreignkey",
    )
    op.drop_column("action_approval_requests", "browser_session_id", schema="execution")
    op.drop_column("action_approval_requests", "control_generation", schema="execution")
    op.drop_column("execution_suspensions", "pending_approval_id", schema="execution")
    op.drop_constraint(
        "ck_action_approval_requests_status_allowed",
        "action_approval_requests",
        schema="execution",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_approval_requests_status_allowed",
        "action_approval_requests",
        "status IN ('pending', 'approved', 'rejected', 'expired', 'consumed')",
        schema="execution",
    )
    op.drop_constraint(
        "ck_test_runs_status_allowed", "test_runs", schema="testing", type_="check"
    )
    op.create_check_constraint(
        "ck_test_runs_status_allowed",
        "test_runs",
        "status IN ('draft', 'planning', 'queued', 'running', 'completed', 'failed', 'cancelled')",
        schema="testing",
    )
    op.drop_column("test_runs", "human_action_approvals_enabled", schema="testing")
