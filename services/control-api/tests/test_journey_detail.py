"""Authorized, bounded journey reads and safe execution summaries."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from markettwin_control_api.api import test_run_results
from markettwin_control_api.persistence.repositories.test_run_results_repository import (
    TestRunResultsRepository as Repository,
)
from markettwin_control_api.persistence.repositories.test_run_results_repository import (
    _safe_action_summary,
    _safe_observation_summary,
    _safe_policy_diagnostic,
)


class Context:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_):
        return False


@pytest.mark.parametrize("accessible,owned", [(False, False), (True, False), (True, True)])
async def test_detail_authorizes_run_then_checks_journey(monkeypatch, accessible, owned):
    run_id, journey_id, user_id = uuid4(), uuid4(), uuid4()
    called = []

    async def authenticate(**_):
        return user_id

    async def get_run(**kwargs):
        assert kwargs == {"test_run_id": run_id, "user_id": user_id}
        return object() if accessible else None

    async def get_journey(**kwargs):
        called.append(kwargs)
        if not owned:
            return None
        return {"journey": {
            "id": journey_id, "ordinal": 1, "persona_name": "Customer",
            "persona_perspective": "New customer", "mission_title": "Checkout",
            "mission_objective": "Complete an order", "success_criteria": ["Order recorded"],
            "step_count": 0, "artifact_count": 0, "evidence_available": False,
            "summary": None, "execution_id": None, "attempt_number": None,
            "execution_status": None, "outcome": None, "started_at": None,
            "completed_at": None, "error_message": None, "result": None,
        }, "steps": [], "artifacts": [], "findings": (),
            "artifacts_truncated": False, "next_after_step": None}

    monkeypatch.setattr(test_run_results, "get_authenticated_user_id", authenticate)
    monkeypatch.setattr(test_run_results, "get_database_runtime", lambda _: SimpleNamespace(
        session_factory=Context,
    ))
    monkeypatch.setattr(test_run_results, "TestRunRepository", lambda _: SimpleNamespace(
        get_for_user=get_run,
    ))
    monkeypatch.setattr(test_run_results, "TestRunResultsRepository", lambda _: SimpleNamespace(
        get_journey=get_journey,
    ))
    if accessible and owned:
        result = await test_run_results.get_test_run_journey(
            run_id, journey_id, SimpleNamespace(), after_step=0, limit=50,
        )
        assert result.journey.id == journey_id
        assert result.steps == []
        assert not result.journey.evidence_available
    else:
        with pytest.raises(HTTPException) as error:
            await test_run_results.get_test_run_journey(
                run_id, journey_id, SimpleNamespace(), after_step=0, limit=50,
            )
        assert error.value.status_code == 404
    assert bool(called) == accessible
    if called:
        assert called[0]["test_run_id"] == run_id
        assert called[0]["journey_id"] == journey_id


async def test_detail_pages_only_latest_attempt_and_returns_no_storage_details(monkeypatch):
    run_id, journey_id, execution_id = uuid4(), uuid4(), uuid4()
    statements = []
    steps = [SimpleNamespace(
        id=index, step_number=index, action_type="fill", action_summary="secret-input",
        observation_summary="secret exception", status="failed", started_at=None,
        completed_at=None,
    ) for index in (11, 12, 13)]
    artifact = SimpleNamespace(
        id=uuid4(), step_id=11, execution_id=execution_id, artifact_type="screenshot",
        content_type="image/png", size_bytes=1, created_at=None,
        metadata_json={"kind": "viewport", "private": "secret"},
        bucket="private-bucket", object_key="private-key",
    )

    class Session:
        async def scalars(self, statement):
            statements.append(statement)
            return SimpleNamespace(all=lambda: [artifact] if "evidence.artifacts" in
                                   str(statement) else steps)

    repository = Repository(Session())

    async def list_journeys(**kwargs):
        assert kwargs == {"test_run_id": run_id, "journey_id": journey_id}
        return [{"id": journey_id, "execution_id": execution_id}]

    async def results(**_):
        return None

    monkeypatch.setattr(repository, "list_journeys", list_journeys)
    monkeypatch.setattr(repository, "get_completed_results", results)
    detail = await repository.get_journey(
        test_run_id=run_id, journey_id=journey_id, after_step=10, limit=2,
    )
    assert [step["step_number"] for step in detail["steps"]] == [11, 12]
    assert detail["next_after_step"] == 12
    assert "ORDER BY" in str(statements[0])
    assert execution_id in statements[0].compile().params.values()
    assert 10 in statements[0].compile().params.values()
    assert 3 in statements[0].compile().params.values()
    assert detail["artifacts"][0]["id"] == artifact.id
    assert "bucket" not in detail["artifacts"][0]
    assert "object_key" not in detail["artifacts"][0]
    assert "secret" not in str(detail)


def test_safe_summaries_exclude_filled_values_exception_text_and_url_secrets():
    step = SimpleNamespace(action_type="fill", action_summary="password=secret",
                           status="failed", observation_summary="token=secret")
    assert "secret" not in _safe_action_summary(step)
    assert "secret" not in _safe_observation_summary(step)
    step.status = "completed"
    step.observation_summary = (
        "url=https://user:secret@example.test/private-user?token=secret;"
        "console_errors=1;page_errors=0;failed_requests=2;screenshot=yes"
    )
    summary = _safe_observation_summary(step)
    assert "https://example.test" in summary
    assert "console errors: 1" in summary
    assert "secret" not in summary and "private-user" not in summary


def test_structured_assertions_are_readable_only_for_the_owned_step():
    import json

    from markettwin_shared.deep_testing import AssertionResult

    execution_id = uuid4()
    assertion = AssertionResult(
        case_id="navigation", assertion_id="title", oracle="title",
        expected_value="Guide", observed_value="Guide", status="satisfied",
        execution_id=execution_id, step_id=12, artifact_ids=(uuid4(),),
        origin="inferred", elapsed_ms=1,
    )
    step = SimpleNamespace(
        id=12, execution_id=execution_id, action_type="assertion", status="completed",
        observation_summary=assertion.model_dump_json(),
    )
    summary = json.loads(_safe_observation_summary(step))
    assert summary["expected_value"] == "Guide"
    assert summary["observed_value"] == "Guide"
    step.execution_id = uuid4()
    assert "Guide" not in _safe_observation_summary(step)
    step.observation_summary = '{"input": "unreviewed-secret"}'
    assert "unreviewed-secret" not in _safe_observation_summary(step)


def test_denied_origin_is_structured_without_exposing_raw_errors_or_url_credentials():
    expected = {
        "reason_code": "origin_not_authorized",
        "requested_origin": "https://console.example.test",
    }
    assert _safe_policy_diagnostic(
        'Target origin "https://console.example.test" is not allowed.'
    ) == expected
    for value in (
        'Target origin "https://user:secret@example.test" is not allowed.',
        'Target origin "https://example.test?token=secret" is not allowed.',
        'Target origin "https://example.test/private" is not allowed.',
        'Unexpected error secret',
    ):
        assert _safe_policy_diagnostic(value) is None


async def test_skipped_journey_message_does_not_claim_browser_or_policy_failure():
    from unittest.mock import AsyncMock

    journey_id, execution_id = uuid4(), uuid4()
    execution = SimpleNamespace(
        id=execution_id, journey_id=journey_id, attempt_number=1, status="skipped", outcome=None,
        started_at=None, completed_at=None, error_message="secret raw exception",
    )
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[
            SimpleNamespace(all=lambda: [(
                SimpleNamespace(id=journey_id, ordinal=1), "Persona", "Perspective", "Mission",
                "Objective", ["Criterion"],
            )]), SimpleNamespace(all=lambda: []), SimpleNamespace(all=lambda: []),
        ]),
        scalars=AsyncMock(side_effect=[
            SimpleNamespace(all=lambda: [execution]), SimpleNamespace(all=lambda: []),
        ]),
    )
    rows = await Repository(session).list_journeys(test_run_id=uuid4())
    assert rows[0]["error_message"] == "Not tested\u2014human assistance skipped."
    assert rows[0]["outcome"] is None
    assert "secret" not in str(rows)
