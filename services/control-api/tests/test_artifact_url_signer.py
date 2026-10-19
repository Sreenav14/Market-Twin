"""Tests for private evidence URL signing."""

from unittest.mock import Mock

from markettwin_control_api.evidence.artifact_url_signer import (
    ArtifactUrlSigner,
)


def test_signer_uses_configured_storage_credentials(monkeypatch) -> None:
    from markettwin_control_api.evidence import artifact_url_signer as module
    session = Mock()
    factory = Mock(return_value=session)
    monkeypatch.setattr(module, "Session", factory)
    module.ArtifactUrlSigner(region="us-east-1", endpoint_url="http://localhost:9000",
                            access_key_id="local-test-key", secret_access_key="local-test-secret")
    factory.assert_called_once_with(
        aws_access_key_id="local-test-key",
        aws_secret_access_key="local-test-secret",
        aws_session_token=None,
    )


def test_create_download_url_signs_exact_object() -> None:
    """The signer should grant temporary read access to one exact object."""

    client = Mock()

    client.generate_presigned_url.return_value = (
        "http://example.invalid/signed-evidence"
    )

    signer = ArtifactUrlSigner(
        region="us-east-1",
        endpoint_url=None,
        client=client,
    )

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


def test_source_download_does_not_render_declared_html_inline() -> None:
    client = Mock()
    signer = ArtifactUrlSigner(region="us-east-1", endpoint_url=None, client=client)
    signer.create_download_url(
        bucket="sources", object_key="knowledge/source", download_filename="report draft.html"
    )
    params = client.generate_presigned_url.call_args.kwargs["Params"]
    assert params["ResponseContentDisposition"] == (
        "attachment; filename*=UTF-8''report%20draft.html"
    )
    assert params["ResponseContentType"] == "application/octet-stream"
