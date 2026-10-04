"""Store original ingestion sources in the workspace's private object bucket."""

from asyncio import to_thread
from typing import BinaryIO, Literal, Protocol, cast

from boto3.session import Session
from botocore.config import Config

from markettwin_control_api.config import Settings


class S3SourceClient(Protocol):
    def upload_fileobj(
        self, Fileobj: BinaryIO, Bucket: str, Key: str, *, ExtraArgs: dict[str, str]
    ) -> None: ...
    def delete_object(self, *, Bucket: str, Key: str) -> object: ...
    def download_fileobj(self, Bucket: str, Key: str, Fileobj: BinaryIO) -> None: ...


class S3SourceSession(Protocol):
    def client(
        self,
        service_name: Literal["s3"],
        *,
        endpoint_url: str | None,
        region_name: str,
        config: Config,
    ) -> S3SourceClient: ...


class KnowledgeSourceStorage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self._client = cast(S3SourceSession, Session()).client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4"),
        )

    async def put(self, *, key: str, stream: BinaryIO, content_type: str | None) -> None:
        stream.seek(0)
        await to_thread(
            self._client.upload_fileobj,
            stream,
            self.bucket,
            key,
            ExtraArgs={"ContentType": content_type or "application/octet-stream"},
        )

    async def delete(self, *, key: str) -> None:
        await to_thread(self._client.delete_object, Bucket=self.bucket, Key=key)

    async def download(self, *, bucket: str, key: str, stream: BinaryIO) -> None:
        await to_thread(self._client.download_fileobj, bucket, key, stream)
        stream.seek(0)
