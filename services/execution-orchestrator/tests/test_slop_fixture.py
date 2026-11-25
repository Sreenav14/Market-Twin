"""U-P6 gate: a seeded slop+JS app and a clean control page, driven
through the real slop executor with a real browser.

The slop page must be caught: placeholder text + broken media as
slop, and each of the three JS error kinds exactly once (deduped).
The clean page must be acquitted in every family.
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from playwright.async_api import async_playwright

from markettwin_database.models import TestRun
from markettwin_execution_orchestrator.browser.contracts import AllowedOrigin
from markettwin_execution_orchestrator.workflow import slop_run
from markettwin_shared.slop_aggregate import slop_family

SLOP_PAGE = """
<!doctype html><html lang="en"><head><title>Sloppy</title></head>
<body>
  <h1>Welcome to our platform — unlock the power of seamless experience</h1>
  <p>Lorem ipsum dolor sit amet, this text goes here.</p>
  <img src="/missing-badge.png" alt="Trust badge" width="120" height="24">
  <div style="font-size:12px;letter-spacing:1.2px">SEPTEMBER 9, 2026 - PRODUCT NEWS</div>
  <h2 style="margin:0">Shipment alerts are available</h2>
  <a href="/clean">See the clean page</a>
  <button>Get started</button>
  <script>
    console.error('Chunk load failed for settings');
    setTimeout(() => { throw new Error('Kaboom uncaught'); }, 50);
    setTimeout(() => { Promise.reject(new Error('async went wrong')); }, 80);
  </script>
</body></html>
"""

CLEAN_WORDS = " ".join(
    f"Detail{i} explains exactly what this setting does and when to use it."
    for i in range(12)
)

CLEAN_PAGE = f"""
<!doctype html><html lang="en"><head><title>Clean settings</title></head>
<body>
  <h1>Notification settings</h1>
  <p>{CLEAN_WORDS}</p>
  <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8Xw8AAwMCAO+ip1sAAAAASUVORK5CYII=" alt="Status dot" width="8" height="8">
  <button>Save notification settings</button>
</body></html>
"""

BASELINE_ROUTES = {
    "/": ("Shipment alerts", '<button id="save">Save alert preferences</button>'),
    "/editorial": ("Release library", """
        <section><p class="label">Release notes</p><h2>Export delivery dates</h2></section>
        <section><p class="label">Release notes</p><h2>Track delayed parcels</h2></section>
        <section><p class="label">Release notes</p><h2>Schedule pickup windows</h2></section>
    """),
    "/layout": ("Delivery schedules", """
        <section class="layout">
          <article><h2>Warehouse hours</h2><p>Pickup opens at nine.</p></article>
          <article><h2>Holidays</h2><p>Sunday pickups require a reservation.</p></article>
        </section>
    """),
    "/setup": ("Carrier setup", """
        <div class="clip"><button id="activate">Activate carrier integration</button></div>
    """),
    "/team": ("Team alerts", '<button id="save" class="variant">Save alert preferences</button>'),
    "/resources": ("Packaging reference", """
        <img id="diagram" src="/missing-diagram.png" alt="Packing diagram" width="240" height="140">
    """),
    "/account": ("Billing account", """
        <button aria-controls="account-menu" aria-expanded="false"
          onclick="this.setAttribute('aria-expanded', 'true');
                   document.getElementById('account-menu').hidden = false">Account actions</button>
        <div id="account-menu" hidden>
          <div class="clip"><button id="download">Download last invoice</button></div>
        </div>
    """),
}

# Label before inspecting detector output. Route and state define the scope;
# expected rules identify the emitted claims that can address each label.
BASELINE_CASES = [
    {"route": "/", "state": "initial", "task": "Find shipment preferences",
     "target": "Display and body hierarchy", "expected": "clean",
     "rules": ["SLOP_DEFAULT_FONT"]},
    {"route": "/editorial", "state": "initial", "task": "Browse the release library",
     "target": "Release notes category labels", "expected": "clean",
     "rules": ["SLOP_TEMPLATE_CHROME"]},
    {"route": "/layout", "state": "initial", "task": "Read pickup hours and exceptions",
     "target": "Intentional offset between editorial columns", "expected": "clean",
     "rules": ["SLOP_ALIGNMENT"]},
    {"route": "/setup", "state": "initial", "task": "Identify the activation action",
     "target": "Activate carrier integration", "expected": "defect",
     "rules": ["SLOP_VIEWPORT_INTEGRITY", "SLOP_CLIPPED_CONTROL_LABEL"]},
    {"route": "/team", "state": "initial", "task": "Recognize the same save action across alerts",
     "target": "Save alert preferences", "expected": "inconsistency",
     "rules": ["UI_COMPONENT_VARIANT_REVIEW"]},
    {"route": "/resources", "state": "initial", "task": "Read the packing instructions",
     "target": "Packing diagram", "expected": "defect", "rules": ["SLOP_BROKEN_MEDIA"]},
    {"route": "/account", "state": "Account actions open", "task": "Find the invoice download",
     "target": "Download last invoice", "expected": "defect",
     "rules": ["SLOP_VIEWPORT_INTEGRITY", "SLOP_CLIPPED_CONTROL_LABEL"]},
]
FIXTURE_DIR = Path(__file__).with_name("fixtures")

# Kept out of the navigation and sitemap for subsequent independent review.
HOLDOUT_ROUTES = {
    "/holdout/pickup": ("Pickup receipts", "<h2>Receipt history</h2><p>Receipts by date.</p>"),
    "/holdout/returns": ("Return settings", """
        <div class="clip"><button>Confirm the return address</button></div>
    """),
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/missing-"):
            self.send_error(404)
            return
        body = CLEAN_PAGE if self.path.startswith("/clean") else SLOP_PAGE
        payload = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        pass


class _BaselineHandler(_Handler):
    def do_GET(self) -> None:  # noqa: N802
        route = urlsplit(self.path).path
        if route == "/sitemap.xml":
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.end_headers()
            self.wfile.write(b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>')
            return
        page = BASELINE_ROUTES.get(route) or HOLDOUT_ROUTES.get(route)
        if page is None:
            self.send_error(404)
            return
        title, content = page
        links = "".join(f'<li><a href="{path}">{heading}</a></li>'
                        for path, (heading, _) in BASELINE_ROUTES.items() if path != "/")
        body = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>{title}</title>
          <style>
            body {{ font: 16px Inter, Arial, sans-serif; color: #18242d; background: #fff; }}
            main {{ max-width: 960px; margin: 36px auto; }}
            h1 {{ font-size: 44px; font-weight: 700; }}
            nav ul {{ display: flex; gap: 20px; padding: 0; list-style: none; }}
            button {{ background: #164577; color: white; padding: 12px 18px; border: 0; }}
            button.variant {{ background: #533a19; border-radius: 24px; }}
            .label {{ font: bold 12px monospace; }}
            .layout {{ display: grid; grid-template-columns: 2fr 1fr; gap: 44px; }}
            .layout article:nth-child(2) {{ margin-top: 28px; }}
            .clip {{ width: 95px; overflow: hidden; }}
            .clip button {{ width: max-content; white-space: nowrap; }}
          </style>
          <main><h1>{title}</h1><p>Manage delivery schedules and notices for your shipments.
          Preferences apply to new deliveries. Existing delivery records keep their own settings.</p>
          {content}
          {"<nav><ul>" + links + "</ul></nav>" if route == "/" else ""}</main></html>"""
        payload = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


async def _audit_fixture(
    monkeypatch, handler, *, desktop_scan=False, check_fixture=None, review=None,
):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    events: dict[str, list[dict]] = {}

    class _Events:
        def __init__(self, session):
            pass

        async def create(self, **kwargs):
            events.setdefault(kwargs["event_type"], []).append(kwargs["payload"])

    completed: list[bool] = []

    class _States:
        def __init__(self, session):
            pass

        async def mark_running(self, **kwargs):
            return None

        async def mark_completed(self, **kwargs):
            completed.append(True)

    monkeypatch.setattr(slop_run, "RunEventRepository", _Events)
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.persistence.run_state_repository.RunStateRepository",
        _States,
    )
    monkeypatch.setattr(
        slop_run, "ExecutionRepository",
        lambda _: Mock(
            create_agent_execution=AsyncMock(),
            create_browser_session=AsyncMock(),
            mark_browser_session_closed=AsyncMock(),
            finish_agent_execution=AsyncMock(),
        ),
    )
    run_id = uuid4()
    run = TestRun(id=run_id, configuration_snapshot={})
    monkeypatch.setattr(slop_run, "review_screenshots", review or AsyncMock(return_value=[]))
    monkeypatch.setattr(slop_run, "review_checkpoint", AsyncMock(
        return_value={"decision": "continue", "reason": "Fixture baseline"},
    ))
    if desktop_scan:
        async def save_screenshot(state, **kwargs):
            assert Path(state["screenshot_path"]).is_file()
            state["screenshot_artifact_id"] = str(uuid4())

        monkeypatch.setattr(slop_run, "save_state_evidence", save_screenshot)
    session = Mock()
    session.get = AsyncMock(return_value=run)
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    base_url = f"http://127.0.0.1:{port}"
    request = SimpleNamespace(
        run_id=run_id,
        start_url=f"{base_url}/",
        allowed_origins=(AllowedOrigin("http", "127.0.0.1", port),),
        network_policy="local_development",
        study_brief="Audit the fixture UI",
    )
    try:
        if check_fixture is not None:
            await check_fixture(base_url)
        await slop_run.execute_slop_run(request=request, session=session, desktop_scan=desktop_scan)
    finally:
        server.shutdown()
        server.server_close()
    assert completed == [True]
    return base_url, events, run.configuration_snapshot


@pytest.mark.asyncio
async def test_seeded_slop_and_js_fixture(monkeypatch) -> None:
    base_url, events, _ = await _audit_fixture(monkeypatch, _Handler)
    published = events["slop.state.result"]
    by_url = {state["url"]: state for state in published if state.get("viewport") == "desktop1280"}
    slop_state = by_url[f"{base_url}/"]
    clean_state = by_url[f"{base_url}/clean"]

    # Each JS kind caught exactly once (console error reproduces on
    # the executor's re-visit, so it is serious there).
    js_rules = {
        error["rule_id"]: error for error in slop_state["js_errors"]
        if error["rule_id"] != "DEF_JS_CONSOLE_ERROR"
        or "Chunk load failed for settings" in error["message"]
    }
    assert set(js_rules) == {
        "DEF_JS_UNCAUGHT", "DEF_JS_CONSOLE_ERROR", "DEF_JS_UNHANDLED_REJECTION",
    }
    assert js_rules["DEF_JS_UNCAUGHT"]["count"] == 1
    assert js_rules["DEF_JS_UNHANDLED_REJECTION"]["count"] == 1
    assert js_rules["DEF_JS_CONSOLE_ERROR"]["severity"] == "serious"
    # Slop verdicts on the slop page: placeholder + broken media.
    fired = {
        rule["rule_id"]
        for element in slop_state["elements"]
        for rule in element["rules_fired"]
    }
    assert "SLOP_PLACEHOLDER_TEXT" in fired
    assert "SLOP_BROKEN_MEDIA" in fired
    [badge] = [element for element in slop_state["elements"]
               if element["label"] == "Trust badge"]
    assert badge["evidence"]["response_status"] == 404
    [metadata] = [element for element in slop_state["elements"]
                  if element["label"] == "SEPTEMBER 9, 2026 - PRODUCT NEWS"]
    assert all(rule["rule_id"] != "SLOP_TEMPLATE_CHROME" for rule in metadata["rules_fired"])
    assert any(e["verdict"] == "slop" for e in slop_state["elements"])
    # The clean control is acquitted everywhere.
    assert clean_state["js_errors"] == []
    assert all(e["verdict"] == "clean" for e in clean_state["elements"])
    assert all(signal["severity"] == "info" for signal in clean_state["page_signals"])


async def _verify_baseline_labels(base_url):
    """Verify fixture geometry and reachability independently of the audit probes."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            await page.goto(base_url)
            assert await page.evaluate("""() => {
                const heading = getComputedStyle(document.querySelector('h1'));
                const body = getComputedStyle(document.querySelector('main p'));
                return heading.fontFamily === body.fontFamily &&
                    parseInt(heading.fontSize) > parseInt(body.fontSize) * 2 &&
                    Number(heading.fontWeight) > Number(body.fontWeight);
            }""")
            normal = await page.locator("#save").evaluate("el => getComputedStyle(el).backgroundColor")
            await page.goto(f"{base_url}/team")
            assert await page.locator("#save").inner_text() == "Save alert preferences"
            altered = await page.locator("#save").evaluate("el => getComputedStyle(el).backgroundColor")
            assert normal != altered
            await page.goto(f"{base_url}/editorial")
            assert await page.locator(".label").all_text_contents() == ["Release notes"] * 3
            await page.goto(f"{base_url}/layout")
            assert await page.evaluate("""() => {
                const [first, second] = Array.from(document.querySelectorAll('.layout article'));
                return first.offsetWidth > second.offsetWidth && second.offsetTop > first.offsetTop;
            }""")
            await page.goto(f"{base_url}/resources")
            assert await page.locator("#diagram").evaluate("el => el.complete && !el.naturalWidth")
            clipping = """el => {
                const right = el.getBoundingClientRect().right;
                const clip = el.parentElement.getBoundingClientRect().right;
                return right > clip && document.documentElement.scrollWidth === window.innerWidth;
            }"""
            await page.goto(f"{base_url}/setup")
            assert await page.locator("#activate").evaluate(clipping)
            await page.goto(f"{base_url}/account")
            assert not await page.locator("#download").is_visible()
            await page.get_by_text("Account actions").click()
            assert await page.locator("#download").is_visible()
            assert await page.locator("#download").evaluate(clipping)
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_desktop_known_answer_baseline(monkeypatch) -> None:
    _, events, snapshot = await _audit_fixture(
        monkeypatch, _BaselineHandler, desktop_scan=True, check_fixture=_verify_baseline_labels,
    )
    states = events["slop.state.result"]
    by_route = {urlsplit(state["url"]).path: state for state in states}
    assert set(by_route) == set(BASELINE_ROUTES)
    assert len(states) == len(by_route)
    assert {state["viewport"] for state in states} == {"desktop1280"}
    [coverage] = events["run.collection"]
    assert coverage["pages_recorded"] == len(BASELINE_ROUTES)
    assert coverage["pages_unverified"] == coverage["pages_pending"] == 0
    assert coverage["paths_activated"] == 0
    assert all(element["label"] != "Download last invoice"
               for element in by_route["/account"]["elements"])

    scored = []
    for case in BASELINE_CASES:
        state = by_route[case["route"]]
        observations = [
            {"rule": signal["rule_id"], "severity": signal["severity"], "scope": "page"}
            for signal in state["page_signals"]
            if signal["rule_id"] in case["rules"] and signal.get("scope") != "app"
            and (case["expected"] != "inconsistency"
                 or signal["detail"].startswith(f"{case['target']}:"))
        ] + [
            {"rule": signal["rule_id"], "severity": signal["severity"], "scope": "element"}
            for element in state["elements"] if element["label"] == case["target"]
            for signal in element["rules_fired"] if signal["rule_id"] in case["rules"]
        ]
        if case["state"] != "initial":
            result = "untested"
        elif case["expected"] == "clean":
            flagged = any(row["severity"] in {"minor", "severe"} for row in observations)
            result = "false_positive" if flagged else "true_negative"
        elif case["expected"] == "inconsistency":
            result = "review_only" if observations else "missed"
        else:
            located = any(row["scope"] == "element" for row in observations)
            result = "true_positive" if located else "missed"
        scored.append({**case, "result": result, "observations": observations})

    by_result = {row["route"]: row["result"] for row in scored}
    before = json.loads((FIXTURE_DIR / "slop_known_answer_before.json").read_text(encoding="utf-8"))
    assert set(by_result) == set(before["cases"])
    for route in ("/layout", "/team", "/resources", "/account"):
        assert by_result[route] == before["cases"][route]
    assert by_result["/"] == by_result["/editorial"] == "true_negative"
    assert by_result["/setup"] == "true_positive"
    assert {
        (row["route"], signal["rule"], signal["severity"])
        for row in scored if row["route"] in {"/", "/editorial"} for signal in row["observations"]
    } == {("/", "SLOP_DEFAULT_FONT", "info"), ("/editorial", "SLOP_TEMPLATE_CHROME", "info")}
    assert all("Display and body text" not in finding["detail"]
               for finding in snapshot["slop_entry_assessment"]["findings"])
    [action] = [element for element in by_route["/setup"]["elements"]
                if element["label"] == "Activate carrier integration"]
    assert action["evidence"]["label_clipped_horizontal_px"] > 2
    assert action["evidence"]["label_clipped_vertical_px"] == 0
    assert by_route["/setup"]["screenshot_artifact_id"]
    detected_clips = {
        (route, element["label"])
        for route, state in by_route.items() for element in state["elements"]
        if any(rule["rule_id"] == "SLOP_CLIPPED_CONTROL_LABEL" for rule in element["rules_fired"])
    }
    assert detected_clips == {("/setup", "Activate carrier integration")}
    counts = {outcome: sum(row["result"] == outcome for row in scored)
              for outcome in sorted(set(before["counts"]) | set(by_result.values()))}
    page_flags = {
        route: sorted({signal["rule_id"] for signal in state["page_signals"]
                       if signal["severity"] in {"minor", "severe", "review"}})
        for route, state in sorted(by_route.items())
    }
    print(json.dumps({
        "catalogue_version": states[0]["catalogue_version"],
        "viewport": "desktop1280", "measured_pages": coverage["pages_recorded"],
        "scored": scored, "counts": counts, "all_page_flags": page_flags,
        "held_out": sorted(HOLDOUT_ROUTES), "model_review": "disabled",
    }, sort_keys=True))


def test_replay_historical_slop_counts() -> None:
    fixture = FIXTURE_DIR / "slop_historical_replay.json"
    historical = json.loads(fixture.read_text(encoding="utf-8"))
    older = historical["MT-000199"]
    states = [{"elements": [{"verdict": verdict}
                            for verdict, count in counts.items() for _ in range(count)]}
              for counts in older["state_element_verdict_counts"]]
    assert len(states) == 52
    family = slop_family(states)
    assert {key: family[key] for key in older["reported"]} == older["reported"]
    later = historical["MT-000206"]
    assert later["entry"]["elements_judged"] == 259
    assert later["entry"]["findings_count"] == len(later["findings"]) == 3
    assert all(finding["viewports"] == later["entry"]["viewports"] for finding in later["findings"])


@pytest.mark.asyncio
async def test_desktop_cutoff_with_real_chromium_and_slow_review(monkeypatch) -> None:
    monkeypatch.setattr(slop_run, "DESKTOP_TARGET_SECONDS", 12)
    monkeypatch.setattr(slop_run, "DESKTOP_FINALIZATION_RESERVE_SECONDS", 2)
    review_started = asyncio.Event()

    async def stalled_review(*args, **kwargs):
        review_started.set()
        await asyncio.Event().wait()

    _, events, _ = await asyncio.wait_for(_audit_fixture(
        monkeypatch, _BaselineHandler, desktop_scan=True, review=stalled_review,
    ), timeout=20)
    assert review_started.is_set()
    [coverage] = events["run.collection"]
    assert coverage["partial"] and coverage["budget_exhausted"]
    assert coverage["visual_reviews_unfinished"] == 1
    assert coverage["pages_recorded"] == 1
    assert coverage["pages_pending"] == len(BASELINE_ROUTES) - 1
    assert not coverage["retired_lanes"]
    assert [urlsplit(state["url"]).path for state in events["slop.state.result"]] == ["/"]


# ---------------------------------------------------------------------------
# MT-000237 lane-wedge regression gate (Fix D).
#
# Everything below this line is an additive section: the new handler, the
# new audit helper and the new test. Nothing above this line is modified.
# ---------------------------------------------------------------------------

import socket

# The lane fixture runs under network_policy="public_only" against a
# public-style hostname, as production runs do. That shape has one hard
# consequence in the real policy stack: navigate() and the egress proxy
# resolve the hostname and reject any non-global address
# (browser/network.py resolve_and_validate_host), and the proxy dials the
# validated numeric IP. A hosts alias to 127.0.0.1 therefore CANNOT work —
# the run would die with unsafe_destination, not inspect pages. The
# smallest setup that satisfies the real validation is:
#   * the fixture hostname resolves (via the DNS shim below) to a global
#     unicast address, and
#   * that address is aliased onto the test machine's loopback, so the
#     proxy's dial lands on the in-process server (bound to 0.0.0.0).
# One-time machine setup (the test probes for it and skips with these
# instructions when absent):
#   Linux:   sudo ip addr add 93.184.216.34/32 dev lo
#            (plus a hosts entry is NOT needed — the shim below answers)
#   Windows: netsh interface ipv4 add address `
#              "Loopback Pseudo-Interface 1" 93.184.216.34 255.255.255.255
# The DNS shim patches only the stdlib resolver (socket.getaddrinfo) —
# the same infrastructure seam the suite already patches for egress DNS
# (test_pinned_egress.py) and the seam the MT-000237 prototype used.
# The browser, controller, policy, offsite supervisor, lane factory and
# pool are all the real production objects; nothing about them is mocked.
LANE_HOST = "fixture.test"
LANE_SUB_HOST = "sub.fixture.test"
LANE_ALIAS_IP = "93.184.216.34"

_REAL_GETADDRINFO = socket.getaddrinfo


def _lane_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """Resolve only the fixture hostnames; delegate everything else."""
    if host in (LANE_HOST, LANE_SUB_HOST):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (LANE_ALIAS_IP, port or 0))]
    return _REAL_GETADDRINFO(host, port, family, type, proto, flags)


# Twelve same-origin pages: the home page plus eleven content pages.
# /drift-post and /slow-challenge are linked first from home so they are
# claimed in the first wave, leaving every lane later claims to recover on.
LANE_CONTENT_ROUTES = {
    "/alpha": ("Alpha guide", "Alpha settings decide how delivery notices are grouped, "
               "when they are sent, and who receives them for each shipment."),
    "/bravo": ("Bravo guide", "Bravo settings decide how return labels are printed, "
               "which carriers collect parcels, and how refunds are announced."),
    "/charlie": ("Charlie guide", "Charlie settings control invoice timing, tax "
                 "documents, and the addresses printed on every billing page."),
    "/delta": ("Delta guide", "Delta settings manage warehouse hours, pickup "
               "windows, and the holidays when collections pause for the day."),
    "/echo": ("Echo guide", "Echo settings choose which events create an alert, "
              "how often digests are sent, and who can mute a noisy channel."),
    "/foxtrot": ("Foxtrot guide", "Foxtrot settings govern address books, saved "
                 "recipients, and the checks applied before a label is bought."),
    "/golf": ("Golf guide", "Golf settings describe packaging rules, weight "
              "limits, and the evidence required when a parcel arrives damaged."),
    "/hotel": ("Hotel guide", "Hotel settings list the integrations connected to "
               "this workspace and what each one is allowed to read or change."),
    "/india": ("India guide", "India settings record team roles, invitation "
               "rules, and the approvals needed before account details change."),
}
LANE_ROUTES = ["/", "/drift-post", "/slow-challenge", *LANE_CONTENT_ROUTES]

_LANE_FRAME_LOOP = """<script>
var t = performance.now();
while (performance.now() - t < 600000) { /* frame main thread busy */ }
</script>"""


def _lane_page(port: int, title: str, body: str, extra: str = "") -> bytes:
    links = "".join(
        f'<li><a href="{path}">{path}</a></li>' for path in LANE_ROUTES if path != "/"
    )
    html = f"""<!doctype html><html lang="en"><head><title>{title}</title>{extra}</head>
<body><main><h1>{title}</h1><p>{body}</p>
<button>Save {title} preferences</button>
<nav><ul>{links}</ul></nav></main></body></html>"""
    return html.encode()


class _LaneHandler(BaseHTTPRequestHandler):
    """The Fix D fixture site: twelve interlinked same-origin pages.

    /drift-post carries a form that auto-submits a POST to an
    off-allowlist host ~2 s after load — after the entry measurement
    has read the page, while the lane still rests on it (the
    prototype's test B2 timing). The browser route handler
    refuses a main-frame POST off the allowlist (BrowserActionBlockedError,
    browser/controller.py _route_request) and aborts the navigation, so
    the visiting lane's page comes to rest on the browser error page
    (chrome-error://chromewebdata/) — the exact resting state the
    MT-000237 prototype reproduced (its test B2, via an aborted GET
    redirect) and the state production lanes wedged on. The refusal
    happens before any offsite review, journey stop, or DNS lookup of
    the form's host, so the rest of the run is undisturbed.

    /slow-challenge embeds a captcha-titled iframe whose document
    busy-loops its main thread for ten minutes, so the sensitive
    challenge inspection (browser/auth_verifier.py) can never complete
    inside the run: every inspection of that page hits the 10-second
    bound. (A completed inspection of a non-provider captcha iframe
    would report an active challenge and start a human handoff; the
    loop is what keeps this page a stall, never a detection.)
    """

    def do_GET(self) -> None:  # noqa: N802
        route = urlsplit(self.path).path
        port = self.server.server_address[1]
        if route == "/sitemap.xml":
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.end_headers()
            self.wfile.write(b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>')
            return
        if route == "/captcha-frame":
            body = ("<!doctype html><html><head><title>challenge</title>"
                    + _LANE_FRAME_LOOP + "</head><body><p>challenge widget</p></body></html>")
            return self._send(body.encode())
        if route == "/":
            return self._send(_lane_page(
                port, "Lane fixture home",
                "This fixture exercises the four desktop lanes against a "
                "public-style origin, including one page that strands its "
                "lane on a browser error page and one whose challenge "
                "widget never answers."))
        if route == "/drift-post":
            form = (
                '<form id="driftform" method="POST" '
                f'action="http://{LANE_SUB_HOST}:{port}/collect">'
                '<input type="text" name="note" value="drift"></form>'
                "<script>setTimeout(function () { "
                "document.getElementById('driftform').submit(); }, 2000);</script>"
            )
            return self._send(_lane_page(
                port, "Drift post",
                "This page submits a form off the allowlist shortly after "
                "loading, which strands the visiting browser on an error "
                "page.", form))
        if route == "/slow-challenge":
            iframe = ('<iframe title="reCAPTCHA widget" src="/captcha-frame" '
                      'width="300" height="100"></iframe>')
            return self._send(_lane_page(
                port, "Slow challenge",
                "This page carries a challenge widget whose frame never "
                "finishes loading, so checking it always takes the full "
                "inspection bound.", iframe))
        page = LANE_CONTENT_ROUTES.get(route)
        if page is None:
            self.send_error(404)
            return
        title, text = page
        return self._send(_lane_page(port, title, text))

    def _send(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


async def _audit_lane_fixture(monkeypatch, handler):
    """_audit_fixture's shape, adapted for the lane-wedge gate.

    Deltas from _audit_fixture, each forced by the shape under test:
    * the server binds 0.0.0.0 so it answers on the loopback alias of
      LANE_ALIAS_IP (see the setup note above); a connect probe skips
      the test when the alias has not been configured on this machine.
    * socket.getaddrinfo is shimmed for the fixture hostnames only.
    * the request runs public_only on the fixture origin and sets
      runtime_human_assistance=True, because the challenge checkpoint
      only runs when authentication handlers are bound (MT-000237 ran
      with assistance on). Binding the handlers also binds the room
      lane's cooperative-pause handler, whose first step is a database
      poll for pause requests — the one handoff-path database touch
      that fires unconditionally and the one seam the fixture's mock
      session cannot serve. It is replaced with a no-op, exactly as
      this suite already replaces the other database seams
      (RunEventRepository, RunStateRepository, ExecutionRepository).
      The authentication handler, the challenge inspection, the
      controller, the policy and the lane factory stay fully real; no
      fixture page can complete a challenge detection (the slow page
      stalls forever, the others carry no challenge UI), so the human
      handoff itself never engages.
    """
    server = ThreadingHTTPServer(("0.0.0.0", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Probe with a real HTTP request, not a bare connect: an
    # intercepting egress proxy can accept a TCP connection to any
    # address, but only the alias serving THIS server returns the
    # fixture's home page.
    probe = socket.socket()
    probe.settimeout(3)
    try:
        probe.connect((LANE_ALIAS_IP, port))
        probe.sendall(b"GET / HTTP/1.0\r\nHost: fixture.test\r\n\r\n")
        response = b""
        # Read until the marker itself arrives, not just the header
        # terminator: on Windows the headers and body can land in
        # separate TCP segments, and stopping at \r\n\r\n would check
        # for the marker in a headers-only buffer and skip spuriously.
        while b"Lane fixture home" not in response and len(response) < 65536:
            chunk = probe.recv(4096)
            if not chunk:
                break
            response += chunk
        alias_ready = b"Lane fixture home" in response
    except OSError:
        alias_ready = False
    finally:
        probe.close()
    if not alias_ready:
        server.shutdown()
        server.server_close()
        pytest.skip(
            f"lane fixture alias {LANE_ALIAS_IP} is not routed to this "
            "machine's loopback; configure it once (Linux: sudo ip addr "
            f"add {LANE_ALIAS_IP}/32 dev lo; Windows: netsh interface "
            f"ipv4 add address \"Loopback Pseudo-Interface 1\" "
            f"{LANE_ALIAS_IP} 255.255.255.255) so the public_only "
            "fixture hostname resolves to a global address the egress "
            "proxy may dial."
        )
    monkeypatch.setattr(socket, "getaddrinfo", _lane_getaddrinfo)
    events: dict[str, list[dict]] = {}

    class _Events:
        def __init__(self, session):
            pass

        async def create(self, **kwargs):
            events.setdefault(kwargs["event_type"], []).append(kwargs["payload"])

    completed: list[bool] = []

    class _States:
        def __init__(self, session):
            pass

        async def mark_running(self, **kwargs):
            return None

        async def mark_completed(self, **kwargs):
            completed.append(True)

        # _audit_fixture's double omits these; a zero-evidence lane run
        # takes the publication failure branch, and recording the call
        # (instead of AttributeError) keeps that failure legible — the
        # helper's completed == [True] assertion then reports it.
        async def mark_failed(self, **kwargs):
            completed.append(False)

        async def mark_cancelled(self, **kwargs):
            completed.append(False)

    monkeypatch.setattr(slop_run, "RunEventRepository", _Events)
    monkeypatch.setattr(
        "markettwin_execution_orchestrator.persistence.run_state_repository.RunStateRepository",
        _States,
    )
    monkeypatch.setattr(
        slop_run, "ExecutionRepository",
        lambda _: Mock(
            create_agent_execution=AsyncMock(),
            create_browser_session=AsyncMock(),
            mark_browser_session_closed=AsyncMock(),
            finish_agent_execution=AsyncMock(),
        ),
    )
    monkeypatch.setattr(slop_run, "cooperative_pause_checkpoint", AsyncMock(return_value=None))
    run_id = uuid4()
    run = TestRun(id=run_id, configuration_snapshot={})
    monkeypatch.setattr(slop_run, "review_screenshots", AsyncMock(return_value=[]))
    monkeypatch.setattr(slop_run, "review_checkpoint", AsyncMock(
        return_value={"decision": "continue", "reason": "Lane fixture"},
    ))

    async def save_screenshot(state, **kwargs):
        assert Path(state["screenshot_path"]).is_file()
        state["screenshot_artifact_id"] = str(uuid4())

    monkeypatch.setattr(slop_run, "save_state_evidence", save_screenshot)
    session = Mock()
    session.get = AsyncMock(return_value=run)
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    base_url = f"http://{LANE_HOST}:{port}"
    request = SimpleNamespace(
        run_id=run_id,
        start_url=f"{base_url}/",
        allowed_origins=(AllowedOrigin("http", LANE_HOST, port),),
        network_policy="public_only",
        study_brief="Audit the lane fixture UI",
        runtime_human_assistance=True,
    )
    try:
        await slop_run.execute_slop_run(request=request, session=session, desktop_scan=True)
    finally:
        server.shutdown()
        server.server_close()
    assert completed == [True]
    return base_url, events, run.configuration_snapshot


@pytest.mark.asyncio
async def test_all_four_lanes_keep_inspecting_after_error_page_rest(monkeypatch) -> None:
    """MT-000237 regression gate: a bad resting page must not wedge a lane.

    What it proves (post-fix): all four desktop lanes keep inspecting
    after one lane's page comes to rest on a browser error page and
    another page's challenge inspection stalls past its 10-second
    bound. The self-heal in the controller pre-flight (Fix B) lets the
    stranded lane navigate again; the challenge-timeout change
    (Fix C) keeps the stalled page from failing every later claim.

    Expected PRE-FIX failure signature (this test must fail on the
    code that ran MT-000237, for these reasons):
    * the lane that visited /drift-post rests on
      chrome-error://chromewebdata/ and every later claim it pulls is
      recorded attempted-failed with policy_code "target_url" — the
      zero-target_url assertion and the drift-lane-recovery assertion
      fail, and pages it pulled stay unverified;
    * the lane that visited /slow-challenge fails that claim at the
      10-second challenge bound (~10 s, recorded as a load failure),
      /slow-challenge stays unverified, and any later claim that lane
      pulls fails the same way at the resting page's pre-flight — in
      the observed pre-fix runs the healthy lanes drained the queue
      first, so the slow lane's repeat failures are bounded by
      scheduling; the per-lane slow-failure budget below is the
      post-fix guard that the timeout can never *keep* failing
      claims, and the coverage assertions fail either way.
    """
    _, events, _ = await _audit_lane_fixture(monkeypatch, _LaneHandler)
    published = events["slop.state.result"]
    checkpoint_states = [
        state
        for payload in events["slop.page.checkpoint"]
        for state in payload["states"]
    ]
    inspected = events["slop.page.inspected"]
    [coverage] = events["run.collection"]

    # Every page on the site was recorded; nothing left pending or
    # unverified, and no lane was retired.
    assert coverage["pages_recorded"] == len(LANE_ROUTES)
    assert coverage["pages_unverified"] == 0
    assert coverage["pages_pending"] == 0
    assert not coverage["retired_lanes"]

    # Every one of the four lanes measured at least one page.
    measured_lanes = {
        event["lane_id"] for event in inspected if event["outcome"] == "measured"
    }
    assert measured_lanes == {0, 1, 2, 3}

    # No state anywhere carries the MT-000237 policy code. Every claim
    # in this run is a same-origin URL, so any "target_url" state is
    # the wedge firing on a legal claim.
    assert not [
        state for state in checkpoint_states if state.get("policy_code") == "target_url"
    ]
    assert not [
        state for state in published if state.get("policy_code") == "target_url"
    ]

    # The lane that visited /drift-post went on to measure a later
    # same-origin page: the error-page rest did not end its run.
    [drift] = [
        event for event in inspected
        if urlsplit(event["url"]).path == "/drift-post"
    ]
    assert any(
        event["lane_id"] == drift["lane_id"]
        and event["claim_seq"] > drift["claim_seq"]
        and event["outcome"] == "measured"
        and urlsplit(event["url"]).path != "/drift-post"
        for event in inspected
    )

    # The slow-challenge page itself was measured (post-Fix C the
    # timed-out inspection counts as "no challenge"), and the
    # challenge timeout never *fails* more than one claim per lane:
    # count each lane's failed states whose duration carries the
    # ~10-second timeout signature.
    [slow] = [
        event for event in inspected
        if urlsplit(event["url"]).path == "/slow-challenge"
    ]
    assert slow["outcome"] == "measured"
    failed = [
        state for state in checkpoint_states
        if state.get("failure_site")
        or any(
            signal.get("rule_id") == "UI_STATE_UNASSESSED"
            and str(signal.get("detail", "")).startswith("Page could not be loaded")
            for signal in state.get("page_signals", [])
        )
    ]
    slow_failures: dict[int, int] = {}
    for state in failed:
        if "finished_at" in state and "claimed_at" in state:
            if state["finished_at"] - state["claimed_at"] >= 9:
                slow_failures[state["lane_id"]] = slow_failures.get(state["lane_id"], 0) + 1
    assert all(count <= 1 for count in slow_failures.values()), slow_failures
