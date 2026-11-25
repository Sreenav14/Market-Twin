"""Allow the 'worker' browser session role (D-LIVE-1).

The S1 sibling-session factory persists lane sessions with
session_role='worker' (workflow/harness_run.py), but the P2-era check
constraint only allowed room | proof | persona | legacy. The first
harness item needing a worker session died on the INSERT
(MT-000153, explore_test on klaviyo.com). Widen the allowed set to the
full set of roles the code persists; downgrade restores the P2 set.
"""

from alembic import op

revision = "c9d4e7a21f6b"
down_revision = "065d5a50b766"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_browser_sessions_session_role_allowed",
        "browser_sessions",
        schema="execution",
        type_="check",
    )
    op.create_check_constraint(
        "ck_browser_sessions_session_role_allowed",
        "browser_sessions",
        "session_role IN ('room', 'proof', 'persona', 'legacy', 'worker')",
        schema="execution",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_browser_sessions_session_role_allowed",
        "browser_sessions",
        schema="execution",
        type_="check",
    )
    op.create_check_constraint(
        "ck_browser_sessions_session_role_allowed",
        "browser_sessions",
        "session_role IN ('room', 'proof', 'persona', 'legacy')",
        schema="execution",
    )
