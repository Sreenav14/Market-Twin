"""Phase 1a shared app-map helpers (doc 14 section 4, tests T-S1 to T-S3).

T-S1 pins the canonicalisation behaviour RECONCILED under decision D6
(incumbent wins): the shared ``canonical_url`` is a port of the
orchestrator's ``workflow/harness_state.py`` function, so three vectors
below intentionally expect the incumbent's output where it differs from
doc 14 section 4.1's printed expectation (the incumbent does not
collapse ``/`` runs and does not drop tracking parameters). Each such
vector is marked with a D6 comment.
"""

import pytest
from markettwin_shared.app_map_common import (
    FRESHNESS_OUTCOMES,
    MAP_TTL_TRUST_DAYS,
    ORACLE_SOURCES,
    canonical_url,
    compute_harvest_gate,
    fingerprint_tuple,
    has_wall_markers,
    is_login_path,
    parse_screenshot_phash,
    route_pattern_for,
    state_fingerprint,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        # D6: incumbent keeps the "//" run; only trailing slashes go.
        ("HTTP://Example.COM:80/a//b/", "http://example.com/a//b"),
        ("https://example.com:443/x#frag", "https://example.com/x"),
        ("https://example.com/", "https://example.com/"),
        # D6: incumbent retains tracking parameters; pairs sort by (key, value).
        (
            "https://example.com/a/?b=2&a=1&utm_source=x",
            "https://example.com/a?a=1&b=2&utm_source=x",
        ),
        # D6: incumbent retains a tracking-only query instead of dropping it.
        ("https://example.com/a?gclid=zzz", "https://example.com/a?gclid=zzz"),
        ("https://example.com:8443/a", "https://example.com:8443/a"),
        ("https://example.com/A/B", "https://example.com/A/B"),
        ("https://example.com/a%20b", "https://example.com/a%20b"),
        ("https://example.com?x=1", "https://example.com/?x=1"),
        ("https://example.com/a/", "https://example.com/a"),
    ],
)
def test_canonical_url_vectors(raw, expected):
    assert canonical_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "HTTP://Example.COM:80/a//b/",
        "https://example.com/a/?b=2&a=1&utm_source=x",
        "https://example.com/a?gclid=zzz",
        "https://example.com:8443/a",
        "https://example.com?x=1",
    ],
)
def test_canonical_url_is_idempotent(raw):
    assert canonical_url(canonical_url(raw)) == canonical_url(raw)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("/products/42", "/products/{id}"),
        ("/blog/my-post-123", "/blog/{slug}"),
        ("/2024/11/report", "/{date}/11/report"),
        (
            "/users/9f8e7d6c-1234-4abc-8def-0123456789ab/settings",
            "/users/{uuid}/settings",
        ),
        ("/about", "/about"),
        # Extra UUID case (T-S2).
        ("/teams/9f8e7d6c-1234-4abc-8def-0123456789ab", "/teams/{uuid}"),
        # Extra slug case (T-S2).
        ("/posts/hello-world-2024", "/posts/{slug}"),
        ("/files/0123456789abcdef0123", "/files/{id}"),
        ("https://example.com/products/42?utm_source=x", "/products/{id}"),
        ("/", "/"),
    ],
)
def test_route_pattern_vectors(value, expected):
    assert route_pattern_for(value) == expected


@pytest.mark.parametrize(
    "url",
    [
        "/login",
        "/account/signin",
        "/sso/callback",
        "https://example.com/auth/callback",
        "/LOGIN",
    ],
)
def test_is_login_path_true(url):
    assert is_login_path(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "/login-help",
        "/blog/login-tips",
        "/products",
        "/",
    ],
)
def test_is_login_path_false(url):
    assert is_login_path(url) is False


@pytest.mark.parametrize(
    "body",
    [
        "Just a moment...",
        "Please verify you are human to continue.",
        "This site uses a CAPTCHA check.",
        "Attention Required! | Cloudflare",
        "Powered by DataDome",
    ],
)
def test_has_wall_markers_hit(body):
    assert has_wall_markers(body) is True


@pytest.mark.parametrize(
    "body",
    [
        "Welcome to our store",
        "Our humans are here to help",
        "",
    ],
)
def test_has_wall_markers_miss(body):
    assert has_wall_markers(body) is False


# --- Phase 1b harvest gate (doc 16 section 5.9; T-GT1 shared half) ------


def _gate_counts(**overrides):
    counts = {
        "reachable": 100,
        "visited": 100,
        "blocked_auth": 0,
        "blocked_wall": 0,
        "failed": 0,
        "unprobed_budget": 0,
        "pending": 0,
        "enriched_groups": 4,
        "template_groups": 4,
        "spend_calls": 4,
        "spend_tokens": 4000,
        "skill_verified": True,
        "skill_reason": None,
    }
    counts.update(overrides)
    return counts


def test_harvest_gate_ready_releases_harvest_scope_with_verified_skill():
    result = compute_harvest_gate(_gate_counts())
    assert result.harvest_status == "ready"
    assert result.failure_code is None
    assert result.release_state == "partial"
    assert result.release_scope == "harvest"
    assert result.skill_gate is None
    assert result.metrics()["harvest_rule"] == "harvest-1b.1"
    assert result.metrics()["harvest_coverage"] == 1.0


def test_harvest_gate_empty_is_failed_harvest_empty():
    result = compute_harvest_gate(_gate_counts(visited=0, reachable=12))
    assert result.harvest_status == "failed"
    assert result.failure_code == "harvest_empty"
    assert result.release_scope == "inventory"


def test_harvest_gate_pending_is_failed_incomplete_accounting():
    result = compute_harvest_gate(_gate_counts(visited=90, pending=3))
    assert result.harvest_status == "failed"
    assert result.failure_code == "harvest_incomplete_accounting"


def test_harvest_gate_below_threshold_is_partial():
    result = compute_harvest_gate(_gate_counts(visited=97, blocked_auth=3))
    assert result.harvest_status == "partial"
    assert result.coverage == pytest.approx(0.97)
    assert result.metrics()["blocked"] == 3


def test_harvest_gate_at_threshold_is_ready():
    result = compute_harvest_gate(_gate_counts(visited=98, blocked_wall=2))
    assert result.harvest_status == "ready"
    assert result.metrics()["harvest_coverage"] == 0.98


def test_harvest_gate_without_verified_skill_stays_inventory_scoped():
    result = compute_harvest_gate(
        _gate_counts(skill_verified=False, skill_reason="skill_quarantined")
    )
    assert result.harvest_status == "ready"
    assert result.release_state == "partial"
    assert result.release_scope == "inventory"
    assert result.metrics()["skill_gate"] == "failed"
    assert result.metrics()["skill_gate_reason"] == "skill_quarantined"


def test_oracle_sources_taxonomy_is_the_four_value_set():
    assert ORACLE_SOURCES == (
        "documentation",
        "owner-rule",
        "observation",
        "model-draft",
    )


# --- Phase 3 lifecycle authority (doc 22 sections 4.4, 5.1, 5.3) ---

from markettwin_shared.app_map_common import (  # noqa: E402
    SKILL_LIFECYCLE_STATES,
    SKILL_LIFECYCLE_TRANSITIONS,
    check_skill_transition,
    map_legacy_lifecycle_status,
    skill_currency_check,
)

_FULL_EVIDENCE = {
    "creation_record": {"kind": "compile"},
    "two_clean_replays": ["replay-1", "replay-2"],
    "currency_pass": True,
    "demotion": {"terminal_state_id": "changed"},
    "failed_replays": ["replay-3"],
    "heal_record": {"applicable": False},
    "assertion_divergence": {"replay_id": "replay-9"},
    "seam_failure": {"consecutive_failures": 2},
    "retirement": {"retired_reason": "owner"},
}


def test_transition_table_covers_exactly_the_six_states():
    assert SKILL_LIFECYCLE_STATES == (
        "draft",
        "replay_verified",
        "active",
        "suspect",
        "quarantined",
        "retired",
    )
    for (source, target) in SKILL_LIFECYCLE_TRANSITIONS:
        assert source is None or source in SKILL_LIFECYCLE_STATES
        assert target in SKILL_LIFECYCLE_STATES


def test_transition_grid_matches_the_table_with_full_evidence():
    for source in (None, *SKILL_LIFECYCLE_STATES):
        for target in SKILL_LIFECYCLE_STATES:
            expected = (source, target) in SKILL_LIFECYCLE_TRANSITIONS
            assert (
                check_skill_transition(source, target, _FULL_EVIDENCE)
                is expected
            ), (source, target)


def test_transition_refused_without_the_named_evidence():
    for (source, target), keys in SKILL_LIFECYCLE_TRANSITIONS.items():
        assert check_skill_transition(source, target, {}) is False
        for key in keys:
            partial = {k: v for k, v in _FULL_EVIDENCE.items() if k != key}
            assert check_skill_transition(source, target, partial) is False
    assert check_skill_transition("draft", "replay_verified", None) is False


def test_transition_retired_is_terminal():
    for target in SKILL_LIFECYCLE_STATES:
        assert check_skill_transition("retired", target, _FULL_EVIDENCE) is False


def test_currency_check_compares_the_fingerprint_pair():
    fingerprint = {"start_state_id": "s-1", "terminal_state_id": "t-1"}
    assert skill_currency_check(fingerprint, "s-1", "t-1") is True
    assert skill_currency_check(fingerprint, "s-2", "t-1") is False
    assert skill_currency_check(fingerprint, "s-1", "t-2") is False
    assert skill_currency_check(fingerprint, None, "t-1") is False


def test_currency_check_uncomparable_fingerprint_fails():
    # Legacy scalar fingerprints and partial dicts cannot be compared:
    # currency failure, never a pass (doc 22 section 5.3).
    assert skill_currency_check("t-1", "s-1", "t-1") is False
    assert skill_currency_check(None, "s-1", "t-1") is False
    assert skill_currency_check({"terminal_state_id": "t-1"}, "s-1", "t-1") is False


def test_legacy_lifecycle_value_mapping():
    # T-LB4's pure-function half (doc 22 section 4.4).
    assert map_legacy_lifecycle_status("verified") == "replay_verified"
    assert map_legacy_lifecycle_status("stale") == "suspect"
    for state in SKILL_LIFECYCLE_STATES:
        assert map_legacy_lifecycle_status(state) == state


# --- Phase 4 freshness vocabulary + fingerprints (doc 23; T-FM1 to T-FM4) ---


def test_fm1_freshness_vocabulary_is_the_five_outcomes():
    assert FRESHNESS_OUTCOMES == ("present", "changed", "unreachable", "missing", "new")
    assert MAP_TTL_TRUST_DAYS == 14


def test_fm2_screenshot_phash_parses_algo_hex_pairs():
    assert parse_screenshot_phash("ahash:0123456789abcdef") == (
        "ahash",
        "0123456789abcdef",
    )
    # Case and surrounding whitespace are normalised, never fatal.
    assert parse_screenshot_phash(" AHASH:AB12 ") == ("ahash", "ab12")


@pytest.mark.parametrize(
    "value",
    [None, "", "nocolon", "ahash:", ":ab12", "ahash:xyz!", "ahash:ab 12", 42, b"ahash:ab12"],
)
def test_fm2_screenshot_phash_rejects_malformed_values(value):
    assert parse_screenshot_phash(value) is None


def test_fm3_fingerprint_tuple_keys_on_state_id():
    assert fingerprint_tuple("state-1", "dom", "aria", "shot") == (
        "state-1",
        "dom",
        "aria",
        "shot",
    )
    # Supporting hashes may be absent; identity still stands.
    assert fingerprint_tuple("state-1", None, None, None) == (
        "state-1",
        None,
        None,
        None,
    )


@pytest.mark.parametrize("state_id", [None, ""])
def test_fm3_fingerprint_tuple_without_state_id_is_page_grade(state_id):
    # Hashes alone never stand in for identity (doc 23 section 4.1).
    assert fingerprint_tuple(state_id, "dom", "aria", "shot") == (None, None, None, None)


def test_fm4_state_fingerprint_reads_mappings_and_objects():
    row = {
        "state_id": "state-9",
        "dom_structure_hash": "dom9",
        "aria_hash": "aria9",
        "screenshot_hash": "shot9",
    }
    assert state_fingerprint(row) == ("state-9", "dom9", "aria9", "shot9")

    class Row:
        state_id = "state-9"
        dom_structure_hash = "dom9"
        aria_hash = "aria9"
        screenshot_hash = "shot9"

    assert state_fingerprint(Row()) == ("state-9", "dom9", "aria9", "shot9")
    # A row with no state identity reads page-grade, never an error.
    assert state_fingerprint({}) == (None, None, None, None)
    assert state_fingerprint({"state_id": 17, "dom_structure_hash": "d"}) == (
        None,
        None,
        None,
        None,
    )
