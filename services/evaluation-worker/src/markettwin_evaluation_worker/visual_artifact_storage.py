"""Download selected visual evidence from MinIO or S3."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Literal, Protocol, cast

from boto3.session import Session
from botocore.config import Config

from markettwin_evaluation_worker.persistence.evaluation_repository import (
    VisualArtifactRecord,
)


class S3DownloadClient(Protocol):
    """Small typed S3 surface needed by evaluation."""

    def download_file(
        self,
        Bucket: str,
        Key: str,
        Filename: str,
    ) -> None: ...


class S3Session(Protocol):
    """Typed boto session surface used to construct the S3 client."""

    def client(
        self,
        service_name: Literal["s3"],
        *,
        region_name: str,
        endpoint_url: str | None,
        config: Config,
    ) -> S3DownloadClient: ...


class VisualArtifactStorage:
    """Read persisted screenshot evidence for visual verification."""

    def __init__(
        self,
        *,
        region: str,
        endpoint_url: str | None,
        client: S3DownloadClient | None = None,
        bucket: str | None = None,
    ) -> None:
        self._bucket = (bucket or os.environ.get("S3_BUCKET", "")).strip()
        if not self._bucket:
            raise ValueError("S3_BUCKET must be configured for visual evidence.")
        self._provider = "minio" if endpoint_url else "s3"
        if client is not None:
            self._client = client
            return

        session = cast(S3Session, Session())
        self._client = session.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            config=Config(
                signature_version="s3v4",
            ),
        )

    @classmethod
    def from_environment(
        cls,
    ) -> VisualArtifactStorage:
        """Create storage using the existing MarketTwin S3 configuration."""

        region = os.environ.get(
            "S3_REGION",
            "us-east-1",
        ).strip()

        endpoint_url = (
            os.environ.get(
                "S3_ENDPOINT_URL",
                "",
            ).strip()
            or None
        )

        return cls(
            region=region,
            endpoint_url=endpoint_url,
        )

    async def download(
        self,
        *,
        artifact: VisualArtifactRecord,
        directory: Path,
    ) -> Path:
        """Download one selected visual artifact to a local temporary path."""

        if artifact.storage_provider != self._provider or artifact.bucket != self._bucket:
            raise ValueError("Visual evidence location does not match configured storage.")
        if not artifact.object_key.startswith("executions/") or any(
            segment in {"", ".", ".."} for segment in artifact.object_key.split("/")
        ) or "\\" in artifact.object_key:
            raise ValueError("Visual evidence key must be within executions/.")

        await asyncio.to_thread(
            directory.mkdir,
            parents=True,
            exist_ok=True,
        )

        suffix = (
            ".png"
            if artifact.content_type == "image/png"
            else ".bin"
        )

        local_path = (
            directory
            / f"{artifact.artifact_id}{suffix}"
        )

        await asyncio.to_thread(
            self._client.download_file,
            artifact.bucket,
            artifact.object_key,
            str(local_path),
        )

        if not await asyncio.to_thread(
            local_path.is_file
        ):
            raise RuntimeError(
                "Visual evidence download did not create a local file."
            )

        return local_path