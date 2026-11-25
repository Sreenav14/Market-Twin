"""Doc 21 section 7: form probing tests (T-PR1..T-PR6)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # for grounding_fakes

import pytest
from grounding_fakes import (
    BASE,
    FakeGroundingRepository,
    make_element,
    make_field,
    make_form,
    make_map,
    seed_graph,
)

from markettwin_execution_orchestrator.expectations.grounding import GraphIndex
from markettwin_execution_orchestrator.expectations.grounding_job import (
    GroundingContext,
    production_stages,
)
from markettwin_execution_orchestrator.expectations.probing import run_probing

pytestmark = pytest.mark.asyncio

PAGE = f"{BASE}/"
DONE = f"{BASE}/done"


class FakeDriver:
    def __init__(self, script, *, fail_on_submit=False):
        self.script = list(script)
        self.calls: list = []
        self.fail_on_submit = fail_on_submit

    async def open(self, url):
        self.calls.append(("open", url))

    async def fill(self, *, label, value):
        self.calls.append(("fill", label, value))

    async def submit(self):
        self.calls.append(("submit",))
        if self.fail_on_submit:
            raise RuntimeError("ambiguous submit")

    async def observe(self):
        self.calls.append(("observe",))
        return self.script.pop(0)


def _obs(url, lines, state_id="s0"):
    return {
        "url": url,
        "aria_lines": lines,
        "state_id": state_id,
        "element_signature": "",
    }


def _setup(*, submit_safety="read_only", extra_fields=lambda form: ()):
    app_map = make_map()
    repo = FakeGroundingRepository(app_map)
    graph = seed_graph(repo, app_map)
    submit = make_element(
        graph["home_state"], "Send", page_id=graph["home"].id
    )
    submit.safety_class = submit_safety
    form = make_form(graph["home"], graph["home_state"], submit)
    form.method = "get"
    form.action_url = PAGE
    email = make_field(form, "Email")
    repo.forms = [form]
    repo.fields = [email, *extra_fields(form)]
    repo.elements = [graph["buy"], submit]
    ctx = GroundingContext(repository=repo, app_map=app_map)
    ctx.index = GraphIndex(
        pages=repo.pages,
        states=repo.states,
        elements=repo.elements,
        forms=repo.forms,
        fields=repo.fields,
        transitions=repo.transitions,
        journeys=[],
    )
    return app_map, repo, ctx, form, email, submit


async def test_t_pr1_probe_stage_skips_without_standard_mode_trigger():
    _app_map, repo, ctx, _form, _email, _submit = _setup()
    stages = production_stages(None)
    await stages.candidates(ctx)  # builds the graph index from the repo
    await stages.probe(ctx)
    assert ctx.metrics["probes"]["skipped_no_standard_mode"] == 1
    assert ctx.metrics["probes"]["attempted"] == 0


async def test_t_pr2_destructive_form_named_and_never_submitted():
    _app_map, repo, ctx, form, _email, _submit = _setup(
        submit_safety="irreversible"
    )
    driver = FakeDriver([])
    probes = await run_probing(ctx, approved_test_data={}, driver=driver)
    assert driver.calls == []
    assert probes["unprobed_destructive"] == 1
    assert probes["attempted"] == 0
    assert form.probe_status == "unprobed_destructive"


@pytest.mark.parametrize("method,action,probe_status", [
    ("post", PAGE, "unprobed_readonly"),
    ("get", "https://other.example/submit", "unprobed_readonly"),
    ("get", "javascript:submit()", "unprobed_readonly"),
    ("get", PAGE, "unprobed_destructive"),
])
async def test_unsafe_form_metadata_blocks_before_empty_submit(method, action, probe_status):
    _app_map, repo, ctx, form, _email, _submit = _setup()
    form.method, form.action_url, form.probe_status = method, action, probe_status
    driver = FakeDriver([])
    probes = await run_probing(ctx, approved_test_data={}, driver=driver)
    assert probes["unprobed_destructive"] == 1
    assert driver.calls == []


async def test_missing_submit_is_counted_explicitly():
    _app_map, repo, ctx, form, _email, _submit = _setup()
    form.submit_element_id = None
    driver = FakeDriver([])
    probes = await run_probing(ctx, approved_test_data={}, driver=driver)
    assert probes["skipped_no_submit"] == 1
    assert probes["probed"] == 0
    assert driver.calls == []


async def test_t_pr3_empty_submit_error_is_written_and_authored():
    _app_map, repo, ctx, form, email, _submit = _setup()
    driver = FakeDriver(
        [
            _obs(PAGE, ["Email", "Send"]),
            _obs(PAGE, ["Email", "Send", "Email is required"], "serr"),
            _obs(DONE, ["Thanks"], "s9"),
        ]
    )
    probes = await run_probing(
        ctx, approved_test_data={"Email": "a@b.co"}, driver=driver
    )
    assert probes["probed"] == 1
    assert email.error_text_observed == "Email is required"
    assert email.validation_source == "probed"
    assert form.probe_status == "probed"
    authored = [
        row
        for row in repo.expectations
        if row.oracle_source == "observation"
        and row.assertion
        and row.assertion.get("kind") == "field_validation"
    ]
    assert len(authored) == 1
    assert authored[0].source_ref == f"probe:{form.id}:{email.id}"
    assert authored[0].assertion["params"]["probe_case"] == "empty"
    assert repo.probe_states and repo.probe_states[0]["state_id"] == "serr"


async def test_t_pr4_one_invalid_value_per_constrained_field():
    def extra(form):
        return [make_field(form, "Name", field_type="text", ordinal=1)]

    _app_map, repo, ctx, form, email, _submit = _setup(extra_fields=extra)
    driver = FakeDriver(
        [
            _obs(PAGE, ["Email", "Name", "Send"]),
            _obs(PAGE, ["Email", "Name", "Send"]),  # empty: no errors
            _obs(PAGE, ["Email", "Name", "Send", "Email is invalid"]),
            _obs(PAGE, ["Email", "Name", "Send", "Name is required"]),
        ]
    )
    probes = await run_probing(ctx, approved_test_data={}, driver=driver)
    fills = [call for call in driver.calls if call[0] == "fill"]
    assert len(fills) == 2  # exactly one invalid value per field
    assert probes["valid_completion"][str(form.id)] == "no_test_data"
    assert email.error_text_observed == "Email is invalid"
    name_field = repo.fields[1]
    assert name_field.error_text_observed == "Name is required"


async def test_t_pr5_valid_completion_records_success_transition():
    _app_map, repo, ctx, form, _email, _submit = _setup()
    driver = FakeDriver(
        [
            _obs(PAGE, ["Email", "Send"]),
            _obs(PAGE, ["Email", "Send", "Email is required"], "serr"),
            _obs(DONE, ["Thanks"], "s9"),
        ]
    )
    probes = await run_probing(
        ctx, approved_test_data={"Email": "a@b.co"}, driver=driver
    )
    assert probes["valid_completion"][str(form.id)] == "done"
    assert repo.success_requests == ["s9"]
    assert form.success_transition_id is not None


async def test_t_pr6_ambiguous_submit_never_retried_and_no_model_imports():
    _app_map, repo, ctx, _form, _email, _submit = _setup()
    driver = FakeDriver(
        [_obs(PAGE, ["Email", "Send"])], fail_on_submit=True
    )
    probes = await run_probing(
        ctx, approved_test_data={"Email": "a@b.co"}, driver=driver
    )
    submits = [call for call in driver.calls if call[0] == "submit"]
    assert len(submits) == 1
    assert probes["attempted"] == 1
    assert probes["probed"] == 0
    assert any(
        failure["stage"] == "probe" for failure in ctx.metrics["failures"]
    )

    import markettwin_execution_orchestrator.expectations.probing as probing

    source = Path(probing.__file__).read_text(encoding="utf-8")
    assert "models import ask" not in source
    assert "openai" not in source
    assert "_model_json" not in source
