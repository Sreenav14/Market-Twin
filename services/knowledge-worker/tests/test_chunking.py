"""Focused checks for content preservation and deterministic structural ranges."""

from markettwin_knowledge_worker.extraction.chunking import SourcePart, pack_source_parts


def test_chunking_preserves_order_content_and_ranges() -> None:
    parts = [SourcePart(f"part-{i}", {"paragraph": i}) for i in range(1, 6)]
    chunks = pack_source_parts(parts, max_chars=14, separator="\n")
    assert "\n".join(chunk.text for chunk in chunks) == "\n".join(part.text for part in parts)
    assert all(len(chunk.text) <= 14 for chunk in chunks)
    assert chunks[0].source_locator == {"paragraph_start": 1, "paragraph_end": 2}
    assert chunks == pack_source_parts(parts, max_chars=14, separator="\n")


def test_oversized_part_and_mixed_locators_preserve_content() -> None:
    chunks = pack_source_parts([SourcePart("x" * 35, {"page": 4})], max_chars=10)
    assert "".join(chunk.text for chunk in chunks) == "x" * 35
    assert all(chunk.source_locator == {"page_start": 4, "page_end": 4} for chunk in chunks)
    mixed = pack_source_parts(
        [
            SourcePart("before", {"paragraph": 1}),
            SourcePart("table", {"table": 1}),
            SourcePart("after", {"paragraph": 2}),
        ],
        max_chars=100,
    )
    assert mixed[0].source_locator == {
        "paragraph_start": 1,
        "paragraph_end": 2,
        "table_start": 1,
        "table_end": 1,
    }
