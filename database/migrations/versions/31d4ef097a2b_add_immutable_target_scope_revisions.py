"""Link immutable target execution-scope revisions."""

import sqlalchemy as sa
from alembic import op

revision = "31d4ef097a2b"
down_revision = "f82e4160cb9d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "application_targets",
        sa.Column("scope_parent_id", sa.Uuid(), nullable=True),
        schema="testing",
    )
    op.create_foreign_key(
        "fk_target_scope_parent",
        "application_targets",
        "application_targets",
        ["scope_parent_id"],
        ["id"],
        source_schema="testing",
        referent_schema="testing",
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_testing_application_targets_scope_parent_id",
        "application_targets",
        ["scope_parent_id"],
        schema="testing",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_testing_application_targets_scope_parent_id",
        table_name="application_targets",
        schema="testing",
    )
    op.drop_constraint(
        "fk_target_scope_parent", "application_targets", schema="testing", type_="foreignkey"
    )
    op.drop_column("application_targets", "scope_parent_id", schema="testing")
