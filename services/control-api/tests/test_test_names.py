"""Test names stay separate from goals; test numbers are assigned by PostgreSQL."""

from uuid import uuid4

import pytest
from markettwin_control_api.api.test_run import CreateTestRunRequest
from markettwin_database.models import TestRun as RunModel
from pydantic import ValidationError
from sqlalchemy import Identity
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable


def test_custom_name_is_trimmed_without_changing_goal():
    payload = CreateTestRunRequest(target_id=uuid4(), name="  Pricing clarity  ",
                                   study_brief="Choose the correct plan as a new customer")
    assert payload.name == "Pricing clarity"
    assert payload.study_brief == "Choose the correct plan as a new customer"


@pytest.mark.parametrize("name", ["", "   ", "a" * 81])
def test_blank_or_overlong_names_are_rejected(name):
    with pytest.raises(ValidationError):
        CreateTestRunRequest(target_id=uuid4(), name=name, study_brief="A valid testing goal")


def test_legacy_creation_can_omit_a_name_and_database_assigns_number():
    assert CreateTestRunRequest(target_id=uuid4(), study_brief="A valid testing goal").name is None
    column = RunModel.__table__.c.test_number
    assert isinstance(column.identity, Identity)
    assert column.identity.always
    ddl = str(CreateTable(RunModel.__table__).compile(dialect=postgresql.dialect()))
    assert "GENERATED ALWAYS AS IDENTITY" in ddl
    assert "UNIQUE (test_number)" in ddl
