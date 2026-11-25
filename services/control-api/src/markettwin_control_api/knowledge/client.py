"""Narrow private HTTP client for the knowledge worker."""

from typing import BinaryIO, cast
from uuid import UUID

import httpx
from markettwin_shared.knowledge_markdown import KnowledgeMarkdownResponse
from markettwin_shared.knowledge_preview import KnowledgePreviewResponse
from pydantic import ValidationError

from markettwin_control_api.config import Settings

_OUTPUT_LIMIT_MESSAGE = (
    "Knowledge generation reached its output limit. "
    "Try a smaller source or a model with a larger output limit."
)

_PREVIEW_DETAILS = {
    413: "This source is too large for knowledge preview.",
    415: "Unsupported source format.",
    422: "The source could not be read.",
    502: "Knowledge preview failed.",
    503: "Knowledge processing is unavailable. Please try again.",
    504: "Knowledge preview timed out.",
}

_MARKDOWN_DETAILS = {
    413: "This source is too large for knowledge processing.",
    415: "Unsupported source format.",
    422: "The source could not be read.",
    502: "Knowledge generation failed.",
    503: "Knowledge processing is unavailable. Please try again.",
    504: "Knowledge generation timed out.",
}


class KnowledgeWorkerError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _worker_error(response: httpx.Response, safe_details: dict[int, str]) -> KnowledgeWorkerError:
    code = response.status_code if response.status_code in safe_details else 502
    if code == 502:
        try:
            body: object = response.json()
            if (
                isinstance(body, dict)
                and cast(dict[str, object], body).get("detail") == _OUTPUT_LIMIT_MESSAGE
            ):
                return KnowledgeWorkerError(code, _OUTPUT_LIMIT_MESSAGE)
        except ValueError:
            pass
    return KnowledgeWorkerError(code, safe_details[code])


class KnowledgeWorkerClient:
    def __init__(self, settings: Settings) -> None:
        self._url = settings.knowledge_worker_url.rstrip("/")
        self._timeout = settings.knowledge_preview_timeout_seconds
        secret = settings.knowledge_internal_secret
        self._headers = (
            {"Authorization": f"Bearer {secret.get_secret_value()}"} if secret else {}
        )

    async def _post(
        self,
        path: str,
        *,
        filename: str,
        content_type: str | None,
        stream: BinaryIO,
        data: dict[str, str] | None = None,
        timeout_message: str,
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, connect=5.0)
            ) as client:
                return await client.post(
                    f"{self._url}{path}",
                    headers=self._headers,
                    files={"file": (filename, stream, content_type or "application/octet-stream")},
                    data=data,
                )
        except httpx.TimeoutException as exc:
            raise KnowledgeWorkerError(504, timeout_message) from exc
        except httpx.RequestError as exc:
            raise KnowledgeWorkerError(
                503, "Knowledge processing is unavailable. Please try again."
            ) from exc

    async def preview(
        self,
        *,
        filename: str,
        content_type: str | None,
        stream: BinaryIO,
    ) -> KnowledgePreviewResponse:
        response = await self._post(
            "/internal/v1/knowledge/preview",
            filename=filename,
            content_type=content_type,
            stream=stream,
            timeout_message="Knowledge preview timed out.",
        )
        if response.status_code >= 400:
            raise _worker_error(response, _PREVIEW_DETAILS)
        try:
            return KnowledgePreviewResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise KnowledgeWorkerError(
                502, "Knowledge preview returned an invalid result."
            ) from exc

    async def markdown(
        self,
        *,
        filename: str,
        content_type: str | None,
        stream: BinaryIO,
        entry_id: UUID,
        workspace_id: UUID,
    ) -> KnowledgeMarkdownResponse:
        response = await self._post(
            "/internal/v1/knowledge/markdown",
            filename=filename,
            content_type=content_type,
            stream=stream,
            data={"entry_id": str(entry_id), "workspace_id": str(workspace_id)},
            timeout_message="Knowledge generation timed out.",
        )
        if response.status_code >= 400:
            raise _worker_error(response, _MARKDOWN_DETAILS)
        try:
            return KnowledgeMarkdownResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise KnowledgeWorkerError(
                502, "Knowledge generation returned an invalid result."
            ) from exc
