"""Phase 1b enrichment (doc 16 section 5.6, tests T-EN1 to T-EN5).

The door and the repository are fakes; the accountant is a constant.
No model is ever called in this file — that is the point of the door.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from markettwin_execution_orchestrator.harvest.harvest_enrich import (
    Exemplar,
    enrich_map,
    group_pages,
)


def make_page(pattern, url):
    return SimpleNamespace(
        id=uuid4(), route_pattern=pattern, canonical_url=url, title="T"
    )


def exemplar(url="https://example.com/a", pattern="/a"):
    return Exemplar(
        url=url,
        route_pattern=pattern,
        title="A page",
        element_names=["Go"],
        form_labels=[],
        aria_excerpt="- button \"Go\"",
    )


class FakeRepository:
    def __init__(self, *, spend_calls=0, spend_tokens=0, log=None):
        self.map_row = SimpleNamespace(
            id=uuid4(),
            harvest_metrics={},
            mapping_spend_calls=spend_calls,
            mapping_spend_tokens=spend_tokens,
            mapping_budget_calls=None,
            mapping_budget_tokens=None,
        )
        self.log = log if log is not None else []
        self.purposes = []
        self.metrics_saves = []

    async def get_map(self, map_id):
        return self.map_row

    async def record_mapping_budgets(self, map_id, *, calls_cap, tokens_cap):
        self.log.append("budgets")
        self.map_row.mapping_budget_calls = calls_cap
        self.map_row.mapping_budget_tokens = tokens_cap

    async def record_enrichment_spend(self, map_id, *, calls_delta, tokens_delta):
        self.log.append("spend")
        self.map_row.mapping_spend_calls += calls_delta
        self.map_row.mapping_spend_tokens += tokens_delta
        return self.map_row.mapping_spend_calls, self.map_row.mapping_spend_tokens

    async def save_harvest_metrics(self, map_id, updates):
        self.metrics_saves.append(updates)
        merged = dict(self.map_row.harvest_metrics)
        merged.update(updates)
        self.map_row.harvest_metrics = merged
        return merged

    async def set_page_purpose(self, page_id, *, purpose, purpose_source,
                               template_group):
        self.purposes.append(
            {
                "page_id": page_id,
                "purpose": purpose,
                "purpose_source": purpose_source,
                "template_group": template_group,
            }
        )


class FakeDoor:
    def __init__(self, outputs, log=None):
        self._outputs = list(outputs)
        self.calls = 0
        self.log = log

    async def draft(self, *, system, user):
        self.calls += 1
        if self.log is not None:
            self.log.append("door")
        output = self._outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


VALID = {"purpose": "Shows the thing.", "actions": ["Go"], "journey_name": None}


# T-EN1: grouping merges patterns whose exemplars share a structure
# hash; the merged key is the smallest pattern; a missing hash never
# merges.
def test_grouping_merges_on_shared_structure_hash():
    page_a = make_page("/items/{id}", "https://example.com/items/1")
    page_b = make_page("/things/{id}", "https://example.com/things/2")
    page_c = make_page("/about", "https://example.com/about")
    groups = group_pages(
        [(page_a, "hash-1"), (page_b, "hash-1"), (page_c, None)]
    )
    assert set(groups) == {"/items/{id}", "/about"}
    assert groups["/items/{id}"] == [page_a, page_b]
    assert groups["/about"] == [page_c]


# T-EN2: the happy path drafts one purpose per group and stamps every
# page in the group model-draft.
async def test_enrichment_writes_purposes_as_model_draft():
    repository = FakeRepository()
    page_a = make_page("/a", "https://example.com/a")
    page_b = make_page("/a", "https://example.com/a2")
    groups = {"/a": [page_a, page_b]}
    result = await enrich_map(
        repository=repository,
        app_map=repository.map_row,
        groups=groups,
        exemplars={"/a": exemplar()},
        door=FakeDoor([VALID]),
        accountant=lambda *, system, user: 100,
    )
    assert result.enriched_groups == 1
    assert result.unenriched == []
    assert result.spend_calls == 1
    assert result.spend_tokens == 100
    assert len(repository.purposes) == 2
    assert all(
        purpose["purpose_source"] == "model-draft"
        for purpose in repository.purposes
    )
    assert repository.map_row.harvest_metrics["group_enrichment"]["/a"][
        "purpose"
    ] == "Shows the thing."


# T-EN3: one malformed answer is retried; the retry is a second,
# separately charged call.
async def test_enrichment_retries_one_malformed_output():
    repository = FakeRepository()
    groups = {"/a": [make_page("/a", "https://example.com/a")]}
    door = FakeDoor([{"purpose": 42}, VALID])
    result = await enrich_map(
        repository=repository,
        app_map=repository.map_row,
        groups=groups,
        exemplars={"/a": exemplar()},
        door=door,
        accountant=lambda *, system, user: 10,
    )
    assert result.enriched_groups == 1
    assert door.calls == 2
    assert result.spend_calls == 2


# T-EN4: two malformed answers leave the group unenriched with the
# reason named; no purpose is written.
async def test_enrichment_unenriched_after_two_malformed_outputs():
    repository = FakeRepository()
    groups = {"/a": [make_page("/a", "https://example.com/a")]}
    door = FakeDoor([{"nope": True}, ["not", "a", "dict"]])
    result = await enrich_map(
        repository=repository,
        app_map=repository.map_row,
        groups=groups,
        exemplars={"/a": exemplar()},
        door=door,
        accountant=lambda *, system, user: 10,
    )
    assert result.enriched_groups == 0
    assert result.unenriched == [{"group": "/a", "reason": "invalid_output"}]
    assert repository.purposes == []


# T-EN5: the caps are recorded on the map row BEFORE the first door
# call, and reaching the call cap leaves the remaining groups
# unenriched with reason 'cap'.
async def test_enrichment_records_caps_before_first_call_and_stops_at_cap():
    log: list[str] = []
    repository = FakeRepository(spend_calls=299, log=log)
    groups = {
        "/a": [make_page("/a", "https://example.com/a")],
        "/b": [make_page("/b", "https://example.com/b")],
    }
    door = FakeDoor([VALID], log=log)
    result = await enrich_map(
        repository=repository,
        app_map=repository.map_row,
        groups=groups,
        exemplars={"/a": exemplar(), "/b": exemplar("https://example.com/b", "/b")},
        door=door,
        accountant=lambda *, system, user: 10,
    )
    assert log[0] == "budgets"
    assert log.index("budgets") < log.index("door")
    assert repository.map_row.mapping_budget_calls == 300
    assert repository.map_row.mapping_budget_tokens == 1_000_000
    assert result.enriched_groups == 1
    assert result.cap_reached == "model_calls"
    assert result.unenriched == [{"group": "/b", "reason": "cap"}]


@pytest.mark.parametrize("calls,tokens", [(299, 0), (0, 999990)])
async def test_malformed_retry_cannot_cross_either_cap(calls, tokens):
    repository = FakeRepository(spend_calls=calls, spend_tokens=tokens)
    door = FakeDoor([{"invalid": True}, VALID])
    result = await enrich_map(
        repository=repository, app_map=repository.map_row,
        groups={"/a": [make_page("/a", "https://example.com/a")]},
        exemplars={"/a": exemplar()}, door=door, accountant=lambda **kwargs: 10,
    )
    assert door.calls == 1
    assert result.unenriched == [{"group": "/a", "reason": "cap"}]
    assert result.spend_calls <= 300 and result.spend_tokens <= 1_000_000


async def test_door_error_still_charges_attempted_spend():
    repository = FakeRepository()
    result = await enrich_map(
        repository=repository, app_map=repository.map_row,
        groups={"/a": [make_page("/a", "https://example.com/a")]},
        exemplars={"/a": exemplar()}, door=FakeDoor([RuntimeError("provider failed")]),
        accountant=lambda **kwargs: 10,
    )
    assert result.spend_calls == 1 and result.spend_tokens == 10
    assert result.unenriched == [{"group": "/a", "reason": "door_error"}]
