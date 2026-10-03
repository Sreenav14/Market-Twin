"""Source extraction primitives for the MarketTwin Knowledge Worker."""

from markettwin_knowledge_worker.extraction.contracts import (
    ExtractedEvidence,
    ExtractionIssue,
    ExtractionResult,
)
from markettwin_knowledge_worker.extraction.dispatcher import (
    UnsupportedSourceFormatError,
    extract_source,
)
from markettwin_knowledge_worker.extraction.pdf import (
    PdfExtractionError,
    PdfExtractor,
)

__all__ = [
    "ExtractedEvidence",
    "ExtractionIssue",
    "ExtractionResult",
    "PdfExtractionError",
    "PdfExtractor",
    "UnsupportedSourceFormatError",
    "extract_source",
]