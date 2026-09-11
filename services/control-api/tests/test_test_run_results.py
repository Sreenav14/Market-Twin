from uuid import uuid4

from markettwin_control_api.api.test_run_results import (
    build_finding_response,
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

    assert response.journey_ids == [
        journey_id
    ]

    assert response.evidence.step_ids == [
        12
    ]

    assert response.evidence.artifact_ids == [
        artifact_id
    ]