"""Persist explicit synthetic fixture approval authority outside JSON config."""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "e8d4b7c1a620"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_action_approval_receipts_state_allowed",
        "action_approval_receipts",
        schema="execution",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_approval_receipts_state_allowed",
        "action_approval_receipts",
        "dispatch_state IN ('claimed', 'completed', 'failed_before_effect', 'uncertain')",
        schema="execution",
    )
    op.add_column(
        "test_runs",
        sa.Column(
            "synthetic_fixture_approval_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        schema="testing",
    )


def downgrade() -> None:
    op.drop_column("test_runs", "synthetic_fixture_approval_enabled", schema="testing")
    op.drop_constraint(
        "ck_action_approval_receipts_state_allowed",
        "action_approval_receipts",
        schema="execution",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_approval_receipts_state_allowed",
        "action_approval_receipts",
        "dispatch_state IN ('claimed', 'completed', 'failed_before_effect')",
        schema="execution",
    )
