"""Drop the one-browser-row-per-execution unique (D-LIVE-1, layer 2).

uq_browser_sessions_execution_id encodes the legacy per-case invariant
that an execution owns exactly one browser session row. The unified
engine's sibling design broke that invariant on purpose: the Room row
and every S2 worker-lane row all hang off the run's inventory
execution (workflow/harness_run.py _open_lane persists each lane with
execution_id=inv_execution_id, session_role='worker'). With the role
check widened by c9d4e7a21f6b, the first lane INSERT then died on this
unique instead (MT-000155, Postgres log 2026-11-15 20:52:02 UTC).

Nothing references the single-column unique: every FK to
browser_sessions targets (id), and the one-open-Room-per-run rule is
still enforced by the partial unique index
uq_browser_sessions_open_room_per_run. Downgrade restores the unique —
which will fail if sibling rows sharing an execution exist by then,
by design.
"""

from alembic import op

revision = "d51b8e3f2a47"
down_revision = "c9d4e7a21f6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_browser_sessions_execution_id",
        "browser_sessions",
        schema="execution",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_browser_sessions_execution_id",
        "browser_sessions",
        ["execution_id"],
        schema="execution",
    )
