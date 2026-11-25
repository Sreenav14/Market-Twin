"""Add app maps.

Revision ID: dca08ed17e84
Revises: d2a718c40e91
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "dca08ed17e84"
down_revision: str | Sequence[str] | None = "d2a718c40e91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_maps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'building'"), nullable=False
        ),
        sa.Column("release_state", sa.String(length=16), nullable=True),
        sa.Column("release_scope", sa.String(length=32), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column(
            "builder_version",
            sa.String(length=32),
            server_default=sa.text("'census-1a.1'"),
            nullable=False,
        ),
        sa.Column(
            "census_config",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "census_metrics",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "pattern_stats",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "gate_metrics",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "census_expected_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "census_reachable_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "mapping_spend_calls", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "mapping_spend_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "mapping_spend_seconds", sa.Float(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("mapping_budget_calls", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("failure_site", sa.String(length=128), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('building', 'ready', 'failed')", name="ck_app_maps_status_allowed"
        ),
        sa.CheckConstraint(
            "release_state IN ('trusted', 'partial', 'failed')",
            name="ck_app_maps_release_state_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "application_id"],
            ["testing.applications.workspace_id", "testing.applications.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["application_id", "target_id"],
            ["testing.application_targets.application_id", "testing.application_targets.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_app_maps_workspace_id_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "application_id",
            "target_id",
            "version_number",
            name="uq_app_maps_version",
        ),
        schema="knowledge",
    )
    op.create_index(
        "ix_app_maps_poll", "app_maps", ["status", "started_at"], schema="knowledge"
    )
    op.create_index(
        "uq_app_maps_single_flight",
        "app_maps",
        ["application_id", "target_id"],
        unique=True,
        schema="knowledge",
        postgresql_where=sa.text("status = 'building'"),
    )
    op.create_table(
        "map_pages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("app_map_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("route_pattern", sa.Text(), nullable=False),
        sa.Column("source_kinds", postgresql.JSONB(), nullable=False),
        sa.Column(
            "crawl_status",
            sa.String(length=24),
            server_default=sa.text("'census_incomplete'"),
            nullable=False,
        ),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("redirect_target", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("html_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "requires_auth", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "roles_seen",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "source", sa.String(length=32), server_default=sa.text("'census'"), nullable=False
        ),
        sa.Column(
            "confidence", sa.String(length=8), server_default=sa.text("'low'"), nullable=False
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "crawl_status IN ('fetch_ok', 'redirect', 'blocked_auth', 'blocked_wall', "
            "'gone', 'fetch_error', 'out_of_scope', 'census_incomplete')",
            name="ck_map_pages_crawl_status_allowed",
        ),
        sa.CheckConstraint(
            "confidence IN ('high', 'medium', 'low')", name="ck_map_pages_confidence_allowed"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            ["knowledge.app_maps.workspace_id", "knowledge.app_maps.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_map_pages_workspace_id_id"),
        sa.UniqueConstraint("app_map_id", "canonical_url", name="uq_map_pages_canonical"),
        schema="knowledge",
    )
    op.create_index(
        "ix_map_pages_status", "map_pages", ["app_map_id", "crawl_status"], schema="knowledge"
    )
    op.create_index(
        "ix_map_pages_pattern", "map_pages", ["app_map_id", "route_pattern"], schema="knowledge"
    )
    op.create_table(
        "map_page_states",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("app_map_id", sa.Uuid(), nullable=False),
        sa.Column("map_page_id", sa.Uuid(), nullable=False),
        sa.Column("state_key", sa.Text(), nullable=False),
        sa.Column(
            "state_kind",
            sa.String(length=16),
            server_default=sa.text("'default'"),
            nullable=False,
        ),
        sa.Column("state_id", sa.String(length=64), nullable=True),
        sa.Column("element_signature", sa.Text(), nullable=True),
        sa.Column("form_signature", sa.Text(), nullable=True),
        sa.Column(
            "source", sa.String(length=32), server_default=sa.text("'census'"), nullable=False
        ),
        sa.Column(
            "confidence", sa.String(length=8), server_default=sa.text("'low'"), nullable=False
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "state_kind IN ('default', 'observed')", name="ck_map_page_states_state_kind_allowed"
        ),
        sa.CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="ck_map_page_states_confidence_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            ["knowledge.app_maps.workspace_id", "knowledge.app_maps.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "map_page_id"],
            ["knowledge.map_pages.workspace_id", "knowledge.map_pages.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("map_page_id", "state_key", name="uq_map_page_states_key"),
        schema="knowledge",
    )


def downgrade() -> None:
    op.drop_table("map_page_states", schema="knowledge")
    op.drop_index("ix_map_pages_pattern", table_name="map_pages", schema="knowledge")
    op.drop_index("ix_map_pages_status", table_name="map_pages", schema="knowledge")
    op.drop_table("map_pages", schema="knowledge")
    op.drop_index("uq_app_maps_single_flight", table_name="app_maps", schema="knowledge")
    op.drop_index("ix_app_maps_poll", table_name="app_maps", schema="knowledge")
    op.drop_table("app_maps", schema="knowledge")
