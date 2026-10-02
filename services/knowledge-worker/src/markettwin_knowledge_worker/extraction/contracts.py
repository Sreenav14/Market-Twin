"""Canonical contracts produced by MarketTwin source extractors."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ExtractedEvidence:
    """One useful piece of source content with exact provenance."""

    evidence_type: str

    content_text: str | None
    content_json: dict[str, object] | None

    source_locator: dict[str, object]

    extractor_name: str
    extractor_version: str

    ordinal: int


@dataclass(frozen=True, slots=True)
class ExtractionIssue:
    """Something discovered during extraction that requires attention."""

    code: str
    message: str
    source_locator: dict[str, object]
    requires_fallback: bool = False


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Canonical result from one source extraction."""

    source_path: Path

    units: tuple[ExtractedEvidence, ...]
    issues: tuple[ExtractionIssue, ...]

    source_item_count: int
    processed_item_count: int

    @property
    def requires_fallback(self) -> bool:
        """Whether another extraction strategy is required."""

        return any(issue.requires_fallback for issue in self.issues)

    @property
    def coverage_complete(self) -> bool:
        """Whether the extractor inspected every source item."""

        return self.source_item_count == self.processed_item_count