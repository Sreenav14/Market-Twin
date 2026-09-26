"""Short-lived access URLs for private MarketTwin evidence artifacts."""

from __future__ import annotations

from typing import Literal, Protocol, cast

from boto3.session import Session
from botocore.config import Config

DEFAULT_ARTIFACT_TTL_SECONDS = 300

class S3PresignClient(Protocol):
    """Small S3 client surface needed for presigned downloads."""
    
    def generate_presigned_url(
        self,
        ClientMethod:str,
        Params: dict[str, str],
        ExpiresIn: int,
    ) -> str: ...


class S3Session(Protocol):
    """Typed boto session surface used to construct the S3 client."""

    def client(
        self,
        service_name: Literal["s3"],
        *,
        region_name: str,
        endpoint_url: str | None,
        config: Config,
    ) -> S3PresignClient: ...


class ArtifactUrlSigner:
    """Generate temporary download URLs for private evidence objects."""
    
    def __init__(
        self,
        *,
        region: str,
        endpoint_url: str | None,
        client: S3PresignClient | None = None,
    ) -> None:
        if client is not None:
            self._client = client
            return

        session = cast(S3Session, Session())
        self._client = session.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            config=Config(signature_version="s3v4"),
        )
        
        
    def create_download_url(
        self,
        *,
        bucket: str,
        object_key: str,
        expires_in_seconds: int = DEFAULT_ARTIFACT_TTL_SECONDS,
    ) -> str:
        """Create a temporary signed URL for one private object."""
        
        return self._client.generate_presigned_url(\
                ClientMethod="get_object",
                Params={
                    "Bucket": bucket,
                    "Key": object_key,
                },
                ExpiresIn=expires_in_seconds,
            )
    