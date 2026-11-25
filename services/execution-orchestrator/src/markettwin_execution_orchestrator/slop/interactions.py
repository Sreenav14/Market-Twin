"""Explore explicit UI disclosures with replayable paths and bounded work."""

import hashlib
import asyncio
import json
import re
import time
from urllib.parse import urlsplit

from markettwin_execution_orchestrator.browser.errors import BrowserPolicyError, BrowserActionError, BrowserActionBlockedError
from markettwin_execution_orchestrator.slop.evidence import retain_finding_evidence
from markettwin_execution_orchestrator.slop.measure import measure_state
from markettwin_execution_orchestrator.slop.probe import non_html_type
from markettwin_execution_orchestrator.slop.visual_review import review_screenshots
from markettwin_execution_orchestrator.workflow.harness_state import canonical_url


def audit_url(url: str) -> str:
    """Preserve hash-router screens while merging ordinary page anchors."""
    fragment = urlsplit(url).fragment
    return canonical_url(url) + ("#" + fragment if fragment.startswith(("/", "!")) else "")


_CHROME_REGIONS = {"header", "footer", "nav"}

# Speed S0 (doc 18 section 6.2): new-state screenshots are reviewed in
# batches of at most this many states per vision call.
VISION_BATCH_MAX = 8

_CONSENT_NAME = re.compile(r"cookie|consent|do not sell", re.IGNORECASE)
_CONSENT_OPENER = re.compile(
    r"^(manage|customi[sz]e|set|edit|open)\b.{0,30}(cookie|consent|preference|privacy|choices)",
    re.IGNORECASE)
_CONSENT_DISMISS = re.compile(
    r"^(accept|reject|allow|decline|deny|dismiss|close|ok|got it|i agree|agree)"
    r"( all)?( cookies?| consent)?$", re.IGNORECASE)
_CONSENT_CATEGORY = re.compile(
    r"^(strictly necessary|necessary|essential|functional|performance|analytics|"
    r"targeting|advertising|marketing|personalisation|personalization)"
    r"( cookies?)?$", re.IGNORECASE)


def _consent_cluster(targets):
    """The controls of a cookie-consent overlay, if one is present.

    Detection uses the overlay's own vocabulary, never a site name: a
    control naming cookies or consent anchors the cluster; generic
    accept/reject wording and the standard consent-category names join
    it only when such an anchor exists, so an ordinary product control
    that happens to be named e.g. Accept is never chrome on its own."""
    if not any(_CONSENT_NAME.search(target["name"]) for target in targets):
        return []
    return [target for target in targets
            if _CONSENT_NAME.search(target["name"])
            or _CONSENT_OPENER.search(target["name"])
            or _CONSENT_DISMISS.match(target["name"].strip())
            or _CONSENT_CATEGORY.match(target["name"].strip())]


def _consent_dismissal(cluster):
    """The cluster's standard accept/reject control, if it has one.
    Preference/settings openers are never a dismissal: the anchored
    pattern only matches accept/reject-style names."""
    for target in cluster:
        if _CONSENT_DISMISS.match(target["name"].strip()):
            return target
    return None


def view_fingerprint(probe: dict) -> str:
    """Identity of a view: where it is + what can be acted on inside its
    content. Chrome (header/footer/nav) never contributes — a menu
    opening there cannot mint a view. Text contributes structure only
    (tag/role), never its wording, so rotating headlines and banners do
    not mint views either. Measuring still uses the full probe; this
    function is identity only."""
    elements = probe.get("elements", [])
    content = [e for e in elements if e.get("region") not in _CHROME_REGIONS]
    if not content:
        content = list(elements)
    identity = []
    for element in content:
        if element.get("kind") == "interactive":
            identity.append(("i", element.get("tag"), element.get("role"),
                             element.get("name"), bool(element.get("disabled")),
                             element.get("selected"), element.get("expanded"),
                             element.get("invalid")))
        else:
            identity.append(("t", element.get("tag"), element.get("role")))
    identity.sort(key=repr)
    payload = {"url": audit_url(str(probe.get("url") or "")),
               "elements": identity}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


async def inspect_interactions(*, controller, handle, url: str, viewport: str,
                               deadline: float = float("inf"),
                               page_ready: bool = False, checkpoint=None, on_progress=None, on_state=None,
                               known_fingerprints=(), capture=None):
    capture = capture or controller.capture_evidence_screenshot
    root_targets = await controller.ui_state_targets(session_id=handle.session_id)
    active_path = () if page_ready else None
    seen_paths = set()
    seen_states = set(known_fingerprints)
    states, links, skipped = [], [], []
    review_batch: list = []
    consent = _consent_cluster(root_targets)
    consent_keys = {(target["role"], target["name"]) for target in consent}
    if consent:
        # A cookie-consent overlay is site chrome, like the header or
        # footer: dismiss it once through its standard accept/reject
        # control when it has one, and never explore its inner controls
        # (preference toggles, category switches) as product UI.
        # MT-000150 died inside such a preferences centre.
        dismissal = _consent_dismissal(consent) if page_ready else None
        if dismissal is not None:
            try:
                preflight = getattr(controller, "inspect_click_approval", None)
                if callable(preflight):
                    try:
                        intent = await preflight(session_id=handle.session_id,
                            execution_id=handle.execution_id, journey_id=handle.journey_id, **dismissal)
                    except BrowserActionBlockedError:
                        intent = True
                    if intent is not None:
                        raise BrowserActionError("Consent dismissal requires approval; not exercised by UI audit.",
                                                 reason_code="approval_required")
                await controller.click(session_id=handle.session_id,
                    execution_id=handle.execution_id, journey_id=handle.journey_id,
                    observe=False, **dismissal)
                root_targets = await controller.ui_state_targets(session_id=handle.session_id)
                consent_keys |= {(target["role"], target["name"])
                                 for target in _consent_cluster(root_targets)}
                skipped.append({'state': 'Cookie consent', 'reason':
                    f'Consent overlay dismissed via "{dismissal["name"]}"; its controls are site chrome, not product UI.'})
            except BrowserActionError as error:
                skipped.append({'state': 'Cookie consent', 'reason':
                    f'Consent overlay could not be dismissed ({error.reason_code}); its controls were not explored as product UI.'})
        else:
            skipped.append({'state': 'Cookie consent', 'reason':
                'Consent overlay controls were not explored as product UI (site chrome).'})
        root_targets = [target for target in root_targets
                        if (target["role"], target["name"]) not in consent_keys]
    pending = [[target] for target in root_targets]
    active_targets = root_targets
    stopped = False
    last_actual_url = url
    last_reviewed = 0
    classified = 0
    last_checkpoint_classified = 0
    last_checkpoint_attempted = 0
    last_checkpoint_productive = 0
    started_at = time.monotonic()
    target_failures: dict = {}
    root_failures: dict = {}
    while pending and time.monotonic() < deadline:
        if checkpoint is not None and len(seen_paths) - last_reviewed >= 15:
            last_reviewed = len(seen_paths)
            routes_found = len(set(links))
            productive = len(states) + routes_found
            review = await checkpoint({"url": url, "current_url": last_actual_url,
                "viewport": viewport,
                "paths_attempted": len(seen_paths), "unique_states": len(states),
                "pending_paths": len(pending), "skipped": skipped[-5:],
                "checked_items": classified,
                "checked_delta": classified - last_checkpoint_classified,
                "attempted_delta": len(seen_paths) - last_checkpoint_attempted,
                "states_measured": len(states),
                "routes_discovered": routes_found,
                "productive_delta": productive - last_checkpoint_productive,
                "elapsed_seconds": round(time.monotonic() - started_at, 1)})
            last_checkpoint_classified = classified
            last_checkpoint_attempted = len(seen_paths)
            last_checkpoint_productive = productive
            if review["decision"] == "stop":
                skipped.append({'state': 'Lead checkpoint', 'reason': review['reason']})
                stopped = True
                break
        path = pending.pop(0)
        key = tuple((target['role'], target['name']) for target in path)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        label = ' → '.join(target['name'] for target in path)
        if target_failures.get(key[-1], 0) >= 2:
            skipped.append({'state': label, 'reason':
                'Control could not be activated on two earlier attempts; it was not retried.'})
            continue
        if len(key) > 1 and root_failures.get(key[0], 0) >= 5:
            skipped.append({'state': label, 'reason':
                'Five controls in this group already failed to activate; the rest of the group was not retried.'})
            continue
        outcome = "observed"
        try:
            # Only a child of the current state can be entered without reset.
            # Siblings must start clean: toggling back is not a reliable undo.
            if active_path is not None and key[:-1] == active_path:
                replay = path[-1:]
                before_targets = active_targets
            else:
                await controller.navigate(session_id=handle.session_id, url=url,
                                          observe=False)
                replay = path
                for target in replay[:-1]:
                    if time.monotonic() >= deadline:
                        raise TimeoutError
                    await controller.click(session_id=handle.session_id,
                        execution_id=handle.execution_id, journey_id=handle.journey_id,
                        observe=False, **target)
                before_targets = (await controller.ui_state_targets(session_id=handle.session_id)
                                  if len(replay) > 1 else root_targets)
                replay = replay[-1:]
            before = {(target['role'], target['name']) for target in before_targets}
            for target in replay:
                if time.monotonic() >= deadline:
                    raise TimeoutError
                # Identify sensitive controls without dispatching their action.
                preflight = getattr(controller, "inspect_click_approval", None)
                if callable(preflight):
                    try:
                        intent = await preflight(session_id=handle.session_id,
                            execution_id=handle.execution_id, journey_id=handle.journey_id, **target)
                    except BrowserActionBlockedError:
                        intent = True
                    if intent is not None:
                        raise BrowserActionError("Control requires approval; not exercised by UI audit.",
                                                 reason_code="approval_required")
                await controller.click(session_id=handle.session_id, execution_id=handle.execution_id,
                    journey_id=handle.journey_id, observe=False, **target)
            active_path = key
            probe = await controller.probe_page(session_id=handle.session_id)
            if non_html_type(probe):
                skipped.append({"state": label, "reason": "Control reached a non-HTML document."})
                active_path = None
                continue
            active_targets = await controller.ui_state_targets(session_id=handle.session_id)
            last_actual_url = str(probe.get('url') or url)
            # Duplicate presentation can still expose a different navigation link.
            links.extend(await controller.page_links(session_id=handle.session_id))
            if audit_url(last_actual_url) != audit_url(url):
                # The click navigated. That is a route discovery, not a
                # state of this page: the landed page's links were
                # harvested above, nothing is minted or measured, and
                # the next path restarts from this page.
                outcome = "navigated"
                active_path = None
                continue
            fingerprint = view_fingerprint(probe)
            if fingerprint in seen_states:
                outcome = "duplicate_state"
                # A duplicate view can still reveal controls that were
                # not visible before it (an opened menu's items). Their
                # outcomes are unknown, so they join the traversal queue
                # even though the view itself is not new.
                children = [target for target in active_targets
                            if (target['role'], target['name']) not in before
                            and (target['role'], target['name']) not in key
                            and (target['role'], target['name']) not in consent_keys]
                pending[0:0] = [path + [target] for target in children]
                continue
            seen_states.add(fingerprint)
            measured = measure_state(probe)
            measured.update(viewport=viewport, interaction_path=label, js_errors=[])
            measured['screenshot_path'] = await capture(
                session_id=handle.session_id)
            states.append(measured)
            review_batch.append(measured)
            targets = active_targets
            children = [target for target in targets
                        if (target['role'], target['name']) not in before
                        and (target['role'], target['name']) not in key
                        and (target['role'], target['name']) not in consent_keys]
            pending[0:0] = [path + [target] for target in children]
        except TimeoutError:
            skipped.append({'state': label, 'reason': 'State time budget reached.'})
            break
        except BrowserPolicyError:
            skipped.append({'state': label, 'reason': 'Browser policy blocked this state; traversal stopped.'})
            stopped = True
            break
        except BrowserActionError as error:
            active_path = None
            target_failures[key[-1]] = target_failures.get(key[-1], 0) + 1
            root_failures[key[0]] = root_failures.get(key[0], 0) + 1
            skipped.append({'state': label, 'reason':
                f'Control could not be resolved or activated ({error.reason_code}). '
                'Other states and pages will still be inspected.'})
            continue
        except BaseException as error:
            outcome = f"interrupted:{type(error).__name__}"
            raise
        finally:
            if not outcome.startswith("interrupted:"):
                classified += 1
            if on_progress is not None:
                await on_progress({"url": url, "actual_url": last_actual_url,
                    "viewport": viewport, "path": label,
                    "paths_attempted": len(seen_paths), "unique_states": len(states),
                    "pending_paths": len(pending), "stopped": stopped,
                    "result": next((entry['reason'] for entry in reversed(skipped)
                                    if entry['state'] == label), outcome),
                    "screenshot_artifact_id": states[-1].get('screenshot_artifact_id')
                        if states and states[-1].get('interaction_path') == label else None})
    # Speed S0 (doc 18 section 6.2): one vision call per chunk of at most
    # VISION_BATCH_MAX states, in discovery order; a chunk's findings are
    # attached to its first state (the per-state attachment this replaces).
    # Every state in the chunk is sent — batching never reuses one state's
    # verdict for another (doc 13 section 3.5). A chunk the traversal
    # budget never reaches leaves each of its states with the named
    # unassessed signal instead of silence.
    for start in range(0, len(review_batch), VISION_BATCH_MAX):
        chunk = review_batch[start:start + VISION_BATCH_MAX]
        findings = None
        if time.monotonic() < deadline:
            try:
                async with asyncio.timeout(max(0.01, deadline - time.monotonic())):
                    findings = await review_screenshots(chunk)
            except TimeoutError:
                findings = None
        if findings is None:
            for state in chunk:
                state['page_signals'].append({
                    "rule_id": "UI_VISUAL_UNASSESSED", "severity": "info",
                    "detail": "Batched visual review was not reached before "
                              "the traversal budget expired."})
        else:
            chunk[0]['page_signals'].extend(findings)
        if on_state is not None:
            await retain_finding_evidence(chunk, findings or [], on_state)
    skipped.extend({'state': ' → '.join(t['name'] for t in path), 'reason': 'Not inspected: traversal ended before this path was attempted.'}
                   for path in pending)
    return states, list(dict.fromkeys(links)), skipped, stopped
