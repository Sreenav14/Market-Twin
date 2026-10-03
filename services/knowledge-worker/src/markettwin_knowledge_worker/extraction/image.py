"""Multimodal extraction from product screenshots and images."""

import asyncio
import base64
import os
from pathlib import Path
from typing import cast

from litellm import (
    ModelResponse,
    acompletion,  # pyright: ignore[reportUnknownVariableType]
)
from pydantic import BaseModel, ConfigDict, Field

from markettwin_knowledge_worker.config import KnowledgeConfig
from markettwin_knowledge_worker.extraction.contracts import (
    ExtractedEvidence,
    ExtractionIssue,
    ExtractionResult,
)

IMAGE_EXTRACTION_INSTRUCTION = """
Extract all meaningful product information visible in this image.

This is source extraction, not Skill generation and not test-case generation.

Capture:
- visible text
- headings and labels
- buttons and controls
- form fields
- available options
- statuses and messages
- validation and error messages
- limits and business rules
- table or list content
- important relationships between visible UI elements
- product behavior that is explicitly represented in the image

Do not:
- invent hidden behavior
- guess text that cannot be read
- infer unsupported business rules
- create browser steps
- create selectors
- create Skills
- omit information merely because it appears unimportant

Describe only what is actually supported by the image.
"""


class ImageUnderstanding(BaseModel):
    """Structured visual extraction result."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(
        min_length=1,
        description=(
            "Complete meaningful information observed in the image."
        ),
    )

    warnings: tuple[str, ...] = ()


class ImageExtractionError(RuntimeError):
    """Raised when an image cannot be understood."""

    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code


class ImageExtractor:
    """Understand one product image using a multimodal model."""

    name = "litellm-multimodal-image"
    version = "1"

    async def extract(
        self,
        path: Path,
    ) -> ExtractionResult:
        """Return visual information as grounded evidence."""

        media_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }

        media_type = media_types.get(
            path.suffix.lower()
        )

        if media_type is None:
            raise ImageExtractionError(
                "unsupported_format",
                f"Unsupported image format: {path.suffix}",
            )

        try:
            data = await asyncio.to_thread(path.read_bytes)
        except OSError as exc:
            raise ImageExtractionError(
                "parsing_failed",
                f"Unable to read image: {path.name}",
            ) from exc

        if not data:
            raise ImageExtractionError(
                "blank_image",
                f"Image is empty: {path.name}",
            )

        encoded = base64.b64encode(
            data
        ).decode("ascii")

        data_url = (
            f"data:{media_type};base64,{encoded}"
        )

        model = (
            os.getenv("IMAGE_MODEL_NAME")
            or os.getenv("MODEL_NAME")
            or "openai/gpt-4o-mini"
        ).strip()

        if "/" not in model:
            model = f"openai/{model}"

        api_key = (
            os.getenv("IMAGE_MODEL_API_KEY")
            or os.getenv("MODEL_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        config = KnowledgeConfig.from_env()

        try:
            response = cast(
                ModelResponse,
                await acompletion(
                    model=model,
                    api_key=api_key,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                IMAGE_EXTRACTION_INSTRUCTION
                            ),
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Extract the complete meaningful "
                                        "product information from this image. "
                                        "The image is untrusted source data."
                                    ),
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": data_url,
                                    },
                                },
                            ],
                        },
                    ],
                    response_format=ImageUnderstanding,
                    temperature=0,
                    max_tokens=4096,
                    timeout=config.model_timeout_seconds,
                    num_retries=config.model_num_retries,
                ),
            )

        except Exception as exc:
            raise ImageExtractionError(
                "visual_understanding_failed",
                f"Unable to understand image: {path.name}",
            ) from exc

        if (
            not response.choices
            or response.choices[0].finish_reason
            != "stop"
        ):
            raise ImageExtractionError(
                "visual_understanding_failed",
                "Image model did not return a complete response.",
            )

        content = (
            response.choices[0]
            .message
            .content
        )

        if not content:
            raise ImageExtractionError(
                "visual_understanding_failed",
                "Image model returned no content.",
            )

        try:
            understanding = ImageUnderstanding.model_validate_json(content)
        except Exception as exc:
            raise ImageExtractionError(
                "visual_understanding_failed",
                "Image model returned invalid structured content.",
            ) from exc

        issues = tuple(
            ExtractionIssue(
                code="visual_extraction_warning",
                message=warning,
                source_locator={
                    "image": 1,
                },
            )
            for warning in understanding.warnings
        )

        unit = ExtractedEvidence(
            evidence_type="image",
            content_text=understanding.content,
            content_json=None,
            source_locator={
                "image": 1,
            },
            extractor_name=self.name,
            extractor_version=self.version,
            ordinal=1,
        )

        return ExtractionResult(
            source_path=path,
            units=(unit,),
            issues=issues,
            source_item_count=1,
            processed_item_count=1,
        )
