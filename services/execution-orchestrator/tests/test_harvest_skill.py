"""Phase 1b journey selection and compilation (doc 16 sections
5.7-5.8 and 9, tests T-SK1 to T-SK4). All persistence is faked; the
registry failure in T-SK4 is the OQ2 blocker reproduced in miniature.
"""

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

from markettwin_execution_orchestrator.harvest.harvest_skill import (
    JourneyEdge,
    JourneyNode,
    build_definition,
    compile_journey,
    render_package,
    select_journey,
)
from markettwin_shared.feature_plan import TestCaseSpec
from sqlalchemy.exc import IntegrityError

BASE = "https://example.com/"


def node(url):
    return JourneyNode(
        page_id=uuid4(),
        canonical_url=url,
        default_state_id=uuid4(),
        default_state_identity=f"state-{url}",
        default_element_signature=["link|Go"],
    )


def edge(from_node, to_node, *, role="link", name="Go"):
    return JourneyEdge(
        from_page_id=from_node.page_id,
        from_state_id=from_node.default_state_id,
        element_id=uuid4(),
        role=role,
        name=name,
        locators=[{"kind": "role_name", "value": f"{role}|{name}", "stability": 1}],
        to_page_id=to_node.page_id,
    )


def graph(*nodes):
    return {item.page_id: item for item in nodes}


def test_recorded_form_action_preserves_parameter_binding():
    base, terminal = node(BASE), node(BASE + "agents")
    nodes = graph(base, terminal)
    recorded = replace(edge(base, terminal), action="fill", test_value_key="agent_name",
                       locators=[{"kind": "label", "value": "Agent name"}])
    selection = select_journey(
        nodes=nodes, edges=[recorded], base_page_id=base.page_id,
        owner_terminal_url=terminal.canonical_url,
    )
    assert selection is not None
    definition = build_definition(
        selection=selection, base_node=base, nodes=nodes, journey_name="Name agent",
        app_map=SimpleNamespace(id=uuid4(), version_number=1),
    )
    assert definition is not None
    assert definition["steps"][1] == {
        "action": "fill", "target": {"label": "Agent name"}, "test_value_key": "agent_name",
    }
    selection.path[0] = replace(recorded, test_value_key=None)
    assert build_definition(
        selection=selection, base_node=base, nodes=nodes, journey_name="Name agent",
        app_map=SimpleNamespace(id=uuid4(), version_number=1),
    ) is None


def test_compiled_navigation_does_not_claim_task_verification():
    base, terminal = node(BASE), node(BASE + "agents")
    nodes = graph(base, terminal)
    selection = select_journey(
        nodes=nodes, edges=[edge(base, terminal)], base_page_id=base.page_id,
        owner_terminal_url=terminal.canonical_url,
    )
    assert selection is not None
    app_map = SimpleNamespace(id=uuid4(), version_number=1)
    definition = build_definition(
        selection=selection, base_node=base, nodes=nodes,
        journey_name="Create an agent", app_map=app_map,
    )
    assert definition is not None
    assert definition["verification_scope"] == "navigation"
    package = render_package(
        selection=selection, journey_name="Create an agent", application_name="Glean",
        app_map=app_map, nodes=nodes, base_url=BASE,
    )
    assert "Arrival does not prove completion" in package["body_md"]


# T-SK1: conversion priority beats distance ties, and the owner's
# terminal overrides the rule entirely.
def test_selection_prefers_highest_priority_conversion_terminal():
    base, pricing, demo = node(BASE), node(BASE + "pricing"), node(BASE + "get-a-demo")
    nodes = graph(base, pricing, demo)
    edges = [edge(base, pricing, name="Pricing"), edge(base, demo, name="Get a demo")]
    selection = select_journey(
        nodes=nodes, edges=edges, base_page_id=base.page_id,
        owner_terminal_url=None,
    )
    assert selection is not None
    assert selection.terminal.canonical_url == BASE + "get-a-demo"
    assert selection.selection == "rule"
    assert len(selection.path) == 1

    owned = select_journey(
        nodes=nodes, edges=edges, base_page_id=base.page_id,
        owner_terminal_url=BASE + "pricing",
    )
    assert owned is not None
    assert owned.terminal.canonical_url == BASE + "pricing"
    assert owned.selection == "owner"


# T-SK2: with no conversion page reachable, the terminal is the page
# whose shortest path from the base is longest.
def test_selection_falls_back_to_longest_path():
    base = node(BASE)
    a, b, c = node(BASE + "a"), node(BASE + "b"), node(BASE + "c")
    nodes = graph(base, a, b, c)
    edges = [edge(base, a), edge(a, b), edge(b, c), edge(base, c)]
    selection = select_journey(
        nodes=nodes, edges=edges, base_page_id=base.page_id,
        owner_terminal_url=None,
    )
    assert selection is not None
    # c is reachable in 1 step directly, so the longest SHORTEST path
    # is b at depth 2.
    assert selection.terminal.canonical_url == BASE + "b"
    assert len(selection.path) == 2


def make_map():
    return SimpleNamespace(
        id=uuid4(), version_number=2, harvest_metrics={}
    )


# T-SK3: the compiled definition's native subset round-trips through
# the real TestCaseSpec contract; bindings parallel the click steps;
# an over-long journey is an honest compile failure (None).
def test_definition_round_trips_and_binds_every_click():
    base, demo = node(BASE), node(BASE + "get-a-demo")
    nodes = graph(base, demo)
    selection = select_journey(
        nodes=nodes, edges=[edge(base, demo)],
        base_page_id=base.page_id, owner_terminal_url=None,
    )
    assert selection is not None
    definition = build_definition(
        selection=selection, base_node=base, nodes=nodes,
        journey_name="Get a demo", app_map=make_map(),
    )
    assert definition is not None
    native = {
        key: definition[key]
        for key in (
            "case_id", "feature_key", "title", "kind", "steps",
            "expected", "safety", "estimated_seconds",
        )
    }
    spec = TestCaseSpec.model_validate(native)
    assert [step.action for step in spec.steps] == ["navigate", "click"]
    assert definition["locator_bindings"][0]["order"] == 2
    assert definition["locator_bindings"][0]["element"] == {
        "role": "link", "name": "Go",
    }
    assert definition["success_assertion"]["url"] == BASE + "get-a-demo"
    assert definition["success_assertion"]["state_id"] == demo.default_state_identity
    assert definition["source_map_version"] == 2

    long_base = node(BASE)
    chain_nodes = [long_base]
    chain_edges = []
    for index in range(25):
        nxt = node(f"{BASE}p{index}")
        chain_edges.append(edge(chain_nodes[-1], nxt))
        chain_nodes.append(nxt)
    long_selection = select_journey(
        nodes=graph(*chain_nodes), edges=chain_edges,
        base_page_id=long_base.page_id, owner_terminal_url=None,
    )
    assert long_selection is not None
    assert build_definition(
        selection=long_selection, base_node=long_base,
        nodes=graph(*chain_nodes), journey_name="Long", app_map=make_map(),
    ) is None


class FakeCompileRepository:
    def __init__(self, *, registry_error=None):
        self.journeys = []
        self.metrics = []
        self.attached = []
        self._registry_error = registry_error

    async def create_journey(self, app_map, **kwargs):
        journey = SimpleNamespace(id=uuid4(), **kwargs)
        self.journeys.append(journey)
        return journey

    async def create_skill_with_version(self, app_map, **kwargs):
        if self._registry_error is not None:
            raise self._registry_error
        skill = SimpleNamespace(id=uuid4())
        version = SimpleNamespace(id=uuid4(), skill_id=skill.id)
        return skill, version

    async def attach_journey_skill(self, journey_id, skill_id):
        self.attached.append((journey_id, skill_id))

    async def save_harvest_metrics(self, map_id, updates):
        self.metrics.append(updates)
        return updates


async def test_journey_with_inputs_is_refused_before_registry_or_replay():
    base, terminal = node(BASE), node(BASE + "agents")
    selection = select_journey(
        nodes=graph(base, terminal),
        edges=[replace(edge(base, terminal), action="fill", test_value_key="name")],
        base_page_id=base.page_id, owner_terminal_url=terminal.canonical_url,
    )
    repository = FakeCompileRepository()
    result = await compile_journey(
        repository=repository, app_map=make_map(), selection=selection,
        base_node=base, nodes=graph(base, terminal), journey_name="Name agent",
        application_name="Example",
    )
    assert result.skill_version is None
    assert result.registry_error == "journey_input_context_unavailable"
    assert not repository.journeys
    assert repository.metrics[-1]["skill_compile"]["result"] == "refused"


# T-SK4: when the registry write is blocked (OQ2), the journey row
# still lands, the failure is recorded in harvest_metrics with the
# real error named, and no skill version is claimed.
async def test_compile_records_registry_blocker_honestly():
    base, demo = node(BASE), node(BASE + "get-a-demo")
    nodes = graph(base, demo)
    selection = select_journey(
        nodes=nodes, edges=[edge(base, demo)],
        base_page_id=base.page_id, owner_terminal_url=None,
    )
    assert selection is not None
    repository = FakeCompileRepository(
        registry_error=IntegrityError(
            "INSERT", {}, RuntimeError("null value in column blueprint_id")
        )
    )
    result = await compile_journey(
        repository=repository,
        app_map=make_map(),
        selection=selection,
        base_node=base,
        nodes=nodes,
        journey_name="Get a demo",
        application_name="Demo Store",
    )
    assert result.journey is not None
    assert result.skill_version is None
    assert result.registry_error is not None
    assert "IntegrityError" in result.registry_error
    assert repository.attached == []
    compile_records = [
        item["skill_compile"]
        for item in repository.metrics
        if "skill_compile" in item
    ]
    assert compile_records[-1]["result"] == "failed"
    assert "blueprint_id" in compile_records[-1]["reason"]
    assert result.definition is not None
    assert result.definition["source_journey_id"] == str(result.journey.id)
    assert result.package is not None
    assert result.package["catalogue"]["level2"] == "body_md"
