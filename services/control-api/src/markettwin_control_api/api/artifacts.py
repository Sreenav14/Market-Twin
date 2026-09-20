"""Secure access endpoints for MarketTwin evidence artifacts."""

from uuid import UUID

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    status,
)
from pydantic import BaseModel

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import (
    get_authenticated_user_id,
)
from markettwin_control_api.config import get_settings
from markettwin_control_api.evidence.artifact_url_signer import (
    DEFAULT_ARTIFACT_TTL_SECONDS,
    ArtifactUrlSigner,
)
from markettwin_control_api.persistence.repositories.artifact_access_repository import (
    ArtifactAccessRepository,
)
from markettwin_control_api.persistence.repositories.test_run_repository import (
    TestRunRepository,
)

router = APIRouter(
    tags=["Artifacts"],
)


class ArtifactAccessResponse(BaseModel):
    """Temporary browser access to one private evidence artifact."""

    artifact_id: UUID
    artifact_type: str
    content_type: str
    url: str
    expires_in_seconds: int


@router.get(
    "/api/v1/test-runs/{test_run_id}/artifacts/{artifact_id}/access",
    response_model=ArtifactAccessResponse,
)
async def get_artifact_access(
    test_run_id: UUID,
    artifact_id: UUID,
    request: Request,
) -> ArtifactAccessResponse:
    """Return a short-lived URL for an authorized evidence artifact."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        test_run_repository = TestRunRepository(
            database_session
        )

        test_run = await test_run_repository.get_for_user(
            test_run_id=test_run_id,
            user_id=user_id,
        )

        if test_run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test run not found.",
            )

        artifact_repository = ArtifactAccessRepository(
            database_session
        )

        artifact = await artifact_repository.get_for_test_run(
            artifact_id=artifact_id,
            test_run_id=test_run_id,
        )

        if artifact is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Artifact not found.",
            )

    settings = get_settings()

    signer = ArtifactUrlSigner(
        region=settings.s3_region,
        endpoint_url=settings.s3_endpoint_url or None,
    )

    url = signer.create_download_url(
        bucket=artifact.bucket,
        object_key=artifact.object_key,
    )

    return ArtifactAccessResponse(
        artifact_id=artifact.artifact_id,
        artifact_type=artifact.artifact_type,
        content_type=artifact.content_type,
        url=url,
        expires_in_seconds=DEFAULT_ARTIFACT_TTL_SECONDS,
    )