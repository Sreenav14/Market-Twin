"""Add phase 2 expectations wiring.

Revision ID: 811153077c0e
Revises: 51e27d6f11a2

Doc 21 section 4: grounding lifecycle columns on app_maps, the
assertion/promotion/supersession machinery columns on
map_expectations, the conflict kind/detection columns on
map_conflicts, and the two new tables map_expectation_events +
graph_audit_reports. Also carries the Wave 1 OQ2 fix: the legacy
skills/skill_versions columns blueprint_id, blueprint_version_id and
created_by_user_id relax to nullable so graph-scoped skill rows
(which have no blueprint or human creator) can be written -- Wave 1
proved empirically that the NOT NULL constraints refuse them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "811153077c0e"
down_revision: str | Sequence[str] | None = "51e27d6f11a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "knowledge"


def upgrade() -> None:
    # -- app_maps: grounding lifecycle (mirrors the harvest_* pattern) --
    op.add_column(
        "app_maps",
        sa.Column(
            "grounding_status", sa.String(16),
            server_default=sa.text("'not_started'"), nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "app_maps",
        sa.Column(
            "grounding_metrics", postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "app_maps",
        sa.Column("grounding_started_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "app_maps",
        sa.Column("grounding_completed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "app_maps",
        sa.Column("grounding_failure_code", sa.String(64), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "app_maps",
        sa.Column("grounding_failure_message", sa.Text(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "app_maps",
        sa.Column("grounding_failure_site", sa.String(128), nullable=True),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_app_maps_grounding_status_allowed",
        "app_maps",
        "grounding_status IN ('not_started', 'building', 'ready', 'partial', 'failed')",
        schema=SCHEMA,
    )
    op.create_index(
        "uq_app_maps_grounding_single_flight",
        "app_maps",
        ["application_id", "target_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("grounding_status = 'building'"),
    )
    op.create_index(
        "ix_app_maps_grounding_poll",
        "app_maps",
        ["grounding_status", "grounding_started_at"],
        schema=SCHEMA,
    )

    # -- map_expectations: assertion + promotion + supersession machinery --
    op.add_column(
        "map_expectations",
        sa.Column("assertion", postgresql.JSONB(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "map_expectations",
        sa.Column("assertion_kind", sa.String(24), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "map_expectations",
        sa.Column("assertion_origin", sa.String(16), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "map_expectations",
        sa.Column("promoted_by", sa.String(128), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "map_expectations",
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "map_expectations",
        sa.Column("superseded_by_id", sa.Uuid(), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_map_expectations_superseded_by",
        "map_expectations",
        "map_expectations",
        ["superseded_by_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="RESTRICT",
    )
    op.add_column(
        "map_expectations",
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "map_expectations",
        sa.Column("last_check_result", sa.String(8), nullable=True),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_map_expectations_last_check_result_allowed",
        "map_expectations",
        "last_check_result IS NULL OR last_check_result IN ('passed', 'failed')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_map_expectations_assertion_kind_allowed",
        "map_expectations",
        "assertion_kind IS NULL OR assertion_kind IN "
        "('element_state', 'navigation', 'page_text', 'journey_terminal', "
        "'field_validation')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_map_expectations_assertion_origin_allowed",
        "map_expectations",
        "assertion_origin IS NULL OR assertion_origin IN "
        "('deterministic', 'model-drafted', 'owner-entered')",
        schema=SCHEMA,
    )
    op.create_index(
        "ix_map_expectations_seeding",
        "map_expectations",
        ["app_map_id", "oracle_source", "status"],
        schema=SCHEMA,
    )

    # -- map_conflicts: kind + detection provenance --
    op.add_column(
        "map_conflicts",
        sa.Column(
            "conflict_kind", sa.String(24),
            server_default=sa.text("'statement_vs_observation'"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "map_conflicts",
        sa.Column(
            "detection_source", sa.String(16),
            server_default=sa.text("'grounding'"), nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "map_conflicts",
        sa.Column("observed_subject_id", sa.Uuid(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "map_conflicts",
        sa.Column("run_id", sa.Uuid(), nullable=True),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_map_conflicts_kind_allowed",
        "map_conflicts",
        "conflict_kind IN "
        "('statement_vs_observation', 'oracle_check_failed', "
        "'navigation_mismatch')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_map_conflicts_detection_source_allowed",
        "map_conflicts",
        "detection_source IN ('grounding', 'verification', 'run')",
        schema=SCHEMA,
    )
    op.create_index(
        "ix_map_conflicts_open",
        "map_conflicts",
        ["app_map_id", "status"],
        schema=SCHEMA,
    )

    # -- map_expectation_events: append-only expectation history --
    op.create_table(
        "map_expectation_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("app_map_id", sa.Uuid(), nullable=False),
        sa.Column("expectation_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('authored', 'matched', 'adjudicated', 'promoted', "
            "'rejected', 'conflicted', 'resolved', 'superseded', 'checked', "
            "'refused_non_verdict')",
            name="ck_map_expectation_events_type_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "app_map_id"],
            ["knowledge.app_maps.workspace_id", "knowledge.app_maps.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["expectation_id"],
            ["knowledge.map_expectations.id"],
            ondelete="RESTRICT",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_map_expectation_events_expectation",
        "map_expectation_events",
        ["expectation_id", "occurred_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_map_expectation_events_map_occurred",
        "map_expectation_events",
        ["app_map_id", "occurred_at"],
        schema=SCHEMA,
    )

    # -- graph_audit_reports: read-only audit output (INSERT-only) --
    op.create_table(
        "graph_audit_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("app_map_id", sa.Uuid(), nullable=True),
        sa.Column("audit_kind", sa.String(32), nullable=False),
        sa.Column(
            "checks", postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            "findings", postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column("graph_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "audit_kind IN ('scheduled', 'post_gate', 'on_demand')",
            name="ck_graph_audit_reports_kind_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["app_map_id"],
            ["knowledge.app_maps.id"],
            ondelete="RESTRICT",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_graph_audit_reports_map_created",
        "graph_audit_reports",
        ["app_map_id", "created_at"],
        schema=SCHEMA,
    )

    # -- OQ2 (Wave 1): legacy skill registry columns relax to nullable --
    op.alter_column("skills", "blueprint_id", nullable=True, schema=SCHEMA)
    op.alter_column("skills", "created_by_user_id", nullable=True, schema=SCHEMA)
    op.alter_column("skill_versions", "blueprint_id", nullable=True, schema=SCHEMA)
    op.alter_column(
        "skill_versions", "blueprint_version_id", nullable=True, schema=SCHEMA
    )
    op.alter_column(
        "skill_versions", "created_by_user_id", nullable=True, schema=SCHEMA
    )


def downgrade() -> None:
    op.alter_column(
        "skill_versions", "created_by_user_id", nullable=False, schema=SCHEMA
    )
    op.alter_column(
        "skill_versions", "blueprint_version_id", nullable=False, schema=SCHEMA
    )
    op.alter_column("skill_versions", "blueprint_id", nullable=False, schema=SCHEMA)
    op.alter_column("skills", "created_by_user_id", nullable=False, schema=SCHEMA)
    op.alter_column("skills", "blueprint_id", nullable=False, schema=SCHEMA)

    op.drop_index(
        "ix_graph_audit_reports_map_created",
        table_name="graph_audit_reports",
        schema=SCHEMA,
    )
    op.drop_table("graph_audit_reports", schema=SCHEMA)

    op.drop_index(
        "ix_map_expectation_events_map_occurred",
        table_name="map_expectation_events",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_map_expectation_events_expectation",
        table_name="map_expectation_events",
        schema=SCHEMA,
    )
    op.drop_table("map_expectation_events", schema=SCHEMA)

    op.drop_index(
        "ix_map_conflicts_open", table_name="map_conflicts", schema=SCHEMA
    )
    op.drop_constraint(
        "ck_map_conflicts_detection_source_allowed", "map_conflicts",
        schema=SCHEMA, type_="check",
    )
    op.drop_constraint(
        "ck_map_conflicts_kind_allowed", "map_conflicts",
        schema=SCHEMA, type_="check",
    )
    op.drop_column("map_conflicts", "run_id", schema=SCHEMA)
    op.drop_column("map_conflicts", "observed_subject_id", schema=SCHEMA)
    op.drop_column("map_conflicts", "detection_source", schema=SCHEMA)
    op.drop_column("map_conflicts", "conflict_kind", schema=SCHEMA)

    op.drop_index(
        "ix_map_expectations_seeding",
        table_name="map_expectations",
        schema=SCHEMA,
    )
    op.drop_constraint(
        "ck_map_expectations_assertion_origin_allowed", "map_expectations",
        schema=SCHEMA, type_="check",
    )
    op.drop_constraint(
        "ck_map_expectations_assertion_kind_allowed", "map_expectations",
        schema=SCHEMA, type_="check",
    )
    op.drop_constraint(
        "ck_map_expectations_last_check_result_allowed", "map_expectations",
        schema=SCHEMA, type_="check",
    )
    op.drop_column("map_expectations", "last_check_result", schema=SCHEMA)
    op.drop_column("map_expectations", "last_checked_at", schema=SCHEMA)
    op.drop_constraint(
        "fk_map_expectations_superseded_by", "map_expectations",
        schema=SCHEMA, type_="foreignkey",
    )
    op.drop_column("map_expectations", "superseded_by_id", schema=SCHEMA)
    op.drop_column("map_expectations", "promoted_at", schema=SCHEMA)
    op.drop_column("map_expectations", "promoted_by", schema=SCHEMA)
    op.drop_column("map_expectations", "assertion_origin", schema=SCHEMA)
    op.drop_column("map_expectations", "assertion_kind", schema=SCHEMA)
    op.drop_column("map_expectations", "assertion", schema=SCHEMA)

    op.drop_index(
        "ix_app_maps_grounding_poll", table_name="app_maps", schema=SCHEMA
    )
    op.drop_index(
        "uq_app_maps_grounding_single_flight",
        table_name="app_maps",
        schema=SCHEMA,
    )
    op.drop_constraint(
        "ck_app_maps_grounding_status_allowed", "app_maps",
        schema=SCHEMA, type_="check",
    )
    op.drop_column("app_maps", "grounding_failure_site", schema=SCHEMA)
    op.drop_column("app_maps", "grounding_failure_message", schema=SCHEMA)
    op.drop_column("app_maps", "grounding_failure_code", schema=SCHEMA)
    op.drop_column("app_maps", "grounding_completed_at", schema=SCHEMA)
    op.drop_column("app_maps", "grounding_started_at", schema=SCHEMA)
    op.drop_column("app_maps", "grounding_metrics", schema=SCHEMA)
    op.drop_column("app_maps", "grounding_status", schema=SCHEMA)
