"""Doc 21 section 12: persona graph derivation tests (T-PN1..T-PN3)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from markettwin_execution_orchestrator.workflow import persona_run


def _request(app_map):
    return SimpleNamespace(app_map=app_map, study_brief="Study the shop")


def test_t_pn1_objectives_derive_from_journeys_not_steps():
    request = _request(
        {
            "journeys": [
                {
                    "name": "Buy a mug",
                    "intent": "Buy a mug and check out",
                    "terminal_url": "https://shop.example.com/thanks",
                    "steps": [
                        {"map_page_state_id": "abc", "element_id": "el-1"}
                    ],
                },
                {"name": "Find help", "intent": "", "terminal_url": None, "steps": []},
            ]
        }
    )
    objectives = persona_run.persona_objectives(request)
    assert objectives == [
        "Buy a mug and check out (The goal is reached at https://shop.example.com/thanks.)",
        "Find help",
    ]
    for objective in objectives:
        assert "el-1" not in objective
        assert "map_page_state_id" not in objective


def test_t_pn2_fallback_to_study_brief_without_journeys():
    assert persona_run.persona_objectives(_request(None)) == ["Study the shop"]
    assert persona_run.persona_objectives(_request({"journeys": []})) == [
        "Study the shop"
    ]
    assert persona_run.persona_objectives(
        _request({"journeys": [{"steps": []}]})
    ) == ["Study the shop"]


def test_t_pn3_persona_modules_never_write_the_graph():
    for module in (persona_run,):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "MapExpectation" not in source
        assert "GroundingRepository" not in source
        assert "insert_expectation" not in source
        assert "expectations_repository" not in source
