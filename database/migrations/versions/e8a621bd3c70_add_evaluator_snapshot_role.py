"""Record the evaluator's actual prompt alongside historical runtime snapshots."""

from alembic import op

revision = "e8a621bd3c70"
down_revision = "d6e71a092f41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_agent_runtime_snapshots_role_allowed",
        "agent_runtime_snapshots",
        schema="execution",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_runtime_snapshots_role_allowed",
        "agent_runtime_snapshots",
        "agent_role IN ('meta', 'persona', 'visual_verifier', 'evaluator')",
        schema="execution",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_runtime_snapshots_role_allowed",
        "agent_runtime_snapshots",
        schema="execution",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_runtime_snapshots_role_allowed",
        "agent_runtime_snapshots",
        "agent_role IN ('meta', 'persona', 'visual_verifier')",
        schema="execution",
    )
