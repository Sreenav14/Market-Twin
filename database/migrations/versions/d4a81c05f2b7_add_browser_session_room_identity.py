"""Give browser sessions a run identity and a role (U-P2-01).

The unified engine's Room is one browser session per run, shared by
every worker in the run. Sessions gain test_run_id + session_role
(room | proof | persona | legacy); existing rows default to legacy.
A partial unique index guarantees at most one OPEN room per run.
"""

import sqlalchemy as sa
from alembic import op

revision = "d4a81c05f2b7"
down_revision = "c7d2e91a4b60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "browser_sessions",
        sa.Column(
            "test_run_id",
            sa.Uuid(),
            sa.ForeignKey("testing.test_runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        schema="execution",
    )
    op.add_column(
        "browser_sessions",
        sa.Column(
            "session_role",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'legacy'"),
        ),
        schema="execution",
    )
    op.create_check_constraint(
        "ck_browser_sessions_session_role_allowed",
        "browser_sessions",
        "session_role IN ('room', 'proof', 'persona', 'legacy')",
        schema="execution",
    )
    op.create_index(
        "ix_browser_sessions_test_run_id",
        "browser_sessions",
        ["test_run_id"],
        schema="execution",
    )
    op.create_index(
        "uq_browser_sessions_open_room_per_run",
        "browser_sessions",
        ["test_run_id"],
        unique=True,
        schema="execution",
        postgresql_where=sa.text(
            "session_role = 'room' AND state IN ('starting', 'open')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_browser_sessions_open_room_per_run",
        table_name="browser_sessions",
        schema="execution",
    )
    op.drop_index(
        "ix_browser_sessions_test_run_id",
        table_name="browser_sessions",
        schema="execution",
    )
    op.drop_constraint(
        "ck_browser_sessions_session_role_allowed",
        "browser_sessions",
        schema="execution",
        type_="check",
    )
    op.drop_column("browser_sessions", "session_role", schema="execution")
    op.drop_column("browser_sessions", "test_run_id", schema="execution")
