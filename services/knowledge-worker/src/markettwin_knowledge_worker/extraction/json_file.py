"""Deterministic structured extraction from JSON files."""

import json
from pathlib import Path
from typing import cast

from markettwin_knowledge_worker.config import KnowledgeConfig
from markettwin_knowledge_worker.extraction.contracts import (
    ExtractedEvidence,
    ExtractionResult,
)


class JsonExtractionError(RuntimeError):
    """Raised when a JSON document cannot be extracted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class JsonExtractor:
    """Extract the complete JSON document as structured evidence."""

    name = "python-json"
    version = "1"

    def extract(self, path: Path) -> ExtractionResult:
        """Return the complete JSON value without semantic filtering."""

        try:
            with path.open(
                "r",
                encoding="utf-8-sig",
            ) as stream:
                value = cast(
                    object,
                    json.load(stream),
                )

        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise JsonExtractionError(
                "parsing_failed",
                f"Unable to extract JSON: {path.name}",
            ) from exc

        pieces = _split_json_value(
            value, "$", KnowledgeConfig.from_env().source_chunk_max_chars
        )
        units = tuple(
            ExtractedEvidence(
                evidence_type="structured_data",
                content_text=None,
                content_json=payload,
                source_locator={"json_path": json_path},
                extractor_name=self.name,
                extractor_version=self.version,
                ordinal=ordinal,
            )
            for ordinal, (json_path, payload) in enumerate(pieces, start=1)
        )

        return ExtractionResult(
            source_path=path,
            units=units,
            issues=(),
            source_item_count=len(pieces),
            processed_item_count=len(pieces),
        )


def _json_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _split_json_value(
    value: object, json_path: str, max_chars: int
) -> tuple[tuple[str, dict[str, object]], ...]:
    """Split at JSON object/array boundaries while keeping every payload valid JSON."""
    wrapped = {"value": value}
    if _json_size(wrapped) <= max_chars:
        return ((json_path, wrapped),)
    if isinstance(value, dict):
        object_value = cast(dict[object, object], value)
        pieces: list[tuple[str, dict[str, object]]] = []
        for key, child in object_value.items():
            child_path = f"{json_path}.{key}"
            candidate: dict[str, object] = {"value": {str(key): child}}
            if _json_size(candidate) <= max_chars:
                pieces.append((child_path, candidate))
            else:
                pieces.extend(_split_json_value(child, child_path, max_chars))
        return tuple(pieces)
    if isinstance(value, list):
        array_value = cast(list[object], value)
        pieces = []
        group: list[object] = []
        group_start = 0
        for index, child in enumerate(array_value):
            candidate = {"value": [*group, child]}
            if group and _json_size(candidate) > max_chars:
                pieces.append((f"{json_path}[{group_start}:{index}]", {"value": group}))
                group = []
                group_start = index
            if _json_size({"value": child}) > max_chars:
                pieces.extend(_split_json_value(child, f"{json_path}[{index}]", max_chars))
            else:
                if not group:
                    group_start = index
                group.append(child)
        if group:
            pieces.append(
                (f"{json_path}[{group_start}:{len(array_value)}]", {"value": group})
            )
        return tuple(pieces)
    if isinstance(value, str):
        pieces = []
        start = 0
        while start < len(value):
            low, high = 1, len(value) - start
            fitting_length = 0
            while low <= high:
                middle = (low + high) // 2
                if _json_size({"value": value[start : start + middle]}) <= max_chars:
                    fitting_length = middle
                    low = middle + 1
                else:
                    high = middle - 1
            if fitting_length == 0:
                raise ValueError("JSON chunk limit is too small for a valid scalar payload.")
            end = start + fitting_length
            pieces.append(
                (f"{json_path}[chars:{start}:{end}]", {"value": value[start:end]})
            )
            start = end
        return tuple(pieces)
    return ((json_path, wrapped),)
