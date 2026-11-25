"""Typed contracts, validator, guardrails, and renderer for Markdown knowledge files.

The understanding pass (doc 33) turns an extracted source into real Markdown
files split by topic. This module is the frozen contract for that pipeline:
the model fills `UnderstandResult`, `validate_understood_files` checks it
deterministically against the extraction evidence, `apply_split_guardrails`
enforces the topic-splitting rules by moving whole sections only, and
`render_knowledge_file` renders one file exactly as agents and the owner read it.
"""

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

PositiveOrdinal = Annotated[int, Field(gt=0, strict=True)]

# OD-K4 starting values [J]; recalibrate from measured file counts.
SINGLE_FILE_MAX_TOKENS = 6000
MAX_FILES_PER_SOURCE = 12
MERGE_UNDER_TOKENS = 150
MERGE_SHARED_EVIDENCE = 0.5


def estimate_tokens(text: str) -> int:
    """The one deterministic token estimator used across the pipeline."""
    return math.ceil(len(text) / 4)


class UncertaintyRecord(BaseModel):
    """Something the source leaves unclear, recorded as content, not a warning."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    # May be empty: an uncertainty about an absent point cites no evidence.
    evidence_ordinals: tuple[PositiveOrdinal, ...] = ()


class UnderstoodSection(BaseModel):
    """One atomic section of a topic file. Sections are never split."""

    model_config = ConfigDict(extra="forbid")

    heading: str = Field(min_length=1, max_length=200)
    body_md: str = Field(min_length=1)
    evidence_ordinals: tuple[PositiveOrdinal, ...] = Field(min_length=1)
    uncertainties: tuple[UncertaintyRecord, ...] = ()


class UnderstoodFile(BaseModel):
    """One topic of understood knowledge, rendered as one .md file."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=200)
    sections: tuple[UnderstoodSection, ...] = Field(min_length=1)


class UnderstandResult(BaseModel):
    """The typed output of the understand_source call-point."""

    model_config = ConfigDict(extra="forbid")

    files: tuple[UnderstoodFile, ...] = Field(min_length=1)


class MarkdownEvidenceUnit(BaseModel):
    """One extracted evidence unit with its provenance locator."""

    model_config = ConfigDict(extra="forbid")

    ordinal: int
    evidence_type: str
    content_text: str | None = None
    content_json: dict[str, object] | None = None
    source_locator: dict[str, object]
    extractor_name: str
    extractor_version: str


class MarkdownExtractionIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    source_locator: dict[str, object]
    requires_fallback: bool


class KnowledgeMarkdownUsage(BaseModel):
    """Durable per-job model spend for the understanding pass."""

    model_config = ConfigDict(extra="forbid")

    model: str
    calls: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class KnowledgeMarkdownSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    source_item_count: int
    processed_item_count: int
    original_url: str | None = None


class KnowledgeMarkdownResponse(BaseModel):
    """The knowledge-worker's markdown endpoint response (structured, unrendered)."""

    model_config = ConfigDict(extra="forbid")

    source: KnowledgeMarkdownSource
    files: tuple[UnderstoodFile, ...]
    evidence: tuple[MarkdownEvidenceUnit, ...]
    extraction_issues: tuple[MarkdownExtractionIssue, ...]
    usage: KnowledgeMarkdownUsage


class KnowledgeManifestFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    title: str
    description: str
    object_key: str
    sha256: str
    token_count: int
    section_headings: tuple[str, ...]
    evidence_ordinals: tuple[int, ...]


class KnowledgeManifest(BaseModel):
    """The per-version file index stored beside the files in object storage."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str
    workspace_id: str
    source_name: str
    original_url: str | None = None
    version: int
    files: tuple[KnowledgeManifestFile, ...]
    usage: KnowledgeMarkdownUsage


class KnowledgeEvidenceIndex(BaseModel):
    """The extraction evidence for one entry version, stored as evidence.json."""

    model_config = ConfigDict(extra="forbid")

    units: tuple[MarkdownEvidenceUnit, ...]
    issues: tuple[MarkdownExtractionIssue, ...]


class KnowledgeFileSummary(BaseModel):
    """One knowledge_files index row as served to clients (no body)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    slug: str
    title: str
    description: str
    object_key: str
    sha256: str
    token_count: int
    version: int
    status: str


class KnowledgeMarkdownValidationError(ValueError):
    """The understood file set failed deterministic validation; problems are named."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CURRENCY_PATTERN = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")
_QUOTED_PATTERN = re.compile(r'"([^"\n]{3,})"')
_NUMBER_UNIT_PATTERN = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s?(?:%|KB|MB|GB|TB|ms|seconds?|minutes?|hours?|days?|weeks?"
    r"|months?|years?|users?|seats?)",
    re.IGNORECASE,
)


def _tripwire_values(body: str) -> list[str]:
    values: list[str] = []
    for match in _CURRENCY_PATTERN.finditer(body):
        values.append(match.group(0))
    for match in _QUOTED_PATTERN.finditer(body):
        values.append(match.group(1))
    for match in _NUMBER_UNIT_PATTERN.finditer(body):
        values.append(match.group(0))
    return values


def _value_present(value: str, texts: Sequence[str]) -> bool:
    variants = {value, value.replace(" ", ""), value.replace(",", "")}
    return any(
        variant and any(variant in text or variant in text.replace(",", "") for text in texts)
        for variant in variants
    )


def validate_understood_files(
    files: Sequence[UnderstoodFile], evidence_texts: Mapping[int, str]
) -> None:
    """Reject a file set that invents, mis-cites, or breaks the format rules.

    Every rejection names the problem; nothing is silently repaired.
    `evidence_texts` maps evidence ordinal -> extracted text (text-bearing
    units only); ordinal existence is checked against its keys.
    """
    problems: list[str] = []
    if not files:
        problems.append("The file set is empty.")
    seen_slugs: set[str] = set()
    for file in files:
        if not _SLUG_PATTERN.match(file.slug):
            problems.append(f"File slug '{file.slug}' is not kebab-case.")
        if file.slug in seen_slugs:
            problems.append(f"File slug '{file.slug}' is duplicated.")
        seen_slugs.add(file.slug)
        if "\n" in file.description:
            problems.append(f"File '{file.slug}' description is not one line.")
        for section in file.sections:
            cited = [evidence_texts.get(ordinal) for ordinal in section.evidence_ordinals]
            for ordinal in section.evidence_ordinals:
                if ordinal not in evidence_texts:
                    problems.append(
                        f"Section '{section.heading}' in '{file.slug}' cites unknown "
                        f"evidence ordinal {ordinal}."
                    )
            for record in section.uncertainties:
                for ordinal in record.evidence_ordinals:
                    if ordinal not in evidence_texts:
                        problems.append(
                            f"Uncertainty in section '{section.heading}' of '{file.slug}' "
                            f"cites unknown evidence ordinal {ordinal}."
                        )
            texts = [text for text in cited if text is not None]
            if texts:
                for value in _tripwire_values(section.body_md):
                    if not _value_present(value, texts):
                        problems.append(
                            f"Section '{section.heading}' in '{file.slug}' states "
                            f"'{value}' which does not appear in its cited evidence."
                        )
    if problems:
        raise KnowledgeMarkdownValidationError(problems)


def _file_tokens(file: UnderstoodFile) -> int:
    return sum(
        estimate_tokens(
            section.heading + section.body_md
            + "".join(record.text for record in section.uncertainties)
        )
        for section in file.sections
    )


def _file_ordinals(file: UnderstoodFile) -> set[int]:
    return {ordinal for section in file.sections for ordinal in section.evidence_ordinals}


def _merge_files(keep: UnderstoodFile, other: UnderstoodFile) -> UnderstoodFile:
    """Merge whole sections only; the larger file keeps its identity."""
    if _file_tokens(other) > _file_tokens(keep):
        keep, other = other, keep
    return keep.model_copy(update={"sections": (*keep.sections, *other.sections)})


def apply_split_guardrails(
    files: Sequence[UnderstoodFile],
    *,
    single_file_max_tokens: int = SINGLE_FILE_MAX_TOKENS,
    max_files: int = MAX_FILES_PER_SOURCE,
    merge_under_tokens: int = MERGE_UNDER_TOKENS,
    merge_shared_evidence: float = MERGE_SHARED_EVIDENCE,
) -> tuple[UnderstoodFile, ...]:
    """Enforce the topic-splitting guardrails deterministically (doc 33 §3.4).

    Sections are atomic: files merge, sections never split.
    """
    result = list(files)
    if len(result) > 1 and sum(_file_tokens(file) for file in result) <= single_file_max_tokens:
        merged = result[0]
        for other in result[1:]:
            merged = _merge_files(merged, other)
        result = [merged]

    def nearest_neighbour(index: int) -> int | None:
        ordinals = _file_ordinals(result[index])
        best: int | None = None
        best_shared = -1
        for other_index, other in enumerate(result):
            if other_index == index:
                continue
            shared = len(ordinals & _file_ordinals(other))
            if shared > best_shared:
                best, best_shared = other_index, shared
        return best

    changed = True
    while changed:
        changed = False
        for index, file in enumerate(result):
            if len(result) <= 1 or _file_tokens(file) >= merge_under_tokens:
                continue
            neighbour = nearest_neighbour(index)
            if neighbour is None:
                break
            ordinals = _file_ordinals(file)
            shared = len(ordinals & _file_ordinals(result[neighbour]))
            if ordinals and shared / len(ordinals) >= merge_shared_evidence:
                merged = _merge_files(result[neighbour], file)
                result = [
                    merged if i == neighbour else item
                    for i, item in enumerate(result) if i != index
                ]
                changed = True
                break
    while len(result) > max_files:
        smallest = min(range(len(result)), key=lambda i: _file_tokens(result[i]))
        neighbour = nearest_neighbour(smallest)
        if neighbour is None:
            break
        merged = _merge_files(result[neighbour], result[smallest])
        result = [
            merged if i == neighbour else item
            for i, item in enumerate(result) if i != smallest
        ]
    return tuple(result)


def locator_label(locator: Mapping[str, object]) -> str:
    """A short human label for an evidence locator, e.g. 'page 2'."""
    def _seconds(value: object) -> str:
        total = int(float(str(value)))
        return f"{total // 60}:{total % 60:02d}"

    if "page" in locator:
        return f"page {locator['page']}"
    if "slide" in locator:
        return f"slide {locator['slide']}"
    if "sheet" in locator and "row" in locator:
        return f"sheet {locator['sheet']}, row {locator['row']}"
    if "row" in locator:
        return f"row {locator['row']}"
    if "line_start" in locator:
        start = locator["line_start"]
        end = locator.get("line_end")
        return f"lines {start}–{end}" if end is not None and end != start else f"line {start}"
    if "json_path" in locator:
        return f"path {locator['json_path']}"
    if "start_seconds" in locator:
        label = _seconds(locator["start_seconds"])
        if "end_seconds" in locator:
            label += f"–{_seconds(locator['end_seconds'])}"
        return label
    if "source_url" in locator:
        return str(locator["source_url"])
    if "url" in locator:
        return str(locator["url"])
    return json.dumps(dict(locator), ensure_ascii=False, sort_keys=True)


def render_knowledge_file(
    file: UnderstoodFile,
    *,
    source_entry: str,
    source_name: str,
    file_version: int,
    generated_from: str,
    evidence: Mapping[int, MarkdownEvidenceUnit],
    original_url: str | None = None,
) -> str:
    """Render one understood file to its stored Markdown form (doc 33 §3.4)."""
    frontmatter = [
        "---",
        f"title: {json.dumps(file.title, ensure_ascii=False)}",
        f"description: {json.dumps(file.description, ensure_ascii=False)}",
        f"source_entry: {source_entry}",
        f"source_name: {json.dumps(source_name, ensure_ascii=False)}",
        f"file_version: {file_version}",
        f"generated_from: {json.dumps(generated_from, ensure_ascii=False)}",
    ]
    if original_url is not None:
        frontmatter.append(f"original_url: {json.dumps(original_url, ensure_ascii=False)}")
    frontmatter.append("---")

    parts = ["\n".join(frontmatter), f"# {file.title}"]
    uncertainties: list[UncertaintyRecord] = []
    cited: set[int] = set()
    for section in file.sections:
        parts.append(f"## {section.heading}\n\n{section.body_md.strip()}")
        uncertainties.extend(section.uncertainties)
        cited.update(section.evidence_ordinals)
    if uncertainties:
        lines = []
        for record in uncertainties:
            suffix = (
                f" (Evidence {', '.join(str(o) for o in record.evidence_ordinals)})"
                if record.evidence_ordinals else ""
            )
            lines.append(f"- {record.text}{suffix}")
        parts.append("## Uncertainties\n\n" + "\n".join(lines))
    else:
        parts.append("## Uncertainties\n\nNone recorded.")
    references = []
    for ordinal in sorted(cited):
        unit = evidence.get(ordinal)
        label = locator_label(unit.source_locator) if unit is not None else "unknown locator"
        references.append(f"- Evidence {ordinal} — {source_name}, {label}")
    parts.append("## Source references\n\n" + "\n".join(references))
    return "\n\n".join(parts) + "\n"
