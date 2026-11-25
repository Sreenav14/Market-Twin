"""Add phase 3 skill library lifecycle.

Revision ID: b4d8c2e6f107
Revises: 811153077c0e

Doc 22 section 4: skills gain ``skill_kind`` and the graph-scope
name index; skill_versions' lifecycle vocabulary extends to the six
states of section 5.1 (with the section 4.4 value migration), and
the table gains the per-version map binding, heal lineage, replay
rollup and retirement fields; skill_replays gain run provenance;
``knowledge.skill_usage_events`` is created (the per-skill ledger,
section 4.3); a partial unique index backs C1 (one active version
per skill).

The section 4.4 stale guard halts this migration when a ``stale``
row belongs to a non-login skill (the unknown-writer case) instead
of renaming it blind: the DO block raises and the migration
transaction aborts before the stale UPDATE runs.

Downgrade collapses the Phase 3 serving states back onto the old
evidence vocabulary (replay_verified/active/retired -> verified,
suspect -> stale): lossy by design, since the old vocabulary has no
serving axis.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4d8c2e6f107"
down_revision: str | Sequence[str] | None = "811153077c0e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "knowledge"


def upgrade() -> None:
    # -- skills: kind + graph-scope identity (doc 22 section 4.2) --
    op.add_column(
        "skills",
        sa.Column(
            "skill_kind", sa.String(16),
            server_default=sa.text("'journey'"), nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_skills_skill_kind_allowed",
        "skills",
        "skill_kind IN ('journey', 'platform')",
        schema=SCHEMA,
    )
    op.create_index(
        "uq_skills_graph_name",
        "skills",
        ["workspace_id", "application_id", "target_id", "name"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("application_id IS NOT NULL"),
    )

    # -- skill_versions: lifecycle vocabulary + new columns --
    op.drop_constraint(
        "ck_skill_versions_lifecycle_status_allowed",
        "skill_versions",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_skill_versions_lifecycle_status_allowed",
        "skill_versions",
        "lifecycle_status IN ('draft', 'replay_verified', 'active', "
        "'suspect', 'quarantined', 'retired')",
        schema=SCHEMA,
    )
    op.add_column(
        "skill_versions",
        sa.Column("app_map_id", sa.Uuid(), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_skill_versions_workspace_app_map",
        "skill_versions",
        "app_maps",
        ["workspace_id", "app_map_id"],
        ["workspace_id", "id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="RESTRICT",
    )
    op.add_column(
        "skill_versions",
        sa.Column("heal_of_version_id", sa.Uuid(), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_skill_versions_heal_of",
        "skill_versions",
        "skill_versions",
        ["heal_of_version_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="RESTRICT",
    )
    op.add_column(
        "skill_versions",
        sa.Column(
            "replay_count", sa.Integer(),
            server_default=sa.text("0"), nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "skill_versions",
        sa.Column("retired_reason", sa.String(32), nullable=True),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_skill_versions_retired_reason_allowed",
        "skill_versions",
        "retired_reason IS NULL OR retired_reason IN "
        "('superseded', 'journey_absent', 'owner', 'scope_removed')",
        schema=SCHEMA,
    )
    op.add_column(
        "skill_versions",
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    # -- skill_replays: run provenance (doc 22 section 4.2) --
    op.add_column(
        "skill_replays",
        sa.Column("run_id", sa.Uuid(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "skill_replays",
        sa.Column("board_item_ref", sa.String(128), nullable=True),
        schema=SCHEMA,
    )

    # -- skill_usage_events: the per-skill ledger (doc 22 section 4.3) --
    op.create_table(
        "skill_usage_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.Column("skill_version_id", sa.Uuid(), nullable=False),
        sa.Column("app_map_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("job_ref", sa.String(128), nullable=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=True),
        sa.Column(
            "model_calls", sa.Integer(),
            server_default=sa.text("0"), nullable=False,
        ),
        sa.Column(
            "model_tokens", sa.Integer(),
            server_default=sa.text("0"), nullable=False,
        ),
        sa.Column("result", sa.String(16), nullable=True),
        sa.Column(
            "payload", postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('compile', 'verification_replay', 'run_replay', "
            "'heal_attempt', 'heal_diagnosis', 'activation', 'demotion', "
            "'quarantine', 'retirement')",
            name="ck_skill_usage_events_kind_allowed",
        ),
        sa.CheckConstraint(
            "result IS NULL OR "
            "result IN ('passed', 'failed', 'applied', 'refused')",
            name="ck_skill_usage_events_result_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["knowledge.skills.id"], ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["skill_version_id"],
            ["knowledge.skill_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["app_map_id"], ["knowledge.app_maps.id"], ondelete="RESTRICT",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_skill_usage_events_skill_created",
        "skill_usage_events",
        ["skill_id", "created_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_skill_usage_events_version_kind",
        "skill_usage_events",
        ["skill_version_id", "kind"],
        schema=SCHEMA,
    )

    # -- C1 backstop: one active version per skill --
    op.create_index(
        "uq_skill_versions_one_active",
        "skill_versions",
        ["skill_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("lifecycle_status = 'active'"),
    )

    # -- section 4.4 value migration --
    op.execute(
        "UPDATE knowledge.skill_versions "
        "SET lifecycle_status = 'replay_verified' "
        "WHERE lifecycle_status = 'verified'"
    )
    op.execute(
        "UPDATE knowledge.skills SET skill_kind = 'platform' "
        "WHERE name = 'login' AND application_id IS NOT NULL"
    )
    # Stop condition (doc 22 section 4.4): a stale row that is not a
    # login skill is the unknown-writer case -- halt, do not rename.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM knowledge.skill_versions sv
                JOIN knowledge.skills s ON s.id = sv.skill_id
                WHERE sv.lifecycle_status = 'stale'
                  AND NOT (s.name = 'login' AND s.application_id IS NOT NULL)
            ) THEN
                RAISE EXCEPTION 'phase 3 migration halted: stale '
                    'skill_version row on a non-login skill';
            END IF;
        END $$
        """
    )
    op.execute(
        "UPDATE knowledge.skill_versions "
        "SET lifecycle_status = 'suspect' "
        "WHERE lifecycle_status = 'stale'"
    )


def downgrade() -> None:
    # Value reversal first, while the six-state CHECK still admits
    # the source values (see the module docstring for the collapse).
    op.execute(
        "UPDATE knowledge.skill_versions "
        "SET lifecycle_status = 'verified' "
        "WHERE lifecycle_status IN ('replay_verified', 'active', 'retired')"
    )
    op.execute(
        "UPDATE knowledge.skill_versions "
        "SET lifecycle_status = 'stale' "
        "WHERE lifecycle_status = 'suspect'"
    )

    op.drop_index(
        "uq_skill_versions_one_active",
        table_name="skill_versions",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_skill_usage_events_version_kind",
        table_name="skill_usage_events",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_skill_usage_events_skill_created",
        table_name="skill_usage_events",
        schema=SCHEMA,
    )
    op.drop_table("skill_usage_events", schema=SCHEMA)

    op.drop_column("skill_replays", "board_item_ref", schema=SCHEMA)
    op.drop_column("skill_replays", "run_id", schema=SCHEMA)

    op.drop_column("skill_versions", "retired_at", schema=SCHEMA)
    op.drop_constraint(
        "ck_skill_versions_retired_reason_allowed",
        "skill_versions",
        schema=SCHEMA,
    )
    op.drop_column("skill_versions", "retired_reason", schema=SCHEMA)
    op.drop_column("skill_versions", "replay_count", schema=SCHEMA)
    op.drop_constraint(
        "fk_skill_versions_heal_of", "skill_versions", schema=SCHEMA,
    )
    op.drop_column("skill_versions", "heal_of_version_id", schema=SCHEMA)
    op.drop_constraint(
        "fk_skill_versions_workspace_app_map", "skill_versions", schema=SCHEMA,
    )
    op.drop_column("skill_versions", "app_map_id", schema=SCHEMA)
    op.drop_constraint(
        "ck_skill_versions_lifecycle_status_allowed",
        "skill_versions",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_skill_versions_lifecycle_status_allowed",
        "skill_versions",
        "lifecycle_status IN ('draft', 'verified', 'stale', 'quarantined')",
        schema=SCHEMA,
    )

    op.drop_index(
        "uq_skills_graph_name", table_name="skills", schema=SCHEMA,
    )
    op.drop_constraint(
        "ck_skills_skill_kind_allowed", "skills", schema=SCHEMA,
    )
    op.drop_column("skills", "skill_kind", schema=SCHEMA)
