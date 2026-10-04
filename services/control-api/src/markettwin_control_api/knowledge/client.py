"""Narrow private HTTP client for source preview."""

from typing import BinaryIO, cast

import httpx
from markettwin_shared.knowledge_preview import KnowledgePreviewResponse
from pydantic import ValidationError

from markettwin_control_api.config import Settings


class KnowledgeWorkerError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class KnowledgeWorkerClient:
    def __init__(self, settings: Settings) -> None:
        self._url = settings.knowledge_worker_url.rstrip("/")
        self._timeout = settings.knowledge_preview_timeout_seconds

    async def preview(
        self,
        *,
        filename: str,
        content_type: str | None,
        stream: BinaryIO,
    ) -> KnowledgePreviewResponse:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, connect=5.0)
            ) as client:
                response = await client.post(
                    f"{self._url}/internal/v1/knowledge/preview",
                    files={"file": (filename, stream, content_type or "application/octet-stream")},
                )
        except httpx.TimeoutException as exc:
            raise KnowledgeWorkerError(504, "Knowledge preview timed out.") from exc
        except httpx.RequestError as exc:
            raise KnowledgeWorkerError(
                503, "Knowledge processing is unavailable. Please try again."
            ) from exc

        safe_details = {
            413: "This source is too large for knowledge preview.",
            415: "Unsupported source format.",
            422: "The source could not be read.",
            502: "Knowledge preview failed.",
            504: "Knowledge preview timed out.",
        }
        if response.status_code >= 400:
            code = response.status_code if response.status_code in safe_details else 502
            output_limit_message = (
                "Knowledge generation reached its output limit. "
                "Try a smaller source or a model with a larger output limit."
            )
            if code == 502:
                try:
                    body: object = response.json()
                    if (
                        isinstance(body, dict)
                        and cast(dict[str, object], body).get("detail") == output_limit_message
                    ):
                        raise KnowledgeWorkerError(code, output_limit_message)
                except ValueError:
                    pass
            raise KnowledgeWorkerError(code, safe_details[code])
        try:
            return KnowledgePreviewResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise KnowledgeWorkerError(
                502, "Knowledge preview returned an invalid result."
            ) from exc
