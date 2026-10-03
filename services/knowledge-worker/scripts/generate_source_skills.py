"""Generate MarketTwin Skill drafts from any supported source file."""

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from markettwin_knowledge_worker.extraction import extract_source
from markettwin_knowledge_worker.skill_generator import SkillGenerator


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

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

    args = parser.parse_args()

    source = args.source

    if not source.is_file():
        raise FileNotFoundError(
            f"Source file does not exist: {source}"
        )

    extraction = await extract_source(
        source
    )

    skills = await SkillGenerator().generate(
        extraction
    )

    print(
        json.dumps(
            {
                "source": {
                    "name": extraction.source_path.name,
                    "path": str(extraction.source_path),
                    "source_item_count": (
                        extraction.source_item_count
                    ),
                    "processed_item_count": (
                        extraction.processed_item_count
                    ),
                },
                "evidence": [
                    {
                        "ordinal": unit.ordinal,
                        "evidence_type": (
                            unit.evidence_type
                        ),
                        **(
                            {
                                "content": unit.content_text
                                if unit.content_text is not None
                                else unit.content_json
                            }
                            if args.include_evidence
                            else {
                                "content_chars": len(
                                    unit.content_text
                                    or json.dumps(unit.content_json, ensure_ascii=False)
                                )
                            }
                        ),
                        "source_locator": (
                            unit.source_locator
                        ),
                        "extractor": {
                            "name": (
                                unit.extractor_name
                            ),
                            "version": (
                                unit.extractor_version
                            ),
                        },
                    }
                    for unit in extraction.units
                ],
                "extraction_issues": [
                    asdict(issue)
                    for issue in extraction.issues
                ],
                "skills": [
                    skill.model_dump(
                        mode="json"
                    )
                    for skill in skills
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
