"""Add the unified run_kind column to test_runs (U-P0-03).

The kind is the single run-type value of the unified engine
(explore_test | persona | slop). Existing rows stay NULL; readers
resolve their kind from the legacy configuration_snapshot
execution_mode via read-time translation until retirement.
"""

import sqlalchemy as sa
from alembic import op

revision = "c7d2e91a4b60"
down_revision = "b3f8a24c910e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "test_runs",
        sa.Column("run_kind", sa.String(length=32), nullable=True),
        schema="testing",
    )
    op.create_check_constraint(
        "ck_test_runs_run_kind_allowed",
        "test_runs",
        "run_kind IS NULL OR run_kind IN ('explore_test', 'persona', 'slop')",
        schema="testing",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_test_runs_run_kind_allowed", "test_runs", schema="testing", type_="check"
    )
    op.drop_column("test_runs", "run_kind", schema="testing")
