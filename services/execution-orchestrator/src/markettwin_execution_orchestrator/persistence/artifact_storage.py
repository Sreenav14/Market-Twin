"""S3-compatible storage for MarketTwin evidence artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast

from boto3.session import Session

StorageProvider = Literal["minio", "s3"]


class S3UploadClient(Protocol):
    """Small typed surface used from the boto3 S3 client."""

    def upload_file(
        self,
        Filename: str,
        Bucket: str,
        Key: str,
        ExtraArgs: dict[str, str],
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """Metadata for one successfully uploaded artifact."""

    storage_provider: StorageProvider
    bucket: str
    object_key: str
    content_type: str
    size_bytes: int
    sha256: str


class S3ArtifactStorage:
    """Upload evidence to MinIO locally or AWS S3 in production."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str | None,
    ) -> None:
        self._bucket = bucket
        self._provider: StorageProvider = (
            "minio" if endpoint_url else "s3"
        )

        self._client = cast(
            S3UploadClient,
            Session().client(  # pyright: ignore[reportUnknownMemberType]
                "s3",
                region_name=region,
                endpoint_url=endpoint_url,
            ),
        )

    @classmethod
    def from_environment(cls) -> S3ArtifactStorage:
        bucket = os.environ.get("S3_BUCKET", "").strip()

        if not bucket:
            raise RuntimeError("S3_BUCKET must be configured.")

        region = os.environ.get(
            "S3_REGION",
            "us-east-1",
        ).strip()

        endpoint_url = (
            os.environ.get("S3_ENDPOINT_URL", "").strip()
            or None
        )

        return cls(
            bucket=bucket,
            region=region,
            endpoint_url=endpoint_url,
        )

    async def upload(
        self,
        *,
        local_path: Path,
        object_key: str,
        content_type: str,
    ) -> StoredArtifact:
        if not await asyncio.to_thread(local_path.is_file):
            raise FileNotFoundError(
                f'Evidence file "{local_path}" does not exist.'
            )

        size_bytes = (await asyncio.to_thread(local_path.stat)).st_size

        sha256 = await asyncio.to_thread(
            self._sha256,
            local_path,
        )

        await asyncio.to_thread(
            self._client.upload_file,
            str(local_path),
            self._bucket,
            object_key,
            ExtraArgs={
                "ContentType": content_type,
            },
        )

        return StoredArtifact(
            storage_provider=self._provider,
            bucket=self._bucket,
            object_key=object_key,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        with path.open("rb") as file:
            return hashlib.file_digest(
                file,
                "sha256",
            ).hexdigest()
