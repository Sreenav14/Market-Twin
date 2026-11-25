"""Pin model invariants already enforced by production migrations."""

from markettwin_database.models.execution import ExecutionPauseRequest
from markettwin_database.models.knowledge import SkillVersion


def test_pause_requests_are_already_nonnullable():
    for name in ("test_run_id", "journey_id", "requested_by_user_id"):
        assert ExecutionPauseRequest.__table__.c[name].nullable is False


def test_skill_definition_is_required_and_only_one_version_can_be_active():
    assert SkillVersion.__table__.c.definition_json.nullable is False
    index = next(i for i in SkillVersion.__table__.indexes if i.name == "uq_skill_versions_one_active")
    assert index.unique
    assert [column.name for column in index.columns] == ["skill_id"]
    assert str(index.dialect_options["postgresql"]["where"]) == "lifecycle_status = 'active'"
