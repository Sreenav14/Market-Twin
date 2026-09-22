"""Download selected visual evidence from MinIO or S3."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Protocol, cast

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


class VisualArtifactStorage:
    """Read persisted screenshot evidence for visual verification."""

    def __init__(
        self,
        *,
        region: str,
        endpoint_url: str | None,
        client: S3DownloadClient | None = None,
    ) -> None:
        if client is not None:
            self._client = client
            return

        self._client = cast(
            S3DownloadClient,
            Session().client(  # pyright: ignore[reportUnknownMemberType]
                "s3",
                region_name=region,
                endpoint_url=endpoint_url,
                config=Config(
                    signature_version="s3v4",
                ),
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