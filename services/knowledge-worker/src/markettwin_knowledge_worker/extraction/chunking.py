"""Pack ordered normalized source parts without semantic processing."""

from collections.abc import Iterable
from dataclasses import dataclass

from markettwin_knowledge_worker.config import KnowledgeConfig
from markettwin_knowledge_worker.extraction.contracts import ExtractedEvidence


@dataclass(frozen=True, slots=True)
class SourcePart:
    text: str
    locator: dict[str, object]


@dataclass(frozen=True, slots=True)
class PackedTextChunk:
    text: str
    start_locator: dict[str, object]
    end_locator: dict[str, object]

    @property
    def source_locator(self) -> dict[str, object]:
        locator: dict[str, object] = {}
        for key, value in self.start_locator.items():
            if isinstance(value, int):
                locator[f"{key}_start"] = value
                locator[f"{key}_end"] = self.end_locator[key]
            else:
                locator[key] = value
        return locator


def pack_source_parts(
    parts: Iterable[SourcePart], *, max_chars: int, separator: str = "\n\n"
) -> tuple[PackedTextChunk, ...]:
    """Keep normal parts whole and split an oversized part at deterministic character boundaries."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive.")
    chunks: list[PackedTextChunk] = []
    text = ""
    start: dict[str, object] = {}
    end: dict[str, object] = {}
    for part in parts:
        for offset in range(0, len(part.text), max_chars):
            piece = part.text[offset : offset + max_chars]
            joined = f"{text}{separator}{piece}" if text else piece
            if text and len(joined) > max_chars:
                chunks.append(PackedTextChunk(text, start, end))
                text, start, end = "", {}, {}
                joined = piece
            text = joined
            for key, value in part.locator.items():
                start.setdefault(key, value)
                end[key] = value
    if text:
        chunks.append(PackedTextChunk(text, start, end))
    return tuple(chunks)


def text_evidence(
    parts: Iterable[SourcePart],
    *,
    extractor_name: str,
    extractor_version: str,
    evidence_type: str = "text",
    separator: str = "\n\n",
) -> tuple[ExtractedEvidence, ...]:
    chunks = pack_source_parts(
        parts,
        max_chars=KnowledgeConfig.from_env().source_chunk_max_chars,
        separator=separator,
    )
    return tuple(
        ExtractedEvidence(
            evidence_type=evidence_type,
            content_text=chunk.text,
            content_json=None,
            source_locator=chunk.source_locator,
            extractor_name=extractor_name,
            extractor_version=extractor_version,
            ordinal=ordinal,
        )
        for ordinal, chunk in enumerate(chunks, start=1)
    )
