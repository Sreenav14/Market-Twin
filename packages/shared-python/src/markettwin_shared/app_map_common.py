"""Shared helpers for application maps (Phase 1a, doc 14 section 4).

Pure functions only: no I/O, no model clients. Imported by control-api
(census, snapshot) and available to the execution orchestrator later.

``canonical_url`` is a faithful port of the orchestrator's
``workflow/harness_state.py`` ``canonical_url``. Decision D6 (doc 14
section 16) is incumbent-wins: persisted ``state_id`` values are computed
from the orchestrator function, so this implementation must agree with
it exactly. Where doc 14 section 4.1's printed rules differ from the
incumbent -- the incumbent does not collapse runs of ``/`` in the path
and does not drop tracking parameters from the query -- the incumbent
behaviour is adopted here; the differences are listed in the Phase 1a
build report. ``TRACKING_PARAMS`` is still exported with the exact set
from section 4.1 for callers that need the list itself.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

__all__ = [
    "EXPECTATION_GATE_RULE_ID",
    "FRESHNESS_OUTCOMES",
    "GATE_COVERAGE_THRESHOLD",
    "GATE_RULE_ID",
    "HARVEST_COVERAGE_THRESHOLD",
    "HARVEST_GATE_RULE_ID",
    "LOGIN_SEGMENTS",
    "MAP_TTL_TRUST_DAYS",
    "NAMED_STATUSES",
    "ORACLE_SOURCES",
    "REACHABLE_STATUSES",
    "TRACKING_PARAMS",
    "VERDICT_ORACLE_SOURCES",
    "WALL_TEXT_MARKERS",
    "ExpectationGateResult",
    "GateResult",
    "HarvestGateResult",
    "SKILL_LIFECYCLE_STATES",
    "SKILL_LIFECYCLE_TRANSITIONS",
    "canonical_url",
    "check_skill_transition",
    "compute_expectation_gate",
    "compute_harvest_gate",
    "compute_inventory_gate",
    "expectation_coverage",
    "expectation_verdict_eligible",
    "fingerprint_tuple",
    "has_wall_markers",
    "is_login_path",
    "map_legacy_lifecycle_status",
    "parse_screenshot_phash",
    "route_pattern_for",
    "skill_currency_check",
    "state_fingerprint",
]

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "msclkid",
    "ref",
    "mc_cid",
    "mc_eid",
}

LOGIN_SEGMENTS = {"login", "log-in", "signin", "sign-in", "sso", "auth"}

WALL_TEXT_MARKERS = (
    "captcha",
    "are you a robot",
    "verify you are human",
    "checking your browser",
    "just a moment",
    "attention required",
    "datadome",
    "incapsula",
    "perimeterx",
    "human verification",
)


def canonical_url(url: str) -> str:
    """Normalise a URL for map/state identity: no fragment, sorted query.

    Byte-for-byte port of ``workflow/harness_state.py``'s ``canonical_url``
    (decision D6, incumbent wins). Lowercases scheme and host, drops the
    port iff it is the scheme default, drops the fragment, strips trailing
    slashes from a non-root path, and sorts query pairs by (key, value)
    keeping blank values.
    """

    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    default_port = {"http": 80, "https": 443}.get(parsed.scheme.lower())
    netloc = host if port is None or port == default_port else f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunsplit((parsed.scheme.lower(), netloc, path, query, ""))


_UUID_SEGMENT = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_FULL_DATE_SEGMENT = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YEAR_SEGMENT = re.compile(r"^\d{4}$")
_MONTH_DAY_SEGMENT = re.compile(r"^\d{1,2}$")
_LONG_HEX_SEGMENT = re.compile(r"^[0-9a-fA-F]{16,}$")
_SHORT_HEX_SEGMENT = re.compile(r"^[0-9a-fA-F]{8}$")
_SLUG_SEGMENT = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-\d+$")
_DIGITS_SEGMENT = re.compile(r"^\d+$")


def _pattern_segment(segment: str, *, previous_was_year: bool) -> tuple[str, bool]:
    """Return (pattern segment, this segment is a bare year) for one segment."""

    if not segment:
        return segment, False
    if _UUID_SEGMENT.match(segment):
        return "{uuid}", False
    if _FULL_DATE_SEGMENT.match(segment):
        return "{date}", False
    if _YEAR_SEGMENT.match(segment):
        return "{date}", True
    if _LONG_HEX_SEGMENT.match(segment):
        return "{id}", False
    if (
        _SHORT_HEX_SEGMENT.match(segment)
        and any(char.isdigit() for char in segment)
        and any(char in "abcdefABCDEF" for char in segment)
    ):
        return "{id}", False
    if _SLUG_SEGMENT.match(segment):
        return "{slug}", False
    if _DIGITS_SEGMENT.match(segment):
        # A 1-2 digit segment immediately after a year segment is the
        # month (or day) of a date path, not an id: /2024/11/report
        # patterns as /{date}/11/report (doc 14 section 4.2 vectors).
        if previous_was_year and _MONTH_DAY_SEGMENT.match(segment):
            return segment, False
        return "{id}", False
    return segment, False


def route_pattern_for(canonical_url_or_path: str) -> str:
    """Reduce a canonical URL (or bare path) to its route pattern.

    Query and fragment are ignored. Variable segments become ``{id}``,
    ``{uuid}``, ``{date}`` or ``{slug}`` per doc 14 section 4.2; every
    other segment stays literal. The root path patterns as ``/``.
    """

    value = canonical_url_or_path
    if "://" in value:
        path = urlsplit(value).path
    else:
        path = value.split("#", 1)[0].split("?", 1)[0]
    if not path:
        path = "/"
    patterned: list[str] = []
    previous_was_year = False
    for segment in path.split("/"):
        replacement, previous_was_year = _pattern_segment(
            segment, previous_was_year=previous_was_year
        )
        patterned.append(replacement)
    return "/".join(patterned)


def _path_of(url: str) -> str:
    if "://" in url:
        return urlsplit(url).path
    return url.split("#", 1)[0].split("?", 1)[0]


def is_login_path(url: str) -> bool:
    """True iff any path segment, lowercased, is a known login segment.

    Segment match, not substring: ``/login-help`` is one segment
    (``login-help``) and is not a login path.
    """

    segments = {segment.lower() for segment in _path_of(url).split("/") if segment}
    return bool(segments & LOGIN_SEGMENTS)


def has_wall_markers(body_text_lower: str) -> bool:
    """True iff the body text carries a bot-wall / checkpoint marker.

    The census passes already-lowercased text; the scan lowercases again
    so the check is case-insensitive regardless of the caller.
    """

    text = body_text_lower.lower()
    return any(marker in text for marker in WALL_TEXT_MARKERS)
# --- Phase 1b: oracle taxonomy + harvest gate (doc 16 sections 5.9, 18-D14) ---

ORACLE_SOURCES = ("documentation", "owner-rule", "observation", "model-draft")

HARVEST_GATE_RULE_ID = "harvest-1b.1"
HARVEST_COVERAGE_THRESHOLD = 0.98  # [J] research section 6.5 starting value


@dataclass(frozen=True)
class HarvestGateResult:
    """The harvest gate's verdict (doc 16 section 5.9).

    ``release_state`` is ``'partial'`` on every path: this function has
    no route to ``'trusted'`` (spec C6), and a failed harvest leaves the
    map's census release standing at ``partial`` / ``inventory``.
    """

    harvest_status: str  # 'ready' | 'partial' | 'failed'
    failure_code: str | None  # 'harvest_empty' | 'harvest_incomplete_accounting'
    failure_message: str | None
    release_state: str  # always 'partial'
    release_scope: str  # 'harvest' | 'inventory'
    coverage: float
    reachable: int
    visited: int
    blocked: int
    failed: int
    unprobed_budget: int
    pending: int
    enriched_groups: int
    template_groups: int
    spend_calls: int
    spend_tokens: int
    skill_gate: str | None  # 'failed' when no verified skill releases the scope
    skill_gate_reason: str | None

    def metrics(self) -> dict[str, object]:
        """The gate_metrics block of doc 16 section 5.9."""
        block: dict[str, object] = {
            "harvest_rule": HARVEST_GATE_RULE_ID,
            "reachable": self.reachable,
            "visited": self.visited,
            "blocked": self.blocked,
            "failed": self.failed,
            "unprobed_budget": self.unprobed_budget,
            "harvest_coverage": round(self.coverage, 4),
            "enriched_groups": self.enriched_groups,
            "template_groups": self.template_groups,
            "spend_calls": self.spend_calls,
            "spend_tokens": self.spend_tokens,
        }
        if self.skill_gate is not None:
            block["skill_gate"] = self.skill_gate
            block["skill_gate_reason"] = self.skill_gate_reason
        return block


def compute_harvest_gate(counts: Mapping[str, object]) -> HarvestGateResult:
    """Pure harvest gate over counts (doc 16 section 5.9, rules in order).

    ``counts`` keys: ``reachable``, ``visited``, ``blocked_auth``,
    ``blocked_wall``, ``failed``, ``unprobed_budget``, ``pending``,
    ``enriched_groups``, ``template_groups``, ``spend_calls``,
    ``spend_tokens`` (ints), ``skill_verified`` (bool) and
    ``skill_reason`` (str | None — why no verified skill exists, when
    known). One implementation for the worker (which applies it) and
    control-api's repository (which delegates to it): the rule set
    cannot drift between the applier and the tests that pin it.
    """

    def count(key: str) -> int:
        value = counts.get(key, 0)
        return value if isinstance(value, int) else 0

    reachable = count("reachable")
    visited = count("visited")
    blocked = count("blocked_auth") + count("blocked_wall")
    failed = count("failed")
    unprobed_budget = count("unprobed_budget")
    pending = count("pending")
    coverage = visited / reachable if reachable else 0.0
    skill_verified = counts.get("skill_verified") is True
    skill_reason = counts.get("skill_reason")
    if not isinstance(skill_reason, str) or not skill_reason:
        skill_reason = None

    failure_code: str | None = None
    failure_message: str | None = None
    if visited == 0:
        harvest_status = "failed"
        failure_code = "harvest_empty"
        failure_message = "harvest visited no reachable page"
    elif pending > 0:
        harvest_status = "failed"
        failure_code = "harvest_incomplete_accounting"
        failure_message = (
            f"harvest ended with {pending} reachable page(s) still pending "
            "and unnamed by a disposition"
        )
    elif coverage < HARVEST_COVERAGE_THRESHOLD:
        harvest_status = "partial"
    else:
        harvest_status = "ready"

    if harvest_status in ("ready", "partial") and skill_verified:
        release_scope = "harvest"
        skill_gate = None
        skill_gate_reason = None
    else:
        release_scope = "inventory"
        skill_gate = "failed"
        skill_gate_reason = skill_reason or "no_verified_skill"

    return HarvestGateResult(
        harvest_status=harvest_status,
        failure_code=failure_code,
        failure_message=failure_message,
        release_state="partial",
        release_scope=release_scope,
        coverage=coverage,
        reachable=reachable,
        visited=visited,
        blocked=blocked,
        failed=failed,
        unprobed_budget=unprobed_budget,
        pending=pending,
        enriched_groups=count("enriched_groups"),
        template_groups=count("template_groups"),
        spend_calls=count("spend_calls"),
        spend_tokens=count("spend_tokens"),
        skill_gate=skill_gate,
        skill_gate_reason=skill_gate_reason,
    )


# --- Phase 1a inventory gate (doc 14 section 7) ---------------------------
# Moved here from control-api's map_repository in Phase 4 (doc 23
# section 6.6): the freshness reconcile applies the same gate from the
# orchestrator, and there is exactly ONE implementation (doc 16 D14).
# map_repository re-exports both names for its incumbent callers.

GATE_RULE_ID = "inventory-1a.1"
GATE_COVERAGE_THRESHOLD = 0.98  # [J] research section 6.5 starting value (doc 14 section 7)

REACHABLE_STATUSES = ("fetch_ok", "redirect")
NAMED_STATUSES = ("blocked_auth", "blocked_wall", "gone", "fetch_error", "out_of_scope")


@dataclass(frozen=True)
class GateResult:
    """The inventory gate's verdict. ``release_state`` is never ``'trusted'``
    in Phase 1a: no code path in this module can produce it (spec C6)."""

    status: str  # 'ready' | 'failed'
    release_state: str  # 'partial' | 'failed'
    release_scope: str | None  # 'inventory' on release, NULL on failure
    failure_code: str | None
    failure_message: str | None
    expected: int
    reachable: int
    named: int
    incomplete: int
    coverage: float

    def metrics(self) -> dict[str, object]:
        return {
            "rule": GATE_RULE_ID,
            "expected": self.expected,
            "reachable": self.reachable,
            "named": self.named,
            "incomplete": self.incomplete,
            "coverage": round(self.coverage, 4),
        }


def compute_inventory_gate(counts: Mapping[str, int], overflow_count: int) -> GateResult:
    """Pure gate over disposition counts (doc 14 section 7).

    ``counts`` maps crawl_status -> row count for one map. Overflow URLs were
    cut from the denominator before rowing (section 6.3), so they join the
    incomplete count and widen the coverage denominator: a truncated census
    cannot release above its honesty (section 6.3, test T-C12).
    """
    expected = sum(counts.values())
    reachable = sum(counts.get(status, 0) for status in REACHABLE_STATUSES)
    named = sum(counts.get(status, 0) for status in NAMED_STATUSES)
    incomplete = counts.get("census_incomplete", 0) + overflow_count
    denominator = expected + overflow_count
    coverage = (reachable + named) / denominator if denominator else 0.0
    if expected == 0:
        return GateResult(
            status="failed", release_state="failed", release_scope=None,
            failure_code="empty_census",
            failure_message="census produced no denominator URLs",
            expected=expected, reachable=reachable, named=named,
            incomplete=incomplete, coverage=coverage,
        )
    if reachable == 0:
        return GateResult(
            status="failed", release_state="failed", release_scope=None,
            failure_code="nothing_reachable",
            failure_message="no denominator URL could be fetched successfully",
            expected=expected, reachable=reachable, named=named,
            incomplete=incomplete, coverage=coverage,
        )
    if coverage < GATE_COVERAGE_THRESHOLD:
        return GateResult(
            status="failed", release_state="failed", release_scope=None,
            failure_code="census_incomplete",
            failure_message=(
                f"census incomplete: {incomplete} of {expected} map rows "
                f"({denominator} denominator URLs including overflow) "
                "have no disposition"
            ),
            expected=expected, reachable=reachable, named=named,
            incomplete=incomplete, coverage=coverage,
        )
    return GateResult(
        status="ready", release_state="partial", release_scope="inventory",
        failure_code=None, failure_message=None,
        expected=expected, reachable=reachable, named=named,
        incomplete=incomplete, coverage=coverage,
    )


# --- Phase 2: expectation eligibility + coverage + gate (doc 21 sections 8.2, 10, 15) ---

EXPECTATION_GATE_RULE_ID = "expectations-2.1"

#: Oracle sources that may ever carry a verdict (doc 21 section 5.6).
VERDICT_ORACLE_SOURCES = ("documentation", "owner-rule")

_ELIGIBLE_STATUSES = ("unverified", "replay-verified", "owner-confirmed")


def _record_value(record: object, key: str) -> object:
    """Read ``key`` from a mapping or an attribute object (ORM row)."""

    if isinstance(record, Mapping):
        return record.get(key)
    return getattr(record, key, None)


def expectation_verdict_eligible(expectation: object) -> bool:
    """The ONE verdict-eligibility implementation (doc 21 section 8.2, C3).

    TRUE iff ALL of:

    1. ``oracle_source`` is ``documentation``/``owner-rule`` OR the
       record was owner-promoted (``promoted_by`` set);
    2. ``status`` is not ``conflicted``;
    3. the record is not superseded (``superseded_by_id`` unset);
    4. ``assertion`` is present AND NOT (``assertion_origin`` is
       ``model-drafted`` AND the record is unpromoted) -- a model-
       drafted assertion needs its own owner review (section 5.2);
    5. ``status`` is one of unverified / replay-verified /
       owner-confirmed (any future status defaults to ineligible).

    Everything else is navigation-grade: servable, citable as context,
    and structurally incapable of grounding a verdict.
    """

    source = _record_value(expectation, "oracle_source")
    promoted_by = _record_value(expectation, "promoted_by")
    if source not in VERDICT_ORACLE_SOURCES and not promoted_by:
        return False
    status = _record_value(expectation, "status")
    if status == "conflicted":
        return False
    if _record_value(expectation, "superseded_by_id"):
        return False
    assertion = _record_value(expectation, "assertion")
    if not isinstance(assertion, Mapping):
        return False
    origin = _record_value(expectation, "assertion_origin")
    if origin is None and isinstance(assertion, Mapping):
        origin = assertion.get("assertion_origin")
    if origin == "model-drafted" and not promoted_by:
        return False
    return status in _ELIGIBLE_STATUSES


def expectation_coverage(
    expectations: object, journeys: object = ()
) -> dict[str, object]:
    """Journey expectation coverage (doc 21 section 10; ONE implementation).

    ``journeys`` entries are mappings with ``id``, ``intent`` and
    ``subject_ids`` (the element/field ids the journey traverses, from
    its steps' page states). A journey carries an expectation when a
    journey-subject expectation names it or an expectation's subject
    is one of its traversed subjects.
    """

    records = list(expectations)  # type: ignore[arg-type]
    by_source: dict[str, int] = {source: 0 for source in ORACLE_SOURCES}
    eligible = 0
    conflicted_open = 0
    subjects: set[str] = set()
    journey_subjects: set[str] = set()
    for record in records:
        source = _record_value(record, "oracle_source")
        key = source if isinstance(source, str) else "unknown"
        by_source[key] = by_source.get(key, 0) + 1
        if expectation_verdict_eligible(record):
            eligible += 1
        if _record_value(record, "has_open_conflict") is True or (
            _record_value(record, "status") == "conflicted"
        ):
            conflicted_open += 1
        subject_id = _record_value(record, "subject_id")
        if isinstance(subject_id, str) and subject_id:
            subjects.add(subject_id)
            if _record_value(record, "subject_kind") == "journey":
                journey_subjects.add(subject_id)
    total = len(records)
    documentation = by_source.get("documentation", 0)
    journey_rows = list(journeys)  # type: ignore[arg-type]
    with_expectations: list[dict[str, object]] = []
    without: list[dict[str, object]] = []
    for journey in journey_rows:
        journey_id = _record_value(journey, "id")
        traversed = _record_value(journey, "subject_ids") or ()
        traversed_ids = {str(value) for value in traversed}  # type: ignore[union-attr]
        carries = (
            isinstance(journey_id, str) and journey_id in journey_subjects
        ) or bool(subjects & traversed_ids)
        entry = {
            "id": journey_id,
            "intent": _record_value(journey, "intent")
            or _record_value(journey, "name"),
        }
        (with_expectations if carries else without).append(entry)
    return {
        "journeys_total": len(journey_rows),
        "journeys_with_expectations": len(with_expectations),
        "expectations_total": total,
        "expectations_by_source": by_source,
        "verdict_eligible": eligible,
        "conflicted_open": conflicted_open,
        "doc_sourced_share": (documentation / total) if total else 0.0,
        "journeys_without_expectations": without,
    }


@dataclass(frozen=True)
class ExpectationGateResult:
    """The expectation gate's release decision (doc 21 section 15.1).

    ``release_state`` is ``'partial'`` on every path: no code in this
    phase writes ``'trusted'`` (spec C6), and the gate never raises a
    map's harvest scope -- it contributes a separately-reported scope
    line. ``release_scope`` is ``'expectations'`` only when journeys
    are judged by at least one eligible assertion with full accounting
    and no open taxonomy violations; ``'none'`` when grounding failed
    or never ran; ``'partial'`` otherwise.
    """

    release_state: str  # always 'partial'
    release_scope: str  # 'expectations' | 'partial' | 'none'
    journeys_total: int
    journeys_with_expectations: int
    doc_sourced_share: float
    eligible_with_assertion: int
    conflicts_open: int
    taxonomy_violations_open: int | None
    taxonomy_source: str  # 'audit' | 'grounding_sweep'

    def metrics(self) -> dict[str, object]:
        """The gate_metrics expectation_gate block of doc 21 section 15.1."""
        return {
            "expectation_gate": {
                "rule": EXPECTATION_GATE_RULE_ID,
                "journeys_total": self.journeys_total,
                "journeys_with_expectations": self.journeys_with_expectations,
                "doc_sourced_share": round(self.doc_sourced_share, 4),
                "eligible_with_assertion": self.eligible_with_assertion,
                "conflicts_open": self.conflicts_open,
                "taxonomy_violations_open": self.taxonomy_violations_open,
                "taxonomy_source": self.taxonomy_source,
                "release_scope": self.release_scope,
            }
        }


def compute_expectation_gate(
    coverage: Mapping[str, object], counts: Mapping[str, object]
) -> ExpectationGateResult:
    """Pure expectation gate (doc 21 section 15.1, constraints C3/C6).

    ``coverage`` is section 10's object; ``counts`` carries
    ``eligible_with_assertion``, ``conflicts_open``,
    ``taxonomy_violations_open`` (int, or None when no audit has run),
    ``sweep_violations`` (grounding's own sweep count, used until the
    first audit), ``grounding_completed`` and ``accounting_complete``.
    """

    def count(key: str) -> int:
        value = counts.get(key, 0)
        return value if isinstance(value, int) else 0

    journeys_total = coverage.get("journeys_total", 0)
    journeys_total = journeys_total if isinstance(journeys_total, int) else 0
    journeys_with = coverage.get("journeys_with_expectations", 0)
    journeys_with = journeys_with if isinstance(journeys_with, int) else 0
    share = coverage.get("doc_sourced_share", 0.0)
    share = share if isinstance(share, (int, float)) else 0.0
    eligible_with_assertion = count("eligible_with_assertion")
    conflicts_open = count("conflicts_open")
    taxonomy = counts.get("taxonomy_violations_open")
    if isinstance(taxonomy, int):
        taxonomy_open: int | None = taxonomy
        taxonomy_source = "audit"
        taxonomy_clear = taxonomy == 0
    else:
        taxonomy_open = None
        taxonomy_source = "grounding_sweep"
        taxonomy_clear = count("sweep_violations") == 0
    if counts.get("grounding_completed") is not True:
        release_scope = "none"
    elif (
        journeys_total >= 1
        and journeys_with >= 1
        and eligible_with_assertion >= 1
        and counts.get("accounting_complete") is True
        and taxonomy_clear
    ):
        release_scope = "expectations"
    else:
        release_scope = "partial"
    return ExpectationGateResult(
        release_state="partial",
        release_scope=release_scope,
        journeys_total=journeys_total,
        journeys_with_expectations=journeys_with,
        doc_sourced_share=float(share),
        eligible_with_assertion=eligible_with_assertion,
        conflicts_open=conflicts_open,
        taxonomy_violations_open=taxonomy_open,
        taxonomy_source=taxonomy_source,
    )


# --- Phase 3: skill lifecycle authority (doc 22 sections 4.4, 5.1, 5.3) ---

SKILL_LIFECYCLE_STATES = (
    "draft",
    "replay_verified",
    "active",
    "suspect",
    "quarantined",
    "retired",
)

# The transition table (doc 22 section 5.1): (from, to) -> the evidence
# keys that must ALL be present and truthy in the caller's evidence
# mapping. Every pair not listed is refused. Three edges extend the
# section 5.1 table's letter because landed behaviour requires them,
# each forced by a named source: draft -> quarantined is doc 16
# section 5.8's verification dead end (a draft that fails after its
# one heal cycle); draft/replay_verified -> suspect is doc 21 section
# 13's login-seam stale rule, which section 4.4's value migration maps
# onto 'suspect' (fingerprint drift at snapshot time, second
# consecutive seam-replay failure).
SKILL_LIFECYCLE_TRANSITIONS: dict[tuple[str | None, str], tuple[str, ...]] = {
    (None, "draft"): ("creation_record",),
    ("draft", "replay_verified"): ("two_clean_replays",),
    ("replay_verified", "active"): ("currency_pass",),
    ("active", "suspect"): ("demotion",),
    ("suspect", "replay_verified"): ("two_clean_replays",),
    ("suspect", "quarantined"): ("failed_replays", "heal_record"),
    ("active", "quarantined"): ("assertion_divergence",),
    ("draft", "quarantined"): ("failed_replays", "heal_record"),
    ("draft", "suspect"): ("seam_failure",),
    ("replay_verified", "suspect"): ("seam_failure",),
    ("draft", "retired"): ("retirement",),
    ("replay_verified", "retired"): ("retirement",),
    ("active", "retired"): ("retirement",),
    ("suspect", "retired"): ("retirement",),
    ("quarantined", "retired"): ("retirement",),
}


def check_skill_transition(
    from_status: str | None,
    to_status: str,
    evidence: Mapping[str, object] | None,
) -> bool:
    """The ONE lifecycle authority (doc 22 section 5.1, constraint C3).

    Pure: a transition is allowed iff the (from, to) pair is in the
    table AND every evidence key the table names for that edge is
    present and truthy in ``evidence``. Writers in both services pass
    this check at the write site and record the transition in
    ``skill_usage_events`` in the same transaction; a refusal is the
    caller's bug, surfaced as an exception there -- never a skipped
    write.
    """
    required = SKILL_LIFECYCLE_TRANSITIONS.get((from_status, to_status))
    if required is None or not isinstance(evidence, Mapping):
        return False
    return all(evidence.get(key) for key in required)


def skill_currency_check(
    version_fingerprint: object,
    current_start_state_id: str | None,
    current_terminal_state_id: str | None,
) -> bool:
    """The point currency check (doc 22 section 5.3).

    A version is current for a map iff the fingerprint its two clean
    replays proved -- ``{start_state_id, terminal_state_id}`` -- still
    equals the current map's start page default-state id and its
    journey-terminal page default-state id (compared as strings, from
    the map rows; no browser, no model). A fingerprint that cannot be
    compared (not a mapping, a missing key, or a legacy scalar) is a
    currency FAILURE: the caller routes it as ``journey_absent`` or
    toward re-verification, never as a pass.
    """
    if not isinstance(version_fingerprint, Mapping):
        return False
    start = version_fingerprint.get("start_state_id")
    terminal = version_fingerprint.get("terminal_state_id")
    if not isinstance(start, str) or not isinstance(terminal, str):
        return False
    if current_start_state_id is None or current_terminal_state_id is None:
        return False
    return start == current_start_state_id and terminal == current_terminal_state_id


def map_legacy_lifecycle_status(status: str) -> str:
    """The section 4.4 value migration as a pure function: 1b/Phase 2
    spellings map onto the six-state vocabulary; the six states (and
    anything else) pass through unchanged."""
    return {"verified": "replay_verified", "stale": "suspect"}.get(status, status)


# --- Phase 4: freshness vocabulary + fingerprint helpers (doc 23) ---------

#: The five per-URL preflight outcomes (doc 23 section 4.2). A sweep
#: classifies every expected URL into exactly one of these, or names it
#: deferred with a reason -- never a sixth spelling.
FRESHNESS_OUTCOMES = ("present", "changed", "unreachable", "missing", "new")

#: TTL trust window for non-verdict run kinds (doc 23 section 11) [J]:
#: a map younger than this is trusted without a preflight; an older map
#: is disclosed as beyond-TTL in the run snapshot, never silently trusted.
MAP_TTL_TRUST_DAYS = 14

_SCREENSHOT_PHASH_RE = re.compile(r"^([a-z0-9_-]+):([0-9a-f]+)$")


def parse_screenshot_phash(value: object) -> tuple[str, str] | None:
    """Parse a stored ``"<algo>:<hex>"`` perceptual hash (doc 23 section 5.2).

    Returns ``(algo, hex_digits)``, or ``None`` for anything that is not
    exactly that shape -- never raises: an unreadable stored value means
    "no comparable hash", not an error.
    """
    if not isinstance(value, str):
        return None
    match = _SCREENSHOT_PHASH_RE.match(value.strip().lower())
    if match is None:
        return None
    return match.group(1), match.group(2)


def fingerprint_tuple(
    state_id: str | None,
    dom_structure_hash: str | None,
    aria_hash: str | None,
    screenshot_hash: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """The normalised state fingerprint (doc 23 section 4.1).

    ``state_id`` is the verdict-grade identity -- it is computed from
    element/form identity, so it alone decides "changed". The hashes are
    supporting evidence. A row with no ``state_id`` has no state
    identity at all: the tuple is page-grade (all ``None``) and the
    hashes never stand in for identity.
    """
    if not state_id:
        return (None, None, None, None)
    return (state_id, dom_structure_hash, aria_hash, screenshot_hash)


def state_fingerprint(
    record: object,
) -> tuple[str | None, str | None, str | None, str | None]:
    """``fingerprint_tuple`` over a mapping or ORM state row."""

    def _text(key: str) -> str | None:
        value = _record_value(record, key)
        return value if isinstance(value, str) and value else None

    return fingerprint_tuple(
        _text("state_id"),
        _text("dom_structure_hash"),
        _text("aria_hash"),
        _text("screenshot_hash"),
    )
