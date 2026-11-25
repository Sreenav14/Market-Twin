"""Phase 1b capture and inventory (doc 16 sections 5.2-5.5, tests
T-HV1 to T-HV10, plus one extra consent-ordering test declared in the
build report). The browser controller and the object store are
fakes; the identity, distillation, redaction, and visit logic under
test are the real modules.
"""

import hashlib
import json
import time
from types import SimpleNamespace
from uuid import uuid4

from markettwin_execution_orchestrator.harvest import harvest_inventory
from markettwin_execution_orchestrator.harvest.harvest_capture import (
    StateCapture,
    redact_har,
    store_state_evidence,
)
from markettwin_execution_orchestrator.harvest.harvest_inventory import (
    distil_elements,
    distil_forms,
    identity_for,
    rank_locators,
    visit_page,
)
from markettwin_execution_orchestrator.workflow.harness_state import (
    state_id_for,
)

BASE = "https://example.com/"


def aria_entry(role, name, **extra):
    return {"role": role, "name": name, **extra}


def state_capture(**overrides):
    values = {
        "url": BASE,
        "title": "Home",
        "aria_snapshot": "- link \"Home\"",
        "aria_entries": [aria_entry("link", "Home")],
        "probe": {"url": BASE, "title": "Home"},
        "dom_elements": [],
        "forms": [],
        "dom_structure_hash": "skeleton",
        "aria_hash": "aria",
        "screenshot_path": "",
    }
    values.update(overrides)
    return StateCapture(**values)


# T-HV1: the harvested identity IS the harness identity — same
# function, same output, so run-side lookups can match them.
def test_identity_matches_harness_state_id():
    elements = [
        {"role": "link", "name": "Home"},
        {"role": "button", "name": "Buy"},
    ]
    forms = [{"fields": [{"label": "Email"}]}]
    state_id, element_signature, form_signature = identity_for(
        BASE, elements, forms
    )
    assert state_id == state_id_for(
        BASE,
        elements=[("link", "Home"), ("button", "Buy")],
        form_fields=["Email"],
    )
    assert element_signature == "button|Buy;link|Home"
    assert form_signature == "field|Email"


# T-HV2: locator ranking — data-testid first when present, then
# role+name, label, text, structural; aria-refs never appear.
def test_locator_ranking():
    with_testid = rank_locators(
        {
            "testid": "buy-btn", "label": "Buy now", "text": "Buy today",
            "structural_path": "div:nth-of-type(1)",
        },
        role="button", name="Buy",
    )
    assert [item["kind"] for item in with_testid] == [
        "testid", "role_name", "label", "text", "structural",
    ]
    assert [item["stability"] for item in with_testid] == [1, 2, 3, 4, 5]
    without = rank_locators(None, role="button", name="Buy")
    assert [item["kind"] for item in without] == ["role_name"]
    blob = json.dumps(with_testid)
    assert "aria-ref" not in blob and "ref=" not in blob


# T-HV3: element distillation joins aria entries to DOM evidence and
# keeps the harness actionability/safety vocabulary.
def test_distil_elements_maps_actionability_and_safety():
    capture = state_capture(
        aria_entries=[
            aria_entry("button", "Delete account"),
            aria_entry("link", "Home"),
            aria_entry("textbox", "Email"),
            aria_entry("heading", "Welcome"),
        ],
        dom_elements=[
            {"role": "button", "aria_label": "Delete account",
             "label": "Delete account", "text": "Delete account",
             "testid": "delete", "structural_path": "div:nth-of-type(3)"},
        ],
    )
    elements = distil_elements(capture)
    by_name = {item["name"]: item for item in elements}
    delete = by_name["Delete account"]
    assert delete["actionability"] == "click"
    assert delete["safety_class"] == "irreversible"
    assert delete["locators"][0]["kind"] == "testid"
    assert by_name["Home"]["safety_class"] == "read"
    assert by_name["Email"]["actionability"] == "fill"
    # A heading can never enter the discovery fence.
    assert by_name["Welcome"]["safety_class"] == "irreversible"


# T-HV4: form distillation — labels and constraints come from the DOM
# (validation_source 'dom'), and an irreversible submit marks the
# form unprobed_destructive.
def test_distil_forms_from_dom():
    capture = state_capture(forms=[
        {
            "form_index": 1,
            "method": "post",
            "action": "/subscribe",
            "fields": [
                {"label": "Email", "field_type": "email", "required": True,
                 "constraints": {"pattern": ".+@.+"},
                 "options": [], "error_text": None},
                {"label": "Delete everything", "field_type": "submit",
                 "required": False, "constraints": {}, "options": [],
                 "error_text": None},
            ],
        }
    ])
    forms = distil_forms(capture)
    assert forms[0]["form_key"] == "form-1"
    assert forms[0]["probe_status"] == "unprobed_destructive"
    email = forms[0]["fields"][0]
    assert email["label"] == "Email"
    assert email["validation_source"] == "dom"
    assert email["required"] is True
    assert email["constraints"]["pattern"] == ".+@.+"


def secret_har():
    return {
        "log": {
            "version": "1.2",
            "entries": [
                {
                    "startedDateTime": "2026-11-14T00:00:00Z",
                    "request": {
                        "method": "GET",
                        "url": "https://example.com/x?token=supersecretvalue",
                        "headers": [
                            {"name": "Authorization",
                             "value": "Bearer abcdefghijklmnopqrstuvwxyz"},
                            {"name": "Cookie", "value": "session=abc"},
                            {"name": "Accept", "value": "text/html"},
                        ],
                        "queryString": [
                            {"name": "token", "value": "supersecretvalue"},
                            {"name": "page", "value": "2"},
                        ],
                    },
                    "response": {
                        "status": 200,
                        "headers": [
                            {"name": "Set-Cookie", "value": "id=1"},
                        ],
                        "content": {"size": 10, "mimeType": "text/html"},
                    },
                },
                {
                    "startedDateTime": "2026-11-14T00:00:01Z",
                    "request": {"method": "GET", "url": "https://example.com/img",
                                "headers": [], "queryString": []},
                    "response": {
                        "status": 200, "headers": [],
                        "content": {"size": 4, "mimeType": "image/png",
                                    "text": "\x89PNG"},
                    },
                },
            ],
        }
    }


# T-HV5: redaction kills credentials in headers, URLs, and query
# strings; binary content is dropped and counted; no secret substring
# survives anywhere in the stored JSON.
def test_redact_har_removes_secrets_and_drops_binary():
    redacted, hits = redact_har(secret_har())
    blob = json.dumps(redacted)
    assert "supersecretvalue" not in blob
    assert "abcdefghijklmnopqrstuvwxyz" not in blob
    assert "session=abc" not in blob
    assert "Bearer " not in blob
    entry = redacted["log"]["entries"][0]
    headers = {item["name"]: item["value"] for item in entry["request"]["headers"]}
    assert headers["Authorization"] == "[REDACTED]"
    assert headers["Cookie"] == "[REDACTED]"
    assert headers["Accept"] == "text/html"
    query = {item["name"]: item["value"] for item in entry["request"]["queryString"]}
    assert query["token"] == "[REDACTED]"
    assert query["page"] == "2"
    binary = redacted["log"]["entries"][1]["response"]["content"]
    assert binary["text"] == "[BINARY DROPPED]"
    assert hits >= 5


class FakeStore:
    def __init__(self):
        self.objects = {}

    async def put(self, *, object_key, data, content_type):
        self.objects[object_key] = data
        return SimpleNamespace(
            sha256=hashlib.sha256(data).hexdigest(), byte_size=len(data)
        )


class FakeEvidenceRepository:
    def __init__(self):
        self.rows = []

    async def record_evidence(self, app_map, page, state, **kwargs):
        self.rows.append({"state_id": state.id if state else None, **kwargs})
        return SimpleNamespace(id=uuid4())


# T-HV6: when redaction itself fails, the HAR row is recorded as
# dropped with no object stored, the failure is counted, and the
# other evidence objects still land.
async def test_redaction_failure_drops_har_and_counts_it(monkeypatch):
    def exploding_redact(har):
        raise RuntimeError("redactor broke")

    monkeypatch.setattr(
        "markettwin_execution_orchestrator.harvest.harvest_capture.redact_har",
        exploding_redact,
    )
    repository = FakeEvidenceRepository()
    store = FakeStore()
    entry = {
        "startedDateTime": "2026-11-14T00:00:00Z",
        "time": 5,
        "request": {
            "method": "GET", "url": "https://example.com/x",
            "headers": [], "queryString": [],
        },
        "response": {
            "status": 200, "statusText": "OK", "headers": [],
            "content": {"size": 10, "mimeType": "text/html"},
        },
        "cache": {},
        "timings": {"wait": 5},
    }
    counts = await store_state_evidence(
        store=store,
        repository=repository,
        app_map=SimpleNamespace(id=uuid4()),
        page=SimpleNamespace(id=uuid4(), canonical_url=BASE),
        state=SimpleNamespace(id=uuid4(), state_key="default"),
        capture=state_capture(),
        har_entries=[entry],
        viewport="desktop1280",
    )
    assert counts["har_dropped"] == 1
    by_kind = {row["kind"]: row for row in repository.rows}
    assert by_kind["harvest_har"]["redaction_status"] == "dropped"
    assert by_kind["harvest_har"]["object_key"] == ""
    assert by_kind["aria_snapshot"]["redaction_status"] == "not_applicable"
    assert any(
        key.endswith("aria_snapshot-default.json") for key in store.objects
    )


class FakeVisitRepository:
    def __init__(self):
        self.pages = {}
        self.states = {}
        self.elements = {}
        self.forms = []
        self.transitions = []
        self.evidence = []

    def add_page(self, page):
        self.pages[page.id] = page
        state = SimpleNamespace(
            id=uuid4(), map_page_id=page.id, state_key="default",
            state_kind="default", state_id=None, element_signature=None,
            form_signature=None, dom_structure_hash=None, aria_hash=None,
        )
        self.states[state.id] = state
        return state

    async def get_default_state(self, page_id):
        return next(
            state for state in self.states.values()
            if state.map_page_id == page_id and state.state_key == "default"
        )

    async def list_states(self, page_id):
        return [
            state for state in self.states.values()
            if state.map_page_id == page_id
        ]

    async def complete_default_state(self, state_id, **fields):
        state = self.states[state_id]
        state.state_id = fields.get("state_id_value")
        state.element_signature = fields.get("element_signature")
        state.form_signature = fields.get("form_signature")
        state.dom_structure_hash = fields.get("dom_structure_hash")
        state.aria_hash = fields.get("aria_hash")
        return state

    async def create_observed_state(self, app_map, page, **fields):
        state = SimpleNamespace(
            id=uuid4(), map_page_id=page.id,
            state_key=fields["state_key"], state_kind=fields["state_kind"],
            state_id=fields.get("state_id_value"),
            element_signature=fields.get("element_signature"),
            form_signature=fields.get("form_signature"),
        )
        self.states[state.id] = state
        return state

    async def insert_elements(self, app_map, page, state, elements):
        rows = []
        for item in elements:
            row_data = {
                "id": uuid4(), "map_page_state_id": state.id,
                "opens_state_key": None, "navigates_to_url": None,
            }
            row_data.update(item)
            row = SimpleNamespace(**row_data)
            self.elements[row.id] = row
            rows.append(row)
        return rows

    async def insert_forms(self, app_map, page, state, forms):
        rows = []
        for form in forms:
            row = SimpleNamespace(
                id=uuid4(), map_page_state_id=state.id, **form
            )
            self.forms.append(row)
            rows.append(row)
        return rows

    async def set_element_opens_state(self, element_id, state_key):
        self.elements[element_id].opens_state_key = state_key

    async def set_element_navigates(self, element_id, url):
        self.elements[element_id].navigates_to_url = url

    async def upsert_transition(self, app_map, **kwargs):
        self.transitions.append(kwargs)
        return SimpleNamespace(id=uuid4())

    async def record_evidence(self, app_map, page, state, **kwargs):
        self.evidence.append(kwargs)
        return SimpleNamespace(id=uuid4())

    async def find_page_by_url(self, map_id, canonical):
        for page in self.pages.values():
            if page.canonical_url == canonical:
                return page
        return None


class FakePage:
    def __init__(self, controller):
        self._controller = controller

    @property
    def url(self):
        return self._controller.current_capture().url

    async def inner_text(self, selector):
        return self._controller.body_text


class FakeController:
    """Serves a scripted sequence of captures; a click on a target
    with a scripted effect switches what the next capture returns."""

    def __init__(self, captures, *, effects=None, targets=None, body_text=""):
        self._captures = list(captures)
        self._effects = effects or {}
        self._targets = targets or []
        self.body_text = body_text
        self.clicks = []
        self.events = []
        self.current = 0
        self.handle = SimpleNamespace(session_id=uuid4())
        self.page = FakePage(self)

    def current_capture(self):
        return self._captures[self.current]

    async def navigate(self, *, session_id, url, **kwargs):
        return SimpleNamespace(
            observation=SimpleNamespace(url=self.current_capture().url)
        )

    async def click(self, *, session_id, role=None, name=None, **kwargs):
        self.clicks.append(name)
        self.events.append(("click", name))
        if name in self._effects:
            self.current = self._effects[name]
        return SimpleNamespace()

    async def wait(self, **kwargs):
        return SimpleNamespace()

    async def ui_state_targets(self, session_id=None):
        return list(self._targets)

    def _get_session(self, session_id=None):
        return SimpleNamespace(page=self.page)

    async def capture(self):
        self.events.append(("capture", self.current))
        return self.current_capture()


def make_page(repository, url=BASE):
    page = SimpleNamespace(
        id=uuid4(), canonical_url=url, crawl_status="ok",
        redirect_target=None, requires_auth=False,
        harvest_status=None, template_group=None,
    )
    repository.add_page(page)
    return page


async def run_visit(repository, controller, page):
    return await visit_page(
        controller=controller,
        handle=controller.handle,
        repository=repository,
        store=FakeStore(),
        app_map=SimpleNamespace(id=uuid4()),
        page=page,
        execution_id=uuid4(),
        journey_id=uuid4(),
        network=SimpleNamespace(entries=[]),
        deadline=time.monotonic() + 120,
    )


def patch_capture(monkeypatch):
    async def fake_capture(controller_, handle, **kwargs):
        return await controller_.capture()

    monkeypatch.setattr(harvest_inventory, "capture_state", fake_capture)


def landing_capture():
    return state_capture(
        aria_entries=[
            aria_entry("button", "Open menu"),
            aria_entry("link", "Home"),
        ],
    )


def menu_capture():
    return state_capture(
        aria_snapshot="- button \"Close menu\"\n- link \"Home\"\n- link \"Pricing\"",
        aria_entries=[
            aria_entry("button", "Close menu"),
            aria_entry("link", "Home"),
            aria_entry("link", "Pricing"),
        ],
    )


# T-HV7: the landing capture completes the page's default state IN
# PLACE — no second default row is ever created.
async def test_visit_completes_default_state_in_place(monkeypatch):
    repository = FakeVisitRepository()
    page = make_page(repository)
    controller = FakeController([landing_capture()])
    patch_capture(monkeypatch)
    result = await run_visit(repository, controller, page)
    assert result.disposition == "visited"
    defaults = [
        state for state in repository.states.values()
        if state.state_key == "default"
    ]
    assert len(defaults) == 1
    assert defaults[0].state_id is not None


# T-HV8: a login landing marks the page blocked_auth and a bot wall
# marks it blocked_wall; neither is captured further.
async def test_visit_login_landing_is_blocked_auth(monkeypatch):
    repository = FakeVisitRepository()
    page = make_page(repository, url=BASE + "login")
    controller = FakeController([state_capture(url=BASE + "login")])
    patch_capture(monkeypatch)
    result = await run_visit(repository, controller, page)
    assert result.disposition == "blocked_auth"
    assert result.reason == "login_landing"


async def test_visit_wall_is_blocked_wall(monkeypatch):
    repository = FakeVisitRepository()
    page = make_page(repository)
    controller = FakeController(
        [landing_capture()],
        body_text="Please verify you are human to continue",
    )
    patch_capture(monkeypatch)
    result = await run_visit(repository, controller, page)
    assert result.disposition == "blocked_wall"


# T-HV9: clicking a read-class candidate that reveals a new view
# creates an observed state, wires opens_state_key, and records the
# transition; an irreversible candidate is NEVER clicked.
async def test_visit_discovers_state_and_never_clicks_irreversible(monkeypatch):
    repository = FakeVisitRepository()
    page = make_page(repository)
    landing = state_capture(
        aria_entries=[
            aria_entry("button", "Open menu"),
            aria_entry("button", "Delete account"),
            aria_entry("link", "Home"),
        ],
    )
    controller = FakeController(
        [landing, menu_capture()], effects={"Open menu": 1}
    )
    patch_capture(monkeypatch)
    result = await run_visit(repository, controller, page)
    assert result.disposition == "visited"
    assert "Delete account" not in controller.clicks
    assert "Open menu" in controller.clicks
    observed = [
        state for state in repository.states.values()
        if state.state_key.startswith("observed-")
    ]
    assert len(observed) == 1
    default_state = await repository.get_default_state(page.id)
    openers = [
        element for element in repository.elements.values()
        if element.name == "Open menu"
        and element.map_page_state_id == default_state.id
    ]
    assert openers[0].opens_state_key == observed[0].state_key
    assert any(
        transition["to_state_id"] == observed[0].id
        and transition["via_action"] == "click"
        for transition in repository.transitions
    )


# T-HV10: a navigation click during discovery wires the element's
# navigates_to_url and the transition to the target page's default
# state.
async def test_visit_navigation_click_wires_transition(monkeypatch):
    repository = FakeVisitRepository()
    page = make_page(repository)
    pricing = make_page(repository, url=BASE + "pricing")
    landing = state_capture(
        aria_entries=[
            aria_entry("link", "Pricing"),
            aria_entry("link", "Home"),
        ],
    )
    pricing_capture = state_capture(
        url=BASE + "pricing",
        aria_entries=[aria_entry("link", "Home")],
    )
    controller = FakeController(
        [landing, pricing_capture], effects={"Pricing": 1}
    )
    patch_capture(monkeypatch)
    result = await run_visit(repository, controller, page)
    assert result.disposition == "visited"
    pricing_links = [
        element for element in repository.elements.values()
        if element.name == "Pricing"
    ]
    assert pricing_links[0].navigates_to_url == BASE + "pricing"
    pricing_default = await repository.get_default_state(pricing.id)
    assert any(
        transition["to_state_id"] == pricing_default.id
        for transition in repository.transitions
    )


# EXTRA (declared): consent-as-chrome — the dismissal is clicked
# BEFORE the first state capture, so the overlay never pollutes the
# harvested inventory.
async def test_visit_dismisses_consent_before_first_capture(monkeypatch):
    repository = FakeVisitRepository()
    page = make_page(repository)
    controller = FakeController(
        [landing_capture()],
        targets=[{"role": "button", "name": "Accept all cookies"}],
    )
    patch_capture(monkeypatch)
    result = await run_visit(repository, controller, page)
    assert result.disposition == "visited"
    click_index = controller.events.index(("click", "Accept all cookies"))
    capture_index = next(
        index for index, event in enumerate(controller.events)
        if event[0] == "capture"
    )
    assert click_index < capture_index
