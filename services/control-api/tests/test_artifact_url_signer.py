"""Tests for private evidence URL signing."""

from unittest.mock import Mock

from markettwin_control_api.evidence.artifact_url_signer import (
    ArtifactUrlSigner,
)


def test_create_download_url_signs_exact_object() -> None:
    """The signer should grant temporary read access to one exact object."""

    client = Mock()

    client.generate_presigned_url.return_value = (
        "http://example.invalid/signed-evidence"
    )

    signer = ArtifactUrlSigner.__new__(ArtifactUrlSigner)
    signer._client = client  # pyright: ignore[reportPrivateUsage]

    result = signer.create_download_url(
        bucket="markettwin-local",
        object_key="executions/example/steps/1/screenshot.png",
    )

    assert result == "http://example.invalid/signed-evidence"

    client.generate_presigned_url.assert_called_once_with(
        ClientMethod="get_object",
        Params={
            "Bucket": "markettwin-local",
            "Key": "executions/example/steps/1/screenshot.png",
        },
        ExpiresIn=300,
    )
