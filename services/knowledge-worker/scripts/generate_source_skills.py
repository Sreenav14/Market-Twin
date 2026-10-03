"""Build grounded application knowledge from a supported MarketTwin source file."""

import argparse
import asyncio
import json
import shutil
from dataclasses import asdict
from pathlib import Path

from markettwin_knowledge_worker.extraction import ExtractionResult, extract_source


def _evidence_payload(
    *, extraction: ExtractionResult, include_content: bool
) -> list[dict[str, object]]:
    """Render extraction evidence without exposing media bytes."""
    return [
        {
            "ordinal": unit.ordinal,
            "evidence_type": unit.evidence_type,
            **(
                {
                    "content": (
                        unit.content_text if unit.content_text is not None else unit.content_json
                    ),
                }
                if include_content
                else {
                    "content_chars": len(
                        unit.content_text
                        or json.dumps(unit.content_json, ensure_ascii=False)
                    ),
                }
            ),
            "source_locator": unit.source_locator,
            "extractor": {
                "name": unit.extractor_name,
                "version": unit.extractor_version,
            },
        }
        for unit in extraction.units
    ]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        type=Path,
        help="Path to a supported MarketTwin knowledge source.",
    )
    parser.add_argument(
        "--include-evidence",
        action="store_true",
        help="Include complete extracted evidence content in the JSON output.",
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Extract and print source evidence without semantic generation.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Include evidence locators, extraction issues, and grounding metadata.",
    )
    args = parser.parse_args()
    if not args.source.is_file():
        raise FileNotFoundError(f"Source file does not exist: {args.source}")

    extraction = await extract_source(args.source)
    if args.extract_only:
        try:
            extraction_payload: dict[str, object] = {
                "source": extraction.source_path.name,
                "evidence": _evidence_payload(
                    extraction=extraction,
                    include_content=True,
                ),
            }
            if args.debug:
                extraction_payload["extraction_issues"] = [
                    asdict(issue) for issue in extraction.issues
                ]
            print(json.dumps(extraction_payload, indent=2, ensure_ascii=False))
        finally:
            for cleanup_path in extraction.cleanup_paths:
                shutil.rmtree(cleanup_path, ignore_errors=True)
        return

    # Adapter-only diagnostics must not initialize the model client or fetch its metadata.
    from markettwin_knowledge_worker.knowledge_builder import KnowledgeBuilder

    knowledge = await KnowledgeBuilder().build(extraction)
    payload: dict[str, object] = {
        "source": {
            "name": extraction.source_path.name,
            "path": str(extraction.source_path),
            "source_item_count": extraction.source_item_count,
            "processed_item_count": extraction.processed_item_count,
        },
        "application_knowledge": [
            item.model_dump(mode="json") for item in knowledge.application_knowledge
        ],
        "artifacts": [item.model_dump(mode="json") for item in knowledge.artifacts],
        "skills": [item.model_dump(mode="json") for item in knowledge.skills],
    }
    if args.debug or args.include_evidence:
        payload["evidence"] = _evidence_payload(
            extraction=extraction,
            include_content=args.include_evidence,
        )
        payload["extraction_issues"] = [asdict(issue) for issue in extraction.issues]
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
