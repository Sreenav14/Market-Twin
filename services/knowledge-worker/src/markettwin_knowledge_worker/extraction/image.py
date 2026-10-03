"""Thin image source adapter for direct multimodal Knowledge Builder input."""

import asyncio
from pathlib import Path

from markettwin_knowledge_worker.extraction.contracts import (
    ExtractedEvidence,
    ExtractionResult,
)


class ImageExtractionError(RuntimeError):
    """Raised when an image cannot be prepared as source evidence."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ImageExtractor:
    """Validate one image and preserve it for the semantic Knowledge Builder."""

    name = "image-source-adapter"
    version = "1"

    async def extract(self, path: Path) -> ExtractionResult:
        """Return one whole-image evidence unit without semantic interpretation."""
        media_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(path.suffix.lower())
        if media_type is None:
            raise ImageExtractionError(
                "unsupported_format", f"Unsupported image format: {path.suffix}"
            )
        try:
            size = await asyncio.to_thread(path.stat)
        except OSError as exc:
            raise ImageExtractionError(
                "parsing_failed", f"Unable to read image: {path.name}"
            ) from exc
        if size.st_size == 0:
            raise ImageExtractionError("blank_image", f"Image is empty: {path.name}")
        return ExtractionResult(
            source_path=path,
            units=(
                ExtractedEvidence(
                    evidence_type="image",
                    content_text=None,
                    content_json={"media_type": media_type},
                    source_locator={"image": 1},
                    extractor_name=self.name,
                    extractor_version=self.version,
                    ordinal=1,
                    media_path=path,
                ),
            ),
            issues=(),
            source_item_count=1,
            processed_item_count=1,
        )
