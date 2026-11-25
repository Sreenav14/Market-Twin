from uuid import uuid4

import pytest
from markettwin_control_api.api.test_run_results import (
    build_finding_response,
    build_run_flow,
)
from markettwin_control_api.persistence.repositories import (
    FindingResultRecord,
)


def test_finding_response_includes_evidence() -> None:
    finding_id = uuid4()
    journey_id = uuid4()
    artifact_id = uuid4()

    response = build_finding_response(
        FindingResultRecord(
            finding_id=finding_id,
            severity="high",
            category="journey_outcome",
            title="Checkout failed",
            summary="Checkout did not finish.",
            recommendation="Inspect checkout.",
            status="open",
            journey_ids=(journey_id,),
            step_ids=(12,),
            artifact_ids=(artifact_id,),
        )
    )

    assert response.id == finding_id
    assert response.severity == "high"
    assert response.finding_kind == "not_verified"
    assert response.verification_status == "unverified"

    assert response.journey_ids == [
        journey_id
    ]

    assert response.evidence.step_ids == [
        12
    ]

    assert response.evidence.artifact_ids == [
        artifact_id
    ]


@pytest.mark.parametrize("category,has_visual_evidence,kind,verification", [
    ("cross_persona_pattern", True, "not_verified", "unverified"),
    ("visual_criterion", False, "not_verified", "unverified"),
    ("visual_criterion", True, "observed_product_issue", "verified_visual"),
    ("policy", False, "test_execution_issue", "not_applicable"),
    ("unknown_legacy_category", True, "not_verified", "unverified"),
])
def test_finding_classification_is_independent_of_repetition_and_severity(
    category: str, has_visual_evidence: bool, kind: str, verification: str,
) -> None:
    response = build_finding_response(FindingResultRecord(
        finding_id=uuid4(), severity="high", category=category, title="Reported issue",
        summary="Repeated claim", recommendation=None, status="open",
        journey_ids=(uuid4(), uuid4()),
        step_ids=(7,), artifact_ids=(uuid4(),), has_visual_evidence=has_visual_evidence,
    ))
    assert response.finding_kind == kind
    assert response.verification_status == verification
    if category == "cross_persona_pattern":
        assert response.severity == "info"

def _meta_label(**kwargs) -> str:
    flow = build_run_flow(
        run_status="completed",
        journeys=[],
        collected=True,
        report_status="completed",
        **kwargs,
    )
    return next(node["label"] for node in flow["nodes"] if node["kind"] == "meta")


def test_run_flow_labels_the_plan_node_by_run_kind() -> None:
    # Unified runs never carry execution_mode in their snapshot (creation
    # rejects the retired field), so the plan node must be labelled from
    # the run kind, never with the retired legacy label.
    assert _meta_label(run_kind="explore_test") == "Test plan"
    assert _meta_label(run_kind="persona") == "Test plan"
    assert _meta_label(run_kind="slop") == "Audit scope"
    # Legacy shapes keep their labels: deep runs planned a feature plan,
    # and a caller with no kind information keeps the legacy default.
    assert _meta_label(execution_mode="deep_feature_v1", run_kind="explore_test") == "Feature plan"
    assert _meta_label() == "Meta Agent"
