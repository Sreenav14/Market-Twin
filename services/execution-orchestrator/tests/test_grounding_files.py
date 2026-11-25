"""Doc 33 step 6: grounding candidates derive from Markdown files.

The candidate pool reads approved entries' knowledge files (one
candidate per file section, source ref entry:slug:section); the
legacy preview slice is no longer consumed by grounding.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # for grounding_fakes

from types import SimpleNamespace
from uuid import uuid4

import pytest
from grounding_fakes import (
    FakeDoor,
    FakeGroundingRepository,
    entry_with_files,
    make_map,
    seed_graph,
)

from markettwin_execution_orchestrator.expectations.grounding import (
    extract_candidates,
)
from markettwin_execution_orchestrator.expectations.grounding_job import (
    execute_grounding,
    production_stages,
)

pytestmark = pytest.mark.asyncio

PRICING_MD = """---
title: Pricing
description: Plan prices and the annual-discount exception.
source_entry: {entry}
---

# Pricing

## Plans
The Pro plan costs $50 per month. The Team plan costs $200 per month.

> **Exception:** the annual discount does not apply to the Team plan.

## Billing
Invoices are issued on the first of each month.

## Uncertainties
- The guide does not say whether prices include tax.

## Source references
- Evidence 3 — pricing-guide.pdf, page 2
"""

REFUNDS_MD = """# Refunds

## Window
Refunds are available within 30 days of purchase.
"""


def test_candidates_come_from_file_sections():
    entry_id = uuid4()
    entry = entry_with_files(
        entry_id,
        [
            {"slug": "pricing", "content": PRICING_MD.format(entry=entry_id)},
            {"slug": "refunds", "content": REFUNDS_MD},
        ],
    )
    candidates = extract_candidates([entry])
    assert [(c.name, c.ordinal) for c in candidates] == [
        ("Plans", 0),
        ("Billing", 1),
        ("Window", 2),
    ]
    assert candidates[0].source_ref == f"{entry_id}:pricing:Plans"
    assert candidates[2].source_ref == f"{entry_id}:refunds:Window"
    assert "$50 per month" in candidates[0].content
    assert "annual discount does not apply" in candidates[0].content
    assert all(c.source_kind == "owner_document" for c in candidates)
    # Uncertainties / Source references sections never become candidates.
    assert all("include tax" not in c.content for c in candidates)
    assert all("Evidence 3" not in c.content for c in candidates)


def test_entry_with_files_ignores_stale_preview():
    entry_id = uuid4()
    entry = entry_with_files(
        entry_id, [{"slug": "refunds", "content": REFUNDS_MD}]
    )
    entry.preview = {
        "application_knowledge": [
            {
                "name": "Stale",
                "content": "The stale preview claims a 90 day window.",
                "source_kind": "owner_document",
            }
        ]
    }
    candidates = extract_candidates([entry])
    assert [c.name for c in candidates] == ["Window"]
    assert all("90 day" not in c.content for c in candidates)


def test_entry_with_preview_only_yields_no_candidates():
    entry = SimpleNamespace(
        id=uuid4(),
        preview={
            "application_knowledge": [
                {
                    "name": "Legacy",
                    "content": "Preview-only knowledge.",
                    "source_kind": "owner_document",
                }
            ]
        },
    )
    assert extract_candidates([entry]) == []


def test_candidates_from_structured_contract_sections():
    # The shared knowledge_markdown contract shape: slug + sections of
    # heading/body_md (UnderstoodFile), no rendered text involved.
    entry_id = uuid4()
    entry = entry_with_files(
        entry_id,
        [
            {
                "slug": "pricing",
                "sections": [
                    {"heading": "Plans", "body_md": "The Pro plan costs $50."},
                    {"heading": "Empty", "body_md": "  "},
                ],
            }
        ],
    )
    candidates = extract_candidates([entry])
    assert [(c.name, c.content, c.ordinal) for c in candidates] == [
        ("Plans", "The Pro plan costs $50.", 0)
    ]
    assert candidates[0].source_ref == f"{entry_id}:pricing:Plans"


async def test_file_candidate_matches_and_authors_with_file_ref():
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    seed_graph(repo, app_map)
    entry_id = uuid4()
    repo.entries = [
        entry_with_files(
            entry_id,
            [
                {
                    "slug": "guide",
                    "content": (
                        "# Guide\n\n## Checkout\n"
                        "'Buy now' completes the purchase.\n"
                    ),
                }
            ],
        )
    ]
    await execute_grounding(
        repo, app_map, production_stages(FakeDoor([])), door=FakeDoor([])
    )
    doc_rows = [
        r for r in repo.expectations if r.oracle_source == "documentation"
    ]
    assert len(doc_rows) == 1
    assert doc_rows[0].source_ref == f"{entry_id}:guide:Checkout"
    assert app_map.grounding_metrics["promotions_at_grounding"] == 0
