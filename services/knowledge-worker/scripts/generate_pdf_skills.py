"""Run the V1 PDF-to-Skills proof without Kafka or database writes."""

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from markettwin_knowledge_worker.extraction import PdfExtractor
from markettwin_knowledge_worker.skill_generator import SkillGenerator


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Path to the PDF to extract and synthesize.")
    args = parser.parse_args()
    extraction = PdfExtractor().extract(args.pdf)
    skills = await SkillGenerator().generate(extraction)
    print(
        json.dumps(
            {
                "source_name": extraction.source_path.name,
                "evidence": [
                    {
                        "ordinal": unit.ordinal,
                        "content": unit.content_text,
                        "source_locator": unit.source_locator,
                    }
                    for unit in extraction.units
                ],
                "extraction_issues": [asdict(issue) for issue in extraction.issues],
                "skills": [skill.model_dump(mode="json") for skill in skills],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
