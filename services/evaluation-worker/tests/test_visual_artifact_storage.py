"""Tests for visual artifact storage."""

from pathlib import Path
from uuid import uuid4

import pytest
from markettwin_evaluation_worker.persistence.evaluation_repository import (
    VisualArtifactRecord,
)
from markettwin_evaluation_worker.visual_artifact_storage import (
    VisualArtifactStorage,
)


class FakeS3Client:
    def __init__(self) -> None:
        self.downloads: list[
            tuple[str, str, str]
        ] = []

    def download_file(
        self,
        Bucket: str,
        Key: str,
        Filename: str,
    ) -> None:
        self.downloads.append(
            (
                Bucket,
                Key,
                Filename,
            )
        )

        Path(Filename).write_bytes(
            b"fake-png-bytes"
        )


@pytest.mark.asyncio
async def test_download_uses_exact_artifact_location(
    tmp_path: Path,
) -> None:
    """Evaluation must download the exact DB-selected object."""

    artifact_id = uuid4()

    artifact = VisualArtifactRecord(
        artifact_id=artifact_id,
        step_id=7,
        kind="element_crop",
        storage_provider="minio",
        bucket="markettwin",
        object_key=(
            "executions/test/steps/7/"
            "action-0007-element.png"
        ),
        content_type="image/png",
    )

    client = FakeS3Client()

    storage = VisualArtifactStorage(
        region="us-east-1",
        endpoint_url="http://localhost:9000",
        client=client,
        bucket="markettwin",
    )

    path = await storage.download(
        artifact=artifact,
        directory=tmp_path,
    )

    assert path == (
        tmp_path
        / f"{artifact_id}.png"
    )

    assert path.read_bytes() == (
        b"fake-png-bytes"
    )

    assert client.downloads == [
        (
            "markettwin",
            (
                "executions/test/steps/7/"
                "action-0007-element.png"
            ),
            str(path),
        )
    ]

@pytest.mark.parametrize("provider,bucket,key", [
    ("s3", "markettwin", "executions/test/image.png"),
    ("minio", "private-bucket", "executions/test/image.png"),
    ("minio", "markettwin", "secrets/config.json"),
    ("minio", "markettwin", "executions/../config.json"),
])
async def test_download_rejects_unconfigured_locations_before_io(
    tmp_path: Path, provider: str, bucket: str, key: str,
) -> None:
    artifact = VisualArtifactRecord(artifact_id=uuid4(), step_id=1, kind="viewport",
        storage_provider=provider, bucket=bucket, object_key=key, content_type="image/png")
    client = FakeS3Client()
    storage = VisualArtifactStorage(region="us-east-1", endpoint_url="http://localhost:9000",
                                    bucket="markettwin", client=client)
    with pytest.raises(ValueError):
        await storage.download(artifact=artifact, directory=tmp_path)
    assert client.downloads == []
