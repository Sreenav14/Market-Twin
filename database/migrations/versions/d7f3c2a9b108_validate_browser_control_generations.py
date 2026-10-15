"""Constrain browser and checkpoint fencing generations to nonnegative values.

Revision ID: d7f3c2a9b108
Revises: c7a411f2b903
"""

from alembic import op

revision = "d7f3c2a9b108"
down_revision = "c7a411f2b903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_browser_sessions_generation_nonnegative",
        "browser_sessions",
        "control_generation >= 0",
        schema="execution",
    )
    op.create_check_constraint(
        "ck_suspensions_generation_nonnegative",
        "execution_suspensions",
        "owner_generation >= 0",
        schema="execution",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_suspensions_generation_nonnegative",
        "execution_suspensions",
        schema="execution",
        type_="check",
    )
    op.drop_constraint(
        "ck_browser_sessions_generation_nonnegative",
        "browser_sessions",
        schema="execution",
        type_="check",
    )
