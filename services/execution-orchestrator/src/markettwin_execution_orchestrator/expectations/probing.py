"""Form probing (doc 21 section 7). No model imports.

Preconditions (all required, else the grounding stage completes the
probe step as skipped_no_standard_mode): the trigger carried
probe=true and approved test data arrived through doc 17's approved
channel. A form whose submit classifies irreversible is named
unprobed_destructive and NEVER submitted (C5). Protocol per form,
fresh navigation for each sub-probe: (a) empty submit, (b) one
invalid value per constrained field, (c) one valid completion when
approved data covers every field. An ambiguous submit is never
retried. Writes stay inside the probing-owned fields (C9).
"""

from __future__ import annotations

from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from markettwin_database.models.knowledge import MapPageState, MapTransition

from . import authoring
from .grounding import GraphIndex

_VALIDATION_WORDS = ("required", "invalid", "error", "must", "please", "enter a")
_INVALID_BY_TYPE = {"email": "not-an-email", "url": "not a url", "tel": "abc"}


class ProbeDriver(Protocol):
    """The browser primitives probing orchestrates. The production
    driver wraps the BrowserController; tests fake this surface."""

    async def open(self, url: str) -> None: ...
    async def fill(self, *, label: str, value: str) -> None: ...
    async def submit(self) -> None: ...
    async def observe(self) -> dict: ...


def extract_errors(
    aria_lines: list[str], baseline_lines: list[str], fields: list
) -> dict[UUID, str]:
    """New post-submit lines that read as validation errors, mapped
    to fields by label (a lone field takes any new error line)."""
    baseline = {line.strip() for line in baseline_lines}
    fresh = [
        line.strip()
        for line in aria_lines
        if line.strip() and line.strip() not in baseline
    ]
    errors: dict[UUID, str] = {}
    for line in fresh:
        lowered = line.lower()
        if not any(word in lowered for word in _VALIDATION_WORDS):
            continue
        matched = [
            field_row
            for field_row in fields
            if field_row.label and field_row.label.lower() in lowered
        ]
        if len(matched) == 1:
            errors.setdefault(matched[0].id, line)
        elif not matched and len(fields) == 1:
            errors.setdefault(fields[0].id, line)
    return errors


def _is_constrained(field_row) -> bool:
    return bool(field_row.required) or bool(field_row.constraints)


async def run_probing(ctx, *, approved_test_data: dict, driver=None) -> dict:
    """Probe every form of the map; returns the section 6.4 probes
    metrics dict. Per-form failures are recorded on the context and
    never retried."""
    index: GraphIndex = ctx.index
    repository = ctx.repository
    probes = {
        "attempted": 0,
        "probed": 0,
        "unprobed_destructive": 0,
        "skipped_no_standard_mode": 0,
        "skipped_no_submit": 0,
        "skipped_missing_page": 0,
        "valid_completion": {},
    }
    rejected = await repository.rejected_keys(ctx.app_map.id)
    forms = [
        form
        for form in index.forms.values()
        if any(f.form_id == form.id for f in index.fields.values())
    ]
    for form in forms:
        fields = [f for f in index.fields.values() if f.form_id == form.id]
        fields.sort(key=lambda f: f.ordinal or 0)
        submit_element = (
            index.elements.get(form.submit_element_id)
            if form.submit_element_id
            else None
        )
        if (form.probe_status == "unprobed_destructive"
                or (form.method or "get").lower() != "get"
                or submit_element is not None and submit_element.safety_class == "irreversible"):
            probes["unprobed_destructive"] += 1
            await repository.save_form_probe(form.id, "unprobed_destructive")
            continue
        page = index.pages.get(form.map_page_id)
        if page is None:
            probes["skipped_missing_page"] += 1
            continue
        if submit_element is None:
            probes["skipped_no_submit"] += 1
            continue
        if form.action_url:
            action, origin = urlsplit(form.action_url), urlsplit(page.canonical_url)
            if action.scheme not in {"http", "https"} or (
                action.scheme, action.hostname, action.port or (443 if action.scheme == "https" else 80)
            ) != (origin.scheme, origin.hostname, origin.port or (443 if origin.scheme == "https" else 80)):
                probes["unprobed_destructive"] += 1
                await repository.save_form_probe(form.id, "unprobed_destructive")
                continue
        probes["attempted"] += 1
        form_driver = driver or BrowserProbeDriver(
            ctx.app_map,
            submit_role=submit_element.role,
            submit_name=submit_element.name,
            form_key=form.form_key,
        )
        values = {
            field_row.id: approved_test_data.get(
                field_row.label or "", approved_test_data.get(field_row.name_attr or "")
            )
            for field_row in fields
        }
        try:
            observed = await _probe_one(
                form_driver,
                page_url=page.canonical_url,
                submit_name=submit_element.name,
                fields=fields,
                values=values,
                probes=probes,
                form=form,
            )
        except Exception as exc:  # ambiguous submit: never retried
            ctx.record_failure("probe", exc)
            continue
        finally:
            if driver is None:
                await form_driver.close()
        for field_id, error_text in observed["errors"].items():
            await repository.save_field_validation(field_id, error_text)
            field_row = index.fields[field_id]
            probe_case = observed["cases"][field_id]
            await authoring.author_expectation(
                repository,
                ctx.app_map,
                subject_kind="field",
                subject_id=field_id,
                statement=(
                    f"Submitting '{field_row.label}' with a {probe_case} "
                    f"value shows: {error_text}"
                ),
                oracle_source="observation",
                source_ref=f"probe:{form.id}:{field_id}",
                confidence="medium",
                assertion={
                    "kind": "field_validation",
                    "subject": {
                        "field_id": str(field_id),
                        "label": field_row.label,
                    },
                    "params": {
                        "probe_case": probe_case,
                        "expected_error_text": error_text,
                    },
                },
                assertion_origin="deterministic",
                rejected_keys=rejected,
            )
        if observed["error_state"] is not None:
            await repository.add_probe_state(
                ctx.app_map,
                form=form,
                submit_element_id=submit_element.id,
                **observed["error_state"],
            )
        success_transition_id = None
        if observed["success_state_identity"] is not None:
            success_transition_id = await repository.resolve_success_transition(
                ctx.app_map,
                form=form,
                submit_element_id=submit_element.id,
                to_state_identity=observed["success_state_identity"],
            )
        await repository.save_form_probe(
            form.id,
            "probed",
            success_transition_id=success_transition_id,
        )
        probes["probed"] += 1
    return probes


async def _probe_one(
    driver: ProbeDriver,
    *,
    page_url: str,
    submit_name: str,
    fields: list,
    values: dict,
    probes: dict,
    form,
) -> dict:
    """The per-form protocol (section 7.2). Returns the observed
    errors {field_id: text}, the probe case per field, the error
    state identity if a new one appeared, and the success transition
    target state id when the valid completion navigated."""
    await driver.open(page_url)
    baseline = await driver.observe()
    baseline_lines = baseline["aria_lines"]
    errors: dict[UUID, str] = {}
    cases: dict[UUID, str] = {}
    error_state = None

    await driver.submit()
    after_empty = await driver.observe()
    for field_id, text in extract_errors(
        after_empty["aria_lines"], baseline_lines, fields
    ).items():
        errors[field_id] = text
        cases[field_id] = "empty"
    if errors and after_empty.get("state_id"):
        error_state = {
            "state_id": after_empty["state_id"],
            "element_signature": after_empty.get("element_signature", ""),
            "url": after_empty["url"],
        }

    for field_row in fields:
        if not _is_constrained(field_row) or field_row.id in errors:
            continue
        await driver.open(page_url)
        await driver.fill(
            label=field_row.label or "",
            value=_INVALID_BY_TYPE.get(field_row.field_type or "", "!!!"),
        )
        await driver.submit()
        after_invalid = await driver.observe()
        found = extract_errors(after_invalid["aria_lines"], baseline_lines, fields)
        if field_row.id in found:
            errors[field_row.id] = found[field_row.id]
            cases[field_row.id] = "invalid"

    success_state_identity = None
    covered = all(values.get(field_row.id) for field_row in fields)
    if covered:
        await driver.open(page_url)
        for field_row in fields:
            await driver.fill(
                label=field_row.label or "", value=str(values[field_row.id])
            )
        await driver.submit()
        after_valid = await driver.observe()
        probes["valid_completion"][str(form.id)] = "done"
        if after_valid["url"] != page_url:
            success_state_identity = after_valid.get("state_id")
    else:
        probes["valid_completion"][str(form.id)] = "no_test_data"
    return {
        "errors": errors,
        "cases": cases,
        "error_state": error_state,
        "success_state_identity": success_state_identity,
    }


class BrowserProbeDriver:
    """Production driver: one clean controller session per form,
    actions through perform_case_action (guarded freedom is the
    controller's own policy: public_only + the map's origin)."""

    def __init__(self, app_map, *, submit_role: str, submit_name: str, form_key: str) -> None:
        self._app_map = app_map
        self._submit_target = (submit_role, submit_name)
        self._form_key = form_key
        self._controller = None
        self._handle = None
        self._scope = None
        self._execution_id = uuid4()
        self._journey_id = uuid4()

    async def _ensure_session(self) -> None:
        from urllib.parse import urlsplit

        from markettwin_execution_orchestrator.browser.contracts import (
            AllowedOrigin,
        )
        from markettwin_execution_orchestrator.browser.controller import (
            BrowserController,
        )
        from markettwin_shared.feature_plan import FeatureScope

        if self._controller is not None:
            return
        parts = urlsplit(self._app_map.base_url)
        origin = AllowedOrigin(
            scheme=parts.scheme,
            hostname=parts.hostname or "",
            port=parts.port or (443 if parts.scheme == "https" else 80),
        )
        self._scope = FeatureScope(
            feature_key="probing",
            goal="Probe form validation with approved test data.",
            starting_url=self._app_map.base_url,
            allowed_origins=(f"{parts.scheme}://{parts.netloc}",),
        )
        self._controller = BrowserController()
        self._handle = await self._controller.create_session(
            execution_id=self._execution_id,
            journey_id=self._journey_id,
            allowed_origins=[origin],
            network_policy="public_only",
            js_capture=True,
        )

    async def open(self, url: str) -> None:
        from markettwin_execution_orchestrator.workflow.case_execution import (
            perform_case_action,
        )
        from markettwin_shared.feature_plan import CaseAction

        await self._ensure_session()
        await perform_case_action(
            self._controller,
            self._handle,
            CaseAction(action="navigate", url=url),
            self._scope,
        )

    async def fill(self, *, label: str, value: str) -> None:
        from markettwin_execution_orchestrator.workflow.case_execution import (
            perform_case_action,
        )
        from markettwin_shared.feature_plan import (
            CaseAction,
            SafeTestValue,
            SemanticTarget,
        )

        await self._ensure_session()
        key = f"probe_{uuid4().hex[:8]}"
        scope = self._scope.model_copy(
            update={
                "safe_test_data": self._scope.safe_test_data
                + (SafeTestValue(key=key, value=value[:256]),)
            }
        )
        await perform_case_action(
            self._controller,
            self._handle,
            CaseAction(
                action="fill",
                target=SemanticTarget(label=label),
                test_value_key=key,
            ),
            scope,
        )

    async def submit(self) -> None:
        import re

        await self._ensure_session()
        match = re.fullmatch(r"form-(\d+)", self._form_key)
        if match is None:
            raise ValueError("probe_form_identity_unavailable")
        role, name = self._submit_target
        await self._controller.click(
            session_id=self._handle.session_id, execution_id=self._execution_id,
            journey_id=self._journey_id, role=role, name=name, form_index=int(match.group(1)),
        )

    async def close(self) -> None:
        if self._controller is not None:
            await self._controller.close()
            self._controller = None
            self._handle = None

    async def observe(self) -> dict:
        from markettwin_execution_orchestrator.harvest.harvest_capture import (
            capture_state,
        )
        from markettwin_execution_orchestrator.harvest.harvest_inventory import (
            distil_elements,
            distil_forms,
            identity_for,
        )

        await self._ensure_session()
        capture = await capture_state(
            self._controller,
            self._handle,
            execution_id=self._execution_id,
            journey_id=self._journey_id,
        )
        elements = distil_elements(capture)
        forms = distil_forms(capture)
        state_id, _, _ = identity_for(capture.url, elements, forms)
        return {
            "url": capture.url,
            "aria_lines": capture.aria_snapshot.splitlines(),
            "state_id": state_id,
            "element_signature": ";".join(
                f"{element['role']}|{element['name']}" for element in elements
            ),
        }
