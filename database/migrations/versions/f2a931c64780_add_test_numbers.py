"""Assign atomic, unique, human-readable test numbers, including existing tests."""

import sqlalchemy as sa
from alembic import op

revision = "f2a931c64780"
down_revision = "e8a621bd3c70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("test_runs", sa.Column(
        "test_number", sa.BigInteger(), sa.Identity(always=True), nullable=False,
    ), schema="testing")
    op.create_unique_constraint(
        "uq_test_runs_test_number", "test_runs", ["test_number"], schema="testing",
    )


def downgrade() -> None:
    op.drop_constraint("uq_test_runs_test_number", "test_runs", schema="testing")
    op.drop_column("test_runs", "test_number", schema="testing")
