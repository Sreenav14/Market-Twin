"""Phase 1b run-side map lookups (doc 16 section 8, tests T-LK1 to
T-LK3). Pure functions over a snapshot block — no database, no
browser, no model.
"""

from markettwin_execution_orchestrator.workflow.map_lookup import (
    EXPECTATIONS_SOURCE,
    find_journey,
    find_page,
    find_skill,
    get_expectations,
    page_elements,
)

BLOCK = {
    "map_id": "map-1",
    "pages": [
        {
            "url": "https://example.com/",
            "effective_url": "https://example.com/",
            "pattern": "/",
            "elements": [
                {
                    "state_key": "default",
                    "state_id": "s1",
                    "elements": [
                        {"role": "link", "name": "Pricing"},
                        {"role": "button", "name": "Open menu"},
                    ],
                },
                {
                    "state_key": "observed-1",
                    "state_id": "s2",
                    "elements": [{"role": "link", "name": "Close"}],
                },
            ],
        },
        {
            "url": "https://example.com/pricing",
            "effective_url": "https://example.com/pricing",
            "pattern": "/pricing",
            "states": [],
        },
    ],
    "journeys": [
        {"name": "Reach pricing", "intent": "see pricing",
         "selection": "rule", "terminal_url": "https://example.com/pricing",
         "steps": [{"page_url": "https://example.com/", "role": "link",
                    "name": "Pricing"}]},
    ],
    "skills": [
        {"name": "reach-pricing", "description": "Use when...",
         "definition": {"case_id": "reach_pricing_ab12"},
         "skill_version_id": "v1"},
    ],
}


# T-LK1: page lookup matches canonically (trailing slash, effective
# URL), and page elements flatten across states with the state key
# kept; a census-only page yields an empty list, an unknown page
# yields None.
def test_page_lookup_and_elements():
    page = find_page(BLOCK, "https://example.com")
    assert page is not None
    assert page["pattern"] == "/"
    assert find_page(BLOCK, "https://example.com/missing") is None
    assert find_page(None, "https://example.com/") is None

    elements = page_elements(BLOCK, "https://example.com/")
    assert elements is not None
    assert [(item["role"], item["name"], item["state_key"]) for item in elements] == [
        ("link", "Pricing", "default"),
        ("button", "Open menu", "default"),
        ("link", "Close", "observed-1"),
    ]
    assert page_elements(BLOCK, "https://example.com/pricing") == []
    assert page_elements(BLOCK, "https://example.com/missing") is None


# T-LK2: journey and skill lookup — first by default, by name when
# asked, None when absent; a 1a-shaped block (no keys) finds nothing.
def test_journey_and_skill_lookup():
    assert find_journey(BLOCK)["name"] == "Reach pricing"
    assert find_journey(BLOCK, "Reach pricing")["selection"] == "rule"
    assert find_journey(BLOCK, "Nope") is None
    assert find_skill(BLOCK)["skill_version_id"] == "v1"
    assert find_skill(BLOCK, "reach-pricing")["name"] == "reach-pricing"
    assert find_skill(BLOCK, "nope") is None
    legacy = {"pages": []}
    assert find_journey(legacy) is None
    assert find_skill(legacy) is None


# T-LK3: expectations are the labelled empty result in 1b — an empty
# list that still says where the absence comes from.
def test_expectations_are_labelled_empty_in_1b():
    result = get_expectations(BLOCK, "https://example.com/")
    assert result == []
    assert isinstance(result, list)
    assert result.source == "none_in_1b"
    assert EXPECTATIONS_SOURCE == "none_in_1b"
    assert get_expectations(None) == []
