"""create auth and core schemas

Revision ID: e0281710e3af
Revises: 
Create Date: 2026-08-17 19:08:19.931642

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e0281710e3af'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(sa.text("CREATE SCHEMA auth"))
    op.execute(sa.text("CREATE SCHEMA core"))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(sa.text("DROP SCHEMA core"))
    op.execute(sa.text("DROP SCHEMA auth"))
