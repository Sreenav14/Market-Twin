"""Private worker multipart transport contract."""

from io import BytesIO

import httpx
import pytest
from markettwin_control_api.config import Settings
from markettwin_control_api.knowledge.client import KnowledgeWorkerClient, KnowledgeWorkerError
from markettwin_shared.knowledge_preview import (
    KnowledgePreviewResponse,
    KnowledgePreviewSourceResponse,
)


async def test_private_client_sends_multipart_and_validates_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = KnowledgePreviewResponse(
        source=KnowledgePreviewSourceResponse(
            name="source.txt", source_item_count=1, processed_item_count=1
        ),
        application_knowledge=(),
        artifacts=(),
        skills=(),
        evidence=(),
        extraction_issues=(),
    )

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/v1/knowledge/preview"
        assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
        assert b"source bytes" in request.read()
        return httpx.Response(200, json=result.model_dump(mode="json"))

    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    response = await KnowledgeWorkerClient(Settings(_env_file=None)).preview(
        filename="source.txt",
        content_type="text/plain",
        stream=BytesIO(b"source bytes"),
    )
    assert response == result


@pytest.mark.parametrize(
    "detail,expected",
    [
        (
            "Knowledge generation reached its output limit. "
            "Try a smaller source or a model with a larger output limit.",
            "Knowledge generation reached its output limit.",
        ),
        ("private provider detail", "Knowledge preview failed."),
    ],
)
async def test_client_preserves_only_safe_output_limit_error(
    monkeypatch: pytest.MonkeyPatch, detail: str, expected: str,
) -> None:
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: async_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(502, json={"detail": detail})
            ),
            **kwargs,
        ),
    )
    with pytest.raises(KnowledgeWorkerError, match=expected) as caught:
        await KnowledgeWorkerClient(Settings(_env_file=None)).preview(
            filename="source.txt", content_type="text/plain", stream=BytesIO(b"source"),
        )
    assert caught.value.status_code == 502
