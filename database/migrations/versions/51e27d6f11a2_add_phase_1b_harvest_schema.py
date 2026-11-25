"""Add phase 1b harvest schema.

Revision ID: 51e27d6f11a2
Revises: dca08ed17e84
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "51e27d6f11a2"
down_revision: str | Sequence[str] | None = "dca08ed17e84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    ]


def _keys() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("app_map_id", sa.Uuid(), nullable=False),
    ]


def _fk_app_map() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id", "app_map_id"],
        ["knowledge.app_maps.workspace_id", "knowledge.app_maps.id"],
        ondelete="RESTRICT",
    )


def _fk_map_page() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id", "map_page_id"],
        ["knowledge.map_pages.workspace_id", "knowledge.map_pages.id"],
        ondelete="RESTRICT",
    )


def _trio() -> list[sa.Column]:
    return [
        sa.Column(
            "source", sa.String(length=32),
            server_default=sa.text("'harvest'"), nullable=False,
        ),
        sa.Column(
            "confidence", sa.String(length=8),
            server_default=sa.text("'low'"), nullable=False,
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _confidence_check(table: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        "confidence IN ('high', 'medium', 'low')",
        name=f"ck_{table}_confidence_allowed",
    )


def upgrade() -> None:
    # 1. app_maps: harvest lifecycle + budget columns, poll index,
    #    harvest single-flight partial unique index.
    op.add_column(
        "app_maps",
        sa.Column(
            "harvest_status", sa.String(length=16),
            server_default=sa.text("'not_started'"), nullable=False,
        ),
        schema="knowledge",
    )
    op.add_column(
        "app_maps",
        sa.Column(
            "harvest_metrics", postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        schema="knowledge",
    )
    op.add_column(
        "app_maps",
        sa.Column("harvest_started_at", sa.DateTime(timezone=True), nullable=True),
        schema="knowledge",
    )
    op.add_column(
        "app_maps",
        sa.Column("harvest_completed_at", sa.DateTime(timezone=True), nullable=True),
        schema="knowledge",
    )
    op.add_column(
        "app_maps",
        sa.Column("harvest_failure_code", sa.String(length=64), nullable=True),
        schema="knowledge",
    )
    op.add_column(
        "app_maps",
        sa.Column("harvest_failure_message", sa.Text(), nullable=True),
        schema="knowledge",
    )
    op.add_column(
        "app_maps",
        sa.Column("harvest_failure_site", sa.String(length=128), nullable=True),
        schema="knowledge",
    )
    op.add_column(
        "app_maps",
        sa.Column("mapping_budget_tokens", sa.Integer(), nullable=True),
        schema="knowledge",
    )
    op.create_check_constraint(
        "ck_app_maps_harvest_status_allowed",
        "app_maps",
        "harvest_status IN ('not_started', 'building', 'ready', 'partial', 'failed')",
        schema="knowledge",
    )
    op.create_index(
        "ix_app_maps_harvest_poll", "app_maps",
        ["harvest_status", "harvest_started_at"], schema="knowledge",
    )
    op.create_index(
        "uq_app_maps_harvest_single_flight", "app_maps",
        ["application_id", "target_id"], unique=True, schema="knowledge",
        postgresql_where=sa.text("harvest_status = 'building'"),
    )

    # 2. map_pages: harvest outcome + enrichment columns.
    op.add_column(
        "map_pages",
        sa.Column(
            "harvest_status", sa.String(length=24),
            server_default=sa.text("'pending'"), nullable=False,
        ),
        schema="knowledge",
    )
    op.add_column(
        "map_pages",
        sa.Column("template_group", sa.String(length=128), nullable=True),
        schema="knowledge",
    )
    op.add_column(
        "map_pages",
        sa.Column("purpose", sa.Text(), nullable=True),
        schema="knowledge",
    )
    op.add_column(
        "map_pages",
        sa.Column("purpose_source", sa.String(length=16), nullable=True),
        schema="knowledge",
    )
    op.add_column(
        "map_pages",
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=True),
        schema="knowledge",
    )
    op.create_check_constraint(
        "ck_map_pages_harvest_status_allowed",
        "map_pages",
        "harvest_status IN ('pending', 'visited', 'blocked_auth', 'blocked_wall', "
        "'failed', 'unprobed_budget')",
        schema="knowledge",
    )
    op.create_check_constraint(
        "ck_map_pages_purpose_source_allowed",
        "map_pages",
        "purpose_source IS NULL OR purpose_source IN "
        "('documentation', 'owner-rule', 'observation', 'model-draft')",
        schema="knowledge",
    )
    op.create_index(
        "ix_map_pages_harvest", "map_pages",
        ["app_map_id", "harvest_status"], schema="knowledge",
    )

    # 3. map_page_states: fingerprint hash columns.
    for column in ("dom_structure_hash", "aria_hash", "screenshot_hash"):
        op.add_column(
            "map_page_states",
            sa.Column(column, sa.String(length=64), nullable=True),
            schema="knowledge",
        )

    # 4. skills: graph scope columns + composite FK to app_maps.
    op.add_column(
        "skills",
        sa.Column("application_id", sa.Uuid(), nullable=True),
        schema="knowledge",
    )
    op.add_column(
        "skills",
        sa.Column("target_id", sa.Uuid(), nullable=True),
        schema="knowledge",
    )
    op.add_column(
        "skills",
        sa.Column("app_map_id", sa.Uuid(), nullable=True),
        schema="knowledge",
    )
    op.create_foreign_key(
        "fk_skills_workspace_app_map",
        "skills",
        "app_maps",
        ["workspace_id", "app_map_id"],
        ["workspace_id", "id"],
        source_schema="knowledge",
        referent_schema="knowledge",
        ondelete="RESTRICT",
    )

    # 5. skill_versions: lifecycle + package + replay columns.
    op.add_column(
        "skill_versions",
        sa.Column(
            "lifecycle_status", sa.String(length=16),
            server_default=sa.text("'draft'"), nullable=False,
        ),
        schema="knowledge",
    )
    op.add_column(
        "skill_versions",
        sa.Column(
            "package", postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        schema="knowledge",
    )
    op.add_column(
        "skill_versions",
        sa.Column(
            "verified_fingerprint", postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        schema="knowledge",
    )
    op.add_column(
        "skill_versions",
        sa.Column("last_replay_result", sa.String(length=8), nullable=True),
        schema="knowledge",
    )
    op.add_column(
        "skill_versions",
        sa.Column("last_replay_at", sa.DateTime(timezone=True), nullable=True),
        schema="knowledge",
    )
    op.add_column(
        "skill_versions",
        sa.Column(
            "heal_count", sa.Integer(), server_default=sa.text("0"), nullable=False,
        ),
        schema="knowledge",
    )
    op.create_check_constraint(
        "ck_skill_versions_lifecycle_status_allowed",
        "skill_versions",
        "lifecycle_status IN ('draft', 'verified', 'stale', 'quarantined')",
        schema="knowledge",
    )
    op.create_check_constraint(
        "ck_skill_versions_last_replay_result_allowed",
        "skill_versions",
        "last_replay_result IS NULL OR last_replay_result IN ('passed', 'failed')",
        schema="knowledge",
    )

    # 6. map_elements.
    op.create_table(
        "map_elements",
        *_keys(),
        sa.Column("map_page_id", sa.Uuid(), nullable=False),
        sa.Column("map_page_state_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "ordinal", sa.Integer(), server_default=sa.text("0"), nullable=False,
        ),
        sa.Column("label_text", sa.Text(), nullable=True),
        sa.Column("actionability", sa.String(length=16), nullable=False),
        sa.Column(
            "locators", postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column("safety_class", sa.String(length=16), nullable=False),
        sa.Column("navigates_to_url", sa.Text(), nullable=True),
        sa.Column("opens_state_key", sa.Text(), nullable=True),
        *_trio(),
        *_timestamps(),
        sa.CheckConstraint(
            "actionability IN ('click', 'fill', 'select', 'check', 'press', "
            "'toggle', 'readonly')",
            name="ck_map_elements_actionability_allowed",
        ),
        sa.CheckConstraint(
            "safety_class IN ('read', 'reversible', 'irreversible', 'unknown')",
            name="ck_map_elements_safety_class_allowed",
        ),
        _confidence_check("map_elements"),
        sa.UniqueConstraint(
            "map_page_state_id", "role", "name", "ordinal",
            name="uq_map_elements_identity",
        ),
        _fk_app_map(),
        _fk_map_page(),
        sa.ForeignKeyConstraint(
            ["map_page_state_id"], ["knowledge.map_page_states.id"],
            ondelete="RESTRICT",
        ),
        schema="knowledge",
    )
    op.create_index(
        "ix_map_elements_map_page", "map_elements",
        ["app_map_id", "map_page_id"], schema="knowledge",
    )
    op.create_index(
        "ix_map_elements_state", "map_elements",
        ["map_page_state_id"], schema="knowledge",
    )

    # 7. map_transitions (before map_forms: forms reference transitions).
    op.create_table(
        "map_transitions",
        *_keys(),
        sa.Column("from_state_id", sa.Uuid(), nullable=False),
        sa.Column("to_state_id", sa.Uuid(), nullable=False),
        sa.Column("via_element_id", sa.Uuid(), nullable=True),
        sa.Column("via_action", sa.String(length=32), nullable=False),
        sa.Column(
            "observed_count", sa.Integer(),
            server_default=sa.text("1"), nullable=False,
        ),
        *_trio(),
        *_timestamps(),
        _confidence_check("map_transitions"),
        sa.UniqueConstraint(
            "from_state_id", "via_element_id", "to_state_id",
            name="uq_map_transitions_edge",
        ),
        _fk_app_map(),
        sa.ForeignKeyConstraint(
            ["from_state_id"], ["knowledge.map_page_states.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["to_state_id"], ["knowledge.map_page_states.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["via_element_id"], ["knowledge.map_elements.id"],
            ondelete="RESTRICT",
        ),
        schema="knowledge",
    )

    # 8. map_forms.
    op.create_table(
        "map_forms",
        *_keys(),
        sa.Column("map_page_id", sa.Uuid(), nullable=False),
        sa.Column("map_page_state_id", sa.Uuid(), nullable=False),
        sa.Column("form_key", sa.String(length=32), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=True),
        sa.Column("action_url", sa.Text(), nullable=True),
        sa.Column("submit_element_id", sa.Uuid(), nullable=True),
        sa.Column("success_transition_id", sa.Uuid(), nullable=True),
        sa.Column(
            "probe_status", sa.String(length=32),
            server_default=sa.text("'unprobed_readonly'"), nullable=False,
        ),
        *_trio(),
        *_timestamps(),
        sa.CheckConstraint(
            "probe_status IN ('unprobed_readonly', 'unprobed_destructive', 'probed')",
            name="ck_map_forms_probe_status_allowed",
        ),
        _confidence_check("map_forms"),
        sa.UniqueConstraint(
            "map_page_state_id", "form_key", name="uq_map_forms_key",
        ),
        _fk_app_map(),
        _fk_map_page(),
        sa.ForeignKeyConstraint(
            ["map_page_state_id"], ["knowledge.map_page_states.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["submit_element_id"], ["knowledge.map_elements.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["success_transition_id"], ["knowledge.map_transitions.id"],
            ondelete="RESTRICT",
        ),
        schema="knowledge",
    )

    # 9. map_fields.
    op.create_table(
        "map_fields",
        *_keys(),
        sa.Column("form_id", sa.Uuid(), nullable=False),
        sa.Column("element_id", sa.Uuid(), nullable=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("field_type", sa.String(length=32), nullable=False),
        sa.Column("name_attr", sa.String(length=128), nullable=True),
        sa.Column(
            "required", sa.Boolean(),
            server_default=sa.text("false"), nullable=False,
        ),
        sa.Column(
            "constraints", postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            "options", postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column("help_text", sa.Text(), nullable=True),
        sa.Column("error_text_observed", sa.Text(), nullable=True),
        sa.Column(
            "validation_source", sa.String(length=8),
            server_default=sa.text("'dom'"), nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        *_trio(),
        *_timestamps(),
        sa.CheckConstraint(
            "validation_source IN ('dom', 'probed', 'doc')",
            name="ck_map_fields_validation_source_allowed",
        ),
        _confidence_check("map_fields"),
        sa.UniqueConstraint("form_id", "ordinal", name="uq_map_fields_ordinal"),
        _fk_app_map(),
        sa.ForeignKeyConstraint(
            ["form_id"], ["knowledge.map_forms.id"], ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["element_id"], ["knowledge.map_elements.id"], ondelete="RESTRICT",
        ),
        schema="knowledge",
    )

    # 10. map_journeys.
    op.create_table(
        "map_journeys",
        *_keys(),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("intent", sa.Text(), nullable=True),
        sa.Column(
            "preconditions", postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            "steps", postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column("success_state_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=True),
        sa.Column("selection", sa.String(length=8), nullable=False),
        *_trio(),
        *_timestamps(),
        sa.CheckConstraint(
            "selection IN ('rule', 'owner')",
            name="ck_map_journeys_selection_allowed",
        ),
        _confidence_check("map_journeys"),
        _fk_app_map(),
        sa.ForeignKeyConstraint(
            ["success_state_id"], ["knowledge.map_page_states.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["knowledge.skills.id"], ondelete="RESTRICT",
        ),
        schema="knowledge",
    )

    # 11. map_expectations (no FK on the polymorphic subject_id, deliberate).
    op.create_table(
        "map_expectations",
        *_keys(),
        sa.Column("subject_kind", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("oracle_source", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column(
            "confidence", sa.String(length=8),
            server_default=sa.text("'low'"), nullable=False,
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "subject_kind IN ('page', 'element', 'journey', 'field', 'form')",
            name="ck_map_expectations_subject_kind_allowed",
        ),
        sa.CheckConstraint(
            "oracle_source IN ('documentation', 'owner-rule', 'observation', "
            "'model-draft')",
            name="ck_map_expectations_oracle_source_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('unverified', 'replay-verified', 'conflicted', "
            "'owner-confirmed')",
            name="ck_map_expectations_status_allowed",
        ),
        _confidence_check("map_expectations"),
        _fk_app_map(),
        schema="knowledge",
    )
    op.create_index(
        "ix_map_expectations_subject", "map_expectations",
        ["app_map_id", "subject_kind", "subject_id"], schema="knowledge",
    )

    # 12. map_conflicts.
    op.create_table(
        "map_conflicts",
        *_keys(),
        sa.Column("expectation_id", sa.Uuid(), nullable=False),
        sa.Column("observed_behaviour", sa.Text(), nullable=False),
        sa.Column(
            "evidence_refs", postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=8),
            server_default=sa.text("'open'"), nullable=False,
        ),
        sa.Column("resolution", sa.String(length=16), nullable=True),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('open', 'resolved')",
            name="ck_map_conflicts_status_allowed",
        ),
        sa.CheckConstraint(
            "resolution IS NULL OR resolution IN ('docs-win', 'app-win', "
            "'owner-decided')",
            name="ck_map_conflicts_resolution_allowed",
        ),
        _fk_app_map(),
        sa.ForeignKeyConstraint(
            ["expectation_id"], ["knowledge.map_expectations.id"],
            ondelete="RESTRICT",
        ),
        schema="knowledge",
    )

    # 13. map_evidence_objects.
    op.create_table(
        "map_evidence_objects",
        *_keys(),
        sa.Column("map_page_id", sa.Uuid(), nullable=False),
        sa.Column("map_page_state_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("viewport", sa.String(length=16), nullable=True),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("redaction_status", sa.String(length=16), nullable=False),
        sa.Column(
            "redaction_count", sa.Integer(),
            server_default=sa.text("0"), nullable=False,
        ),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "kind IN ('aria_snapshot', 'element_inventory', 'form_inventory', "
            "'harvest_har', 'screenshot', 'console_log', 'transition_log')",
            name="ck_map_evidence_objects_kind_allowed",
        ),
        sa.CheckConstraint(
            "redaction_status IN ('redacted', 'not_applicable', 'dropped')",
            name="ck_map_evidence_objects_redaction_status_allowed",
        ),
        _fk_app_map(),
        _fk_map_page(),
        sa.ForeignKeyConstraint(
            ["map_page_state_id"], ["knowledge.map_page_states.id"],
            ondelete="RESTRICT",
        ),
        schema="knowledge",
    )
    op.create_index(
        "ix_map_evidence_objects_page_kind", "map_evidence_objects",
        ["app_map_id", "map_page_id", "kind"], schema="knowledge",
    )

    # 14. skill_replays.
    op.create_table(
        "skill_replays",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("skill_version_id", sa.Uuid(), nullable=False),
        sa.Column("app_map_id", sa.Uuid(), nullable=False),
        sa.Column("result", sa.String(length=8), nullable=False),
        sa.Column("failure_step", sa.Integer(), nullable=True),
        sa.Column("failure_site", sa.String(length=128), nullable=True),
        sa.Column(
            "heal_cycle", sa.Integer(), server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "context_kind", sa.String(length=8),
            server_default=sa.text("'clean'"), nullable=False,
        ),
        sa.Column(
            "model_calls", sa.Integer(), server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "result IN ('passed', 'failed')",
            name="ck_skill_replays_result_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["skill_version_id"], ["knowledge.skill_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["app_map_id"], ["knowledge.app_maps.id"], ondelete="RESTRICT",
        ),
        schema="knowledge",
    )

    # 15. map_harvest_events.
    op.create_table(
        "map_harvest_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("app_map_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["app_map_id"], ["knowledge.app_maps.id"], ondelete="RESTRICT",
        ),
        schema="knowledge",
    )
    op.create_index(
        "ix_map_harvest_events_map_occurred", "map_harvest_events",
        ["app_map_id", "occurred_at"], schema="knowledge",
    )


def downgrade() -> None:
    # Exact reverse of upgrade().
    op.drop_index(
        "ix_map_harvest_events_map_occurred",
        table_name="map_harvest_events", schema="knowledge",
    )
    op.drop_table("map_harvest_events", schema="knowledge")
    op.drop_table("skill_replays", schema="knowledge")
    op.drop_index(
        "ix_map_evidence_objects_page_kind",
        table_name="map_evidence_objects", schema="knowledge",
    )
    op.drop_table("map_evidence_objects", schema="knowledge")
    op.drop_table("map_conflicts", schema="knowledge")
    op.drop_index(
        "ix_map_expectations_subject",
        table_name="map_expectations", schema="knowledge",
    )
    op.drop_table("map_expectations", schema="knowledge")
    op.drop_table("map_journeys", schema="knowledge")
    op.drop_table("map_fields", schema="knowledge")
    op.drop_table("map_forms", schema="knowledge")
    op.drop_table("map_transitions", schema="knowledge")
    op.drop_index(
        "ix_map_elements_state", table_name="map_elements", schema="knowledge",
    )
    op.drop_index(
        "ix_map_elements_map_page", table_name="map_elements", schema="knowledge",
    )
    op.drop_table("map_elements", schema="knowledge")

    op.drop_constraint(
        "ck_skill_versions_last_replay_result_allowed",
        "skill_versions", schema="knowledge",
    )
    op.drop_constraint(
        "ck_skill_versions_lifecycle_status_allowed",
        "skill_versions", schema="knowledge",
    )
    for column in (
        "heal_count", "last_replay_at", "last_replay_result",
        "verified_fingerprint", "package", "lifecycle_status",
    ):
        op.drop_column("skill_versions", column, schema="knowledge")

    op.drop_constraint(
        "fk_skills_workspace_app_map", "skills", schema="knowledge",
    )
    for column in ("app_map_id", "target_id", "application_id"):
        op.drop_column("skills", column, schema="knowledge")

    for column in ("screenshot_hash", "aria_hash", "dom_structure_hash"):
        op.drop_column("map_page_states", column, schema="knowledge")

    op.drop_index(
        "ix_map_pages_harvest", table_name="map_pages", schema="knowledge",
    )
    op.drop_constraint(
        "ck_map_pages_purpose_source_allowed", "map_pages", schema="knowledge",
    )
    op.drop_constraint(
        "ck_map_pages_harvest_status_allowed", "map_pages", schema="knowledge",
    )
    for column in (
        "enriched_at", "purpose_source", "purpose", "template_group",
        "harvest_status",
    ):
        op.drop_column("map_pages", column, schema="knowledge")

    op.drop_index(
        "uq_app_maps_harvest_single_flight",
        table_name="app_maps", schema="knowledge",
    )
    op.drop_index(
        "ix_app_maps_harvest_poll", table_name="app_maps", schema="knowledge",
    )
    op.drop_constraint(
        "ck_app_maps_harvest_status_allowed", "app_maps", schema="knowledge",
    )
    for column in (
        "mapping_budget_tokens", "harvest_failure_site",
        "harvest_failure_message", "harvest_failure_code",
        "harvest_completed_at", "harvest_started_at", "harvest_metrics",
        "harvest_status",
    ):
        op.drop_column("app_maps", column, schema="knowledge")
