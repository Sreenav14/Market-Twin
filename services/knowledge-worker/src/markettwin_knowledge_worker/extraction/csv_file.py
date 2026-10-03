"""Deterministic structured extraction from CSV files."""

import csv
from pathlib import Path

from markettwin_knowledge_worker.extraction.chunking import SourcePart, text_evidence
from markettwin_knowledge_worker.extraction.contracts import (
    ExtractionIssue,
    ExtractionResult,
)


class CsvExtractionError(RuntimeError):
    """Raised when a CSV file cannot be extracted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CsvExtractor:
    """Extract all non-empty CSV rows while preserving row numbers."""

    name = "python-csv"
    version = "1"

    def extract(self, path: Path) -> ExtractionResult:
        """Return the CSV contents as structured evidence."""

        rows: list[SourcePart] = []

        try:
            with path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as stream:
                reader = csv.reader(stream)

                for row_number, row in enumerate(
                    reader,
                    start=1,
                ):
                    values = [
                        value.strip()
                        for value in row
                    ]

                    if not any(values):
                        continue

                    rows.append(
                        SourcePart(
                            text=f"Row {row_number}: " + " | ".join(values),
                            locator={"row": row_number},
                        )
                    )

        except (
            OSError,
            UnicodeDecodeError,
            csv.Error,
        ) as exc:
            raise CsvExtractionError(
                "parsing_failed",
                f"Unable to extract CSV: {path.name}",
            ) from exc

        if not rows:
            return ExtractionResult(
                source_path=path,
                units=(),
                issues=(
                    ExtractionIssue(
                        code="blank_document",
                        message="CSV contains no extractable rows.",
                        source_locator={},
                    ),
                ),
                source_item_count=0,
                processed_item_count=0,
            )

        return ExtractionResult(
            source_path=path,
            units=text_evidence(
                rows,
                extractor_name=self.name,
                extractor_version=self.version,
                evidence_type="table",
                separator="\n",
            ),
            issues=(),
            source_item_count=len(rows),
            processed_item_count=len(rows),
        )
