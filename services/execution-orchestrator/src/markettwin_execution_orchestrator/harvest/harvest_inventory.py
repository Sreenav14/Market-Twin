"""Distil one visited page into graph rows (doc 16 sections 5.4-5.5).

The pure distillation lives apart from the browser walk: aria entries
plus the DOM extraction become element and form dicts whose identity
is computed by the harness's OWN state function, so a harvested state
and a live run's state agree on identity byte for byte. The walk
itself (``visit_page``) drives one page through the controller:
navigate, disposition, consent-as-chrome, landing capture, then a
bounded discovery of the states its safe controls open.
"""

import asyncio
import hashlib
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit
from uuid import UUID

from markettwin_shared.app_map_common import (
    canonical_url,
    has_wall_markers,
    is_login_path,
)

from markettwin_execution_orchestrator.harvest.harvest_capture import (
    NetworkCapture,
    StateCapture,
    capture_state,
    store_state_evidence,
)
from markettwin_execution_orchestrator.slop.interactions import (
    _consent_cluster,
    _consent_dismissal,
)
from markettwin_execution_orchestrator.workflow.harness_items import classify_action
from markettwin_execution_orchestrator.workflow.harness_state import HarnessState

HARVEST_PAGE_STATE_CAP = 8  # [J] doc 16 section 13
HARVEST_STATE_ACTION_CAP = 40  # [J] doc 16 section 13
HARVEST_VIEWPORT = "desktop1280"

_ACTIONABILITY_BY_ROLE = {
    "checkbox": "toggle",
    "switch": "toggle",
    "radio": "check",
    "slider": "press",
    "textbox": "fill",
    "searchbox": "fill",
    "spinbutton": "fill",
    "combobox": "select",
    "listbox": "select",
}
_FENCE_ACTIONABILITY = ("click", "press", "toggle")
_FENCE_SAFETY = ("read", "reversible")


def actionability_for(role: str) -> str:
    return _ACTIONABILITY_BY_ROLE.get(role, "click" if role else "readonly")


def rank_locators(
    dom_element: dict[str, Any] | None, *, role: str, name: str
) -> list[dict[str, object]]:
    """The ranked locator list of section 5.5: testid, role+name,
    label, text, structural — each with its rank as its stability.
    Aria snapshot refs are NEVER stored (they are per-snapshot)."""
    locators: list[dict[str, object]] = []

    def add(kind: str, value: str) -> None:
        if value:
            locators.append(
                {"kind": kind, "value": value, "stability": len(locators) + 1}
            )

    if dom_element is not None:
        add("testid", str(dom_element.get("testid") or ""))
    add("role_name", f"{role}|{name}")
    if dom_element is not None:
        add("label", str(dom_element.get("label") or ""))
        add("text", str(dom_element.get("text") or ""))
        add("structural", str(dom_element.get("structural_path") or ""))
    return locators


def _dom_name_candidates(dom_element: dict[str, Any]) -> set[str]:
    return {
        str(dom_element.get("aria_label") or ""),
        str(dom_element.get("label") or ""),
        str(dom_element.get("text") or ""),
    } - {""}


def distil_elements(capture: StateCapture) -> list[dict[str, object]]:
    """Element dicts for one captured state, in aria order.

    The aria entries are the element universe (the same list the
    harness's live page index produces); each is enriched with the
    best-matching DOM node's locator material, matched by role and
    accessible name, each DOM node used at most once.
    """
    dom_pool = list(capture.dom_elements)
    used: set[int] = set()
    elements: list[dict[str, object]] = []
    for ordinal, entry in enumerate(capture.aria_entries):
        role = str(entry.get("role") or "")
        name = str(entry.get("name") or "")
        match: dict[str, Any] | None = None
        for index, candidate in enumerate(dom_pool):
            if index in used:
                continue
            if str(candidate.get("role") or "") != role:
                continue
            if name and name not in _dom_name_candidates(candidate):
                continue
            match = candidate
            used.add(index)
            break
        href = str(match.get("href") or "") if match is not None else ""
        elements.append(
            {
                "role": role,
                "name": name,
                "ordinal": ordinal,
                "label_text": (str(match.get("label") or "") or None)
                if match is not None
                else None,
                "actionability": actionability_for(role),
                "locators": rank_locators(match, role=role, name=name),
                "safety_class": classify_action(role=role, name=name),
                "navigates_to_url": urljoin(capture.url, href) if href else None,
            }
        )
    return elements


def _field_label(field: dict[str, Any]) -> str:
    return (
        str(field.get("label") or "")
        or str(field.get("name_attr") or "")
        or str(field.get("field_type") or "")
    )


def distil_forms(capture: StateCapture) -> list[dict[str, object]]:
    """Form dicts for one captured state (doc 16 section 5.5). Forms
    are recorded, never probed, in Phase 1b: probe_status separates a
    form whose submit control classifies read/reversible from one
    whose submit is destructive."""
    forms: list[dict[str, object]] = []
    for form in capture.forms:
        fields: list[dict[str, object]] = []
        for field in form.get("fields") or []:
            constraints = {
                key: value
                for key, value in dict(field.get("constraints") or {}).items()
                if value
            }
            fields.append(
                {
                    "label": _field_label(field),
                    "field_type": str(field.get("field_type") or "text"),
                    "name_attr": str(field.get("name_attr") or "") or None,
                    "required": bool(field.get("required")),
                    "constraints": constraints,
                    "options": list(field.get("options") or []),
                    "help_text": str(field.get("help_text") or "") or None,
                    "error_text_observed": str(field.get("error_text") or "")
                    or None,
                    "validation_source": "dom",
                    "ordinal": int(field.get("field_index") or 0),
                    "element_id": None,
                }
            )
        destructive = any(
            classify_action(role="button", name=str(field.get("label") or ""))
            == "irreversible"
            for field in fields
            if str(field.get("field_type")) in ("submit",)
        )
        forms.append(
            {
                "form_key": f"form-{int(form.get('form_index') or 0)}",
                "method": str(form.get("method") or "") or None,
                "action_url": urljoin(
                    capture.url, str(form.get("action") or "")
                )
                or None,
                "probe_status": (
                    "unprobed_destructive" if destructive else "unprobed_readonly"
                ),
                "fields": fields,
            }
        )
    return forms


def identity_for(
    url: str,
    elements: list[dict[str, object]],
    forms: list[dict[str, object]],
) -> tuple[str, str | None, str | None]:
    """(state_id, element_signature, form_signature) computed by the
    harness's own identity function (workflow/harness_state.py), so
    harvested identity equals live identity by construction."""
    labels: list[str] = []
    for form in forms:
        for field in form.get("fields") or []:  # type: ignore[union-attr]
            labels.append(str(field["label"]))  # type: ignore[union-attr]
    state = HarnessState().add_state(
        url=url,
        elements=[
            (str(element["role"]), str(element["name"])) for element in elements
        ],
        form_fields=labels,
    )
    return (
        state.state_id,
        ";".join(state.element_signature) or None,
        ";".join(state.form_signature) or None,
    )


def page_effective_url(page: Any) -> str:
    """The URL a visit should use for this page (mirrors the census
    rule: a redirect page is visited at its target)."""
    if page.crawl_status == "redirect" and page.redirect_target:
        return page.redirect_target
    return page.canonical_url


@dataclass
class PageVisitResult:
    disposition: str  # 'visited' | 'blocked_auth' | 'blocked_wall' | 'failed'
    reason: str | None = None
    states: int = 0
    elements: int = 0
    forms: int = 0
    transitions: int = 0
    evidence_objects: int = 0
    har_dropped: int = 0
    aria_excerpt: str = ""


async def _body_text(controller: Any, handle: Any) -> str:
    try:
        session = controller._get_session(  # pyright: ignore[reportPrivateUsage]
            session_id=handle.session_id
        )
        return str(await session.page.inner_text("body"))[:20000]
    except Exception:
        return ""


async def _current_url(controller: Any, handle: Any) -> str:
    try:
        session = controller._get_session(  # pyright: ignore[reportPrivateUsage]
            session_id=handle.session_id
        )
        return str(session.page.url)
    except Exception:
        return ""


async def _dismiss_consent(
    controller: Any, handle: Any, *, execution_id: UUID, journey_id: UUID
) -> None:
    """Consent-as-chrome (Step 1 rule, reused verbatim): if a consent
    cluster is on the page, click its standard dismissal once."""
    try:
        targets = await controller.ui_state_targets(session_id=handle.session_id)
        dismissal = _consent_dismissal(_consent_cluster(targets))
        if dismissal is not None:
            await controller.click(
                session_id=handle.session_id,
                role=dismissal["role"],
                name=dismissal["name"],
                execution_id=execution_id,
                journey_id=journey_id,
                observe=False,
            )
            await controller.wait(
                session_id=handle.session_id, milliseconds=500, observe=False
            )
    except Exception:
        return


async def visit_page(
    *,
    controller: Any,
    handle: Any,
    repository: Any,
    store: Any,
    app_map: Any,
    page: Any,
    execution_id: UUID,
    journey_id: UUID,
    network: NetworkCapture,
    deadline: float,
) -> PageVisitResult:
    """Visit one page and write its inventory (doc 16 section 5.4).

    One page = one logical commit unit: the caller marks the page's
    disposition from the returned result. A failure anywhere after the
    landing capture still returns 'visited' with what was captured —
    partial truth beats a lost page — while a navigation failure is a
    page failure the job records and moves past.
    """
    result = PageVisitResult(disposition="visited")
    effective_url = page_effective_url(page)
    network.entries.clear()
    try:
        navigation = await controller.navigate(
            session_id=handle.session_id,
            url=effective_url,
            execution_id=execution_id,
            journey_id=journey_id,
            observe=True,
        )
    except Exception as exc:  # a dead page never stops the job
        return PageVisitResult(
            disposition="failed", reason=type(exc).__name__
        )
    landed_url = (
        navigation.observation.url
        if navigation is not None and navigation.observation is not None
        else await _current_url(controller, handle)
    )
    if is_login_path(urlsplit(landed_url).path) or (
        page.requires_auth and is_login_path(urlsplit(landed_url).path)
    ):
        return PageVisitResult(disposition="blocked_auth", reason="login_landing")
    body_text = await _body_text(controller, handle)
    if has_wall_markers(body_text):
        return PageVisitResult(disposition="blocked_wall", reason="wall_markers")

    await _dismiss_consent(
        controller, handle, execution_id=execution_id, journey_id=journey_id
    )

    default_state = await repository.get_default_state(page.id)
    har_mark = 0

    async def persist_state(
        capture: StateCapture,
        *,
        complete_row: Any | None,
    ) -> tuple[Any, list[dict[str, object]], dict[tuple[str, str], Any], str]:
        """Write one captured state's rows + evidence. With
        ``complete_row`` the census default state is completed in
        place; otherwise a new observed state is created."""
        nonlocal har_mark
        elements = distil_elements(capture)
        forms = distil_forms(capture)
        state_id_value, element_signature, form_signature = identity_for(
            capture.url, elements, forms
        )
        screenshot_hash = None
        if capture.screenshot_path:
            try:
                data = await asyncio.to_thread(
                    Path(capture.screenshot_path).read_bytes
                )
                screenshot_hash = hashlib.sha256(data).hexdigest()
            except OSError:
                screenshot_hash = None
        if complete_row is not None:
            await repository.complete_default_state(
                complete_row.id,
                state_id_value=state_id_value,
                element_signature=element_signature,
                form_signature=form_signature,
                dom_structure_hash=capture.dom_structure_hash,
                aria_hash=capture.aria_hash,
                screenshot_hash=screenshot_hash,
            )
            complete_row.state_id = state_id_value
            state_row = complete_row
        else:
            existing = await repository.list_states(page.id)
            observed_count = sum(
                1 for row in existing if row.state_kind == "observed"
            )
            state_row = await repository.create_observed_state(
                app_map,
                page,
                state_key=f"observed-{observed_count + 1}",
                state_kind="observed",
                state_id_value=state_id_value,
                element_signature=element_signature,
                form_signature=form_signature,
                dom_structure_hash=capture.dom_structure_hash,
                aria_hash=capture.aria_hash,
                screenshot_hash=screenshot_hash,
            )
        element_rows = await repository.insert_elements(
            app_map, page, state_row, elements
        )
        await repository.insert_forms(app_map, page, state_row, forms)
        counts = await store_state_evidence(
            store=store,
            repository=repository,
            app_map=app_map,
            page=page,
            state=state_row,
            capture=capture,
            har_entries=network.entries[har_mark:],
            viewport=HARVEST_VIEWPORT,
        )
        har_mark = len(network.entries)
        result.states += 1
        result.elements += len(elements)
        result.forms += len(forms)
        result.evidence_objects += counts["evidence_objects"]
        result.har_dropped += counts["har_dropped"]
        rows_by_key = {
            (str(element["role"]), str(element["name"])): row
            for element, row in zip(elements, element_rows, strict=False)
        }
        return state_row, elements, rows_by_key, state_id_value

    landing_capture = await capture_state(
        controller, handle, execution_id=execution_id, journey_id=journey_id
    )
    result.aria_excerpt = landing_capture.aria_snapshot[:12000]
    current_row, current_elements, current_rows, current_identity = (
        await persist_state(landing_capture, complete_row=default_state)
    )
    known_states: dict[str, Any] = {current_identity: current_row}
    rows_by_state: dict[str, dict[tuple[str, str], Any]] = {
        current_row.state_key: current_rows
    }
    openers: dict[str, tuple[str, str]] = {}

    def candidates(elements: list[dict[str, object]]) -> list[dict[str, object]]:
        return [
            element
            for element in elements
            if element["actionability"] in _FENCE_ACTIONABILITY
            and element["safety_class"] in _FENCE_SAFETY
        ]

    actions = 0
    queue: list[dict[str, object]] = candidates(current_elements)
    attempted: set[tuple[str, str]] = set()
    while queue and actions < HARVEST_STATE_ACTION_CAP:
        if time.monotonic() > deadline:
            break
        element = queue.pop(0)
        key = (str(element["role"]), str(element["name"]))
        if key in attempted:
            continue
        attempted.add(key)
        actions += 1
        # Only the CURRENT state's own element row may be wired: a
        # same-named element on another state is a different row.
        element_row = rows_by_state.get(current_row.state_key, {}).get(key)
        try:
            await controller.click(
                session_id=handle.session_id,
                role=key[0],
                name=key[1],
                execution_id=execution_id,
                journey_id=journey_id,
                observe=False,
            )
            await controller.wait(
                session_id=handle.session_id, milliseconds=300, observe=False
            )
        except Exception:
            continue
        landed = await _current_url(controller, handle)
        if canonical_url(landed) != canonical_url(effective_url):
            # A navigation, not a state: wire it to the target page's
            # default state when that page is in the map, then return
            # to the state we were in.
            if element_row is not None:
                await repository.set_element_navigates(element_row.id, landed)
                target_page = await repository.find_page_by_url(
                    app_map.id, canonical_url(landed)
                )
                if target_page is not None:
                    target_state = await repository.get_default_state(
                        target_page.id
                    )
                    if target_state is not None:
                        await repository.upsert_transition(
                            app_map,
                            from_state_id=current_row.id,
                            to_state_id=target_state.id,
                            via_element_id=element_row.id,
                            via_action="click",
                        )
                        result.transitions += 1
            try:
                await controller.navigate(
                    session_id=handle.session_id,
                    url=effective_url,
                    execution_id=execution_id,
                    journey_id=journey_id,
                    observe=False,
                )
                opener = openers.get(current_row.state_key)
                if opener is not None:
                    await controller.click(
                        session_id=handle.session_id,
                        role=opener[0],
                        name=opener[1],
                        execution_id=execution_id,
                        journey_id=journey_id,
                        observe=False,
                    )
                    await controller.wait(
                        session_id=handle.session_id,
                        milliseconds=300,
                        observe=False,
                    )
            except Exception:
                break
            continue
        # Same URL: a possible new state of this page.
        probe_capture = await capture_state(
            controller, handle, execution_id=execution_id, journey_id=journey_id
        )
        probe_elements = distil_elements(probe_capture)
        probe_forms = distil_forms(probe_capture)
        identity, _, _ = identity_for(
            probe_capture.url, probe_elements, probe_forms
        )
        if identity == current_identity:
            continue
        if identity in known_states:
            target_row = known_states[identity]
            if element_row is not None:
                await repository.set_element_opens_state(
                    element_row.id, target_row.state_key
                )
                await repository.upsert_transition(
                    app_map,
                    from_state_id=current_row.id,
                    to_state_id=target_row.id,
                    via_element_id=element_row.id,
                    via_action="click",
                )
                result.transitions += 1
            current_row = target_row
            current_identity = identity
            continue
        if result.states >= HARVEST_PAGE_STATE_CAP:
            break
        new_row, new_elements, new_rows, new_identity = await persist_state(
            probe_capture, complete_row=None
        )
        known_states[new_identity] = new_row
        rows_by_state[new_row.state_key] = new_rows
        openers[new_row.state_key] = key
        if element_row is not None:
            await repository.set_element_opens_state(
                element_row.id, new_row.state_key
            )
            await repository.upsert_transition(
                app_map,
                from_state_id=current_row.id,
                to_state_id=new_row.id,
                via_element_id=element_row.id,
                via_action="click",
            )
            result.transitions += 1
        current_row = new_row
        current_identity = new_identity
        queue.extend(candidates(new_elements))
    return result
