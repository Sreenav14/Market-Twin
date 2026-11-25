"""Add the 'task' skill kind (doc 29 section 3.1).

The task-skill pipeline stores learned task skills in the same
registry as journeys and platform skills; the skills.skill_kind
check constraint only allowed 'journey' | 'platform'. Widen the
allowed set with 'task'; downgrade restores the Phase 3 set.
"""

from alembic import op

revision = "a4c8e7d2b915"
down_revision = "d51b8e3f2a47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_skills_skill_kind_allowed",
        "skills",
        schema="knowledge",
        type_="check",
    )
    op.create_check_constraint(
        "ck_skills_skill_kind_allowed",
        "skills",
        "skill_kind IN ('journey', 'platform', 'task')",
        schema="knowledge",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_skills_skill_kind_allowed",
        "skills",
        schema="knowledge",
        type_="check",
    )
    op.create_check_constraint(
        "ck_skills_skill_kind_allowed",
        "skills",
        "skill_kind IN ('journey', 'platform')",
        schema="knowledge",
    )
