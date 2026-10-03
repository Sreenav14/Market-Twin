"""Deterministic structured extraction from Excel workbooks."""

from pathlib import Path
from zipfile import BadZipFile

import openpyxl
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from markettwin_knowledge_worker.config import KnowledgeConfig
from markettwin_knowledge_worker.extraction.chunking import SourcePart, pack_source_parts
from markettwin_knowledge_worker.extraction.contracts import (
    ExtractedEvidence,
    ExtractionIssue,
    ExtractionResult,
)


class XlsxExtractionError(RuntimeError):
    """Raised when an Excel workbook cannot be extracted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _json_value(
    value: object,
) -> str | int | float | bool | None:
    """Convert an Excel value into a JSON-safe value."""

    if value is None:
        return None

    if isinstance(
        value,
        (str, int, float, bool),
    ):
        return value

    return str(value)


def _trim_trailing_empty(
    values: list[str | int | float | bool | None],
) -> list[str | int | float | bool | None]:
    """Remove unused cells at the end of an Excel row."""

    while values and values[-1] is None:
        values.pop()

    return values


class XlsxExtractor:
    """Extract non-empty workbook rows grouped by worksheet."""

    name = "openpyxl"
    version = openpyxl.__version__

    def extract(self, path: Path) -> ExtractionResult:
        """Return one structured evidence unit per non-empty worksheet."""

        try:
            workbook = load_workbook(
                filename=path,
                read_only=True,
                data_only=False,
            )
        except (
            OSError,
            InvalidFileException,
            BadZipFile,
            ValueError,
            KeyError,
        ) as exc:
            raise XlsxExtractionError(
                "parsing_failed",
                f"Unable to extract Excel workbook: {path.name}",
            ) from exc

        units: list[ExtractedEvidence] = []
        issues: list[ExtractionIssue] = []

        try:
            sheet_count = len(workbook.worksheets)

            for worksheet in workbook.worksheets:
                rows: list[SourcePart] = []

                for row_number, raw_row in enumerate(
                    worksheet.iter_rows(
                        values_only=True
                    ),
                    start=1,
                ):
                    values = [
                        _json_value(value)
                        for value in raw_row
                    ]

                    values = _trim_trailing_empty(
                        values
                    )

                    if not values:
                        continue

                    if not any(
                        value not in (None, "")
                        for value in values
                    ):
                        continue

                    rows.append(
                        SourcePart(
                            text=(
                                f"Row {row_number}: "
                                + " | ".join(
                                    "" if value is None else str(value) for value in values
                                )
                            ),
                            locator={"sheet": worksheet.title, "row": row_number},
                        )
                    )

                if not rows:
                    issues.append(
                        ExtractionIssue(
                            code="blank_sheet",
                            message=(
                                "Worksheet contains no "
                                "extractable cell values."
                            ),
                            source_locator={
                                "sheet": worksheet.title,
                            },
                        )
                    )

                    continue

                sheet_header = f"[SHEET: {worksheet.title}]"
                chunks = pack_source_parts(
                    rows,
                    max_chars=(
                        KnowledgeConfig.from_env().source_chunk_max_chars
                        - len(sheet_header)
                        - 1
                    ),
                    separator="\n",
                )
                for chunk in chunks:
                    units.append(
                        ExtractedEvidence(
                            evidence_type="table",
                            content_text=f"{sheet_header}\n{chunk.text}",
                            content_json=None,
                            source_locator=chunk.source_locator,
                            extractor_name=self.name,
                            extractor_version=self.version,
                            ordinal=len(units) + 1,
                        )
                    )

        finally:
            workbook.close()

        return ExtractionResult(
            source_path=path,
            units=tuple(units),
            issues=tuple(issues),
            source_item_count=sheet_count,
            processed_item_count=sheet_count,
        )
