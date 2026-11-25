"""Add phase 4 freshness schema.

Revision ID: 065d5a50b766
Revises: b4d8c2e6f107

Doc 23 section 5: ``app_maps`` gains the freshness summary columns
(``freshness_state`` / ``last_preflight_at`` / ``freshness_metrics``);
``map_page_states`` gains ``screenshot_phash``; the preflight job
record (``map_preflights``, with the single-flight partial unique
index of section 5.2), its event log (``map_preflight_events``) and
the append-only fingerprint history (``map_fingerprint_history``,
section 5.3) are created.

Downgrade reverses exactly this revision, in reverse order.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "065d5a50b766"
down_revision: str | Sequence[str] | None = "b4d8c2e6f107"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "knowledge"


def upgrade() -> None:
    # -- app_maps: freshness summary (doc 23 section 5.2) --
    op.add_column(
        "app_maps",
        sa.Column(
            "freshness_state", sa.String(16),
            server_default=sa.text("'unknown'"), nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_app_maps_freshness_state_allowed",
        "app_maps",
        "freshness_state IN ('unknown', 'current', 'stale')",
        schema=SCHEMA,
    )
    op.add_column(
        "app_maps",
        sa.Column("last_preflight_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "app_maps",
        sa.Column(
            "freshness_metrics", postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        schema=SCHEMA,
    )

    # -- map_page_states: perceptual screenshot hash (section 5.2) --
    op.add_column(
        "map_page_states",
        sa.Column("screenshot_phash", sa.String(80), nullable=True),
        schema=SCHEMA,
    )

    # -- map_preflights: the preflight job record (section 5.2) --
    op.create_table(
        "map_preflights",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("app_map_id", sa.Uuid(), nullable=False),
        sa.Column("resulting_map_id", sa.Uuid(), nullable=True),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status", sa.String(16),
            server_default=sa.text("'building'"), nullable=False,
        ),
        sa.Column(
            "config", postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            "outcome", postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            "deferred", postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            "tier_counts", postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            "spend_seconds", sa.Float(),
            server_default=sa.text("0"), nullable=False,
        ),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("failure_site", sa.String(128), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "trigger IN ('run_creation', 'manual')",
            name="ck_map_preflights_trigger_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('building', 'ready', 'partial', 'failed')",
            name="ck_map_preflights_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            ["knowledge.app_maps.workspace_id", "knowledge.app_maps.id"],
            ondelete="RESTRICT",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_map_preflights_single_flight",
        "map_preflights",
        ["app_map_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'building'"),
    )
    op.create_index(
        "ix_map_preflights_poll",
        "map_preflights",
        ["status", "started_at"],
        schema=SCHEMA,
    )

    # -- map_preflight_events: heartbeat + audit trail (section 5.2) --
    op.create_table(
        "map_preflight_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("preflight_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["preflight_id"],
            ["knowledge.map_preflights.id"],
            ondelete="RESTRICT",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_map_preflight_events_preflight_occurred",
        "map_preflight_events",
        ["preflight_id", "occurred_at"],
        schema=SCHEMA,
    )

    # -- map_fingerprint_history: append-only observations (section 5.3) --
    op.create_table(
        "map_fingerprint_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("app_map_id", sa.Uuid(), nullable=False),
        sa.Column("map_page_id", sa.Uuid(), nullable=False),
        sa.Column("map_page_state_id", sa.Uuid(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("state_key", sa.Text(), nullable=False),
        sa.Column("state_id", sa.String(64), nullable=True),
        sa.Column("dom_structure_hash", sa.String(64), nullable=True),
        sa.Column("aria_hash", sa.String(64), nullable=True),
        sa.Column("screenshot_hash", sa.String(64), nullable=True),
        sa.Column("screenshot_phash", sa.String(80), nullable=True),
        sa.Column("html_sha256", sa.String(64), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("preflight_id", sa.Uuid(), nullable=True),
        sa.Column(
            "observed_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('harvest', 'preflight', 'reconcile')",
            name="ck_map_fingerprint_history_source_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            ["knowledge.app_maps.workspace_id", "knowledge.app_maps.id"],
            ondelete="RESTRICT",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_map_fingerprint_history_page",
        "map_fingerprint_history",
        ["application_id", "target_id", "canonical_url", "state_key", "observed_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_map_fingerprint_history_page",
        table_name="map_fingerprint_history",
        schema=SCHEMA,
    )
    op.drop_table("map_fingerprint_history", schema=SCHEMA)
    op.drop_index(
        "ix_map_preflight_events_preflight_occurred",
        table_name="map_preflight_events",
        schema=SCHEMA,
    )
    op.drop_table("map_preflight_events", schema=SCHEMA)
    op.drop_index(
        "ix_map_preflights_poll",
        table_name="map_preflights",
        schema=SCHEMA,
    )
    op.drop_index(
        "uq_map_preflights_single_flight",
        table_name="map_preflights",
        schema=SCHEMA,
    )
    op.drop_table("map_preflights", schema=SCHEMA)
    op.drop_column("map_page_states", "screenshot_phash", schema=SCHEMA)
    op.drop_column("app_maps", "freshness_metrics", schema=SCHEMA)
    op.drop_column("app_maps", "last_preflight_at", schema=SCHEMA)
    op.drop_constraint(
        "ck_app_maps_freshness_state_allowed",
        "app_maps",
        schema=SCHEMA,
    )
    op.drop_column("app_maps", "freshness_state", schema=SCHEMA)
