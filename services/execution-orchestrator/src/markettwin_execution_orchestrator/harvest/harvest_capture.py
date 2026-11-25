"""Layer-0 capture for one harvested page state (doc 16 section 5.3).

Everything a later stage needs is captured while the browser sits on
the state: the accessibility snapshot, the slop probe, a DOM
extraction for locators and forms, the screenshot, console/JS errors,
and the network traffic as a redacted HAR. Redaction happens HERE,
before anything is stored: a stored HAR carrying a live secret is a
gate-stopping defect (live gate H-2), so the redactor is a pure
function with its own tests, and its failure drops the object — raw
bytes are never stored as a fallback.

One honest gap against a full HAR (prep OQ3): the run stack captures
only a failed-request log, so this module installs its own Playwright
listeners on the harvest session. Response bodies and request
postData are NOT stored (size and MIME type only) — the stored object
is a HAR-shaped record of what was requested and what answered, not a
replayable archive.
"""

import hashlib
import json
import re
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlsplit, urlunsplit
from uuid import UUID

REDACTION_VERSION = "redact-1b.1"

REDACTED_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "x-session-id",
        "x-csrf-token",
    }
)

_SECRET_KEY_VALUE = re.compile(
    r"(api[_-]?key|client[_-]?secret|password|passwd|secret|token)",
    re.IGNORECASE,
)
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}"), "Bearer [REDACTED]"),
    (
        re.compile(
            r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"
        ),
        "[REDACTED]",
    ),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED]"),
    (
        re.compile(
            r"(?i)(api[_-]?key|client[_-]?secret|password|passwd|secret|token)"
            r"([\"']?\s*[:=]\s*[\"']?)([^\s\"',&]{8,})"
        ),
        r"\1\2[REDACTED]",
    ),
)

_TEXT_MIME_PREFIXES = ("text/",)
_TEXT_MIME_EXACT = frozenset(
    {
        "application/json",
        "application/javascript",
        "application/xml",
        "application/xhtml+xml",
        "image/svg+xml",
    }
)


def redact_text(text: str) -> tuple[str, int]:
    """Apply the section 5.3.1 secret patterns; returns (text, hits)."""
    count = 0
    for pattern, replacement in _SECRET_PATTERNS:
        text, hits = pattern.subn(replacement, text)
        count += hits
    return text, count


def redact_url(url: str) -> tuple[str, int]:
    """Redact secret-bearing query values and any pattern hits."""
    count = 0
    parts = urlsplit(url)
    if parts.query:
        pairs = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if _SECRET_KEY_VALUE.search(key) and value:
                pairs.append((key, "[REDACTED]"))
                count += 1
            else:
                pairs.append((key, value))
        query = "&".join(f"{key}={value}" for key, value in pairs)
        url = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, query, parts.fragment)
        )
    url, hits = redact_text(url)
    return url, count + hits


def _redact_headers(
    headers: list[dict[str, str]],
) -> tuple[list[dict[str, str]], int]:
    count = 0
    redacted: list[dict[str, str]] = []
    for header in headers:
        name = str(header.get("name", ""))
        value = str(header.get("value", ""))
        if name.lower() in REDACTED_HEADERS:
            redacted.append({"name": name, "value": "[REDACTED]"})
            count += 1
        else:
            value, hits = redact_text(value)
            count += hits
            redacted.append({"name": name, "value": value})
    return redacted, count


def _is_textual(mime_type: str) -> bool:
    base = mime_type.split(";", 1)[0].strip().lower()
    return base.startswith(_TEXT_MIME_PREFIXES) or base in _TEXT_MIME_EXACT


def redact_har(har: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Redact a built HAR in a deep copy; returns (har, hit count).

    Pure (doc 16 section 5.3.1): header names on the redaction list
    lose their values, secret patterns are scrubbed from URLs, header
    values, query strings, and any stored text body, and a binary body
    is dropped outright (counted as a redaction).
    """
    result: dict[str, Any] = json.loads(json.dumps(har))
    count = 0
    entries = result.get("log", {}).get("entries", [])
    for entry in entries:
        request = entry.get("request", {})
        url, hits = redact_url(str(request.get("url", "")))
        request["url"] = url
        count += hits
        headers, hits = _redact_headers(list(request.get("headers") or []))
        request["headers"] = headers
        count += hits
        for pair in request.get("queryString") or []:
            if _SECRET_KEY_VALUE.search(str(pair.get("name", ""))) and pair.get(
                "value"
            ):
                pair["value"] = "[REDACTED]"
                count += 1
        response = entry.get("response", {})
        headers, hits = _redact_headers(list(response.get("headers") or []))
        response["headers"] = headers
        count += hits
        content = response.get("content")
        if isinstance(content, dict) and "text" in content:
            mime_type = str(content.get("mimeType", ""))
            if _is_textual(mime_type):
                text, hits = redact_text(str(content["text"]))
                content["text"] = text
                count += hits
            else:
                content["text"] = "[BINARY DROPPED]"
                count += 1
    return result, count


def build_har(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """The section 5.3 HAR object around captured entries."""
    return {
        "log": {
            "version": "1.2",
            "creator": {
                "name": "markettwin-harvest",
                "version": REDACTION_VERSION,
            },
            "entries": entries,
        }
    }


def _headers_list(headers: dict[str, str]) -> list[dict[str, str]]:
    return [{"name": name, "value": value} for name, value in headers.items()]


def _query_pairs(url: str) -> list[dict[str, str]]:
    return [
        {"name": key, "value": value}
        for key, value in parse_qsl(urlsplit(url).query, keep_blank_values=True)
    ]


class NetworkCapture:
    """Playwright request/response listeners accumulating HAR entries.

    Installed on the harvest session's context before navigation; one
    capture serves the whole page visit (all of its states), and the
    job slices entries per state window by timestamp if it needs to.
    Response bodies are never read; failed requests land as status 0.
    """

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self._started: dict[int, float] = {}

    def install(self, context: Any) -> None:
        context.on("request", self._on_request)
        context.on("response", self._on_response)
        context.on("requestfailed", self._on_request_failed)

    def _on_request(self, request: Any) -> None:
        self._started[id(request)] = datetime.now(UTC).timestamp()

    def _entry_for(self, request: Any) -> dict[str, Any]:
        started = self._started.pop(id(request), datetime.now(UTC).timestamp())
        elapsed_ms = int((datetime.now(UTC).timestamp() - started) * 1000)
        post_size = 0
        try:
            post_data = request.post_data
            if post_data:
                post_size = len(str(post_data).encode("utf-8"))
        except Exception:
            post_size = 0
        return {
            "startedDateTime": datetime.fromtimestamp(
                started, tz=UTC
            ).isoformat(),
            "time": elapsed_ms,
            "request": {
                "method": request.method,
                "url": request.url,
                "httpVersion": "HTTP/1.1",
                "headers": _headers_list(dict(request.headers)),
                "queryString": _query_pairs(request.url),
                "headersSize": -1,
                "bodySize": post_size,
            },
            "cache": {},
            "timings": {"wait": elapsed_ms, "send": -1, "receive": -1},
        }

    def _on_response(self, response: Any) -> None:
        entry = self._entry_for(response.request)
        headers = dict(response.headers)
        content_type = headers.get("content-type", "")
        size = -1
        if headers.get("content-length", "").isdigit():
            size = int(headers["content-length"])
        entry["response"] = {
            "status": response.status,
            "statusText": response.status_text,
            "httpVersion": "HTTP/1.1",
            "headers": _headers_list(headers),
            "content": {"size": size, "mimeType": content_type},
            "headersSize": -1,
            "bodySize": size,
        }
        self.entries.append(entry)

    def _on_request_failed(self, request: Any) -> None:
        entry = self._entry_for(request)
        failure = ""
        try:
            failure_value = request.failure
            failure = (
                failure_value() if callable(failure_value) else str(failure_value)
            )
        except Exception:
            failure = ""
        entry["response"] = {
            "status": 0,
            "statusText": failure or "request failed",
            "httpVersion": "HTTP/1.1",
            "headers": [],
            "content": {"size": 0, "mimeType": ""},
            "headersSize": -1,
            "bodySize": 0,
        }
        self.entries.append(entry)


DOM_ELEMENTS_SCRIPT = """() => {
  const interactive = 'a[href], button, input, select, textarea, [role], [tabindex]';
  const nodes = [...document.querySelectorAll(interactive)];
  const forms = [...document.forms];
  const implicitRole = (el) => {
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return el.hasAttribute('href') ? 'link' : 'generic';
    if (tag === 'button') return 'button';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      if (type === 'submit' || type === 'button' || type === 'reset') return 'button';
      if (type === 'hidden') return 'generic';
      return 'textbox';
    }
    return 'generic';
  };
  const structuralPath = (el) => {
    const parts = [];
    let node = el;
    while (node && node !== document.body && parts.length < 12) {
      const tag = node.tagName.toLowerCase();
      let index = 1;
      let sibling = node.previousElementSibling;
      while (sibling) {
        if (sibling.tagName === node.tagName) index += 1;
        sibling = sibling.previousElementSibling;
      }
      parts.unshift(tag + ':nth-of-type(' + index + ')');
      node = node.parentElement;
    }
    return parts.join(' > ');
  };
  const labelFor = (el) => {
    if (el.id) {
      const label = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (label) return (label.innerText || '').trim();
    }
    const wrapping = el.closest('label');
    if (wrapping) return (wrapping.innerText || '').trim();
    return el.getAttribute('aria-label') || '';
  };
  return nodes.map((el, index) => {
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return {
      dom_index: index,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || implicitRole(el),
      testid: el.getAttribute('data-testid') || el.getAttribute('data-test-id') || el.getAttribute('data-cy') || '',
      id_attr: el.id || '',
      text: (el.innerText || el.value || '').trim().slice(0, 200),
      aria_label: el.getAttribute('aria-label') || '',
      label: labelFor(el),
      href: el.tagName === 'A' ? el.href : '',
      type: (el.getAttribute('type') || '').toLowerCase(),
      structural_path: structuralPath(el),
      form_index: el.form ? forms.indexOf(el.form) : -1,
      visible: rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none',
    };
  });
}"""

FORM_SCRIPT = """() => {
  const describe = (el, ids) => ids.split(/\\s+/).filter(Boolean)
    .map((id) => document.getElementById(id))
    .filter(Boolean)
    .map((node) => (node.innerText || '').trim())
    .filter(Boolean)
    .join(' ');
  const labelFor = (el) => {
    if (el.id) {
      const label = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (label) return (label.innerText || '').trim();
    }
    const wrapping = el.closest('label');
    if (wrapping) return (wrapping.innerText || '').trim();
    return el.getAttribute('aria-label') || '';
  };
  return [...document.forms].map((form, formIndex) => ({
    form_index: formIndex,
    method: (form.getAttribute('method') || 'get').toLowerCase(),
    action: form.action || '',
    fields: [...form.elements].map((el, fieldIndex) => {
      const tag = el.tagName.toLowerCase();
      const describedBy = el.getAttribute('aria-describedby') || '';
      const invalid = el.getAttribute('aria-invalid') === 'true';
      return {
        field_index: fieldIndex,
        tag,
        field_type: tag === 'select' ? 'select' : tag === 'textarea' ? 'textarea' : (el.getAttribute('type') || 'text').toLowerCase(),
        name_attr: el.getAttribute('name') || '',
        id_attr: el.id || '',
        label: labelFor(el),
        required: Boolean(el.required) || el.getAttribute('aria-required') === 'true',
        constraints: {
          pattern: el.getAttribute('pattern') || '',
          min: el.getAttribute('min') || '',
          max: el.getAttribute('max') || '',
          minlength: el.getAttribute('minlength') || '',
          maxlength: el.getAttribute('maxlength') || '',
          step: el.getAttribute('step') || '',
          autocomplete: el.getAttribute('autocomplete') || '',
        },
        options: tag === 'select' ? [...el.options].map((option) => ({
          value: option.value, label: (option.text || '').trim(), selected: option.selected,
        })) : [],
        help_text: describe(el, describedBy),
        error_text: invalid ? describe(el, describedBy) : '',
      };
    }),
  }));
}"""

SKELETON_SCRIPT = """() => {
  const parts = [];
  const walk = (node, depth) => {
    if (depth > 24 || parts.length > 4000) return;
    for (const child of node.children) {
      parts.push(child.tagName.toLowerCase() + '@' + depth);
      walk(child, depth + 1);
    }
  };
  walk(document.body, 0);
  return parts.join(';');
}"""


@dataclass(frozen=True)
class StateCapture:
    """Everything captured on one page state (doc 16 section 5.3)."""

    url: str
    title: str
    aria_snapshot: str
    aria_entries: list[dict[str, Any]]
    probe: dict[str, Any]
    dom_elements: list[dict[str, Any]]
    forms: list[dict[str, Any]]
    dom_structure_hash: str
    aria_hash: str
    screenshot_path: str
    js_errors: list[dict[str, Any]] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)


def aria_hash_of(aria_snapshot: str) -> str:
    collapsed = " ".join(aria_snapshot.split())
    return hashlib.sha256(collapsed.encode("utf-8")).hexdigest()


async def capture_state(
    controller: Any,
    handle: Any,
    *,
    execution_id: UUID,
    journey_id: UUID,
    authenticated_session: bool = False,
) -> StateCapture:
    """Capture one state's Layer-0 record through the controller.

    The aria entries come from the controller's own page index (the
    same universe the harness's live runs see — required for state
    identity to match), paged 80 at a time; the DOM and form
    extractions and the structural skeleton run as page evaluations on
    the session the controller owns.

    ``authenticated_session`` is forwarded to the page index only:
    its documented exception is a session created from an
    AuthSessionBroker snapshot, which is the caller's claim to
    make — harvest callers leave it False.
    """
    entries: list[dict[str, Any]] = []
    aria_snapshot = ""
    url = ""
    title = ""
    cursor = 0
    while True:
        result = await controller.get_page_index(
            session_id=handle.session_id,
            execution_id=execution_id,
            journey_id=journey_id,
            cursor=cursor,
            authenticated_session=authenticated_session,
        )
        if result.observation is not None:
            aria_snapshot = result.observation.aria_snapshot
            url = result.observation.url
            title = result.observation.title
        entries.extend(dict(entry) for entry in (result.page_index or ()))
        if result.next_cursor is None:
            break
        cursor = result.next_cursor
    probe = await controller.probe_page(session_id=handle.session_id)
    session = controller._get_session(  # pyright: ignore[reportPrivateUsage]
        session_id=handle.session_id
    )
    dom_elements = await session.page.evaluate(DOM_ELEMENTS_SCRIPT)
    forms = await session.page.evaluate(FORM_SCRIPT)
    skeleton = await session.page.evaluate(SKELETON_SCRIPT)
    screenshot_path = await controller.capture_evidence_screenshot(
        session_id=handle.session_id
    )
    js_records = await controller.harvest_js_records(
        session_id=handle.session_id
    )
    return StateCapture(
        url=url or str(probe.get("url") or ""),
        title=title or str(probe.get("title") or ""),
        aria_snapshot=aria_snapshot,
        aria_entries=entries,
        probe=dict(probe),
        dom_elements=list(dom_elements),
        forms=list(forms),
        dom_structure_hash=hashlib.sha256(
            str(skeleton).encode("utf-8")
        ).hexdigest(),
        aria_hash=aria_hash_of(aria_snapshot),
        screenshot_path=screenshot_path,
        js_errors=[
            {"kind": record.kind, "message": record.message}
            for record in js_records
        ],
        console_errors=list(session.event_buffer.all_console_errors),
    )


@dataclass(frozen=True)
class StoredObject:
    sha256: str
    byte_size: int


class EvidenceStore(Protocol):
    """Where captured bytes go (S3 in production, a fake in tests)."""

    async def put(
        self, *, object_key: str, data: bytes, content_type: str
    ) -> StoredObject: ...


class S3EvidenceStore:
    """EvidenceStore over the orchestrator's S3ArtifactStorage."""

    def __init__(self, storage: Any) -> None:
        self._storage = storage

    async def put(
        self, *, object_key: str, data: bytes, content_type: str
    ) -> StoredObject:
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(data)
            temp_path = Path(handle.name)
        try:
            stored = await self._storage.upload(
                local_path=temp_path,
                object_key=object_key,
                content_type=content_type,
            )
        finally:
            temp_path.unlink(missing_ok=True)
        return StoredObject(sha256=stored.sha256, byte_size=stored.size_bytes)


def evidence_key(app_map_id: UUID, page_id: UUID, kind: str, state_key: str) -> str:
    """The section 5.3 object key shape."""
    suffix = "png" if kind == "screenshot" else "json"
    return f"app-maps/{app_map_id}/{page_id}/{kind}-{state_key}.{suffix}"


async def store_state_evidence(
    *,
    store: EvidenceStore,
    repository: Any,
    app_map: Any,
    page: Any,
    state: Any,
    capture: StateCapture,
    har_entries: list[dict[str, Any]],
    viewport: str,
) -> dict[str, int]:
    """Store one state's evidence objects and record their rows.

    Returns counts including ``har_dropped``: when the redactor itself
    fails, the HAR row is recorded as dropped with no object behind it
    and the page proceeds (doc 16 section 5.3.1) — raw network bytes
    are never stored as a fallback.
    """
    counts = {"evidence_objects": 0, "har_dropped": 0}
    state_key = state.state_key if state is not None else "page"

    async def record(
        kind: str,
        data: bytes,
        content_type: str,
        redaction_status: str,
        redaction_count: int = 0,
    ) -> None:
        key = evidence_key(app_map.id, page.id, kind, state_key)
        stored = await store.put(
            object_key=key, data=data, content_type=content_type
        )
        await repository.record_evidence(
            app_map,
            page,
            state,
            kind=kind,
            viewport=viewport,
            object_key=key,
            sha256=stored.sha256,
            byte_size=stored.byte_size,
            redaction_status=redaction_status,
            redaction_count=redaction_count,
        )
        counts["evidence_objects"] += 1

    aria_payload = {
        "url": capture.url,
        "title": capture.title,
        "aria_snapshot": capture.aria_snapshot,
        "entries": capture.aria_entries,
    }
    await record(
        "aria_snapshot",
        json.dumps(aria_payload).encode("utf-8"),
        "application/json",
        "not_applicable",
    )
    inventory_payload = {"probe": capture.probe, "elements": capture.dom_elements}
    await record(
        "element_inventory",
        json.dumps(inventory_payload).encode("utf-8"),
        "application/json",
        "not_applicable",
    )
    await record(
        "form_inventory",
        json.dumps({"forms": capture.forms}).encode("utf-8"),
        "application/json",
        "not_applicable",
    )
    console_payload = {
        "console_errors": capture.console_errors,
        "js_errors": capture.js_errors,
    }
    await record(
        "console_log",
        json.dumps(console_payload).encode("utf-8"),
        "application/json",
        "not_applicable",
    )
    if capture.screenshot_path:
        screenshot_bytes = await _read_bytes(capture.screenshot_path)
        if screenshot_bytes:
            await record(
                "screenshot", screenshot_bytes, "image/png", "not_applicable"
            )
    try:
        redacted, hits = redact_har(build_har(har_entries))
    except Exception:
        counts["har_dropped"] += 1
        await repository.record_evidence(
            app_map,
            page,
            state,
            kind="harvest_har",
            viewport=viewport,
            object_key="",
            sha256="",
            byte_size=0,
            redaction_status="dropped",
            redaction_count=0,
        )
        return counts
    await record(
        "harvest_har",
        json.dumps(redacted).encode("utf-8"),
        "application/json",
        "redacted",
        redaction_count=hits,
    )
    return counts


async def _read_bytes(path: str) -> bytes:
    import asyncio

    try:
        return await asyncio.to_thread(Path(path).read_bytes)
    except OSError:
        return b""
