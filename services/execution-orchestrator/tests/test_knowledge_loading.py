"""Doc 33 Steps 4-5: run-start source-knowledge loading, the
ask-door selection call-point, and the mid-run open tool.

- a directly attached file loads whole into the plan, with its
  knowledge.file.opened event;
- a collection is shortlisted deterministically (a pricing brief
  picks the pricing file, a refunds brief does not);
- the deterministic ask-door backend returns the shortlist order
  untouched and makes zero model calls;
- over-budget and integrity-failed files are omitted BY NAME;
- a mid-run open appends a collection file, and refuses files
  outside the attached set and files that break the budget.
"""

from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.browser import AllowedOrigin
from markettwin_execution_orchestrator.models import ask
from markettwin_execution_orchestrator.workflow import (
    app_plan,
    knowledge_loading,
    lead_review,
    run_executor,
    run_request,
)

ENTRY_ID = uuid4()
FILE_ID = uuid4()
PRICING_ID = uuid4()
REFUNDS_ID = uuid4()


def sha(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def content(file_id, *, slug, title, description, text, token_count=None):
    return {
        "file_id": str(file_id), "entry_id": str(ENTRY_ID), "slug": slug,
        "title": title, "description": description, "text": text,
        "sha256": sha(text),
        "token_count": token_count if token_count is not None else -(-len(text) // 4),
    }


def manifest_entry(file_id, *, slug, title, description, text, token_count=None):
    return {
        "file_id": str(file_id), "slug": slug, "title": title,
        "description": description, "object_key": f"knowledge/x/{slug}.md",
        "sha256": sha(text),
        "token_count": token_count if token_count is not None else -(-len(text) // 4),
        "section_headings": [],
    }


class FakeClient:
    def __init__(self, contents=None, manifests=None):
        self.contents = contents or {}
        self.manifests = manifests or {}
        self.content_calls: list[str] = []

    async def fetch_file_content(self, file_id):
        self.content_calls.append(file_id)
        return self.contents.get(file_id)

    async def fetch_collection_manifest(self, entry_id, version):
        return self.manifests.get((entry_id, version))


@pytest.fixture
def events(monkeypatch):
    recorded = []

    class FakeRepo:
        def __init__(self, session):
            pass

        async def create(self, **kwargs):
            recorded.append(kwargs)

    monkeypatch.setattr(knowledge_loading, "RunEventRepository", FakeRepo)
    return recorded


@pytest.fixture(autouse=True)
def _deterministic_door(monkeypatch):
    monkeypatch.delenv("ASK_BACKEND_SELECT_KNOWLEDGE_FILES", raising=False)
    monkeypatch.delenv("ASK_BACKEND_RANK_ITEMS", raising=False)


def make_request(pin, brief="Check the pricing plans and the annual discount."):
    return SimpleNamespace(run_id=uuid4(), study_brief=brief, source_knowledge=pin)


def direct_pin():
    text = "# Pricing\n\nThe Team plan costs $40 per month."
    return {
        "files": [{
            "file_id": str(FILE_ID), "entry_id": str(ENTRY_ID),
            "slug": "pricing", "title": "Pricing",
            "object_key": "knowledge/x/pricing.md", "sha256": sha(text),
        }],
        "collections": [],
    }, text


def collection_setup():
    pricing_text = "# Pricing\n\nThe Team plan costs $40 per month."
    refunds_text = "# Refunds\n\nRefunds are issued within 30 days."
    manifest = {"entry_id": str(ENTRY_ID), "version": 1, "files": [
        manifest_entry(PRICING_ID, slug="pricing", title="Pricing",
                       description="Plan prices and billing cycles.",
                       text=pricing_text),
        manifest_entry(REFUNDS_ID, slug="refunds", title="Refunds",
                       description="Refund windows and exceptions.",
                       text=refunds_text),
    ]}
    client = FakeClient(
        contents={
            str(PRICING_ID): content(PRICING_ID, slug="pricing", title="Pricing",
                                     description="Plan prices and billing cycles.",
                                     text=pricing_text),
            str(REFUNDS_ID): content(REFUNDS_ID, slug="refunds", title="Refunds",
                                     description="Refund windows and exceptions.",
                                     text=refunds_text),
        },
        manifests={(str(ENTRY_ID), 1): manifest},
    )
    pin = {"files": [], "collections": [{
        "entry_id": str(ENTRY_ID),
        "manifest_object_key": "knowledge/x/files/v1/manifest.json",
        "version": 1,
    }]}
    return pin, client, pricing_text, refunds_text


# --- snapshot parser ---------------------------------------------------


def test_parser_accepts_the_pinned_shape():
    pin, _ = direct_pin()
    snapshot = {"source_knowledge": pin}
    assert run_request._parse_source_knowledge(snapshot) == pin


@pytest.mark.parametrize("block", [
    {"files": [{"file_id": "f"}], "collections": []},
    {"files": [], "collections": [{"entry_id": "e"}]},
    {"files": "nope", "collections": []},
    ["not-a-dict"],
])
def test_parser_treats_a_malformed_block_as_absent(block):
    assert run_request._parse_source_knowledge({"source_knowledge": block}) is None
    assert run_request._parse_source_knowledge({}) is None


# --- plan-time loading ---------------------------------------------------


@pytest.mark.asyncio
async def test_direct_file_loads_whole_with_opened_event(events):
    pin, text = direct_pin()
    client = FakeClient(contents={
        str(FILE_ID): content(FILE_ID, slug="pricing", title="Pricing",
                              description="Plan prices.", text=text),
    })
    section, omitted = await knowledge_loading.load_source_knowledge(
        request=make_request(pin), session=SimpleNamespace(),
        selection_text="pricing", client=client,
    )
    assert omitted == []
    assert section["files"][0]["text"] == text
    assert section["files"][0]["via"] == "direct"
    assert section["budget"]["used_tokens"] == section["files"][0]["token_count"]
    opened = [e for e in events if e["event_type"] == "knowledge.file.opened"]
    assert len(opened) == 1
    assert opened[0]["payload"] == {
        "file_id": str(FILE_ID), "slug": "pricing", "via": "direct",
    }


@pytest.mark.asyncio
async def test_collection_shortlist_follows_the_brief(events):
    pin, client, pricing_text, _ = collection_setup()
    section, omitted = await knowledge_loading.load_source_knowledge(
        request=make_request(pin), session=SimpleNamespace(),
        selection_text="Check the pricing plans and the annual discount.",
        client=client,
    )
    assert omitted == []
    assert [f["slug"] for f in section["files"]] == ["pricing"]
    assert section["files"][0]["via"] == "selection"
    # The whole manifest is carried for mid-run opens.
    carried = section["collections"][0]["manifest"]
    assert {entry["slug"] for entry in carried} == {"pricing", "refunds"}

    section2, _ = await knowledge_loading.load_source_knowledge(
        request=make_request(
            pin, brief="How long do refunds take to arrive?"
        ),
        session=SimpleNamespace(),
        selection_text="How long do refunds take to arrive?",
        client=client,
    )
    assert [f["slug"] for f in section2["files"]] == ["refunds"]


@pytest.mark.asyncio
async def test_over_budget_file_is_omitted_by_name(events, monkeypatch):
    monkeypatch.setenv("MARKETTWIN_SOURCE_KNOWLEDGE_TOKEN_BUDGET", "100")
    pin, text = direct_pin()
    big_text = "# Refunds\n\n" + ("Refund policy detail. " * 40)
    pin["files"].append({
        "file_id": str(REFUNDS_ID), "entry_id": str(ENTRY_ID),
        "slug": "refunds", "title": "Refunds",
        "object_key": "knowledge/x/refunds.md", "sha256": sha(big_text),
    })
    client = FakeClient(contents={
        str(FILE_ID): content(FILE_ID, slug="pricing", title="Pricing",
                              description="Plan prices.", text=text,
                              token_count=60),
        str(REFUNDS_ID): content(REFUNDS_ID, slug="refunds", title="Refunds",
                                 description="Refund windows.", text=big_text,
                                 token_count=60),
    })
    section, omitted = await knowledge_loading.load_source_knowledge(
        request=make_request(pin), session=SimpleNamespace(),
        selection_text="pricing refunds", client=client,
    )
    assert [f["slug"] for f in section["files"]] == ["pricing"]
    assert omitted == [{"slug": "refunds", "reason": "budget", "token_count": 60}]
    assert section["budget"] == {"limit": 100, "used_tokens": 60}


@pytest.mark.asyncio
async def test_unavailable_and_integrity_failures_are_named(events):
    pin, text = direct_pin()
    # Bytes that no longer hash to the pin's sha256.
    bad = content(FILE_ID, slug="pricing", title="Pricing",
                  description="Plan prices.", text=text + " Tampered.")
    client = FakeClient(contents={str(FILE_ID): bad})
    section, omitted = await knowledge_loading.load_source_knowledge(
        request=make_request(pin), session=SimpleNamespace(),
        selection_text="pricing", client=client,
    )
    assert section["files"] == []
    assert omitted == [{
        "slug": "pricing", "reason": "integrity",
        "token_count": bad["token_count"],
    }]
    assert events == []

    section, omitted = await knowledge_loading.load_source_knowledge(
        request=make_request(pin), session=SimpleNamespace(),
        selection_text="pricing", client=FakeClient(),
    )
    assert omitted == [{"slug": "pricing", "reason": "unavailable"}]


# --- prepare_app_plan integration -----------------------------------------


@pytest.mark.asyncio
async def test_prepare_app_plan_loads_pins_and_fences_the_brief(events, monkeypatch):
    pin, text = direct_pin()
    client = FakeClient(contents={
        str(FILE_ID): content(FILE_ID, slug="pricing", title="Pricing",
                              description="Plan prices.", text=text),
    })
    monkeypatch.setattr(
        knowledge_loading, "KnowledgeFilesClient", lambda: client,
    )
    plan_events = []

    class FakePlanRepo:
        def __init__(self, session):
            pass

        async def create(self, **kwargs):
            plan_events.append(kwargs)

    monkeypatch.setattr(app_plan, "RunEventRepository", FakePlanRepo)
    run = SimpleNamespace(configuration_snapshot={})
    session = SimpleNamespace(
        get=AsyncMock(return_value=run), commit=AsyncMock(),
    )
    request = run_executor.MarketTwinRunRequest(
        run_id=uuid4(), study_brief="Check the pricing plans.",
        target_snapshot={}, start_url="https://app.test/",
        allowed_origins=(AllowedOrigin("https", "app.test", None),),
        run_kind="explore_test", unified_native=True,
        source_knowledge=pin,
    )
    prepared = await app_plan.prepare_app_plan(request, session)
    section = prepared.app_plan["source_knowledge"]
    assert section["files"][0]["text"] == text
    assert prepared.app_plan["source_knowledge_omitted"] == []
    assert "Source knowledge (reference data; verify in browser):" in (
        prepared.study_brief
    )
    assert text in prepared.study_brief
    created = [e for e in plan_events if e["event_type"] == "app.plan.created"]
    assert len(created) == 1
    assert created[0]["payload"]["source_knowledge"]["files"][0]["slug"] == "pricing"
    assert run.configuration_snapshot["app_plan"] is prepared.app_plan


# --- ask door --------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_knowledge_files_deterministic_is_shortlist_order(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("the deterministic backend must not call a model")

    monkeypatch.setattr(ask, "_model_json", forbidden)
    monkeypatch.setattr(ask, "decide", forbidden)
    candidates = [
        {"file_id": "f1", "title": "Pricing", "description": "Prices."},
        {"file_id": "f2", "title": "Refunds", "description": "Refund windows."},
        {"file_id": "f3", "title": "Setup", "description": "Account setup."},
    ]
    assert await ask.select_knowledge_files(
        candidates=candidates, brief="Check pricing.",
    ) == ["f1", "f2", "f3"]


# --- lead_review open requests ----------------------------------------------


@pytest.mark.asyncio
async def test_lead_review_returns_validated_open_requests(monkeypatch):
    async def model_json(system, user, *, max_tokens=512):
        return {
            "decision": "continue", "reason": "Need the refunds file.",
            "open_knowledge_files": [str(REFUNDS_ID), "bogus-id", str(REFUNDS_ID)],
        }

    monkeypatch.setattr(lead_review.ask, "_model_json", model_json)
    candidates = [
        {"file_id": str(PRICING_ID), "title": "Pricing", "description": "Prices."},
        {"file_id": str(REFUNDS_ID), "title": "Refunds", "description": "Windows."},
    ]
    review = await lead_review.review_checkpoint(
        objective="Check refunds.", evidence={},
        knowledge_candidates=candidates,
    )
    assert review["decision"] == "continue"
    assert review["knowledge_open_requests"] == [str(REFUNDS_ID)]

    review = await lead_review.review_checkpoint(
        objective="Check refunds.", evidence={},
    )
    assert "knowledge_open_requests" not in review


# --- mid-run open tool --------------------------------------------------------


def plan_with_collection():
    pin, client, pricing_text, refunds_text = collection_setup()
    section = {
        "files": [],
        "collections": [{
            "entry_id": str(ENTRY_ID),
            "manifest_object_key": "knowledge/x/files/v1/manifest.json",
            "version": 1,
            "manifest": client.manifests[(str(ENTRY_ID), 1)]["files"],
        }],
        "budget": {"limit": 24000, "used_tokens": 0},
    }
    return {"source_knowledge": section}, client, pricing_text, refunds_text


@pytest.mark.asyncio
async def test_open_knowledge_file_appends_events_and_persists(events):
    plan, client, _, refunds_text = plan_with_collection()
    run = SimpleNamespace(configuration_snapshot={"app_plan": plan})
    session = SimpleNamespace(
        get=AsyncMock(return_value=run), flush=AsyncMock(),
    )
    result = await knowledge_loading.open_knowledge_file(
        session=session, run_id=uuid4(), plan=plan,
        file_id=str(REFUNDS_ID), client=client,
    )
    assert result["status"] == "opened"
    loaded = plan["source_knowledge"]["files"]
    assert [f["slug"] for f in loaded] == ["refunds"]
    assert loaded[0]["text"] == refunds_text
    assert loaded[0]["via"] == "midrun"
    assert plan["source_knowledge"]["budget"]["used_tokens"] == (
        loaded[0]["token_count"]
    )
    opened = [e for e in events if e["event_type"] == "knowledge.file.opened"]
    assert len(opened) == 1
    assert opened[0]["payload"]["via"] == "midrun"
    assert run.configuration_snapshot["app_plan"] is plan

    again = await knowledge_loading.open_knowledge_file(
        session=session, run_id=uuid4(), plan=plan,
        file_id=str(REFUNDS_ID), client=client,
    )
    assert again["status"] == "already_loaded"


@pytest.mark.asyncio
async def test_open_knowledge_file_refuses_outside_the_set(events):
    plan, client, _, _ = plan_with_collection()
    session = SimpleNamespace(get=AsyncMock(return_value=None), flush=AsyncMock())
    result = await knowledge_loading.open_knowledge_file(
        session=session, run_id=uuid4(), plan=plan,
        file_id=str(uuid4()), client=client,
    )
    assert result == {
        "status": "refused", "file_id": result["file_id"],
        "reason": "not_in_attached_collections",
    }
    assert events == []


@pytest.mark.asyncio
async def test_open_knowledge_file_refuses_over_budget(events):
    plan, client, _, _ = plan_with_collection()
    plan["source_knowledge"]["budget"] = {"limit": 10, "used_tokens": 0}
    session = SimpleNamespace(get=AsyncMock(return_value=None), flush=AsyncMock())
    result = await knowledge_loading.open_knowledge_file(
        session=session, run_id=uuid4(), plan=plan,
        file_id=str(REFUNDS_ID), client=client,
    )
    assert result["status"] == "refused"
    assert result["reason"] == "budget"
    assert client.content_calls == []  # refused before any fetch
    assert events == []

# --- SKR step 1: mid-run open refusals + resumed plans -------------------


@pytest.mark.asyncio
async def test_open_knowledge_file_refuses_on_integrity_mismatch(events):
    plan, client, _, _ = plan_with_collection()
    # The manifest pins the sha of the original refunds text; the
    # served bytes no longer match it, so the open must refuse and
    # leave the plan untouched.
    entry = plan["source_knowledge"]["collections"][0]["manifest"][1]
    assert entry["slug"] == "refunds"
    entry["sha256"] = sha("some other text entirely")
    session = SimpleNamespace(get=AsyncMock(return_value=None), flush=AsyncMock())
    result = await knowledge_loading.open_knowledge_file(
        session=session, run_id=uuid4(), plan=plan,
        file_id=str(REFUNDS_ID), client=client,
    )
    assert result["status"] == "refused"
    assert result["reason"] == "integrity"
    assert plan["source_knowledge"]["files"] == []
    assert plan["source_knowledge"]["budget"]["used_tokens"] == 0
    assert events == []


@pytest.mark.asyncio
async def test_open_knowledge_file_already_loaded_after_plan_reload(events):
    # A resumed run reloads the plan from the snapshot: the file is
    # already in the loaded set and its tokens are already charged,
    # so a repeated open is a no-op (no refetch, no double charge).
    plan, client, _, refunds_text = plan_with_collection()
    tokens = -(-len(refunds_text) // 4)
    plan["source_knowledge"]["files"] = [{
        "file_id": str(REFUNDS_ID), "entry_id": str(ENTRY_ID),
        "slug": "refunds", "title": "Refunds",
        "description": "Refund windows and exceptions.",
        "text": refunds_text, "token_count": tokens, "via": "midrun",
    }]
    plan["source_knowledge"]["budget"] = {"limit": 24000, "used_tokens": tokens}
    session = SimpleNamespace(get=AsyncMock(return_value=None), flush=AsyncMock())
    result = await knowledge_loading.open_knowledge_file(
        session=session, run_id=uuid4(), plan=plan,
        file_id=str(REFUNDS_ID), client=client,
    )
    assert result == {"status": "already_loaded", "file_id": str(REFUNDS_ID)}
    assert plan["source_knowledge"]["budget"]["used_tokens"] == tokens
    assert client.content_calls == []
    assert events == []


@pytest.mark.asyncio
async def test_open_knowledge_file_refuses_without_source_knowledge(events):
    session = SimpleNamespace(get=AsyncMock(return_value=None), flush=AsyncMock())
    result = await knowledge_loading.open_knowledge_file(
        session=session, run_id=uuid4(), plan={},
        file_id=str(REFUNDS_ID), client=FakeClient(),
    )
    assert result["status"] == "refused"
    assert result["reason"] == "no_source_knowledge"
    assert events == []


# --- SKR step 2: BM25 + char-gram selection, door escalation, packing ------


class FakeDoor:
    """Stands in for ask.select_knowledge_files; records its calls."""

    def __init__(self, order=None, error=None):
        self.order = order
        self.error = error
        self.calls: list[list[str]] = []

    async def __call__(self, *, candidates, brief):
        self.calls.append([c["file_id"] for c in candidates])
        if self.error is not None:
            raise self.error
        return list(self.order or [])


@pytest.mark.asyncio
async def test_multilingual_brief_uses_char_gram_fallback(events, monkeypatch):
    # A German brief shares no whole token with the English surfaces,
    # so BM25 is empty; character n-grams still catch "Jahresplan"
    # against "plan / prices", and the door is never consulted.
    pin, client, _, _ = collection_setup()
    door = FakeDoor(order=[])
    monkeypatch.setattr(ask, "select_knowledge_files", door)
    section, omitted = await knowledge_loading.load_source_knowledge(
        request=make_request(pin, brief="Wie viel kostet der Jahresplan?"),
        session=SimpleNamespace(),
        selection_text="Wie viel kostet der Jahresplan?",
        client=client,
    )
    assert door.calls == []
    assert [f["slug"] for f in section["files"]] == ["pricing"]
    assert omitted == []


@pytest.mark.asyncio
async def test_cross_lingual_brief_escalates_to_the_door(events, monkeypatch):
    # A Chinese brief shares neither tokens nor character n-grams
    # with the English surfaces: both scorers are empty, so selection
    # escalates to the ask door over the full manifest, and the
    # door's order is recorded on the carried collection.
    pin, client, _, _ = collection_setup()
    door = FakeDoor(order=[str(PRICING_ID), str(REFUNDS_ID)])
    monkeypatch.setattr(ask, "select_knowledge_files", door)
    section, omitted = await knowledge_loading.load_source_knowledge(
        request=make_request(pin, brief="我想知道每年的价格是多少"),
        session=SimpleNamespace(),
        selection_text="我想知道每年的价格是多少",
        client=client,
    )
    assert door.calls == [[str(PRICING_ID), str(REFUNDS_ID)]]
    assert [f["slug"] for f in section["files"]] == ["pricing", "refunds"]
    assert section["collections"][0]["selection_order"] == [
        str(PRICING_ID), str(REFUNDS_ID),
    ]
    assert omitted == []


@pytest.mark.asyncio
async def test_paraphrased_brief_escalates_to_the_door(events, monkeypatch):
    # A paraphrase with no shared keywords (and only stray n-gram
    # noise) leaves both scorers empty; the door orders the files.
    pin, client, _, _ = collection_setup()
    door = FakeDoor(order=[str(REFUNDS_ID), str(PRICING_ID)])
    monkeypatch.setattr(ask, "select_knowledge_files", door)
    brief = "When does the money come back to my card?"
    section, omitted = await knowledge_loading.load_source_knowledge(
        request=make_request(pin, brief=brief),
        session=SimpleNamespace(), selection_text=brief, client=client,
    )
    assert len(door.calls) == 1
    assert [f["slug"] for f in section["files"]] == ["refunds", "pricing"]
    assert section["collections"][0]["selection_order"] == [
        str(REFUNDS_ID), str(PRICING_ID),
    ]
    assert omitted == []


@pytest.mark.asyncio
async def test_door_failure_names_selection_unavailable(events, monkeypatch):
    pin, client, pricing_text, refunds_text = collection_setup()
    brief = "When does the money come back to my card?"
    expected = [
        {"slug": "pricing", "reason": "selection_unavailable",
         "token_count": -(-len(pricing_text) // 4)},
        {"slug": "refunds", "reason": "selection_unavailable",
         "token_count": -(-len(refunds_text) // 4)},
    ]
    for door in (
        FakeDoor(error=RuntimeError("door down")),
        FakeDoor(order=[]),
    ):
        monkeypatch.setattr(ask, "select_knowledge_files", door)
        section, omitted = await knowledge_loading.load_source_knowledge(
            request=make_request(pin, brief=brief),
            session=SimpleNamespace(), selection_text=brief, client=client,
        )
        assert section["files"] == []
        assert omitted == expected
    assert events == []


@pytest.mark.asyncio
async def test_recorded_selection_order_is_replayed_on_resume(events, monkeypatch):
    # A resumed run's pin already carries the door's recorded order:
    # it is replayed verbatim — the scorers and the door stay out of
    # it, even though the brief alone would shortlist differently.
    pin, client, _, _ = collection_setup()
    pin["collections"][0]["selection_order"] = [str(REFUNDS_ID), str(PRICING_ID)]
    door = FakeDoor(error=AssertionError("the door must not be called"))
    monkeypatch.setattr(ask, "select_knowledge_files", door)
    section, omitted = await knowledge_loading.load_source_knowledge(
        request=make_request(pin), session=SimpleNamespace(),
        selection_text="Check the pricing plans and the annual discount.",
        client=client,
    )
    assert door.calls == []
    assert [f["slug"] for f in section["files"]] == ["refunds", "pricing"]
    assert section["collections"][0]["selection_order"] == [
        str(REFUNDS_ID), str(PRICING_ID),
    ]
    assert omitted == []


@pytest.mark.asyncio
async def test_oversized_document_packs_relevant_sections_atomically(
    events, monkeypatch,
):
    # Budget 1200 -> per-file cap 400. The prices section (~320
    # tokens) packs; the discount section (~290 tokens) is relevant
    # but would breach the cap, so it is skipped WHOLE and named as
    # a budget omission; the locations section scores zero and is
    # simply not selected.
    monkeypatch.setenv("MARKETTWIN_SOURCE_KNOWLEDGE_TOKEN_BUDGET", "1200")
    guide_id = uuid4()
    prices_body = (
        "Pricing plans: the annual plan price and the monthly plan price. "
        * 19
    )
    prices_section = "## Plan prices\n\n" + prices_body
    discount_body = "Discount price rules for yearly subscriptions. " * 24
    discount_section = "## Discount schedule\n\n" + discount_body
    locations_body = "Our offices sit in Chicago and Austin towns. " * 26
    locations_section = "## Office locations\n\n" + locations_body
    guide_text = (
        "---\ntitle: Guide\nowner: docs-team\n---\n# Guide\n\n"
        + prices_section + "\n" + discount_section + "\n" + locations_section
    )
    entry = manifest_entry(
        guide_id, slug="guide", title="Guide",
        description="Product guide.", text=guide_text,
    )
    entry["section_headings"] = [
        "Plan prices", "Discount schedule", "Office locations",
    ]
    manifest = {"entry_id": str(ENTRY_ID), "version": 1, "files": [entry]}
    client = FakeClient(
        contents={str(guide_id): content(
            guide_id, slug="guide", title="Guide",
            description="Product guide.", text=guide_text,
        )},
        manifests={(str(ENTRY_ID), 1): manifest},
    )
    pin = {"files": [], "collections": [{
        "entry_id": str(ENTRY_ID),
        "manifest_object_key": "knowledge/x/files/v1/manifest.json",
        "version": 1,
    }]}
    section, omitted = await knowledge_loading.load_source_knowledge(
        request=make_request(pin), session=SimpleNamespace(),
        selection_text="Check the pricing plans and the annual discount.",
        client=client,
    )
    assert [f["slug"] for f in section["files"]] == ["guide"]
    packed = section["files"][0]["text"]
    assert "Guide › Plan prices" in packed
    assert "annual plan price" in packed
    assert "Discount price rules" not in packed
    assert "offices sit in Chicago" not in packed
    assert "docs-team" not in packed  # frontmatter is dropped
    assert section["files"][0]["token_count"] <= 400
    assert section["budget"]["used_tokens"] == section["files"][0]["token_count"]
    assert omitted == [{
        "slug": "guide", "reason": "budget",
        "token_count": knowledge_loading.estimate_tokens(discount_section),
    }]



@pytest.mark.asyncio
async def test_pinned_file_in_own_collection_loads_once(events):
    """D-D1 regression: a file both directly pinned and present in
    its own attached collection loads exactly once — one plan entry,
    one opened event, one budget charge, and no omission entry."""
    text = "# Pricing\n\nThe Team plan costs $40 per month."
    pin = {
        "files": [{
            "file_id": str(FILE_ID), "entry_id": str(ENTRY_ID),
            "slug": "pricing", "title": "Pricing",
            "object_key": "knowledge/x/pricing.md", "sha256": sha(text),
        }],
        "collections": [{
            "entry_id": str(ENTRY_ID),
            "manifest_object_key": "knowledge/x/files/v1/manifest.json",
            "version": 1,
        }],
    }
    manifest = {"entry_id": str(ENTRY_ID), "version": 1, "files": [
        manifest_entry(FILE_ID, slug="pricing", title="Pricing",
                       description="Plan prices and billing cycles.",
                       text=text),
    ]}
    client = FakeClient(
        contents={str(FILE_ID): content(
            FILE_ID, slug="pricing", title="Pricing",
            description="Plan prices and billing cycles.", text=text)},
        manifests={(str(ENTRY_ID), 1): manifest},
    )
    section, omitted = await knowledge_loading.load_source_knowledge(
        request=make_request(pin), session=SimpleNamespace(),
        selection_text="Check the pricing plans and the annual discount.",
        client=client,
    )
    assert [f["file_id"] for f in section["files"]] == [str(FILE_ID)]
    assert section["files"][0]["via"] == "direct"
    assert omitted == []
    assert section["budget"]["used_tokens"] == section["files"][0]["token_count"]
    opened = [
        e for e in events
        if e["event_type"] == "knowledge.file.opened"
        and e["payload"]["file_id"] == str(FILE_ID)
    ]
    assert len(opened) == 1
